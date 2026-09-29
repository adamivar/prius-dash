"""Outline shapes for the parts, so each one looks roughly like the real thing seen from above
(a drum for a motor, a canister for the catalytic converter, terminals on a battery, fins on a radiator...).

Every shape stays inside its part's rectangle. draw() works in pixels; text_box() and width_at() work in the
same units as the rectangle they're given, so the layout checker can use them too.
"""
import math

SHAPES = ("box", "rounded", "finned", "drum", "canister", "pill", "circle", "gear", "throttle", "rack", "valveblock",
          "airbox", "engine", "manifold", "tank", "radiator", "core", "vent", "fan", "pack", "module", "battery",
          "tire", "tread", "geartread", "lamp", "taillight_l", "taillight_r", "ecu", "sump", "strip4", "pulley", "gauge")


def mix(hex_a, hex_b, t):
    a = [int(hex_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def detail_colour(fill):
    """Colour for fins, ribs, terminals: a bit darker than a light fill, a bit lighter than a dark one."""
    r, g, b = (int(fill[i:i + 2], 16) for i in (1, 3, 5))
    return mix(fill, "#000000", 0.32) if 0.299 * r + 0.587 * g + 0.114 * b > 90 else mix(fill, "#ffffff", 0.2)


# ---------- geometry helpers (work in any units) ----------
def _arc(cx, cy, rx, ry, a0, a1, n=10):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _round_rect(x0, y0, x1, y1, r):
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    return (_arc(x1 - r, y0 + r, r, r, -90, 0) + _arc(x1 - r, y1 - r, r, r, 0, 90)
            + _arc(x0 + r, y1 - r, r, r, 90, 180) + _arc(x0 + r, y0 + r, r, r, 180, 270))


def _stadium(x0, y0, x1, y1):
    return _round_rect(x0, y0, x1, y1, min(x1 - x0, y1 - y0) / 2)


def _drum_end(w, h):
    return min(w * 0.08, h * 0.25)


def _terminal_h(h):
    return min(h * 0.14, 2.2)


# ---------- where the text goes ----------
def text_box(kind, x, y, w, h):
    """(x, y, w, h) of the area the label and value are centred in."""
    if kind == "drum":
        e = _drum_end(w, h)
        return x + 0.4 * e, y, w - 1.4 * e, h
    if kind in ("canister", "pill"):
        r = min(w, h) / 2
        return x + r * 0.25, y, w - r * 0.5, h
    if kind == "airbox":
        return x + w * 0.12, y, w * 0.88, h
    if kind in ("module", "battery"):
        t = _terminal_h(h)
        return x, y + t, w, h - t
    if kind == "radiator":
        return x + w * 0.2, y, w * 0.6, h
    if kind == "core":
        return x + w * 0.07, y, w * 0.86, h
    if kind == "vent":
        return x + w * 0.07, y, w * 0.93, h
    if kind == "manifold":
        return x, y, w, h * 0.92
    if kind == "rack":
        return x, y + h * 0.05, w, h * 0.9
    if kind == "ecu":
        return x, y, w, h * 0.92
    if kind == "gauge":                # a dial drawn by the view above, the text underneath
        return x, y + h * 0.8, w, h * 0.2
    return x, y, w, h


def width_at(kind, x, y, w, h, yy):
    """How wide the shape's text area is at height yy (for round shapes it narrows towards the top and bottom)."""
    tx, ty, tw, th = text_box(kind, x, y, w, h)
    if kind in ("circle", "gear", "pulley"):
        r = min(w, h) / 2 * (0.84 if kind == "gear" else 1.0)
        dy = abs(yy - (y + h / 2))
        return 0.0 if dy >= r else 2 * math.sqrt(r * r - dy * dy)
    if kind in ("pill", "canister", "lamp"):
        r = min(w, h) / 2
        dy = abs(yy - (y + h / 2))
        return w - 2 * r + (0 if dy >= r else 2 * math.sqrt(r * r - dy * dy))
    if kind == "sump":   # narrows towards the bottom
        return w * (1 - 0.2 * max(0.0, min(1.0, (yy - y) / h)))
    return tw


# ---------- drawing (pixels) ----------
def rotate(pts, cx, cy, deg):
    """Turn points about (cx, cy) by deg degrees, clockwise on screen (y points down)."""
    if not deg:
        return pts
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


EMPTY = "#16191e"    # the empty part of a part drawn as a tank (see draw(level=...))


def liquid_colour(fill):
    """The fill of a part drawn as a tank, kept mid-tone: light enough to stand out from the empty part, dark
    enough for light text on top (the text runs across both the full and the empty part)."""
    r, g, b = (int(fill[i:i + 2], 16) for i in (1, 3, 5))
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum > 100:
        return mix(fill, "#000000", 1 - 100 / lum)
    if lum < 55:
        return mix(fill, "#ffffff", (55 - lum) / (255 - lum))
    return fill


def clip_below(pts, y_cut):
    """The part of a polygon at or below the horizontal line y = y_cut (screen y grows downwards)."""
    out = []
    for i, (ax, ay) in enumerate(pts):
        bx, by = pts[(i + 1) % len(pts)]
        a_in, b_in = ay >= y_cut, by >= y_cut
        if a_in:
            out.append((ax, ay))
        if a_in != b_in:
            t = (y_cut - ay) / (by - ay)
            out.append((ax + (bx - ax) * t, y_cut))
    return out


def draw(c, kind, x0, y0, x1, y1, fill, outline, width, dash=None, s=4.0, tags=(), rot=0.0, level=None):
    """Draw part `kind` filling the pixel rectangle; returns nothing. s = pixels per drawing unit.
    rot = turn the shape about its centre (degrees, clockwise); only the tire shapes use it (steered wheels).
    level = 0..1: draw it like a tank filled to that height (0 = empty, no line; 1 = full), for things with a
    capacity (battery charge, fuel, pressures...)."""
    w, h = x1 - x0, y1 - y0
    det = detail_colour(fill)
    lw = max(1, round(s * 0.22))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    def body(pts):
        flat_pts = rotate(pts, cx, cy, rot)
        flat = [v for p in flat_pts for v in p]
        if level is None:
            c.create_polygon(flat, fill=fill, outline=outline, width=width, dash=dash, tags=tags)
            return
        c.create_polygon(flat, fill=EMPTY, outline="", tags=tags)
        y_top = y1 - h * max(0.0, min(1.0, level))
        liquid = clip_below(flat_pts, y_top) if level > 0 else []
        if len(liquid) >= 3:
            c.create_polygon([v for p in liquid for v in p], fill=liquid_colour(fill), outline="", tags=tags)
            top = [p for p in liquid if abs(p[1] - y_top) < 0.01]
            if len(top) >= 2 and level < 0.999:     # the fill line
                c.create_line(min(p[0] for p in top), y_top, max(p[0] for p in top), y_top,
                              fill=mix(liquid_colour(fill), "#ffffff", 0.6), width=max(2, lw * 2), tags=tags)
        c.create_polygon(flat, fill="", outline=outline, width=width, dash=dash, tags=tags)

    def line(*pts, colour=det, wd=lw):
        c.create_line(*[v for p in rotate(list(pts), cx, cy, rot) for v in p], fill=colour, width=wd, tags=tags)

    def ticks(xa, xb, step, ya, yb):   # short fins / ribs
        n = max(1, int((xb - xa) / step))
        for i in range(n + 1):
            x = xa + (xb - xa) * i / n
            line((x, ya), (x, yb))

    if kind == "box":
        c.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, width=width, dash=dash, tags=tags)
    elif kind == "rounded":
        body(_round_rect(x0, y0, x1, y1, min(w, h) * 0.18))
    elif kind == "finned":            # cast-aluminium power electronics: heat-sink fins along both long edges
        r = min(w, h) * 0.1
        body(_round_rect(x0, y0, x1, y1, r))
        f = min(h * 0.13, 1.6 * s)
        ticks(x0 + r * 1.5, x1 - r * 1.5, 1.6 * s, y0 + width, y0 + f)
        ticks(x0 + r * 1.5, x1 - r * 1.5, 1.6 * s, y1 - f, y1 - width)
    elif kind == "drum":              # a cylinder lying across the car, one end face showing
        e = _drum_end(w, h)
        body([(x0 + e, y0), (x1 - e, y0)] + _arc(x1 - e, cy, e, h / 2, -90, 90)
             + [(x1 - e, y1), (x0 + e, y1)] + _arc(x0 + e, cy, e, h / 2, 90, 270))
        c.create_oval(x1 - 2 * e, y0 + width / 2, x1, y1 - width / 2, outline=det, width=lw, tags=tags)
        ticks(x0 + e, x1 - 2.2 * e, 2.2 * s, y0 + width, y0 + h * 0.12)       # cooling ribs
        ticks(x0 + e, x1 - 2.2 * e, 2.2 * s, y1 - h * 0.12, y1 - width)
    elif kind == "canister":          # catalytic converter: a rounded can with heat-shield bands
        body(_stadium(x0, y0, x1, y1))
        for fx in (0.3, 0.7):
            line((x0 + w * fx, y0 + width), (x0 + w * fx, y0 + h * 0.18))
            line((x0 + w * fx, y1 - h * 0.18), (x0 + w * fx, y1 - width))
    elif kind in ("pill", "lamp"):
        body(_stadium(x0, y0, x1, y1) if kind == "pill" else _round_rect(x0, y0, x1, y1, min(w, h) * 0.35))
    elif kind == "throttle":           # throttle body: square housing, round bore, butterfly plate
        body(_round_rect(x0, y0, x1, y1, min(w, h) * 0.18))
        r = min(w, h) * 0.42
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=det, width=lw, tags=tags)
        line((cx - r * 0.8, cy + r * 0.45), (cx + r * 0.8, cy - r * 0.45))
    elif kind in ("circle", "pulley"):
        c.create_oval(x0 + (w - min(w, h)) / 2, y0 + (h - min(w, h)) / 2, x1 - (w - min(w, h)) / 2,
                      y1 - (h - min(w, h)) / 2, fill=fill, outline=outline, width=width, dash=dash, tags=tags)
        r = min(w, h) / 2
        if kind == "pulley":           # belt grooves
            for k in (0.9, 0.8):
                c.create_oval(cx - r * k, cy - r * k, cx + r * k, cy + r * k, outline=det, width=lw, tags=tags)
    elif kind == "gear":               # cam sprocket
        r = min(w, h) / 2
        pts = []
        for i in range(48):
            rr = r if (i // 2) % 2 == 0 else r * 0.86
            a = 2 * math.pi * i / 48
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        body(pts)
    elif kind == "rack":               # ring gear seen edge-on: teeth along both sides of a shaft
        t = h * 0.1
        body([(x0, y0 + t), (x1, y0 + t), (x1, y1 - t), (x0, y1 - t)])
        step = 1.3 * s
        x = x0 + step / 2
        while x + step / 2 < x1:
            c.create_rectangle(x, y0, x + step * 0.55, y0 + t, fill=det, outline="", tags=tags)
            c.create_rectangle(x, y1 - t, x + step * 0.55, y1, fill=det, outline="", tags=tags)
            x += step
    elif kind == "valveblock":         # brake actuator: aluminium block with a row of solenoid valves
        body(_round_rect(x0, y0, x1, y1, min(w, h) * 0.12))
        r = min(h * 0.12, 0.9 * s)
        for i in range(6):
            vx = x0 + w * (0.08 + 0.84 * i / 5)
            c.create_oval(vx - r, y0 + h * 0.12, vx + r, y0 + h * 0.12 + 2 * r, outline=det, width=lw, tags=tags)
    elif kind == "airbox":             # air cleaner box with its intake snorkel
        body(_stadium(x0, y0 + h * 0.32, x0 + w * 0.16, y1 - h * 0.32))
        body(_round_rect(x0 + w * 0.1, y0, x1, y1, min(w, h) * 0.2))
    elif kind == "engine":             # cam cover: rounded, with the 4 ignition coils in a row
        body(_round_rect(x0, y0, x1, y1, min(w, h) * 0.14))
        r = min(w / 14, h * 0.07)
        for i in range(4):
            px = x0 + w * (0.2 + 0.2 * i)
            c.create_oval(px - r, y0 + h * 0.16 - r, px + r, y0 + h * 0.16 + r, outline=det, width=lw, tags=tags)
        line((x0 + w * 0.1, y1 - h * 0.14), (x1 - w * 0.1, y1 - h * 0.14))
    elif kind == "manifold":           # plenum along the top, 4 runners scalloped along the bottom
        d = h * 0.1
        pts = [(x0, y0), (x1, y0), (x1, y1 - d)]
        for i in range(4, 0, -1):
            pts += _arc(x0 + w * (i - 0.5) / 4, y1 - d, w / 8 * 0.9, d, 0, 180, 6)
        body(pts + [(x0, y1 - d)])
    elif kind == "tank":               # rounded tank with a filler cap
        body(_round_rect(x0, y0, x1, y1, min(w, h) * 0.38))
        r = min(w, h) * 0.08
        c.create_oval(x1 - w * 0.1 - r, y0 + h * 0.2 - r, x1 - w * 0.1 + r, y0 + h * 0.2 + r, outline=det, width=lw,
                      tags=tags)
    elif kind in ("radiator", "core"):  # a finned core; a radiator also has a tank at each end
        body(_round_rect(x0, y0, x1, y1, min(w, h) * 0.08))
        a, b = (x0 + w * 0.07, x1 - w * 0.07) if kind == "radiator" else (x0 + 2 * width, x1 - 2 * width)
        if kind == "radiator":
            line((a, y0), (a, y1))
            line((b, y0), (b, y1))
        band = w * (0.13 if kind == "radiator" else 0.055)   # fins at both ends, clear of the text in the middle
        ticks(a + s * 0.5, a + band, 0.8 * s, y0 + width, y1 - width)
        ticks(b - band, b - s * 0.5, 0.8 * s, y0 + width, y1 - width)
    elif kind == "vent":               # air grille
        body(_round_rect(x0, y0, x1, y1, min(w, h) * 0.2))
        for fy in (0.25, 0.42, 0.58, 0.75):   # louvres at the outer end, clear of the text
            line((x0 + w * 0.02, y0 + h * fy), (x0 + w * 0.06, y0 + h * fy))
    elif kind == "fan":                # blower housing with the fan wheel
        body(_round_rect(x0, y0, x1, y1, min(w, h) * 0.3))
        r = min(w, h) * 0.44
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=det, width=lw, tags=tags)
    elif kind == "pack":               # a stretch of the battery: thin modules standing side by side
        body(_round_rect(x0, y0, x1, y1, min(w, h) * 0.05))
        ticks(x0 + 1.3 * s, x1 - 1.3 * s, 1.7 * s, y0 + width, y0 + h * 0.1)
        ticks(x0 + 1.3 * s, x1 - 1.3 * s, 1.7 * s, y1 - h * 0.1, y1 - width)
    elif kind in ("module", "battery"):  # a battery with its two terminals on top (+ red, - dark)
        t = _terminal_h(h / s) * s
        body(_round_rect(x0, y0 + t, x1, y1, min(w, h) * 0.08))
        tw = min(w * 0.18, 2.4 * s)
        for fx, colour in ((0.25, "#c0392b"), (0.75, "#15171b")):
            px = x0 + w * fx
            c.create_rectangle(px - tw / 2, y0, px + tw / 2, y0 + t + width, fill=colour, outline=det, tags=tags)
    elif kind == "tread":              # tire whose tread lines the app animates (Spinning view)
        body(_round_rect(x0, y0, x1, y1, w * 0.45))
    elif kind == "geartread":          # ring gear whose teeth the app animates (Spinning view)
        body(_round_rect(x0, y0, x1, y1, min(w, h) * 0.2))
    elif kind == "tire":
        body(_round_rect(x0, y0, x1, y1, w * 0.45))
        y = y0 + h * 0.08
        while y < y1 - h * 0.08:
            line((x0 + w * 0.2, y), (x1 - w * 0.2, y))
            y += 2 * s
    elif kind in ("taillight_l", "taillight_r"):  # tail lamp wrapping round the rear corner
        cut = min(w, h) * 0.6
        if kind == "taillight_l":
            body([(x0 + cut, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0 + cut)])
        else:
            body([(x0, y0), (x1 - cut, y0), (x1, y0 + cut), (x1, y1), (x0, y1)])
    elif kind == "gauge":              # instrument panel; the view draws the dial itself
        body(_round_rect(x0, y0, x1, y1, min(w, h) * 0.08))
    elif kind == "ecu":                # control unit: box with a connector along the bottom
        body(_round_rect(x0, y0, x1, y1 - h * 0.05, min(w, h) * 0.08))
        c.create_rectangle(x0 + w * 0.25, y1 - h * 0.08, x1 - w * 0.25, y1, fill=det, outline="", tags=tags)
    elif kind == "sump":               # oil pan: narrower at the bottom
        body([(x0, y0), (x1, y0), (x1 - w * 0.1, y1), (x0 + w * 0.1, y1)])
    elif kind == "strip4":             # a row of 4 (injectors / coils), one over each cylinder
        body(_round_rect(x0, y0, x1, y1, min(w, h) * 0.3))
        r = min(h * 0.28, 1.2 * s)
        for i in range(4):
            px = x0 + w * (i + 0.5) / 4
            c.create_oval(px - r, cy - r, px + r, cy + r, outline=det, width=lw, tags=tags)
    else:
        raise ValueError(f"unknown shape {kind!r}")
