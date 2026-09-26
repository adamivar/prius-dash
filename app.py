"""Prius Gen 3 live dashboard - top-down car view with coloured component boxes.

Run:  python app.py            (real car on COM6)
      python app.py --demo     (fake data, no car needed)
      python app.py --port COM5
"""
import argparse
import math
import time
import tkinter as tk

from calc import TRACKER
from closeups import BatteryView, EngineView, TripView
from sensors import SENSORS, TRIP_KEYS, Poller
from views import BG, BODY, DIM, IDEAL, TEXT, TIP_FG, WARN, ElectricalView, PressureView, SpinView, TemperatureView

BODY_EDGE = "#4a505c"
TIP_BG = "#f4f4f0"
FLOW = "#ffe14d"
CAR_W, CAR_H = 100, 250   # car drawn in a 100 x 250 unit box, front at the top, driver on the left
FRAME_MS = 40             # wire animation frame time
L_EDGE = 16              # left edge of the parts column (x 4-16 is kept for wires)
REFRESH_MS = 150          # how often the screen picks up new readings (was 500)
ON_OFF_AMPS = 3.0        # arrow speed used for things that only report on/off (not a real current)


def mix(hex_a, hex_b, t):
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def rotor_speed(rpm):
    """On-screen turns per second for a part turning at `rpm`: slowed down a lot (a real engine at 1,500 rpm is
    25 turns a second), square-root scaled so slow and fast parts still look different, capped so it can't strobe."""
    return math.copysign(min(2.5, 0.045 * math.sqrt(abs(rpm))), rpm) if abs(rpm) >= 1 else 0.0


def text_on(hex_colour):
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return "#111111" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else TEXT


