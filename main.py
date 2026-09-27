"""Prius Live for Android (Kivy). Same views, readings and drawing as the Windows app; only the window, the side
panel widgets and the Bluetooth link are different.

Also runs on a PC for testing:  python main.py  (demo data; Bluetooth only works on the phone)
"""
import json
import os
import sys
import time

from mobile import tkshim

sys.modules["tkinter"] = tkshim     # the views build their side panels with tkinter calls - give them Kivy widgets

from kivy.app import App                                   # noqa: E402
from kivy.clock import Clock                               # noqa: E402
from kivy.core.window import Window                        # noqa: E402
from kivy.graphics import Color, Rectangle                 # noqa: E402
from kivy.metrics import Metrics, dp, sp                   # noqa: E402
from kivy.uix.boxlayout import BoxLayout                   # noqa: E402
from kivy.uix.button import Button                         # noqa: E402
from kivy.uix.floatlayout import FloatLayout               # noqa: E402
from kivy.uix.label import Label                           # noqa: E402
from kivy.uix.popup import Popup                           # noqa: E402
from kivy.uix.scrollview import ScrollView                 # noqa: E402
from kivy.uix.spinner import Spinner                       # noqa: E402

import config as cfg                                       # noqa: E402
from calc import TRACKER                                   # noqa: E402
from closeups import BatteryView, EngineView, TripView     # noqa: E402
from merged import EverythingView                          # noqa: E402
from mobile import bt                                      # noqa: E402
from mobile.canvas import FONT, KivyCanvas, rgba                 # noqa: E402
from scene import Scene, poll_plan                         # noqa: E402
from sensors import Poller                                 # noqa: E402
from views import BG, DIM, ElectricalView, PressureView, SpinView, TemperatureView  # noqa: E402



def _bg(widget, colour):
    with widget.canvas.before:
        Color(*rgba(colour))
        rect = Rectangle(pos=widget.pos, size=widget.size)
    widget.bind(pos=lambda w, p: setattr(rect, "pos", p), size=lambda w, s: setattr(rect, "size", s))


