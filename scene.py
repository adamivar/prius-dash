"""Draws the current view: the car (or close-up panel), parts, wires with moving arrows, rotors and the hover card.

Works on any canvas that offers the handful of tkinter Canvas calls used here (create_line / polygon / rectangle /
oval / text, delete, tag_raise, tag_lower, bbox, move, winfo_width / winfo_height), so the same code draws the
Windows app (a real tkinter Canvas) and the Android app (mobile/canvas.py).
"""
import math

import config as cfg
import shapes
from calc import front_wheel_angles_deg
from sensors import SENSORS, TRIP_KEYS
from views import BODY, DIM, IDEAL, TEXT, TIP_FG, WARN, WHEELS_RECT, SpinView

CAR_W, CAR_H = 100, 250   # car drawn in a 100 x 250 unit box, front at the top, driver on the left
FILL_CAR = (4, 1, 96, 248)        # the car body's outline - what fills the screen in fill mode
FILL_CLOSEUP = (1, 1, 99, 248)    # the close-up panel
L_EDGE = 14              # left edge of the parts column (x 4-14 is kept for wires)

mix = shapes.mix


def rotor_speed(rpm):
    """On-screen turns per second for a part turning at `rpm`: slowed down a lot (a real engine at 1,500 rpm is
    25 turns a second), square-root scaled so slow and fast parts still look different, capped so it can't strobe."""
    return (math.copysign(min(cfg.ROTOR_MAX_TURNS_S, cfg.ROTOR_SQRT_GAIN * math.sqrt(abs(rpm))), rpm)
            if abs(rpm) >= 1 else 0.0)


def text_on(hex_colour):
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return cfg.DARK_TEXT if (0.299 * r + 0.587 * g + 0.114 * b) > cfg.TEXT_LIGHTNESS_SWITCH else TEXT


def poll_plan(view, views, poller):
    """Current view polled fast; the trip totals every few loops; every other view in the background."""
    active = view.sensors()
    keys = {s.key for s in active}
    trip = [SENSORS[k] for k in TRIP_KEYS if k not in keys]
    keys |= {s.key for s in trip}
    background = {s.key: s for v in views if v is not view for s in v.sensors() if s.key not in keys}
    poller.set_sensors(active, list(background.values()), trip)


