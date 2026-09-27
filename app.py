"""Prius Gen 3 live dashboard for Windows - top-down car view with coloured parts (drawing is in scene.py).

Run:  python app.py            (real car on COM6)
      python app.py --demo     (fake data, no car needed)
      python app.py --port COM5
"""
import argparse
import time
import tkinter as tk

import config as cfg
from calc import TRACKER
from closeups import BatteryView, EngineView, TripView
from merged import EverythingView
from scene import Scene, poll_plan
from sensors import Poller
from views import BG, BODY, DIM, TEXT, ElectricalView, PressureView, SpinView, TemperatureView


def all_views():
    return [TemperatureView(), ElectricalView(), SpinView(), PressureView(), EverythingView(), EngineView(),
            BatteryView(), TripView()]


class App:
    def __init__(self, root, poller):
        self.root = root
        self.poller = poller
        self.views = all_views()
        self.view = self.views[0]
        self.last_frame = time.monotonic()

        self.ui = root.winfo_fpixels("1i") / 96  # Windows display scaling (1.0 = 100%)
        root.title("Prius Live")
        root.configure(bg=BG)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        (w, h), (mw, mh) = cfg.WINDOW_SIZE, cfg.WINDOW_MARGIN
        root.geometry(f"{min(int(w * self.ui), sw - mw)}x{min(int(h * self.ui), sh - int(mh * self.ui))}+20+20")
        root.minsize(*cfg.WINDOW_MIN_SIZE)

        side = tk.Frame(root, bg=BG)
        side.pack(side="right", fill="y", padx=(0, 12), pady=12)
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True, padx=12, pady=12)
        self.scene = Scene(self.canvas, ui=self.ui)
        self.scene.set_view(self.view)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Leave>", self.on_leave)

        tk.Label(side, text="View", bg=BG, fg=DIM, font=("Segoe UI", 10)).pack(anchor="w")
        self.view_var = tk.StringVar(value=self.view.name)
        for v in self.views:
            tk.Radiobutton(side, text=v.name, value=v.name, variable=self.view_var, command=self.change_view,
                           bg=BG, fg=TEXT, selectcolor=BODY, activebackground=BG, activeforeground=TEXT,
                           font=("Segoe UI", 11), indicatoron=False, pady=4).pack(fill="x", pady=2)
        self.status = tk.Label(side, text="", bg=BG, fg=DIM, font=("Segoe UI", 9), justify="left",
                               wraplength=int(cfg.PANEL_TEXT_WIDTH * self.ui))
        self.status.pack(side="bottom", anchor="w")
        self.panel = tk.Frame(side, bg=BG)
        self.panel.pack(fill="both", expand=True)
        self.view.build_panel(self.panel, self)
        poll_plan(self.view, self.views, self.poller)

        self.tick()
        self.animate()

    def change_view(self):
        self.view = next(v for v in self.views if v.name == self.view_var.get())
        poll_plan(self.view, self.views, self.poller)
        for child in self.panel.winfo_children():
            child.destroy()
        self.view.build_panel(self.panel, self)
        self.scene.set_view(self.view)
        self.refresh()

    # ---------- hover ----------
    def on_motion(self, event):
        hit = self.scene.hit(event.x, event.y)
        new = (hit, event.x, event.y) if hit else None
        if new != self.scene.hover:
            self.scene.hover = new
            self.redraw()

    def on_leave(self, _event):
        if self.scene.hover:
            self.scene.hover = None
            self.redraw()

    # ---------- loops ----------
    def redraw(self):
        values, _, _ = self.poller.snapshot()
        self.scene.redraw(values, time.time())

    def animate(self):
        t = time.monotonic()
        dt, self.last_frame = t - self.last_frame, t
        self.scene.step(dt)
        self.root.after(cfg.FRAME_MS, self.animate)

    def refresh(self):
        values, status, cycle_ms = self.poller.snapshot()
        TRACKER.update(values, time.time())   # running totals (Trip view) and live battery estimates
        self.view.update_panel(values, time.time())
        extra = f"\nfull refresh: {cycle_ms} ms" if cycle_ms else ""
        self.status.config(text=f"{status}{extra}")
        self.redraw()

    def tick(self):
        """Redraw often so new readings show up quickly; the warning border still blinks at ~1 Hz."""
        self.ticks = getattr(self, "ticks", 0) + 1
        self.scene.blink = (self.ticks * cfg.REFRESH_MS // cfg.BLINK_MS) % 2 == 1
        self.refresh()
        self.root.after(cfg.REFRESH_MS, self.tick)


def main():
    ap = argparse.ArgumentParser(description="Prius Gen 3 live dashboard")
    ap.add_argument("--port", default=cfg.PORT)
    ap.add_argument("--demo", action="store_true", help="fake data, no car needed")
    ap.add_argument("--view", default="Temperature", help="start in this view (Temperature, Electrical, Spinning, "
                                                          "Pressure, Everything, Engine, Battery or Trip)")
    args = ap.parse_args()

    try:  # sharp text on scaled Windows displays instead of a blurry stretched window
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    poller = Poller(TemperatureView().sensors(), port=args.port, demo=args.demo)
    poller.start()
    app = App(root, poller)
    start = next((v.name for v in app.views if v.name.lower().startswith(args.view.lower())), None)
    if start and start != app.view.name:
        app.view_var.set(start)
        app.change_view()
    try:
        root.mainloop()
    finally:
        poller.stop_flag.set()


if __name__ == "__main__":
    main()