class PriusApp(App):
    title = "Prius Live"

    def build(self):
        self.ui = max(1.0, Metrics.density * 0.8)   # line widths / spacing (1.0 = a 96 dpi PC screen)
        self.views = [TemperatureView(), ElectricalView(), SpinView(), PressureView(), EverythingView(), EngineView(),
                      BatteryView(), TripView()]
        self.settings = self._load()
        self.view = next((v for v in self.views if v.name == self.settings.get("view")), self.views[0])
        self.poller = None
        self.ticks = 0
        self.last_frame = time.monotonic()

        root = BoxLayout(orientation="vertical")
        _bg(root, BG)
        bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6), padding=(dp(6), dp(4)))
        self.picker = Spinner(text=self.view.name, values=[v.name for v in self.views], font_size=sp(16))
        self.picker.bind(text=lambda _, name: self.change_view(name))
        self.info_btn = Button(text="Info", size_hint_x=None, width=dp(72), font_size=sp(15))
        self.info_btn.bind(on_release=lambda *_: self.toggle_panel())
        adapter_btn = Button(text="Adapter", size_hint_x=None, width=dp(92), font_size=sp(15))
        adapter_btn.bind(on_release=lambda *_: self.choose_adapter())
        for w in (self.picker, self.info_btn, adapter_btn):
            bar.add_widget(w)
        root.add_widget(bar)
        self.status = Label(text="", size_hint_y=None, height=dp(22), font_size=sp(12), color=rgba(DIM),
                            halign="left", valign="middle", font_name=FONT, shorten=True)
        self.status.bind(size=lambda w, s: setattr(w, "text_size", s))
        root.add_widget(self.status)

        body = FloatLayout()
        self.canvas_w = KivyCanvas(on_tap=self.on_tap, size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        body.add_widget(self.canvas_w)
        self.panel_scroll = ScrollView(size_hint=(1, 1), pos_hint={"x": 0, "y": 0}, do_scroll_x=False,
                                       bar_width=dp(4))
        _bg(self.panel_scroll, BG)
        self.panel_open = False
        root.add_widget(body)
        self.body = body

        self.scene = Scene(self.canvas_w, ui=self.ui, font=FONT, margin=10, tooltip_width=cfg.TOOLTIP_WIDTH)
        self.scene.set_view(self.view)
        self._build_panel()
        Window.bind(on_keyboard=self.on_key)
        Clock.schedule_interval(self.tick, cfg.REFRESH_MS / 1000)
        Clock.schedule_interval(self.animate, cfg.FRAME_MS / 1000)
        Clock.schedule_once(lambda *_: self.startup(), 0.3)
        return root

    # ---------- settings ----------
    def _path(self):
        return os.path.join(self.user_data_dir, "settings.json")

    def _load(self):
        try:
            with open(self._path(), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save(self):
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump(self.settings, f)
        except OSError:
            pass

    # ---------- connecting ----------
    def startup(self):
        keep_screen_on()
        if not bt.available():                 # on a PC: demo data
            self.start_poller(demo=True)
        elif self.settings.get("address"):
            bt.request_permissions(lambda: Clock.schedule_once(lambda *_: self.start_poller(), 0))
        else:
            bt.request_permissions(lambda: Clock.schedule_once(lambda *_: self.choose_adapter(), 0))

    def start_poller(self, demo=False):
        if self.poller:
            self.poller.stop_flag.set()
        address, name = self.settings.get("address"), self.settings.get("name", "adapter")
        demo = demo or not address
        self.poller = Poller(self.view.sensors(), port=name, demo=demo,
                             link=None if demo else (lambda: bt.BtSerial(address)))
        poll_plan(self.view, self.views, self.poller)
        self.poller.start()

    def choose_adapter(self):
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        popup = Popup(title="Choose the OBD adapter", content=box, size_hint=(0.92, 0.8))
        try:
            devices = bt.paired_devices() if bt.available() else []
            note = ("Paired Bluetooth devices (pair the adapter in Android's Bluetooth settings first, PIN 1234 or "
                    "0000):" if devices else "No paired Bluetooth devices found. Pair the adapter in Android's "
                    "Bluetooth settings first (PIN 1234 or 0000), then come back.")
        except Exception as e:
            devices, note = [], f"Bluetooth not available: {e}"
        msg = Label(text=note, font_size=sp(14), size_hint_y=None, halign="left", valign="top", font_name=FONT)
        msg.bind(width=lambda w, v: setattr(w, "text_size", (v, None)),
                 texture_size=lambda w, s: setattr(w, "height", s[1]))
        box.add_widget(msg)

        def pick(address, name):
            popup.dismiss()
            self.settings.update(address=address, name=name)
            self._save()
            self.start_poller(demo=address is None)
        for name, address in devices:
            b = Button(text=f"{name}\n{address}", size_hint_y=None, height=dp(58), font_size=sp(15), halign="center")
            b.bind(on_release=lambda _, a=address, n=name: pick(a, n))
            box.add_widget(b)
        demo = Button(text="Demo mode (made-up data, no car)", size_hint_y=None, height=dp(52), font_size=sp(15))
        demo.bind(on_release=lambda *_: pick(None, "demo"))
        box.add_widget(demo)
        box.add_widget(BoxLayout())
        popup.open()

    # ---------- views + panel ----------
    def change_view(self, name):
        view = next(v for v in self.views if v.name == name)
        if view is self.view:
            return
        self.view = view
        self.settings["view"] = name
        self._save()
        if self.poller:
            poll_plan(self.view, self.views, self.poller)
        self.scene.set_view(view)
        self._build_panel()
        self.refresh()

    def _build_panel(self):
        tkshim.PANEL_WIDTH[0] = Window.width - dp(28)
        self.panel_root = tkshim.Frame(None)
        self.panel_root.w.padding = (dp(12), dp(8))
        self.view.build_panel(self.panel_root, self)
        self.panel_scroll.clear_widgets()
        self.panel_scroll.add_widget(self.panel_root.w)

    def toggle_panel(self):
        self.panel_open = not self.panel_open
        if self.panel_open:
            self.body.add_widget(self.panel_scroll)
            self.info_btn.text = "Car"
        else:
            self.body.remove_widget(self.panel_scroll)
            self.info_btn.text = "Info"

    def on_key(self, _window, key, *_):
        if key == 27:   # Android back button: close the panel / info card first
            if self.panel_open:
                self.toggle_panel()
                return True
            if self.scene.hover:
                self.scene.hover = None
                self.redraw()
                return True
        return False

    def on_tap(self, x, y):
        hit = self.scene.hit(x, y)
        self.scene.hover = None if (not hit or (self.scene.hover and self.scene.hover[0] == hit)) else (hit, x, y)
        self.redraw()

    # ---------- loops ----------
    def redraw(self):
        if self.poller:
            values, _, _ = self.poller.snapshot()
            self.scene.redraw(values, time.time())

    def refresh(self):
        if not self.poller:
            return
        values, status, cycle_ms = self.poller.snapshot()
        TRACKER.update(values, time.time())
        self.view.update_panel(values, time.time())
        self.status.text = status.replace("\n", "  ") + (f"   ·   full refresh {cycle_ms} ms" if cycle_ms else "")
        self.redraw()

    def tick(self, _dt):
        self.ticks += 1
        self.scene.blink = (self.ticks * cfg.REFRESH_MS // cfg.BLINK_MS) % 2 == 1
        self.refresh()

    def animate(self, _dt):
        t = time.monotonic()
        dt, self.last_frame = t - self.last_frame, t
        self.scene.step(dt)

    def on_pause(self):
        return True     # keep running (and connected) when the screen turns off or you switch apps

    def on_stop(self):
        if self.poller:
            self.poller.stop_flag.set()


def keep_screen_on():
    """A dashboard shouldn't let the phone go to sleep."""
    try:
        from android.runnable import run_on_ui_thread
        from jnius import autoclass
    except ImportError:
        return

    @run_on_ui_thread
    def _set():
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        flag = autoclass("android.view.WindowManager$LayoutParams").FLAG_KEEP_SCREEN_ON
        activity.getWindow().addFlags(flag)
    _set()


if __name__ == "__main__":
    PriusApp().run()