class Scene:
    def __init__(self, canvas, ui=1.0, font="Segoe UI", margin=16, tooltip_width=cfg.TOOLTIP_WIDTH, max_stretch=1.0,
                 margins=None, glance=None, fill=False):
        self.c = canvas
        # fill = the car body (or close-up panel) touches the canvas edges: no margins, no "FRONT" / title above it
        self.fill = fill
        # glance = (tag px, largest value px): "read from arm's length" mode for the phone. Each part's reading is
        # drawn as big as the part allows (up to the largest size) with its name as a small tag in the corner.
        # Needs a canvas with measure(text, px, bold) -> (width, height).
        self.glance = glance
        self.ui = ui                 # line-width / spacing scale (1.0 = a 96 dpi Windows screen)
        self.font = font
        # drawing units kept free around the car: (left/right each, top, bottom); default = margin / 2 all round
        self.margins = margins or (margin / 2, margin / 2, margin / 2)
        # how much wider (or taller) than true proportions the drawing may be stretched to fill the screen;
        # 1.0 = never. Text follows the smaller scale, so anything that fits unstretched still fits.
        self.max_stretch = max_stretch
        self.tooltip_width = tooltip_width
        self.view = None
        self.blink = False
        self.hover = None            # (component key, pointer x, pointer y)
        self.rotors = []             # see redraw()
        self.rotor_angle = {}        # key -> current angle in degrees
        self.wire_px = []            # [(pixel points, segment lengths, total length, signed amps, width, colour)]
        self.wire_phase = {}         # wire index -> distance travelled by the arrows (px)

    def set_view(self, view):
        self.view = view
        self.wire_phase.clear()
        self.hover = None

    # ---------- geometry ----------
    def scales(self):
        """(s, sx, sy, ox, oy): s = text / detail scale (pixels per drawing unit), sx / sy = horizontal / vertical
        scale (differ when stretching to fill the screen), ox / oy = where drawing unit (0, 0) lands."""
        cw, ch = self.c.winfo_width(), self.c.winfo_height()
        if self.fill:
            vx0, vy0, vx1, vy1 = FILL_CLOSEUP if getattr(self.view, "scene", "car") == "closeup" else FILL_CAR
            sx, sy = max(0.1, cw / (vx1 - vx0)), max(0.1, ch / (vy1 - vy0))
            return min(sx, sy), sx, sy, -vx0 * sx, -vy0 * sy
        side, top, bottom = self.margins
        sx, sy = max(0.1, cw / (CAR_W + 2 * side)), max(0.1, ch / (CAR_H + top + bottom))
        s = min(sx, sy)
        sx, sy = min(sx, s * self.max_stretch), min(sy, s * self.max_stretch)
        ox = (cw - CAR_W * sx) / 2
        oy = (ch - (CAR_H + top + bottom) * sy) / 2 + top * sy
        return s, sx, sy, ox, oy

    def geom(self):
        s, _, _, ox, oy = self.scales()
        return s, ox, oy

    def pt(self, x, y):
        _, sx, sy, ox, oy = self.scales()
        return ox + x * sx, oy + y * sy

    def rect(self, x, y, w, h):
        return (*self.pt(x, y), *self.pt(x + w, y + h))

    def rounded(self, x, y, w, h, r, **kw):
        x0, y0, x1, y1 = self.rect(x, y, w, h)
        pts = shapes._round_rect(x0, y0, x1, y1, r * self.geom()[0])
        return self.c.create_polygon([v for p in pts for v in p], **kw)

    def hit(self, px, py):
        """Which part is under this pixel, or None."""
        _, sx, sy, ox, oy = self.scales()
        ux, uy = (px - ox) / sx, (py - oy) / sy
        return next((k for k, x, y, w_, h in self.view.components if x <= ux <= x + w_ and y <= uy <= y + h), None)

    # ---------- drawing ----------
    def redraw(self, values, now):
        c, f = self.c, self.font
        c.delete("all")
        s, _, _ = self.geom()
        fs = -max(10, int(s * cfg.FONT_SCALE))          # font size in pixels (negative = px), follows window size
        fs_small = -max(9, int(s * cfg.FONT_SCALE_SMALL))
        fs_tiny = -max(8, int(s * cfg.FONT_SCALE_TINY))      # narrow boxes (battery blocks)

        closeup = getattr(self.view, "scene", "car") == "closeup"
        # front wheels turned with the steering wheel (+ angle = left = anticlockwise on screen, so negate)
        left, right = front_wheel_angles_deg(SpinView.steer_angle(values, now))
        steer_rot = {"fl": -left, "fr": -right}
        if closeup:   # close-up views: a plain panel instead of the car
            self.rounded(1, 1, 98, 247, 6, fill=BODY, outline=cfg.BODY_EDGE, width=2)
        else:
            def tires():                                                    # wheels on the real axle lines
                for k, (wx, wy, ww, wh) in WHEELS_RECT.items():
                    shapes.draw(c, "tire", *self.rect(wx, wy, ww, wh), cfg.TIRE, cfg.TIRE_EDGE, 1, s=s,
                                rot=steer_rot.get(k, 0.0))
            if not self.fill:          # PC: tires stick out from under the body
                tires()
            self.rounded(4, 1, 92, 247, 18, fill=BODY, outline=cfg.BODY_EDGE, width=2)
            if self.fill:              # phone: tires sit inside the body outline, drawn on top so they stay visible
                tires()
            self.rounded(12, 87.5, 76, 6, 3, fill=cfg.GLASS, outline="")     # bottom of the windshield (cowl)
            for sx in (16, 54):                                             # front seats
                self.rounded(sx, 121, 30, 18, 4, fill="", outline=cfg.SEAT_OUTLINE, dash=(2, 3))
            self.rounded(16, 158, 68, 24, 4, fill="", outline=cfg.SEAT_OUTLINE, dash=(2, 3))   # rear seat
            c.create_text(*self.pt(L_EDGE, 98), text="Dashboard", anchor="sw", fill=DIM, font=(f, fs_small))
            if not self.fill:
                x0, y0 = self.pt(50, 0)
                c.create_text(x0, y0 - 2, text="▲ FRONT", fill=DIM, font=(f, fs), anchor="s")

        for text, nx, ny in self.view.notes:
            if ny < 0 and self.fill:      # close-up titles sit above the panel; the view name is in the top bar
                continue
            c.create_text(*self.pt(nx, ny), text=text, anchor="n" if ny >= 0 else "s",
                          fill=TEXT if closeup and ny < 0 else DIM,
                          font=(f, fs if ny < 0 else fs_small, "bold" if ny < 0 else "normal"))

        for label, gx, gy, gw, gh in self.view.groups:
            c.create_rectangle(*self.rect(gx, gy, gw, gh), outline=cfg.GROUP_OUTLINE, dash=(4, 3))
            lx, ly = self.pt(gx, gy + gh)
            c.create_text(lx + 2, ly + 1, text=label, anchor="nw", fill=DIM, font=(f, fs_small))

        # wires: base line now, moving arrows in draw_arrows()
        self.wire_px = []
        labels = []
        for pts, amps, label, side, *extra in self.view.wires(values, now):
            active = extra[0] if extra else None   # on/off loads: current unknown, but we know if it's on
            style = extra[1] if len(extra) > 1 and extra[1] else {}   # optional colours, e.g. air / fuel / coolant
            px = [self.pt(x, y) for x, y in pts]
            flat = [v for p in px for v in p]
            if amps is None:
                c.create_line(*flat, fill=style.get("line", cfg.WIRE_ON) if active else cfg.WIRE_UNMEASURED,
                              width=max(cfg.WIRE_MIN_WIDTH, int(cfg.WIRE_MIN_WIDTH * self.ui)), dash=(6, 5))
                width = 0
                amps = cfg.ON_OFF_AMPS if active else None   # fixed slow arrows while it's on
            else:
                width = (cfg.WIRE_MIN_WIDTH + min(abs(amps), cfg.WIRE_FULL_AMPS) / cfg.WIRE_FULL_AMPS
                         * cfg.WIRE_EXTRA_WIDTH) * self.ui
                c.create_line(*flat, fill=style.get("line", cfg.WIRE_ACTIVE) if abs(amps) >= cfg.ARROW_MIN_AMPS
                              else cfg.WIRE_IDLE, width=width, capstyle="round", joinstyle="round")
            segs = [math.dist(a, b) for a, b in zip(px, px[1:])]
            self.wire_px.append((px, segs, sum(segs), amps, width, style.get("arrow", cfg.FLOW)))
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
                outline, width = (WARN if self.blink else cfg.OUTLINE), 3
            elif cell.ring:
                outline, width = cell.ring, max(3, int(4 * self.ui))
            elif cell.state == "ideal":
                outline, width = IDEAL, 3
            else:
                outline, width = (cfg.HOVER_OUTLINE, 2) if key == hovered else (cfg.OUTLINE, 1)
            x0, y0, x1, y1 = self.rect(x, y, w_, h)
            kind = getattr(self.view, "shapes", {}).get(key, "box")   # outline that looks like the real part
            rot = steer_rot.get(key, 0.0) if kind == "tread" else 0.0   # steered front tires (Spinning view)
            shapes.draw(c, kind, x0, y0, x1, y1, cell.fill, outline, width,
                        (5, 3) if cell.dashed and cell.state is None else None, s, rot=rot)
            name = self.view.label(key)
            tx0, ty0, tx1, ty1 = self.rect(*shapes.text_box(kind, x, y, w_, h))
            if self.glance:
                self.glance_text(name, cell, (tx0, ty0, tx1, ty1))
            else:
                text = f"{name.replace(chr(10), ' ')}   {cell.text}" if h < cfg.ONE_LINE_BOX else f"{name}\n{cell.text}"
                c.create_text((tx0 + tx1) / 2, (ty0 + ty1) / 2, text=text, fill=text_on(cell.fill), justify="center",
                              width=max(20, tx1 - tx0 - 6), font=(f, fs if w_ >= cfg.NARROW_BOX else fs_tiny, "bold"),
                              tags="label")
            if key in spinning and kind in ("tread", "geartread"):   # seen from above, tread / teeth roll past
                rpm, torque, _ = spinning[key]
                t = torque or 0.0
                colour = mix(shapes.detail_colour(cell.fill), cfg.ROTOR_TORQUE, min(1.0, t))
                width = max(1, int((1.5 + cfg.ROTOR_MAX_WIDTH / 2 * t) * self.ui))
                # tire: tread lines roll front/back; ring gear: teeth along its top + bottom edges slide sideways
                self.rotors.append((key, (x0 + x1) / 2, (y0 + y1) / 2,
                                    ((x1 - x0) / 2, (y1 - y0) / 2, 2 * s if kind == "tread" else 2.4 * s, rot),
                                    rotor_speed(rpm), colour,
                                    width if kind == "tread" else min(width, max(1, int(0.8 * s))),
                                    "tread" if kind == "tread" else "teeth"))
            elif key in spinning:  # a rotor drawn behind the text, turning with the part
                rpm, torque, angle = spinning[key]
                r = 0.42 * min(x1 - x0, y1 - y0)
                colour = mix(cell.fill, cfg.ROTOR_TINT, cfg.ROTOR_TINT_AMOUNT)
                width = max(2, int(2 * self.ui))
                if torque is not None:  # more torque = thicker, redder rotor
                    colour = mix(colour, cfg.ROTOR_TORQUE, min(1.0, cfg.ROTOR_TORQUE_BASE + torque))
                    width = max(2, int((2 + cfg.ROTOR_MAX_WIDTH * torque) * self.ui))
                if angle is not None:   # e.g. the steering wheel: fixed at its real angle, left = anticlockwise
                    self.rotor_angle[key] = -angle
                    self.rotors.append((key, (x0 + x1) / 2, (y0 + y1) / 2, r, 0.0, colour, width + 1, "wheel"))
                else:
                    self.rotors.append((key, (x0 + x1) / 2, (y0 + y1) / 2, r, rotor_speed(rpm), colour, width, "rotor"))

        for mx, my, vertical, label, width, side in labels:
            off = width / 2 + 6 * self.ui
            if isinstance(side, tuple):  # fixed spot chosen by the view
                c.create_text(*self.pt(*side), text=label, anchor="w", fill=DIM, font=(f, fs_small))
            elif vertical and side == "l":
                c.create_text(mx - off, my, text=label, anchor="e", fill=DIM, font=(f, fs_small))
            elif vertical:
                c.create_text(mx + off, my, text=label, anchor="w", fill=DIM, font=(f, fs_small))
            else:
                c.create_text(mx, my - off, text=label, anchor="s", fill=DIM, font=(f, fs_small))

        for bar in (self.view.overlays(values, now) if hasattr(self.view, "overlays") else []):
            x0, y0, x1, y1 = self.rect(*bar["rect"])
            c.create_rectangle(x0, y0, x1, y1, fill=cfg.BAR_BG, outline=cfg.GROUP_OUTLINE)
            if bar["fraction"] is not None:
                c.create_rectangle(x0, y0, x0 + (x1 - x0) * max(0.0, min(1.0, bar["fraction"])), y1,
                                   fill=bar["colour"], outline="")
            for m in bar.get("marks", ()):  # ideal-range ticks
                mx = x0 + (x1 - x0) * m
                c.create_line(mx, y0 - 3, mx, y1 + 3, fill=TEXT, width=max(1, int(self.ui)))
            if bar["text"]:
                c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=bar["text"], fill=TEXT, font=(f, fs_tiny, "bold"))

        for d in (self.view.decorations(values, now) if hasattr(self.view, "decorations") else []):
            self.decoration(d, fs_small)

        self.draw_arrows()
        self.draw_rotors()
        if self.hover:
            self.draw_tooltip(values, now)

    def glance_text(self, name, cell, box):
        """Phone layout: the reading as big as the part allows (up to the glance size), the name as a small tag.
        Parts with no reading (dashboard lamps) show their name big instead. Tap a part for everything in full."""
        c, f = self.c, self.font
        tag_px, max_px = self.glance
        x0, y0, x1, y1 = box
        pad = max(2.0, 2 * self.ui)
        x0, y0, x1, y1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad
        w, h = x1 - x0, y1 - y0
        if w < 8 or h < 6:
            return
        colour = text_on(cell.fill)
        name = name.replace("\n", " ")
        value = cell.text.strip()
        if not value:                 # dashboard lamps: the name is the reading
            if not name:
                return
            value, name = name, ""

        def fit(text, aw, ah, cap):
            """Largest bold px (<= cap) at which text fits aw x ah, from its size at 100 px."""
            tw, th = c.measure(text, 100, True)
            return max(1.0, min(cap, 100 * aw / max(tw, 1), 100 * ah / max(th, 1)))

        def wrap(text, aw, px, max_lines):
            """Greedy word wrap into at most max_lines lines no wider than aw, or None if it won't fit."""
            lines, cur = [], ""
            for word in text.split(" "):
                trial = f"{cur} {word}".strip()
                if cur and c.measure(trial, px, False)[0] > aw:
                    lines.append(cur)
                    cur = word
                else:
                    cur = trial
            lines.append(cur)
            if len(lines) > max_lines or any(c.measure(ln, px, False)[0] > aw for ln in lines):
                return None
            return lines

        def tag(text, aw, ah):
            """The name as a small tag: full size on 1-2 lines if it fits, else shrunk (to 60%), else shortened
            with an ellipsis as a last resort (tap the part for its full name). Returns (lines, px)."""
            size = min(tag_px, ah)
            for px in (size, size * 0.85, size * 0.72, size * 0.6):
                line_h = c.measure("A", px, False)[1]
                most = max(1, min(2, int(ah // line_h)))
                lines = wrap(text, aw, px, most)
                if lines:
                    return lines, px
            px = size * 0.6
            while text and c.measure(text, px, False)[0] > aw:
                text = text[:-2].rstrip() + "…" if len(text) > 2 else ""
            return ([text] if text else []), px

        def draw_tag(lines, px, x, y, anchor):
            if lines:
                c.create_text(x, y, text="\n".join(lines), anchor=anchor, justify="center" if anchor == "n" else "left",
                              fill=colour, font=(f, -px), tags="label")

        # layout 1: name on top (up to 2 lines, at most ~35% of the height), reading underneath
        v_lines, v_px = tag(name, w, max(tag_px * 0.6, min(2.2 * tag_px, h * 0.35))) if name else ([], 0)
        v_top = y0 + (c.measure("\n".join(v_lines), v_px, False)[1] if v_lines else 0)
        v_value = fit(value, w, y1 - v_top, max_px)
        # layout 2 (short, wide parts): name on the left, reading on the right - only if the reading gets
        # clearly bigger and the name isn't shortened
        best = "top"
        if name and w > 2.2 * h:
            h_lines, h_px = tag(name, w * 0.45, h)
            if h_lines and not h_lines[-1].endswith("…"):
                name_w = max(c.measure(ln, h_px, False)[0] for ln in h_lines) + 2 * pad
                h_value = fit(value, w - name_w, h, max_px)
                if h_value > v_value * 1.15 or (v_lines and v_lines[-1].endswith("…")):
                    best = "left"
        if best == "left":
            draw_tag(h_lines, h_px, x0, (y0 + y1) / 2, "w")
            c.create_text(x1, (y0 + y1) / 2, text=value, anchor="e", justify="right", fill=colour,
                          font=(f, -h_value, "bold"), tags="label")
        else:
            draw_tag(v_lines, v_px, (x0 + x1) / 2, y0, "n")
            c.create_text((x0 + x1) / 2, (v_top + y1) / 2, text=value, justify="center", fill=colour,
                          font=(f, -v_value, "bold"), tags="label")

    def decoration(self, d, fs_small):
        """Extra drawing a view asks for, in drawing units: circle / line / text (e.g. the g-ball)."""
        c, s = self.c, self.scales()[0]
        kind = d["kind"]
        if kind == "circle":
            (x, y), r = self.pt(d["x"], d["y"]), d["r"] * s
            c.create_oval(x - r, y - r, x + r, y + r, fill=d.get("fill", ""), outline=d.get("outline", ""),
                          width=d.get("width", 1) * self.ui)
        elif kind == "line":
            pts = [v for p in d["pts"] for v in self.pt(*p)]
            c.create_line(*pts, fill=d["fill"], width=d.get("width", 1) * self.ui, dash=d.get("dash"))
        elif kind == "text":
            c.create_text(*self.pt(d["x"], d["y"]), text=d["text"], fill=d.get("fill", DIM), anchor=d.get("anchor", "center"),
                          font=(self.font, fs_small))

    def draw_tooltip(self, values, now):
        key, mx, my = self.hover
        title, lines = self.view.tooltip(key, values, now)
        c, f = self.c, self.font
        pad, gap = int(10 * self.ui), int(18 * self.ui)
        width = int(min(self.tooltip_width * self.ui, c.winfo_width() - 2 * pad - 8))   # never wider than the screen
        cw, ch = c.winfo_width(), c.winfo_height()
        shrink = 1.0
        while True:   # a card taller than the screen gets smaller text until it fits
            size = lambda pts: max(6, round(pts * shrink))
            items = [c.create_text(0, 0, text=title, anchor="nw", width=width, fill=TIP_FG, font=(f, size(12), "bold"),
                                   tags="tip")]
            for text, colour, pts, bold in lines:
                y = c.bbox(items[-1])[3] + 4
                items.append(c.create_text(0, y, text=text, anchor="nw", width=width, fill=colour, tags="tip",
                                           font=(f, size(pts), "bold") if bold else (f, size(pts))))
            x0, y0, x1, y1 = c.bbox(*items)
            tw, th = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
            if th <= ch - 8 or shrink <= 0.55:
                break
            c.delete("tip")
            shrink -= 0.1
        tx = mx + gap if mx + gap + tw < cw else mx - gap - tw  # flip to the left near the edge
        tx, ty = max(4, tx), max(4, min(my + gap, ch - th - 4))
        for it in items:
            c.move(it, tx + pad, ty + pad)
        bg = c.create_rectangle(tx, ty, tx + tw, ty + th, fill=cfg.TIP_BG, outline=cfg.TIP_BORDER, tags="tip")
        c.tag_lower(bg, items[0])

    def draw_arrows(self):
        """Moving chevrons along each wire: direction = power flow, speed and size = current."""
        c = self.c
        c.delete("anim")
        spacing = cfg.ARROW_SPACING * self.ui
        for idx, (px, segs, total, amps, width, arrow_colour) in enumerate(self.wire_px):
            if amps is None or abs(amps) < cfg.ARROW_MIN_AMPS or total <= 0:
                continue
            size = max(4 * self.ui, width * 0.75)
            sign = 1 if amps > 0 else -1
            d = self.wire_phase.get(idx, 0.0) % spacing
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
                                 fill=arrow_colour, outline=cfg.ARROW_OUTLINE, tags="anim")
                d += spacing
        c.tag_raise("tip")

    def draw_rotors(self):
        """3-spoke rotor behind each spinning part's text; clockwise = forwards. Tires instead show their tread
        rolling past (seen from above, the top of a wheel turning forwards moves towards the front), and the ring
        gear shows its teeth sliding sideways along its top and bottom edges (left to right = forwards)."""
        c = self.c
        c.delete("spin")
        for key, cx, cy, r, _, colour, width, style in self.rotors:
            if style in ("tread", "teeth"):
                hw, hh, spacing, turn = r
                phase = self.rotor_angle.get(key, 0.0) / 360 * spacing   # one line / tooth per turn of the rotor
                if style == "tread":
                    top, bottom = cy - hh * 0.9, cy + hh * 0.9
                    y = top + (-phase) % spacing
                    while y < bottom:
                        (ax, ay), (bx, by) = shapes.rotate([(cx - hw * 0.6, y), (cx + hw * 0.6, y)], cx, cy, turn)
                        c.create_line(ax, ay, bx, by, fill=colour, width=width, tags="spin")
                        y += spacing
                else:
                    left, right, band = cx - hw * 0.97, cx + hw * 0.97, hh * 0.44
                    x = left + phase % spacing
                    while x < right:
                        for ya, yb in ((cy - hh, cy - band), (cy + band, cy + hh)):
                            c.create_line(x, ya, x, yb, fill=colour, width=width, tags="spin")
                        x += spacing
                continue
            a0 = math.radians(self.rotor_angle.get(key, 0.0))
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=colour, width=width, tags="spin")
            # steering wheel spokes: left, right and down when straight; rotor spokes: 120 degrees apart
            spokes = (0, math.pi, math.pi / 2) if style == "wheel" else (0, 2 * math.pi / 3, 4 * math.pi / 3)
            for off in spokes:
                a = a0 + off
                c.create_line(cx, cy, cx + r * math.cos(a), cy + r * math.sin(a), fill=colour, width=width, tags="spin")
        c.tag_raise("label")
        c.tag_raise("tip")

    def step(self, dt):
        """Advance the rotors and arrows by dt seconds and redraw just those."""
        for key, _, _, _, tps, *_ in self.rotors:
            self.rotor_angle[key] = (self.rotor_angle.get(key, 0.0) + 360 * tps * dt) % 360
        if self.rotors:
            self.draw_rotors()
        for idx, (_, _, _, amps, *_) in enumerate(self.wire_px):
            if amps is not None:
                speed = min(cfg.ARROW_MAX_SPEED, cfg.ARROW_BASE_SPEED + cfg.ARROW_SPEED_PER_AMP * abs(amps)) * self.ui
                # arrows are placed from the start of the wire, so reverse flow = decreasing phase
                self.wire_phase[idx] = self.wire_phase.get(idx, 0.0) + speed * dt * (1 if amps > 0 else -1)
        if self.wire_px:
            self.draw_arrows()