class App:
    def __init__(self, root, poller):
        self.root = root
        self.poller = poller
        self.views = [TemperatureView(), ElectricalView(), SpinView(), PressureView(), EngineView(), BatteryView(),
                      TripView()]
        self.rotors = []           # [(key, centre x, centre y, radius, turns per second, colour)]
        self.rotor_angle = {}      # key -> current angle in degrees
        self.view = self.views[0]
        self.blink = False
        self.hover = None          # (component key, mouse x, mouse y)
        self.wire_px = []          # [(pixel points, segment lengths, total length, signed amps, width)]
        self.wire_phase = {}       # wire index -> distance travelled by the arrows (px)
        self.last_frame = time.monotonic()

        self.ui = root.winfo_fpixels("1i") / 96  # Windows display scaling (1.0 = 100%)
        root.title("Prius Live")
        root.configure(bg=BG)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{min(int(1150 * self.ui), sw - 60)}x{min(int(1000 * self.ui), sh - int(110 * self.ui))}+20+20")
        root.minsize(760, 680)

        side = tk.Frame(root, bg=BG)
        side.pack(side="right", fill="y", padx=(0, 12), pady=12)
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True, padx=12, pady=12)
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
                               wraplength=int(310 * self.ui))
        self.status.pack(side="bottom", anchor="w")
        self.panel = tk.Frame(side, bg=BG)
        self.panel.pack(fill="both", expand=True)
        self.view.build_panel(self.panel, self)
        self.poll_for_view()

        self.tick()
        self.animate()

    def poll_for_view(self):
        """Current view polled fast; every other view's sensors refreshed in the background."""
        active = self.view.sensors()
        keys = {s.key for s in active}
        trip = [SENSORS[k] for k in TRIP_KEYS if k not in keys]
        keys |= {s.key for s in trip}
        background = {s.key: s for v in self.views if v is not self.view for s in v.sensors() if s.key not in keys}
        self.poller.set_sensors(active, list(background.values()), trip)

    def change_view(self):
        self.view = next(v for v in self.views if v.name == self.view_var.get())
        self.poll_for_view()
        for child in self.panel.winfo_children():
            child.destroy()
        self.view.build_panel(self.panel, self)
        self.wire_phase.clear()
        self.hover = None
        self.refresh()

    # ---------- hover ----------
    def on_motion(self, event):
        s, ox, oy = self._geom()
        ux, uy = (event.x - ox) / s, (event.y - oy) / s
        hit = next((k for k, x, y, w_, h in self.view.components if x <= ux <= x + w_ and y <= uy <= y + h), None)
        new = (hit, event.x, event.y) if hit else None
        if new != self.hover:
            self.hover = new
            self.redraw()

    def on_leave(self, _event):
        if self.hover:
            self.hover = None
            self.redraw()

    def draw_tooltip(self, values, now):
        key, mx, my = self.hover
        title, lines = self.view.tooltip(key, values, now)
        c = self.canvas
        width = int(380 * self.ui)
        items = [c.create_text(0, 0, text=title, anchor="nw", width=width, fill=TIP_FG,
                               font=("Segoe UI", 12, "bold"), tags="tip")]
        for text, colour, size, bold in lines:
            y = c.bbox(items[-1])[3] + 4
            items.append(c.create_text(0, y, text=text, anchor="nw", width=width, fill=colour, tags="tip",
                                       font=("Segoe UI", size, "bold") if bold else ("Segoe UI", size)))
        x0, y0, x1, y1 = c.bbox(*items)
        pad, gap = int(10 * self.ui), int(18 * self.ui)
        tw, th = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
        cw, ch = c.winfo_width(), c.winfo_height()
        tx = mx + gap if mx + gap + tw < cw else mx - gap - tw  # flip to the left near the edge
        tx, ty = max(4, tx), min(max(4, my + gap), ch - th - 4)
        for it in items:
            c.move(it, tx + pad, ty + pad)
        bg = c.create_rectangle(tx, ty, tx + tw, ty + th, fill=TIP_BG, outline="#9aa0aa", tags="tip")
        c.tag_lower(bg, items[0])

    # ---------- geometry ----------
    def _geom(self):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        s = min(cw / (CAR_W + 16), ch / (CAR_H + 16))
        ox, oy = (cw - CAR_W * s) / 2, (ch - CAR_H * s) / 2
        return s, ox, oy

    def _pt(self, x, y):
        s, ox, oy = self._geom()
        return ox + x * s, oy + y * s

    def _rect(self, x, y, w, h):
        return (*self._pt(x, y), *self._pt(x + w, y + h))

    def _rounded(self, x, y, w, h, r, **kw):
        x0, y0, x1, y1 = self._rect(x, y, w, h)
        r *= self._geom()[0]
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
               x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    # ---------- drawing ----------
    def redraw(self):
        c = self.canvas
        c.delete("all")
        s, _, _ = self._geom()
        fs = -max(10, int(s * 3.2))          # font size in pixels (negative = px), follows window size
        fs_small = -max(9, int(s * 2.8))
        fs_tiny = -max(8, int(s * 2.2))      # narrow boxes (battery blocks)
        now = time.time()
        values, _, _ = self.poller.snapshot()

        closeup = getattr(self.view, "scene", "car") == "closeup"
        if closeup:   # close-up views: a plain panel instead of the car
            self._rounded(1, 1, 98, 247, 6, fill=BODY, outline=BODY_EDGE, width=2)
        else:
            for wx, wy in ((-1, 36), (94, 36), (-1, 196), (94, 196)):  # wheels
                c.create_rectangle(*self._rect(wx, wy, 7, 24), fill="#0b0c0e", outline="#2c2f36")
            self._rounded(4, 1, 92, 247, 18, fill=BODY, outline=BODY_EDGE, width=2)
            self._rounded(12, 115, 76, 11, 5, fill="#1c2a36", outline="")   # windshield
            self._rounded(20, 232, 60, 11, 5, fill="#1c2a36", outline="")   # rear window
            for sx in (16, 54):                                              # front seats
                self._rounded(sx, 146, 30, 12, 4, fill="", outline="#3a3f49", dash=(2, 3))
            c.create_text(*self._pt(L_EDGE, 129.5), text="Dashboard", anchor="sw", fill=DIM, font=("Segoe UI", fs_small))
            x0, y0 = self._pt(50, 0)
            c.create_text(x0, y0 - 2, text="▲ FRONT", fill=DIM, font=("Segoe UI", fs), anchor="s")

        for text, nx, ny in self.view.notes:
            c.create_text(*self._pt(nx, ny), text=text, anchor="n" if ny >= 0 else "s",
                          fill=TEXT if closeup and ny < 0 else DIM, font=("Segoe UI", fs if ny < 0 else fs_small, "bold"
                                                                          if ny < 0 else "normal"))

        for label, gx, gy, gw, gh in self.view.groups:
            c.create_rectangle(*self._rect(gx, gy, gw, gh), outline="#5b6270", dash=(4, 3))
            lx, ly = self._pt(gx, gy + gh)
            c.create_text(lx + 2, ly + 1, text=label, anchor="nw", fill=DIM, font=("Segoe UI", fs_small))

        # wires: base line now, moving arrows in animate()
        self.wire_px = []
        labels = []
        for pts, amps, label, side, *extra in self.view.wires(values, now):
            active = extra[0] if extra else None   # on/off loads: current unknown, but we know if it's on
            style = extra[1] if len(extra) > 1 and extra[1] else {}   # optional colours, e.g. air / fuel / coolant
            px = [self._pt(x, y) for x, y in pts]
            flat = [v for p in px for v in p]
            if amps is None:
                c.create_line(*flat, fill=style.get("line", "#a89a50") if active else "#6a6f78", width=max(2, int(2 * self.ui)),
                              dash=(6, 5))
                width = 0
                amps = ON_OFF_AMPS if active else None   # fixed slow arrows while it's on
            else:
                width = (2 + min(abs(amps), 150) / 150 * 8) * self.ui
                c.create_line(*flat, fill=style.get("line", "#6b5a12") if abs(amps) >= 0.5 else "#4a4d55",
                              width=width, capstyle="round", joinstyle="round")
            segs = [math.dist(a, b) for a, b in zip(px, px[1:])]
            self.wire_px.append((px, segs, sum(segs), amps, width, style.get("arrow", FLOW)))
            i = max(range(len(segs)), key=segs.__getitem__)   # label the longest segment
            (ax, ay), (bx, by) = px[i], px[i + 1]
            labels.append(((ax + bx) / 2, (ay + by) / 2, abs(bx - ax) < abs(by - ay), label, width, side))

        hovered = self.hover[0] if self.hover else None
        spinning = ({k: (rpm, tq, (rest[0] if rest else None)) for k, rpm, tq, *rest in self.view.spinners(values, now)}
                    if hasattr(self.view, "spinners") else {})
        self.rotors = []
        for key, x, y, w_, h in self.view.components:
            cell = self.view.cell(key, values, now)
            if cell.state == "warn":
                outline, width = (WARN if self.blink else "#0f1013"), 3
            elif cell.state == "ideal":
                outline, width = IDEAL, 3
            else:
                outline, width = ("#c8ccd4", 2) if key == hovered else ("#0f1013", 1)
            x0, y0, x1, y1 = self._rect(x, y, w_, h)
            c.create_rectangle(x0, y0, x1, y1, fill=cell.fill, outline=outline, width=width,
                               dash=(5, 3) if cell.dashed and cell.state is None else None)
            name = self.view.label(key)
            text = f"{name.replace(chr(10), ' ')}   {cell.text}" if h < 12 else f"{name}\n{cell.text}"
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=text, fill=text_on(cell.fill), justify="center",
                          width=max(20, x1 - x0 - 6), font=("Segoe UI", fs if w_ >= 12 else fs_tiny, "bold"),
                          tags="label")
            if key in spinning:  # a rotor drawn behind the text, turning with the part
                rpm, torque, angle = spinning[key]
                r = 0.42 * min(x1 - x0, y1 - y0)
                colour = mix(cell.fill, "#ffffff", 0.3)
                width = max(2, int(2 * self.ui))
                if torque is not None:  # more torque = thicker, redder rotor
                    colour = mix(colour, "#ff2a1a", min(1.0, 0.25 + torque))
                    width = max(2, int((2 + 8 * torque) * self.ui))
                if angle is not None:   # e.g. the steering wheel: fixed at its real angle, left = anticlockwise
                    self.rotor_angle[key] = -angle
                    self.rotors.append((key, (x0 + x1) / 2, (y0 + y1) / 2, r, 0.0, colour, width + 1, "wheel"))
                else:
                    self.rotors.append((key, (x0 + x1) / 2, (y0 + y1) / 2, r, rotor_speed(rpm), colour, width, "rotor"))

        for mx, my, vertical, label, width, side in labels:
            off = width / 2 + 6 * self.ui
            if isinstance(side, tuple):  # fixed spot chosen by the view
                c.create_text(*self._pt(*side), text=label, anchor="w", fill=DIM, font=("Segoe UI", fs_small))
            elif vertical and side == "l":
                c.create_text(mx - off, my, text=label, anchor="e", fill=DIM, font=("Segoe UI", fs_small))
            elif vertical:
                c.create_text(mx + off, my, text=label, anchor="w", fill=DIM, font=("Segoe UI", fs_small))
            else:
                c.create_text(mx, my - off, text=label, anchor="s", fill=DIM, font=("Segoe UI", fs_small))

        for bar in (self.view.overlays(values, now) if hasattr(self.view, "overlays") else []):
            x0, y0, x1, y1 = self._rect(*bar["rect"])
            c.create_rectangle(x0, y0, x1, y1, fill="#101114", outline="#5b6270")
            if bar["fraction"] is not None:
                c.create_rectangle(x0, y0, x0 + (x1 - x0) * max(0.0, min(1.0, bar["fraction"])), y1,
                                   fill=bar["colour"], outline="")
            for m in bar.get("marks", ()):  # ideal-range ticks
                mx = x0 + (x1 - x0) * m
                c.create_line(mx, y0 - 3, mx, y1 + 3, fill=TEXT, width=max(1, int(self.ui)))
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=bar["text"], fill=TEXT,
                          font=("Segoe UI", fs_tiny, "bold"))

        self.draw_arrows()
        self.draw_rotors()
        if self.hover:
            self.draw_tooltip(values, now)

    def draw_arrows(self):
        """Moving chevrons along each wire: direction = power flow, speed and size = current."""
        c = self.canvas
        c.delete("anim")
        spacing = 30 * self.ui
        for idx, (px, segs, total, amps, width, arrow_colour) in enumerate(self.wire_px):
            if amps is None or abs(amps) < 0.5 or total <= 0:
                continue
            size = max(4 * self.ui, width * 0.75)
            sign = 1 if amps > 0 else -1
            phase = self.wire_phase.get(idx, 0.0) % spacing
            d = phase
            while d < total:
                # find the point at distance d along the polyline
                rest, i = d, 0
                while i < len(segs) - 1 and rest > segs[i]:
                    rest -= segs[i]
                    i += 1
                (ax, ay), (bx, by) = px[i], px[i + 1]
                seg = segs[i] or 1
                tx, ty = (bx - ax) / seg * sign, (by - ay) / seg * sign   # travel direction
                cx, cy = ax + (bx - ax) * rest / seg, ay + (by - ay) * rest / seg
                nx, ny = -ty, tx
                c.create_polygon(cx + tx * size, cy + ty * size,
                                 cx - tx * size * 0.6 + nx * size * 0.8, cy - ty * size * 0.6 + ny * size * 0.8,
                                 cx - tx * size * 0.6 - nx * size * 0.8, cy - ty * size * 0.6 - ny * size * 0.8,
                                 fill=arrow_colour, outline="#1a1a1a", tags="anim")
                d += spacing
        c.tag_raise("tip")

    def draw_rotors(self):
        """3-spoke rotor behind each spinning part's text; clockwise = forwards."""
        c = self.canvas
        c.delete("spin")
        for key, cx, cy, r, _, colour, width, style in self.rotors:
            a0 = math.radians(self.rotor_angle.get(key, 0.0))
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=colour, width=width, tags="spin")
            # steering wheel spokes: left, right and down when straight; rotor spokes: 120 degrees apart
            spokes = (0, math.pi, math.pi / 2) if style == "wheel" else (0, 2 * math.pi / 3, 4 * math.pi / 3)
            for off in spokes:
                a = a0 + off
                c.create_line(cx, cy, cx + r * math.cos(a), cy + r * math.sin(a), fill=colour, width=width, tags="spin")
        c.tag_raise("label")
        c.tag_raise("tip")

    def animate(self):
        t = time.monotonic()
        dt, self.last_frame = t - self.last_frame, t
        for key, _, _, _, tps, *_ in self.rotors:
            self.rotor_angle[key] = (self.rotor_angle.get(key, 0.0) + 360 * tps * dt) % 360
        if self.rotors:
            self.draw_rotors()
        for idx, (_, _, _, amps, *_) in enumerate(self.wire_px):
            if amps is not None:
                speed = min(400, 15 + 3 * abs(amps)) * self.ui          # px per second, faster with more amps
                # arrows are placed from the start of the wire, so reverse flow = decreasing phase
                self.wire_phase[idx] = self.wire_phase.get(idx, 0.0) + speed * dt * (1 if amps > 0 else -1)
        if self.wire_px:
            self.draw_arrows()
        self.root.after(FRAME_MS, self.animate)

    # ---------- refresh loop ----------
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
        self.blink = (self.ticks * REFRESH_MS // 500) % 2 == 1
        self.refresh()
        self.root.after(REFRESH_MS, self.tick)


def main():
    ap = argparse.ArgumentParser(description="Prius Gen 3 live dashboard")
    ap.add_argument("--port", default="COM6")
    ap.add_argument("--demo", action="store_true", help="fake data, no car needed")
    ap.add_argument("--view", default="Temperature", help="start in this view (Temperature, Electrical, Spinning, Pressure, Engine, Battery or Trip)")
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
