"""Just enough of tkinter, built from Kivy widgets, for the views' side panels (views.py, closeups.py, merged.py)
to build themselves on Android unchanged. main.py installs it as the `tkinter` module before importing the views.

Covers: Frame, Label, Radiobutton, Button, Canvas (legend colour bars) and StringVar, with pack(side / anchor /
fill / padx / pady), config() and destroy().
"""
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button as KButton
from kivy.uix.label import Label as KLabel
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget as KWidget

from mobile.canvas import FONT, KivyCanvas, rgba

PANEL_WIDTH = [dp(340)]    # set by main.py: how wide the panel is (labels without a wrap width wrap here)


def _font_size(font):
    size = font[1] if font and len(font) > 1 else 10
    return -size if size < 0 else sp(size * 1.25)


class StringVar:
    def __init__(self, value=None, **_):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Widget:
    def __init__(self, parent, kivy_widget):
        self.parent = parent
        self.w = kivy_widget
        self.children = []
        self.side = None

    def pack(self, side=None, anchor=None, fill=None, padx=0, pady=0, expand=None, **_):
        self.side = side
        pady = pady if isinstance(pady, tuple) else (pady, pady)
        padx = padx if isinstance(padx, tuple) else (padx, padx)
        self.pad = (dp(padx[0]), dp(pady[0]), dp(padx[1]), dp(pady[1]))
        self.fill = fill
        if self.parent is not None:
            self.parent._place(self)

    def winfo_children(self):
        return list(self.children)

    def destroy(self):
        if self.parent is not None and self in self.parent.children:
            self.parent.children.remove(self)
            self.parent._rebuild()

    def config(self, **kw):
        pass

    configure = config

    def bind(self, *_, **__):
        pass


class Frame(_Widget):
    """Stacks children top to bottom, or left to right once a child is packed with side=left/right
    (right-packed children go to the far right, like tkinter)."""

    def __init__(self, parent=None, **_):
        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2))
        box.bind(minimum_height=box.setter("height"))
        super().__init__(parent, box)

    def _place(self, child):
        self.children.append(child)
        self._rebuild()

    def _rebuild(self):
        box = self.w
        box.clear_widgets()
        horizontal = any(c.side in ("left", "right") for c in self.children)
        box.orientation = "horizontal" if horizontal else "vertical"
        order = self.children
        if horizontal:
            lefts = [c for c in self.children if c.side != "right"]
            rights = [c for c in self.children if c.side == "right"]
            order = lefts + [None] + rights[::-1]
        for c in order:
            if c is None:
                box.add_widget(KWidget(size_hint_y=None, height=1))   # stretch between left and right items
                continue
            holder = c.w
            if c.pad != (0, 0, 0, 0):
                holder = BoxLayout(size_hint=(None, None) if horizontal else (1, None), padding=c.pad)
                if c.w.parent:
                    c.w.parent.remove_widget(c.w)
                holder.add_widget(c.w)
                holder.bind(minimum_height=holder.setter("height"))
                if horizontal:
                    holder.bind(minimum_width=holder.setter("width"))
            elif c.w.parent:
                c.w.parent.remove_widget(c.w)
            if horizontal:
                holder.size_hint_x = None
            box.add_widget(holder)
        if horizontal:
            box.height = max([c.w.height + c.pad[1] + c.pad[3] for c in self.children] + [dp(20)])
            box.size_hint_y = None


class Label(_Widget):
    def __init__(self, parent=None, text="", fg="#ffffff", font=None, wraplength=None, width=None, anchor=None,
                 **_):
        size = _font_size(font)
        lbl = KLabel(text=text, color=rgba(fg), font_size=size, font_name=FONT, bold=bool(font and "bold" in font[2:]),
                     size_hint=(None, None), halign="right" if anchor == "e" else "left", valign="middle")
        self.chars = width
        self.wrap = min(wraplength, PANEL_WIDTH[0]) if wraplength else None
        super().__init__(parent, lbl)
        lbl.bind(texture_size=self._fit)
        self._set_wrap()

    def _set_wrap(self):
        """Fixed width (value columns), a given wrap width, or natural width - wrapping only if it's too wide."""
        lbl = self.w
        if self.chars:
            lbl.text_size = (lbl.font_size * 0.62 * self.chars, None)
        elif self.wrap:
            lbl.text_size = (self.wrap, None)
        else:
            lbl.text_size = (None, None)
            lbl.texture_update()
            if lbl.texture_size[0] > PANEL_WIDTH[0]:
                lbl.text_size = (PANEL_WIDTH[0], None)
        lbl.texture_update()

    def _fit(self, lbl, size):
        lbl.size = size

    def config(self, text=None, fg=None, wraplength=None, **_):
        if text is not None:
            self.w.text = text
            if not self.chars and not self.wrap:
                self._set_wrap()
        if fg is not None:
            self.w.color = rgba(fg)
        if wraplength is not None:
            self.wrap = min(wraplength, PANEL_WIDTH[0])
            self._set_wrap()

    configure = config


class Radiobutton(_Widget):
    def __init__(self, parent=None, text="", value=None, variable=None, command=None, font=None, **_):
        btn = ToggleButton(text=text, group=f"var{id(variable)}", allow_no_selection=False,
                           font_size=_font_size(font), size_hint=(None, None), height=dp(38),
                           state="down" if variable is not None and variable.get() == value else "normal")
        btn.bind(texture_size=lambda b, s: setattr(b, "width", s[0] + dp(20)))

        def press(*_):
            if variable is not None:
                variable.set(value)
            if command:
                command()
        btn.bind(on_release=press)
        super().__init__(parent, btn)


class Button(_Widget):
    def __init__(self, parent=None, text="", command=None, font=None, **_):
        btn = KButton(text=text, font_size=_font_size(font), size_hint=(None, None), height=dp(40))
        btn.bind(texture_size=lambda b, s: setattr(b, "width", s[0] + dp(24)))
        if command:
            btn.bind(on_release=lambda *_: command())
        super().__init__(parent, btn)


class Canvas(_Widget):
    """The small legend colour bars in the side panels."""

    def __init__(self, parent=None, width=100, height=20, **_):
        super().__init__(parent, KivyCanvas(size_hint=(None, None), size=(width, height)))

    def __getattr__(self, name):   # create_line, create_text, ... go straight to the Kivy canvas
        return getattr(self.w, name)
