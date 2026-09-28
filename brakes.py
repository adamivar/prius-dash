"""Brakes & grip view: the brake system and the car's grip, seen from above.

Wheels: fill = how fast that wheel is speeding up / slowing down (wheelspin or lock-up stands out), coloured ring =
a safety system working that wheel (red ABS, orange stability control, yellow traction control, cyan rear brake
balancing), tread rolling with the wheel's speed. Brake actuator: brake pressure and regen blending. Centre: a
g-ball (braking / accelerating from the g-sensor; sideways worked out from speed x turning rate). Dashed brake
lines show pressure going to the wheels while you brake. Any wiring fault the brake computer reports turns the
part it belongs to flashing red.
"""
import math
import time
from collections import deque

import config as cfg
from config import (BRAKE_PRESSED_V, BRAKE_V_RANGE, DIM, G_FULL_MS2, G_TRAIL_S, IDEAL, NO_DATA, PRESS_RAMP, SPIN_FWD,
                    SPIN_REV, TEXT, TIP_FG, WARN, WHEEL_ACC_FULL, WHEEL_SLIP_WARN)
from sensors import BRAKES, SENSORS
from views import (LAYOUT, R, WHEELS_RECT, L, Cell, SpinView, fresh, panel_label, placed, ramp, reading_rows)

G = 9.80665
WHEELS = ("fl", "fr", "rl", "rr")
WHEEL_NAME = {"fl": "Front left", "fr": "Front right", "rl": "Rear left", "rr": "Rear right"}
LAMPS = {  # key: (box text, colour when on, what it means)
    "lamp_abs": ("ABS", cfg.RING_ABS, "ABS is working on at least one wheel (stops it locking)"),
    "lamp_trc": ("TRAC", cfg.RING_TRC, "Traction control is working (stops the front wheels spinning)"),
    "lamp_vsc": ("VSC", cfg.RING_VSC, "Stability control is braking a wheel to keep the car pointing the right way"),
    "lamp_ba": ("BA", cfg.LAMP_AMBER, "Brake assist: adds pressure because you pressed the pedal fast (emergency stop)"),
    "lamp_pba": ("PBA", cfg.LAMP_AMBER, "Pre-crash brake assist (cars with radar cruise only)"),
    "lamp_regen": ("REGEN", cfg.LAMP_GREEN, "The motor's regenerative braking is blending with the friction brakes"),
}
GBALL = (35, 117, 36, 44)           # g-ball panel; the dial fills its top 80%
FLUID = (L, 59, 26, 13)             # brake master cylinder + fluid reservoir, driver-side firewall
ACTUATOR = LAYOUT["brake_actuator"]
LINE_STYLE = {"line": "#c89b3c", "arrow": "#ffd27a"}   # brake fluid


def _on(values, now, key):
    v = fresh(values, key, now)
    return None if v is None else v >= 0.5


