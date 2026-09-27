"""Layout checker: finds overlapping boxes, text that doesn't fit its box, wires running through boxes,
labels on top of boxes and parts sticking out of the car body - in every view.

Run from the project folder:  python tools/check_layout.py [scale]
scale = pixels per drawing unit to test at (default 4.0, about a 1150 x 1000 window; the app's smallest
window is about 2.4). Uses made-up demo readings, so value text is realistic in length.
"""
import math
import os
import sys
import time
import tkinter as tk
import tkinter.font as tkfont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config as cfg  # noqa: E402
import shapes  # noqa: E402
from closeups import BatteryView, EngineView, TripView  # noqa: E402
from merged import EverythingView  # noqa: E402
from sensors import SENSORS, demo_electrical  # noqa: E402
from views import ElectricalView, PressureView, SpinView, TemperatureView  # noqa: E402

S = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
EPS = 0.05


def demo_values(t, phase, smooth):
    now = time.time()
    vals = {k: (v, now) for k, v in demo_electrical(t, smooth).items()}
    for s in SENSORS.values():
        if s.unit == "°C" and s.key not in vals:
            span = s.danger - s.cold
            wave = (math.sin(t / 6 + phase) + 1) / 2
            vals[s.key] = (round(s.cold - 0.1 * span + wave * 1.2 * span, 1), now)
    return vals


def overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return min(ax + aw, bx + bw) - max(ax, bx) > EPS and min(ay + ah, by + bh) - max(ay, by) > EPS


def seg_hits_rect(p, q, r):
    """Does the segment pass through the inside of the rectangle (not just touch its edge)?"""
    x, y, w, h = r
    x0, y0, x1, y1 = x + EPS, y + EPS, x + w - EPS, y + h - EPS
    (px, py), (qx, qy) = p, q
    for i in range(51):
        t = i / 50
        sx, sy = px + (qx - px) * t, py + (qy - py) * t
        if x0 < sx < x1 and y0 < sy < y1:
            return True
    return False


def inside_body(r):
    """Inside the car body (rounded rect x 4-96, y 1-248, corner radius 18)?"""
    x, y, w, h = r
    for cx, cy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
        if not (4 - EPS <= cx <= 96 + EPS and 1 - EPS <= cy <= 248 + EPS):
            return False
        kx = 22 if cx < 22 else 78 if cx > 78 else cx
        ky = 19 if cy < 19 else 230 if cy > 230 else cy
        if math.hypot(cx - kx, cy - ky) > 18 + 0.3:
            return False
    return True