class BrakesView:
    name = "Brakes"
    units = []
    groups = []
    notes = [("Brake warning lights", 50, 112)]

    def __init__(self):
        self.unit = ""
        places = [(k, f"wheel_{k}") for k in WHEELS] + [("steer", "steering_wheel"),
                                                         ("brake_l", "brake_light_l"), ("brake_r", "brake_light_r")]
        places += [(k, f"lamp{i}") for i, k in enumerate(LAMPS)]
        self.components, self.shapes = placed(places)
        self.components += [("brake_act", *ACTUATOR), ("fluid", *FLUID), ("gball", *GBALL)]
        self.shapes.update({k: "tread" for k in WHEELS}, brake_act="valveblock", fluid="pill", gball="gauge",
                           steer="circle")
        self.trail = deque()
        self.peak_g = 0.0
        self.peak_slip = 0.0

    def sensors(self):
        keys = [s.key for s in BRAKES] + [f"whl_{k}" for k in WHEELS] + ["spd_abs", "yaw", "steer", "steer2",
                                                                        "brake_lights", "regen_req", "regen_op"]
        return [SENSORS[k] for k in keys]

    # ---------- numbers ----------
    @staticmethod
    def g_now(values, now):
        """(forward g, sideways g, sideways is calculated?) - forward + = braking; sideways + = pushed right."""
        decel = fresh(values, "decel", now)
        v = fresh(values, "spd_abs", now)
        yaw = fresh(values, "yaw", now)
        lat = None if v is None or yaw is None else (v / 3.6) * math.radians(yaw) / G
        return (None if decel is None else decel / G), lat

    def wheel_ring(self, k, values, now):
        """Colour of the ring round a wheel, most serious system first."""
        if _on(values, now, f"abs_{k}"):
            return cfg.RING_ABS
        if _on(values, now, f"vsc_{k}"):
            return cfg.RING_VSC
        if k in ("fl", "fr") and (_on(values, now, "trc") or _on(values, now, "trc_brk")):
            return cfg.RING_TRC
        if k in ("rl", "rr") and _on(values, now, f"ebd_{k}"):
            return cfg.RING_EBD
        return None

    def label(self, key):
        if key in LAMPS:
            return LAMPS[key][0]
        return {"brake_act": "Brake actuator", "fluid": "Brake fluid", "gball": "G-force", "steer": "Steering",
                "brake_l": "", "brake_r": ""}.get(key, key.upper())

    def cell(self, key, values, now):
        g = lambda k: fresh(values, k, now)
        if key in WHEELS:
            a = g(f"wacc_{key}")
            if a is None:
                return Cell(NO_DATA, "--")
            self.peak_slip = max(self.peak_slip, abs(a))
            fill = ramp(SPIN_FWD if a >= 0 else SPIN_REV, abs(a) / WHEEL_ACC_FULL)
            return Cell(fill, f"{a:+.1f}".replace("-", "−"), "warn" if _on(values, now, f"open_{key}") else None,
                        ring=self.wheel_ring(key, values, now))
        if key in LAMPS:
            on = {"lamp_abs": any(_on(values, now, f"abs_{k}") for k in WHEELS),
                  "lamp_trc": _on(values, now, "trc") or _on(values, now, "trc_eng") or _on(values, now, "trc_brk"),
                  "lamp_vsc": any(_on(values, now, f"vsc_{k}") for k in WHEELS),
                  "lamp_ba": _on(values, now, "ba"), "lamp_pba": _on(values, now, "pba"),
                  "lamp_regen": _on(values, now, "regen_coop")}[key]
            if g("ba") is None:
                return Cell(NO_DATA, "", dashed=True)
            return Cell(LAMPS[key][1] if on else cfg.LAMP_OFF, "")
        if key in ("brake_l", "brake_r"):
            on = _on(values, now, "brake_lights")
            if on is None:
                return Cell(NO_DATA, "", dashed=True)
            return Cell(cfg.BRAKE_LIGHT_ON if on else cfg.BRAKE_LIGHT_OFF, "")
        if key == "brake_act":
            v = g("brake_v")
            if v is None:
                return Cell(NO_DATA, "--")
            lo, hi = BRAKE_V_RANGE
            frac = max(0.0, (v - lo) / (hi - lo))
            fault = any(_on(values, now, f"open_{k}") for k in ("mc", "stroke", "wc", "accum", "hvcomm"))
            text = f"{frac * 100:.0f}% pressure" + ("  ·  regen" if _on(values, now, "regen_coop") else "")
            return Cell(ramp(PRESS_RAMP, frac), text, "warn" if fault else None)
        if key == "fluid":
            low = _on(values, now, "fluid_low")
            if low is None:
                return Cell(NO_DATA, "--")
            return Cell(cfg.LAMP_RED if low else "#26313b", "LOW" if low else "OK", "warn" if low else "ideal")
        if key == "gball":
            fwd, lat = self.g_now(values, now)
            if fwd is None:
                return Cell(NO_DATA, "--")
            self.peak_g = max(self.peak_g, fwd)
            word = "braking" if fwd > 0.03 else ("accelerating" if fwd < -0.03 else "steady")
            fault = _on(values, now, "open_decel") or _on(values, now, "open_yaw")
            return Cell("#1d2530", f"{abs(fwd):.2f} g {word}", "warn" if fault else None)
        if key == "steer":
            a = SpinView.steer_angle(values, now)
            if a is None:
                return Cell(NO_DATA, "--")
            side = "straight" if abs(a) < cfg.STEER_STRAIGHT_DEG else ("left" if a > 0 else "right")
            return Cell(ramp(SPIN_FWD, abs(a) / cfg.STEER_MAX_DEG), f"{abs(a):.0f}° {side}",
                        "warn" if _on(values, now, "open_steer") else None)
        return Cell(NO_DATA, "--")

    def spinners(self, values, now):
        rpm, _, _ = SpinView.calc(values, now)
        out = [(k, rpm[k], None) for k in WHEELS if rpm[k] is not None]
        a = SpinView.steer_angle(values, now)
        if a is not None:
            out.append(("steer", 0, None, a))
        return out

    def wires(self, values, now):
        """Brake lines from the actuator to each wheel: dashed, with slow arrows while the brakes are applied."""
        v = fresh(values, "brake_v", now)
        pressed = v is not None and v > BRAKE_PRESSED_V
        x0, y0, w, h = ACTUATOR
        mid = y0 + h / 2
        ly, ry, fy, by = 9, 91, WHEELS_RECT["fl"][1] + WHEELS_RECT["fl"][3] / 2, WHEELS_RECT["rl"][1] + WHEELS_RECT["rl"][3] / 2
        lines = [[(x0, mid), (ly, mid), (ly, fy), (6, fy)], [(ly, mid), (ly, by), (6, by)],
                 [(x0 + w, mid), (ry, mid), (ry, fy), (94, fy)], [(ry, mid), (ry, by), (94, by)]]
        out = [(pts, None, "", "r", pressed, LINE_STYLE) for pts in lines]
        out[1] = (lines[1], None, "brake lines", (10.5, 150), pressed, LINE_STYLE)
        return out

    def decorations(self, values, now):
        """The g-ball dial: rings at 0.25 / 0.5 / 0.8 g, the trail of the last few seconds and the dot now."""
        x, y, w, h = GBALL
        cx, cy, r = x + w / 2, y + h * 0.4, min(w, h * 0.8) / 2 - 1.2
        out = [dict(kind="circle", x=cx, y=cy, r=r * k, outline="#3a4452", width=1) for k in (0.3125, 0.625, 1.0)]
        out += [dict(kind="line", pts=[(cx - r, cy), (cx + r, cy)], fill="#3a4452"),
                dict(kind="line", pts=[(cx, cy - r), (cx, cy + r)], fill="#3a4452"),
                dict(kind="text", x=cx, y=cy - r + 1, text="brake", anchor="n", fill=DIM),
                dict(kind="text", x=cx, y=cy + r - 1, text="accel", anchor="s", fill=DIM)]
        fwd, lat = self.g_now(values, now)
        if fwd is None:
            return out
        full = G_FULL_MS2 / G

        def spot(f, s):
            px, py = (s or 0.0) / full, -f / full
            k = math.hypot(px, py)
            if k > 1:
                px, py = px / k, py / k
            return cx + px * r, cy + py * r
        t = time.monotonic()
        if not self.trail or t - self.trail[-1][0] > 0.2:
            self.trail.append((t, fwd, lat))
        while self.trail and t - self.trail[0][0] > G_TRAIL_S:
            self.trail.popleft()
        pts = [spot(f, s) for _, f, s in self.trail]
        if len(pts) > 1:
            out.append(dict(kind="line", pts=pts, fill="#5a7fa8", width=2))
        dx, dy = spot(fwd, lat)
        colour = cfg.RING_ABS if abs(fwd) > 0.6 else (cfg.LAMP_AMBER if abs(fwd) > 0.3 else IDEAL)
        out.append(dict(kind="circle", x=dx, y=dy, r=2.0, fill=colour, outline="#000000", width=1))
        return out

    # ---------- hover ----------
    def tooltip(self, key, values, now):
        g = lambda k: fresh(values, k, now)
        onoff = lambda k: "--" if _on(values, now, k) is None else ("ON" if _on(values, now, k) else "off")
        fmt = lambda v, u, dec=1: "--" if v is None else f"{v:.{dec}f} {u}".replace("-", "−")
        tested = ("Brake computer 7B0 - answered in your car's test (2026-09-26); the working flags only turn on "
                  "when a system steps in, so they haven't been seen ON yet", DIM, 8, False)
        if key in WHEELS:
            name = WHEEL_NAME[key]
            a, kmh = g(f"wacc_{key}"), g(f"whl_{key}")
            lines = [(f"Wheel acceleration: {fmt(a, 'm/s²')} ({fmt(None if a is None else a / G, 'g', 2)})",
                      TIP_FG, 11, True),
                     (f"Wheel speed: {fmt(kmh, 'km/h')}", TIP_FG, 10, False)]
            if a is not None and abs(a) >= WHEEL_SLIP_WARN:
                lines.append(("Changing speed much faster than a car can - wheelspin or lock-up", cfg.TIP_AMBER, 10, True))
            lines += [(f"ABS on this wheel: {onoff(f'abs_{key}')}     Stability control: {onoff(f'vsc_{key}')}",
                       TIP_FG, 10, False)]
            if key in ("fl", "fr"):
                lines.append((f"Traction control: {onoff('trc')} (cutting power {onoff('trc_eng')}, braking "
                              f"{onoff('trc_brk')})", TIP_FG, 10, False))
            else:
                lines.append((f"Rear brake balancing (EBD): {onoff(f'ebd_{key}')}", TIP_FG, 10, False))
            lines += [(f"Wheel-speed sensor wiring: {'FAULT' if _on(values, now, f'open_{key}') else 'OK'}",
                       cfg.TIP_RED if _on(values, now, f"open_{key}") else TIP_FG, 10, False),
                      ("Fill: orange = speeding up, purple = slowing down; stronger = faster change. Ring: red ABS, "
                       "orange stability control, yellow traction control, cyan EBD.", TIP_FG, 10, False),
                      ("The sensor steps in 1.57 m/s² (about 0.16 g), so small changes read as 0.", DIM, 8, False),
                      tested]
            return f"{name} wheel", lines
        if key in LAMPS:
            text, _, info = LAMPS[key]
            return text, [(info, TIP_FG, 10, False), tested]
        if key in ("brake_l", "brake_r"):
            return "Brake lights", [(f"Right now: {onoff('brake_lights')}", TIP_FG, 11, True),
                                    ("From the brake pedal switch (7B0 211F).", DIM, 8, False)]
        if key == "brake_act":
            v = g("brake_v")
            faults = [SENSORS[f"open_{k}"].name for k in ("mc", "stroke", "wc", "accum", "hvcomm")
                      if _on(values, now, f"open_{k}")]
            lines = [(f"Brake pressure sensor: {fmt(v, 'V', 2)}", TIP_FG, 11, True),
                     (f"Regen blending with the brakes: {onoff('regen_coop')}", TIP_FG, 10, False),
                     (f"Regen asked for: {fmt(g('regen_req'), 'Nm', 0)}     delivered: {fmt(g('regen_op'), 'Nm', 0)}",
                      TIP_FG, 10, False),
                     (f"Brake assist: {onoff('ba')}     Pre-crash brake assist: {onoff('pba')}", TIP_FG, 10, False),
                     ("Wiring: " + (", ".join(faults) if faults else "all sensors OK"),
                      cfg.TIP_RED if faults else cfg.TIP_GREEN, 10, bool(faults)),
                     (f"Pressure % = sensor volts between {BRAKE_V_RANGE[0]} V (released) and {BRAKE_V_RANGE[1]} V "
                      "(the hardest stop in your car's test). The volts-to-bar conversion isn't known.", TIP_FG, 10, False),
                     ("The electronically controlled brake unit: it meters brake fluid to each wheel and blends "
                      "friction braking with the motor's regen braking.", TIP_FG, 10, False), tested]
            return "Brake actuator", lines
        if key == "fluid":
            return "Brake fluid", [(f"Reservoir low-level warning: {onoff('fluid_low')}", TIP_FG, 11, True),
                                   ("Float switch in the brake fluid reservoir on the master cylinder.", TIP_FG, 10, False),
                                   ("7B0 211D - answered in your car's test", DIM, 8, False)]
        if key == "gball":
            fwd, lat = self.g_now(values, now)
            return "G-force", [
                (f"Forward / back: {fmt(None if fwd is None else abs(fwd), 'g', 2)} "
                 f"{'' if fwd is None else ('braking' if fwd > 0 else 'accelerating')}", TIP_FG, 11, True),
                (f"Sideways (calculated from speed x turning rate): {fmt(None if lat is None else abs(lat), 'g', 2)}",
                 TIP_FG, 10, False),
                (f"Second g-sensor: {fmt(None if g('decel2') is None else g('decel2') / G, 'g', 2)}", TIP_FG, 10, False),
                (f"Hardest braking since the app started: {self.peak_g:.2f} g", TIP_FG, 10, False),
                ("The dot moves the way you're pushed: forward when braking, back when accelerating, sideways in "
                 f"turns. Rings at 0.25 / 0.5 / 0.8 g; the line is the last {G_TRAIL_S:.0f} s. Around 0.3 g is "
                 "firm braking, 0.8 g+ an emergency stop.", TIP_FG, 10, False),
                ("Forward: the brake computer's g-sensor (7B0 2105). Its direction (+ = braking) and the sideways "
                 "direction are assumptions until checked in the car.", DIM, 8, False)]
        if key == "steer":
            return SpinView().tooltip("steer", values, now)
        return key, []

    # ---------- side panel ----------
    PANEL_ROWS = [("g", "Braking (+) / accelerating (−)"), ("lat", "Sideways (calculated)"),
                  ("pressure", "Brake pressure sensor"), ("regen", "Regen blending"), ("abs", "ABS"),
                  ("trc", "Traction control"), ("vsc", "Stability control"), ("ba", "Brake assist"),
                  ("ebd", "Rear brake balancing (EBD)"), ("wiring", "Brake wiring checks"), ("fluid", "Brake fluid"),
                  ("peak", "Hardest braking (this session)"), ("slip", "Biggest wheel speed change")]

    def build_panel(self, parent, app):
        panel_label(parent, "Wheel fill = how fast that wheel is speeding up (orange)\nor slowing down (purple)",
                    TEXT, 9, (12, 0))
        panel_label(parent, "Ring round a wheel = a system working it:", TEXT, 9, (6, 0))
        for text, colour in (("ABS", cfg.RING_ABS), ("Stability control (VSC)", cfg.RING_VSC),
                             ("Traction control (TRAC)", cfg.RING_TRC), ("Rear brake balancing (EBD)", cfg.RING_EBD)):
            panel_label(parent, f"   {text}", colour, 9)
        panel_label(parent, "Brake lines show arrows while you brake", TEXT, 9, (6, 0))
        panel_label(parent, "Flashing red = a wiring fault on that part", WARN, 9)
        panel_label(parent, "Tap / hover a part for all its readings", DIM, 9)
        self.rows = reading_rows(parent, self.PANEL_ROWS, "Readings")
        panel_label(parent, "All requests answered in your car's test (2026-09-26).\nThe ABS / traction / stability "
                            "flags haven't been\nseen ON yet (nothing triggered them).", DIM, 9, (10, 0))

    def update_panel(self, values, now):
        g = lambda k: fresh(values, k, now)
        fwd, lat = self.g_now(values, now)
        onoff = lambda flag: "--" if flag is None else ("ON" if flag else "off")
        anyof = lambda keys: None if all(_on(values, now, k) is None for k in keys) else any(_on(values, now, k) for k in keys)
        faults = [k for k in (s.key for s in BRAKES if s.key.startswith("open_")) if _on(values, now, k)]
        v = g("brake_v")
        vals = {"g": None if fwd is None else f"{fwd:+.2f} g".replace("-", "−"),
                "lat": None if lat is None else f"{abs(lat):.2f} g",
                "pressure": None if v is None else f"{v:.2f} V",
                "regen": onoff(_on(values, now, "regen_coop")),
                "abs": onoff(anyof([f"abs_{k}" for k in WHEELS])),
                "trc": onoff(anyof(["trc", "trc_eng", "trc_brk"])),
                "vsc": onoff(anyof([f"vsc_{k}" for k in WHEELS])),
                "ba": onoff(anyof(["ba", "pba"])),
                "ebd": onoff(anyof(["ebd_rl", "ebd_rr"])),
                "wiring": None if g("open_fr") is None else (f"{len(faults)} FAULT(S)" if faults else "all OK"),
                "fluid": None if g("fluid_low") is None else ("LOW" if g("fluid_low") >= 0.5 else "OK"),
                "peak": f"{self.peak_g:.2f} g", "slip": f"{self.peak_slip:.1f} m/s²"}
        for k, lbl in self.rows.items():
            t = vals[k]
            colour = WARN if t in ("ON",) and k in ("abs", "trc", "vsc", "ba") or (t or "").endswith("FAULT(S)") \
                or t == "LOW" else (DIM if t is None else TEXT)
            lbl.config(text=t or "--", fg=colour)