def wrap_lines(font, text, width):
    """Rough copy of how Tk wraps text at a width: by words; returns (lines, widest single word)."""
    lines, widest = [], 0
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            widest = max(widest, font.measure(word))
            trial = word if not cur else cur + " " + word
            if cur and font.measure(trial) > width:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
    return lines, widest


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    root = tk.Tk()
    root.withdraw()
    fs = -max(10, int(S * cfg.FONT_SCALE))
    fs_small = -max(9, int(S * cfg.FONT_SCALE_SMALL))
    fs_tiny = -max(8, int(S * cfg.FONT_SCALE_TINY))
    big, tiny = tkfont.Font(family="Segoe UI", size=fs, weight="bold"), tkfont.Font(family="Segoe UI", size=fs_tiny, weight="bold")
    small = tkfont.Font(family="Segoe UI", size=fs_small)
    smooth = {}
    samples = [demo_values(1_000_000 + t * 0.5, p, smooth) for t in range(100) for p in (0, math.pi)]
    problems = 0

    for view in (TemperatureView(), ElectricalView(), SpinView(), PressureView(), EverythingView(), EngineView(), BatteryView(),
                 TripView()):
        car = getattr(view, "scene", "car") != "closeup"
        comps = list(view.components)
        found = []
        rects = {k: (x, y, w, h) for k, x, y, w, h in comps}
        for i, (ka, *ra) in enumerate(comps):
            for kb, *rb in comps[i + 1:]:
                if overlap(ra, rb):
                    found.append(f"boxes overlap: {ka} {ra} and {kb} {rb}")
        for k, r in rects.items():
            if r[2] < 6 or r[3] < 5:
                found.append(f"box too small: {k} {r}")
            if car and not k.startswith("wheel") and k not in ("fl", "fr", "rl", "rr") and not inside_body(r):
                found.append(f"sticks out of the car body: {k} {r}")
        # text fit, over many demo readings
        worst = {}
        for vals in samples:
            now = time.time()
            for k, x, y, w, h in comps:
                cell = view.cell(k, vals, now)
                name = view.label(k)
                text = f"{name.replace(chr(10), ' ')}   {cell.text}" if h < cfg.ONE_LINE_BOX else f"{name}\n{cell.text}"
                font = big if w >= cfg.NARROW_BOX else tiny
                kind = getattr(view, "shapes", {}).get(k, "box")
                tx, ty, tw, th = shapes.text_box(kind, x, y, w, h)
                width = max(20, tw * S - 6)
                lines, widest = wrap_lines(font, text.rstrip(), width)
                ls = font.metrics("linespace")
                need_h = len(lines) * ls
                bad = []
                if widest > width + 1:
                    bad.append(f"a word is {widest - width:.0f}px too wide")
                if need_h > th * S + 1:
                    bad.append(f"{len(lines)} lines need {need_h}px, room for {th * S:.0f}px")
                else:   # round shapes get narrower towards the top and bottom: check each line where it sits
                    top = (ty + th / 2) * S - need_h / 2
                    for i, ln in enumerate(lines):
                        ya, yb = (top + i * ls + ls * 0.2) / S, (top + (i + 1) * ls - ls * 0.2) / S
                        room = min(shapes.width_at(kind, x, y, w, h, ya), shapes.width_at(kind, x, y, w, h, yb)) * S - 4
                        if font.measure(ln) > room + 1:
                            bad.append(f"line {ln!r} is {font.measure(ln) - room:.0f}px wider than the {kind} there")
                if bad and (k not in worst or len(lines) > worst[k][1]):
                    worst[k] = (f"text doesn't fit in {k} ({w}x{h}): {'; '.join(bad)}  text={text!r}", len(lines))
        found += [v[0] for v in worst.values()]
        # labels drawn on the canvas: group labels (under their outline) and notes
        labels = []
        for label, gx, gy, gw, gh in view.groups:
            labels.append((f"group label '{label}'", (gx + 2 / S, gy + gh + 1 / S, small.measure(label) / S,
                                                      small.metrics("linespace") / S)))
        for text, nx, ny in view.notes:
            f = big if ny < 0 else small
            wdt, hgt = f.measure(text) / S, f.metrics("linespace") / S
            labels.append((f"note '{text}'", (nx - wdt / 2, ny if ny >= 0 else ny - hgt, wdt, hgt)))
        wires = view.wires(samples[0], time.time())
        for pts, _amps, label, side, *_ in wires:
            if isinstance(side, tuple) and label:
                labels.append((f"wire label '{label}'", (side[0], side[1] - small.metrics("linespace") / S / 2,
                                                         small.measure(label) / S, small.metrics("linespace") / S)))
        for name, lr in labels:
            for k, r in rects.items():
                if overlap(lr, r):
                    found.append(f"{name} sits on box {k}")
        for i, (na, la) in enumerate(labels):
            for nb, lb in labels[i + 1:]:
                if overlap(la, lb):
                    found.append(f"{na} overlaps {nb}")
        # wires through boxes
        for pts, _amps, label, *_ in wires:
            for p, q in zip(pts, pts[1:]):
                for k, r in rects.items():
                    if k not in getattr(view, "flow_over", ()) and seg_hits_rect(p, q, r):
                        found.append(f"wire {pts[0]}->{pts[-1]} ('{label}') runs through box {k}")
                for name, lr in labels:
                    if "wire label" not in name and seg_hits_rect(p, q, lr):
                        found.append(f"wire {pts[0]}->{pts[-1]} runs through {name}")
        print(f"== {view.name}: {'OK' if not found else f'{len(found)} problem(s)'}")
        for f in sorted(set(found)):
            print("   ", f)
        problems += len(set(found))
    print(f"\nscale {S} px/unit: {problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
