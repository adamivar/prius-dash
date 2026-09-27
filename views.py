"""Dashboard views. Each view decides what the car boxes show, their colour and border,
the hover card, the side panel and (electrical view) the animated wires."""
import math
import tkinter as tk

import calc
from dataclasses import dataclass

from sensors import (ELEC, FINAL_DRIVE, KMH_TO_WHEEL_RPM, MG2_REDUCTION, ONOFF, PRESS, RING_TEETH, ROT, SENSORS,
                     SOC, STEER, ELEC_EXTRA, SUN_TEETH, TEMPS, TIRE_CIRCUMFERENCE_M, TORQUE)

import config as cfg
from config import (AMP_LIMITS, AUX_HIGH, AUX_IDEAL, AUX_LOW, BG, BLK_IDEAL_DEV, BLK_WARN_DEV, BODY, CHARGE, DIM, HEAT,
                    IDEAL, NO_DATA, PRESS_LIMITS, PRESS_RAMP, SLIP_IDEAL, SLIP_WARN, SPIN_FWD, SPIN_REV, SPIN_REV_TEXT,
                    STALE_AFTER_S, TEXT, TIP_FG, WARN, WARN_AT)



def ramp(stops, fraction):
    f = max(0.0, min(1.0, fraction))
    for (f0, c0), (f1, c1) in zip(stops, stops[1:]):
        if f <= f1:
            t = (f - f0) / (f1 - f0)
            return "#%02x%02x%02x" % tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))
    return "#%02x%02x%02x" % stops[-1][1]


def fresh(values, key, now):
    """Latest value for a key, or None if missing / older than STALE_AFTER_S."""
    r = values.get(key)
    return None if r is None or now - r[1] > STALE_AFTER_S else r[0]


@dataclass
class Cell:
    fill: str
    text: str
    state: str = None      # None, "ideal" (green border) or "warn" (flashing red border)
    dashed: bool = False   # dashed outline = this value isn't measured


# ---------- one map of the car, shared by every view ----------
# 100 x 250 units (about 18 mm per unit), front at the top, driver (left-hand drive) on the left.
# Where things are on a real 2010-2015 Prius (Toyota's Gen 3 emergency response guide unless marked):
#  - engine on the passenger side, transaxle (MG1 + MG2 + planetary gear) on the driver side, the inverter
#    assembly (booster, both inverters, DC-DC converter) sitting on top of the transaxle
#  - engine intake manifold at the front, exhaust manifold + catalytic converter at the back by the firewall
#    (Toyota repair manual: the EGR cooler bolts to the exhaust manifold's catalyst); air box on top, centre of the bay
#  - brake actuator deep under the inverter / cowl by the driver-side fender (repair steps: remove cowl + inverter)
#  - Gen 3 meter (warning lights) in the centre of the dashboard, next to the windshield
#  - fuel tank under the centre of the car (under the rear seat); HV battery mounted to the cross member in the
#    cargo area behind the rear seat, its cooling air coming in by the passenger-side rear seat
#  - 12 V battery on the passenger side of the cargo area
# Drawing compromises (so every box stays readable): the inverter assembly is drawn in front of the transaxle
# instead of on top of it, the engine bay is ~25% longer than the real one, the battery blocks are shown as two
# rows of 7 (the real pack is one row of 28 modules across the car), and the ring gear is drawn as a strip under
# the two motors although it sits between them on the same shaft.
# Left channel x 4-14 is kept free for wires (12 V, HV -, HV +).
L, M, R = 14, 35, 56            # driver-side column (transaxle + inverter): left edge, middle split, right edge
HALF = 20
E0, EW = 58, 34                 # passenger-side column (engine): left edge, width
FRONT_AXLE, REAR_AXLE = 58, 202  # real wheelbase 2.70 m; front overhang stretched with the engine bay
WHEEL_H = 32                     # 195/65R15 tire is ~0.63 m tall
BATT_X0, BATT_X1, BATT_Y0, BATT_ROW2 = 14, 88, 187, 20
BLK_W = (BATT_X1 - BATT_X0 - 6 * 2) / 7    # 14 blocks, 2 rows of 7, 2-unit gaps
TB_W = (BATT_X1 - BATT_X0 - 2 * 1.5) / 3   # 3 battery temperature sensors across the same pack
WHEELS_RECT = {"fl": (-1, FRONT_AXLE - WHEEL_H / 2, 7, WHEEL_H), "fr": (94, FRONT_AXLE - WHEEL_H / 2, 7, WHEEL_H),
               "rl": (-1, REAR_AXLE - WHEEL_H / 2, 7, WHEEL_H), "rr": (94, REAR_AXLE - WHEEL_H / 2, 7, WHEEL_H)}
LAYOUT = {
    # front, behind the bumper
    "dcdc": (L, 3.5, 17, 13),                # DC-DC converter: in the bottom front of the inverter assembly
    "outside_air": (L, 3.5, HALF, 13),         # outside air sensor behind the bumper (exact spot unconfirmed)
    "coolant_pump": (L + 18, 3.5, R - L - 18, 13),        # inverter coolant pump, front driver side (unconfirmed)
    "inv_coolant": (M, 3.5, HALF, 13),         # inverter coolant loop (pump / reservoir end)
    "ac_compressor": (60, 3.5, 26, 13),        # electric A/C compressor, low on the front of the engine
    # inverter assembly (on top of the transaxle), each inverter above the motor it drives
    "booster": (L, 18.5, R - L, 13),
    "booster_upper": (L, 18.5, HALF, 13),
    "booster_lower": (M, 18.5, HALF, 13),
    "drive_inverter": (L, 32.5, HALF, 13),
    "gen_inverter": (M, 32.5, HALF, 13),
    # transaxle across the car on the front axle line: MG2 at the outer end, MG1 next to the engine
    "mg2": (L, 51.5, HALF, 21.5),
    "mg1": (M, 51.5, HALF, 21.5),
    "ring_gear": (L, 74, R - L, 10),
    "brake_actuator": (L, 74, R - L, 10.5),
    # engine: air box on top at the front, block, catalytic converter at the back against the firewall
    "intake_air": (E0, 17.5, EW, 9),
    "engine": (E0, 27.5, EW, 42.5),
    "catalyst": (E0, 71, EW, 13),
    "intake_manifold": (E0, 27.5, EW, 14),  # Pressure view: front of the engine
    "oil_pressure": (E0, 56, EW, 13),
    # the wheels themselves (same rectangles the app draws as tires)
    **{f"wheel_{k}": r for k, r in WHEELS_RECT.items()},
    # dashboard: driver side, centre meter with the warning lights (2 rows of 3), air-con unit in the middle
    "steering_wheel": (15, 99, 18, 18),
    "cabin_air": (L, 99, 22, 13),           # cabin temperature sensor in the dash near the steering column
    "evaporator": (39, 99, 22, 13),         # air-con evaporator inside the heater / A/C unit behind the dash
    **{f"lamp{i}": (36.25 + (i % 3) * 9.5, 99 + (i // 3) * 6.5, 8.5, 5.5) for i in range(6)},
    # rear seat: fuel tank under it, battery cooling-air intake by the passenger-side seat
    "fuel_tank": (16, 166, 44, 11),
    "batt_intake": (64, 168, 26, 13),
    "batt_tb1": (BATT_X0, BATT_Y0, TB_W, 16 + BATT_ROW2),
    "batt_tb2": (BATT_X0 + TB_W + 1.5, BATT_Y0, TB_W, 16 + BATT_ROW2),
    "batt_tb3": (BATT_X0 + 2 * (TB_W + 1.5), BATT_Y0, TB_W, 16 + BATT_ROW2),
    # cargo area: 12 V battery passenger side, brake lights in the rear corners
    "aux_batt": (52, 234, 22, 12),
    "brake_light_l": (14, 240, 10, 5.5), "brake_light_r": (76, 240, 10, 5.5),
}
LAYOUT["batt_fan"] = LAYOUT["batt_intake"]   # the fan sits in the battery's air-intake duct

# What each place looks like from above (see shapes.py)
PLACE_SHAPE = {
    "dcdc": "finned", "outside_air": "rounded", "coolant_pump": "rounded", "inv_coolant": "tank", "ac_compressor": "drum",
    "booster": "finned", "booster_upper": "finned", "booster_lower": "finned", "drive_inverter": "finned",
    "gen_inverter": "finned", "mg2": "drum", "mg1": "drum", "ring_gear": "rack", "brake_actuator": "valveblock",
    "intake_air": "airbox", "engine": "engine", "catalyst": "canister", "intake_manifold": "manifold",
    "oil_pressure": "pill", **{f"wheel_{k}": "tire" for k in WHEELS_RECT}, "steering_wheel": "circle",
    "cabin_air": "pill", "evaporator": "core", **{f"lamp{i}": "lamp" for i in range(6)}, "fuel_tank": "tank",
    "batt_intake": "vent", "batt_fan": "fan", "batt_tb1": "pack", "batt_tb2": "pack", "batt_tb3": "pack",
    "aux_batt": "battery", "brake_light_l": "taillight_l", "brake_light_r": "taillight_r",
}


def placed(places):
    """(key, place) pairs -> the view's components [(key, x, y, w, h)] and their shapes {key: shape}."""
    return [(key, *LAYOUT[place]) for key, place in places], {key: PLACE_SHAPE[place] for key, place in places}


def block_rect(i):
    """Block i (0-13), snaking: top row blocks 1-7 left to right, bottom row blocks 8-14 right to left."""
    col = i if i < 7 else 13 - i
    return BATT_X0 + col * (BLK_W + 2), BATT_Y0 if i < 7 else BATT_Y0 + BATT_ROW2, BLK_W, 16


def block_links():
    """Series wires 1->2->...->14 (drawn direction)."""
    out = []
    for i in range(13):
        x, y, w_, h = block_rect(i)
        if i == 6:  # block 7 (top right) down to block 8 (bottom right)
            out.append([(x + w_, y + h / 2), (x + w_ + 1, y + h / 2), (x + w_ + 1, y + BATT_ROW2 + h / 2),
                        (x + w_, y + BATT_ROW2 + h / 2)])
        elif i < 6:
            out.append([(x + w_, y + h / 2), (x + w_ + 2, y + h / 2)])
        else:       # bottom row runs right to left
            out.append([(x, y + h / 2), (x - 2, y + h / 2)])
    return out


# ---------- shared side-panel pieces ----------
def panel_label(parent, text, fg=DIM, size=10, pady=(0, 0)):
    lbl = tk.Label(parent, text=text, bg=BG, fg=fg, font=("Segoe UI", size), justify="left")
    lbl.pack(anchor="w", pady=pady)
    return lbl


def unit_buttons(parent, view, app):
    panel_label(parent, "Units", pady=(12, 0))
    row = tk.Frame(parent, bg=BG)
    row.pack(anchor="w")
    var = tk.StringVar(value=view.unit)

    def pick():
        view.unit = var.get()
        app.refresh()
    for code, text in view.units:
        tk.Radiobutton(row, text=text, value=code, variable=var, command=pick, bg=BG, fg=TEXT,
                       selectcolor=BODY, activebackground=BG, activeforeground=TEXT,
                       font=("Segoe UI", 11), indicatoron=False, padx=8, pady=4).pack(side="left", padx=(0, 4))
    view._unit_var = var


def legend(parent, app, stops, left, right, title):
    panel_label(parent, title, pady=(16, 2))
    lw, lh = int(cfg.LEGEND_WIDTH * app.ui), int(16 * app.ui)
    c = tk.Canvas(parent, height=int(36 * app.ui), width=lw, bg=BG, highlightthickness=0)
    c.pack(anchor="w")
    for i in range(lw):
        c.create_line(i, 0, i, lh, fill=ramp(stops, i / (lw - 1)))
    c.create_text(0, lh + 2, text=left, anchor="nw", fill=DIM, font=("Segoe UI", 9))
    c.create_text(lw - 1, lh + 2, text=right, anchor="ne", fill=DIM, font=("Segoe UI", 9))
    panel_label(parent, "Green border = in ideal range", IDEAL, 9, (4, 0))
    panel_label(parent, "Flashing red border = getting close to danger", WARN, 9)
    panel_label(parent, "Hover over a part for details", DIM, 9)


def reading_rows(parent, rows, title):
    panel_label(parent, title, pady=(16, 2))
    out = {}
    for key, name in rows:
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x")
        tk.Label(row, text=name, bg=BG, fg=TEXT, font=("Segoe UI", 10), anchor="w").pack(side="left")
        val = tk.Label(row, text="--", bg=BG, fg=TEXT, font=("Consolas", 10), anchor="e", width=13)
        val.pack(side="right", padx=(12, 0))
        out[key] = val
    return out


# ======================================================================
# Temperature view
# ======================================================================
class TemperatureView:
    name = "Temperature"
    notes = []
    units = [("C", "Celsius (°C)"), ("F", "Fahrenheit (°F)")]

    groups = [  # dashed outlines: (label, x, y, w, h)
        ("Inverter assembly", L - 1, 17.5, R - L + 2, 29),
        ("Transaxle", L - 1, 50.5, R - L + 2, 23.5),
        ("Hybrid battery (behind rear seat)", BATT_X0 - 1.5, BATT_Y0 - 1.5, BATT_X1 - BATT_X0 + 3, 16 + BATT_ROW2 + 3),
    ]
    places = [  # (sensor key, place on the car)
        ("ambient", "outside_air"), ("inv_coolant", "inv_coolant"),
        ("inv_mg1", "gen_inverter"), ("inv_mg2", "drive_inverter"),
        ("boost_upper", "booster_upper"), ("boost_lower", "booster_lower"),
        ("mg1", "mg1"), ("mg2", "mg2"),
        ("intake_air", "intake_air"), ("engine", "engine"), ("catalyst", "catalyst"),
        ("cabin", "cabin_air"), ("evap", "evaporator"), ("batt_intake", "batt_intake"),
        ("batt_tb1", "batt_tb1"), ("batt_tb2", "batt_tb2"), ("batt_tb3", "batt_tb3"),
        ("aux_batt", "aux_batt"),
    ]
    components, shapes = placed(places)

    def __init__(self):
        self.unit = "C"

    def sensors(self):
        return TEMPS

    def label(self, key):
        return SENSORS[key].label

    def conv(self, c):
        return c * 9 / 5 + 32 if self.unit == "F" else c

    def fmt(self, c):
        return f"{self.conv(c):.0f}°{self.unit}"

    @staticmethod
    def state(s, v):
        if (v - s.cold) / (s.danger - s.cold) >= WARN_AT:
            return "warn"
        lo, hi = s.ideal
        return "ideal" if lo <= v <= hi else None

    def cell(self, key, values, now):
        s = SENSORS[key]
        r = values.get(key)
        if r is None:
            return Cell(NO_DATA, "--")
        if now - r[1] > STALE_AFTER_S:
            return Cell(NO_DATA, f"{self.fmt(r[0])} (old)")
        v = r[0]
        return Cell(ramp(HEAT, (v - s.cold) / (s.danger - s.cold)), self.fmt(v), self.state(s, v))

    def wires(self, values, now):
        return []

    def tooltip(self, key, values, now):
        s = SENSORS[key]
        lo, hi = s.ideal
        lines = []
        r = values.get(key)
        if r is None:
            lines.append(("No reading yet", DIM, 11, True))
        else:
            v, stamp = r
            age = now - stamp
            lines.append((f"Now: {self.fmt(v)}" + (f"  (last seen {age:.0f} s ago)" if age > STALE_AFTER_S else ""),
                          TIP_FG, 11, True))
            if v >= s.danger:
                lines.append(("DANGER - hotter than it should ever get", cfg.TIP_RED, 10, True))
            elif self.state(s, v) == "warn":
                lines.append(("Getting close to danger", cfg.TIP_RED, 10, True))
            elif v > hi:
                lines.append(("Warm - above ideal, still below danger", cfg.TIP_AMBER, 10, True))
            elif v >= lo:
                lines.append(("Ideal - right where it should be", cfg.TIP_GREEN, 10, True))
            else:
                lines.append(("Cool - below its normal working range (normal soon after starting)",
                              cfg.TIP_BLUE, 10, True))
        for label, _, _, _, *unit in s.extras:
            extra = values.get(f"{key}|{label}")
            shown = "--" if not extra else (f"{extra[0]:.0f}{unit[0]}" if unit else self.fmt(extra[0]))
            lines.append((f"{label}: {shown}", TIP_FG, 10, True))
        lines.append((f"Ideal: {self.fmt(lo)} to {self.fmt(hi)}     Danger: {self.fmt(s.danger)} and up",
                      TIP_FG, 10, False))
        lines.append((s.info, TIP_FG, 10, False))
        ecu = {"7E2": "hybrid computer", "7E0": "engine computer", "7C4": "climate computer"}.get(s.header, "")
        lines.append((f"{s.tech}  ·  request {s.pid} to {s.header} ({ecu})  ·  "
                      + ("tested in your car" if s.tested else "NOT yet tested in your car"), DIM, 8, False))
        lines.append(("Limits and description: estimates, not Toyota specs (unconfirmed)", DIM, 8, False))
        return s.name, lines

    def build_panel(self, parent, app):
        unit_buttons(parent, self, app)
        legend(parent, app, HEAT, "cool", "danger", "Colour = how close to danger")
        self.rows = reading_rows(parent, [(s.key, s.name + ("" if s.tested else " *")) for s in TEMPS],
                                 "Readings  (now / danger limit)")
        panel_label(parent, "All readings answered in your car's full test (2026-09-26)\nLimits are estimates (unconfirmed)", DIM, 9, (10, 0))

    def update_panel(self, values, now):
        for s in TEMPS:
            r = values.get(s.key)
            danger = f"{self.conv(s.danger):.0f}"
            if r is None:
                self.rows[s.key].config(text=f"-- / {danger}", fg=DIM)
                continue
            v, stamp = r
            colour = {"warn": WARN, "ideal": IDEAL}.get(self.state(s, v), TEXT)
            self.rows[s.key].config(text=f"{self.conv(v):5.0f} / {danger}",
                                    fg=DIM if now - stamp > STALE_AFTER_S else colour)


# ======================================================================
# Electrical view
# ======================================================================
# Current limits (AMP_LIMITS) and 12 V battery ranges (AUX_*) are in config.py.

ELEC_INFO = {
    "brake_act": ("Brake actuator",
                  "The electronically controlled brake unit. Its solenoid valves meter brake fluid to the wheels "
                  "and blend friction braking with regen. One of the few 12 V parts with a real current reading."),
    "hvbatt": ("Hybrid battery",
               "The big battery in the cargo area, right behind the rear seat (nickel-metal hydride, about 200 V, 14 blocks). "
               "It gives power when you pull away or accelerate and takes power back when braking "
               "or when the engine charges it."),
    "boost": ("Voltage booster",
              "Raises the battery's ~200 V up to as much as ~650 V so the motors can be smaller and "
              "stronger, and steps it back down to recharge the battery."),
    "inv1": ("Generator inverter",
             "Turns the high-voltage DC into 3-phase AC for the generator motor (MG1), and turns "
             "MG1's AC back into DC when it's generating."),
    "inv2": ("Drive motor inverter",
             "Turns the high-voltage DC into 3-phase AC for the drive motor (MG2), and back again "
             "during regenerative braking."),
    "mg1": ("Generator (MG1)",
            "Mostly a generator: the engine spins it to make electricity. It also starts the engine "
            "and controls engine speed through the planetary gear."),
    "mg2": ("Drive motor (MG2)",
            "The main motor that turns the front wheels. When you brake or coast it becomes a "
            "generator and sends power back to the battery (regenerative braking)."),
    "ac": ("A/C compressor",
           "The air-conditioning compressor is electric and runs off the hybrid battery - that's why "
           "the A/C keeps working with the engine off."),
    "dcdc": ("DC-DC converter",
             "Replaces the alternator: steps the hybrid battery's high voltage down to about 14 V to "
             "run the lights, computers and charge the 12 V battery. Its current isn't in the PID list, "
             "so the wire is dashed."),
    "aux": ("12V battery",
            "Powers the computers and 'boots' the hybrid system when you press POWER. While READY "
            "it's charged by the DC-DC converter, so it should read about 13.5-14.5 V."),
}


def elec_state(values, now):
    """Work out volts / amps / watts for each part and wire from the raw readings.
    Signed values: positive = power flowing the way the wire is drawn."""
    g = lambda k: fresh(values, k, now)
    ib, vb, vl, vh, pac, aux = g("batt_amps"), g("pack_volts"), g("vl"), g("vh"), g("ac_watts"), g("aux_volts")
    vb = vb or vl

    def mech(nm, rpm):  # motor power from torque x speed; + = using electricity, - = generating
        return nm * rpm * 2 * math.pi / 60 if nm is not None and rpm is not None else None
    p1, p2 = mech(g("mg1_nm"), g("mg1_rpm")), mech(g("mg2_nm"), g("mg2_rpm"))
    div = lambda p, v: p / v if p is not None and v else None
    pboost = p1 + p2 if p1 is not None and p2 is not None else None

    parts = {
        "hvbatt": dict(V=vb, A=ib, W=vb * ib if vb is not None and ib is not None else None),
        "boost": dict(V=(vl, vh), A=div(pboost, vl), W=pboost),
        "inv1": dict(V=vh, A=div(p1, vh), W=p1),
        "inv2": dict(V=vh, A=div(p2, vh), W=p2),
        "mg1": dict(V=None, A=div(p1, vh), W=p1),
        "mg2": dict(V=None, A=div(p2, vh), W=p2),
        "ac": dict(V=vl, A=div(pac, vl), W=pac),
        "dcdc": dict(V=vl, A=None, W=None),
        "aux": dict(V=aux, A=None, W=None),
    }
    wires = {
        "plus": dict(V=vb, A=ib, W=parts["hvbatt"]["W"]),
        "minus": dict(V=vb, A=ib, W=parts["hvbatt"]["W"]),
        # links between blocks are drawn 1 -> 14; when discharging, current runs 14 -> 1 inside the pack
        "link": dict(V=None, A=None if ib is None else -ib, W=None),
        "vh_gen": dict(V=vh, A=div(p1, vh), W=p1),
        "vh_drive": dict(V=vh, A=div(p2, vh), W=p2),
        "ac_gen": dict(V=None, A=div(p1, vh), W=p1),
        "ac_drive": dict(V=None, A=div(p2, vh), W=p2),
        "ac_comp": dict(V=vl, A=div(pac, vl), W=pac),
        "dcdc": dict(V=vl, A=None, W=None),
        "lv12": dict(V=aux, A=None, W=None),
    }
    return parts, wires


# Block voltage difference from the pack average: ideal within 0.15 V, flashing red from 0.3 V (unconfirmed)


def fmt_watts(w_):
    return f"{w_ / 1000:.1f} kW" if abs(w_) >= 1000 else f"{w_:.0f} W"


class ElectricalView:
    name = "Electrical"
    units = [("V", "Volts"), ("A", "Amps"), ("W", "Watts")]
    groups = []
    places = [  # (part key, place on the car)
        ("dcdc", "dcdc"), ("ac", "ac_compressor"), ("boost", "booster"),
        ("inv1", "gen_inverter"), ("inv2", "drive_inverter"), ("mg1", "mg1"), ("mg2", "mg2"),
        ("aux", "aux_batt"), ("pump", "coolant_pump"), ("fan", "batt_fan"), ("brake_act", "brake_actuator"),
        ("lamp_mil", "lamp0"), ("lamp_abs", "lamp1"), ("lamp_brake", "lamp2"),
        ("lamp_slip", "lamp3"), ("lamp_ecb", "lamp4"), ("buzzer", "lamp5"),
        ("brake_l", "brake_light_l"), ("brake_r", "brake_light_r"),
    ]
    components, shapes = placed(places)
    components += [(f"blk{i + 1:02d}", *block_rect(i)) for i in range(14)]
    shapes.update({f"blk{i + 1:02d}": "module" for i in range(14)})
    PACK_BOTTOM = BATT_Y0 + BATT_ROW2 + 16
    notes = [("Hybrid battery (behind rear seat) - 14 blocks in series", 50, PACK_BOTTOM + 7),
             ("Warning lights (centre meter)", 50, 112)]
    # 12 V runs down the far left (x 5.5), the HV cables from the battery under the floor next to it (- x 8.5, + x 11.5)
    LV_X, MINUS_X, PLUS_X, RIGHT_X = 5.5, 8.5, 11.5, 91.5
    # (wire key, points drawn in the "positive" current direction, label, where the label goes:
    #  "l"/"r" = beside the longest segment, or (x, y) = fixed spot, text to the right)
    wire_paths = [
        ("plus", [(BATT_X0, BATT_Y0 + 8), (PLUS_X, BATT_Y0 + 8), (PLUS_X, 28), (L, 28)], "+ out", (13, 140)),
        ("minus", [(L, 22), (MINUS_X, 22), (MINUS_X, BATT_Y0 + BATT_ROW2 + 8), (BATT_X0, BATT_Y0 + BATT_ROW2 + 8)],
         "− return", (13, 145.5)),
        *[("link", pts, "", "r") for pts in block_links()],
        ("vh_drive", [(L + HALF / 2, 31.5), (L + HALF / 2, 32.5)], "", "r"),
        ("vh_gen", [(M + HALF / 2, 31.5), (M + HALF / 2, 32.5)], "", "r"),
        ("ac_drive", [(L + HALF / 2, 45.5), (L + HALF / 2, 51.5)], "", "r"),
        ("ac_gen", [(M + HALF / 2, 45.5), (M + HALF / 2, 51.5)], "", "r"),
        ("ac_comp", [(R, 25), (57.5, 25), (57.5, 10), (60, 10)], "DC", "r"),
        ("dcdc", [(L + HALF / 2, 18.5), (L + HALF / 2, 16.5)], "", "r"),
        ("lv12", [(L, 10), (LV_X, 10), (LV_X, 237), (52, 237)], "12 V - not measured", (13, 151)),
        # 12 V things that only report on/off: dashed, with slow arrows while they're on
        ("lv_pump", [(L + 17, 10), (L + 18, 10)], "", "r"),
        ("lv_fan", [(74, 237), (RIGHT_X, 237), (RIGHT_X, 174.5), (90, 174.5)], "", "r"),
        ("lv_brake_l", [(19, 237), (19, 240)], "", "r"),
        ("lv_brake_r", [(74, 242.75), (76, 242.75)], "", "r"),
        ("lv_brake_act", [(RIGHT_X, 174.5), (RIGHT_X, 79.25), (R, 79.25)], "", "r"),
    ]
    LAMPS = {  # key: (box text, colour when on, is it a warning?)
        "lamp_mil": ("ENG", cfg.LAMP_AMBER, True), "lamp_abs": ("ABS", cfg.LAMP_AMBER, True),
        "lamp_brake": ("BRAKE", cfg.LAMP_RED, True), "lamp_slip": ("SLIP", cfg.LAMP_AMBER, True),
        "lamp_ecb": ("ECB", cfg.LAMP_RED, True), "buzzer": ("BUZZ", cfg.LAMP_AMBER, True),
        "brake_l": ("", cfg.BRAKE_LIGHT_ON, False), "brake_r": ("", cfg.BRAKE_LIGHT_ON, False),
    }
    FLAGS = {  # extra on/off signals that belong to a part: shown in its hover, bad ones make it flash red
        "boost": [("conv_gate", False), ("conv_shutdown", True), ("conv_fail", True), ("ov_conv", True)],
        "inv1": [("mg1_gate", False), ("mg1_inv_shutdown", True), ("mg1_inv_fail", True), ("ov_inv", True)],
        "inv2": [("mg2_gate", False), ("mg2_inv_shutdown", True), ("mg2_inv_fail", True), ("ov_inv", True)],
        "ac": [("ac_gate", False)],
        "dcdc": [("dcdc_prohibit", False)],
    }
    SOC_IDEAL = cfg.SOC_IDEAL

    def __init__(self):
        self.unit = "A"

    def sensors(self):
        return ELEC + ONOFF + [SOC] + ELEC_EXTRA + [SENSORS[k] for k in ("fan_pct", "fan_relay", "fan_volts", "pump_rpm")]

    SOLENOIDS = ("sol_sla", "sol_slr", "sol_ssc", "sol_scc", "sol_smc", "sol_src")

    def brake_amps(self, values, now):
        amps = [fresh(values, k, now) for k in self.SOLENOIDS]
        return None if None in amps else sum(amps)

    SHORT = {"brake_act": "Brake\nactuator", "dcdc": "DC-DC", "inv1": "Generator\ninverter", "inv2": "Drive\ninverter",
             "mg1": "Generator\n(MG1)", "mg2": "Drive motor\n(MG2)", "pump": "Inverter\ncoolant pump", "fan": "Battery fan"}

    def label(self, key):
        if key.startswith("blk"):
            return f"B{int(key[3:])}"
        if key in self.LAMPS:
            return self.LAMPS[key][0]
        return self.SHORT[key] if key in self.SHORT else ELEC_INFO[key][0]

    @staticmethod
    def on(values, now, key):
        v = fresh(values, key, now)
        return None if v is None else v >= 0.5

    def bad_flags(self, key, values, now):
        return [SENSORS[k].name for k, bad in self.FLAGS.get(key, []) if bad and self.on(values, now, k)]

    def overlays(self, values, now):
        """Battery charge bar under the hybrid battery."""
        soc = fresh(values, "soc", now)
        lo, hi = self.SOC_IDEAL
        colour = IDEAL if soc is not None and lo <= soc <= hi else cfg.LAMP_AMBER
        text = "Battery charge: --" if soc is None else f"Battery charge: {soc:.0f}%"
        cin, cout = fresh(values, "chg_lim", now), fresh(values, "dis_lim", now)
        if cin is not None and cout is not None:
            text += f"   ·   can take in {abs(cin):.0f} kW / give {cout:.0f} kW"
        return [dict(rect=(BATT_X0, self.PACK_BOTTOM + 2, BATT_X1 - BATT_X0, 4), fraction=None if soc is None else soc / 100,
                     colour=colour, text=text, marks=(lo / 100, hi / 100))]

    @staticmethod
    def blocks(values, now):
        return [fresh(values, f"block{i:02d}", now) for i in range(1, 15)]

    def block_cell(self, key, values, now):
        n = int(key[3:])
        blocks = self.blocks(values, now)
        v, ib = blocks[n - 1], fresh(values, "batt_amps", now)
        fill = NO_DATA if ib is None else ramp(CHARGE, abs(ib) / AMP_LIMITS["hvbatt"][1])
        if self.unit == "V":
            text = "--" if v is None else f"{v:.2f} V"
        elif self.unit == "A":
            text = "--" if ib is None else f"{abs(ib):.0f} A"
        else:
            text = "--" if v is None or ib is None else fmt_watts(abs(v * ib))
        state = None
        if None not in blocks:
            dev = abs(v - sum(blocks) / 14)
            state = "warn" if dev >= BLK_WARN_DEV else ("ideal" if dev <= BLK_IDEAL_DEV else None)
        return Cell(fill, text, state)

    def block_tooltip(self, key, values, now):
        n = int(key[3:])
        g = lambda k: fresh(values, k, now)
        blocks = self.blocks(values, now)
        v, ib, res = blocks[n - 1], g("batt_amps"), g(f"res{n:02d}")
        lines = [(f"Voltage: {'--' if v is None else f'{v:.3f} V'}", TIP_FG, 11, True)]
        if None not in blocks:
            avg = sum(blocks) / 14
            dev = v - avg
            order = sorted(range(14), key=lambda i: blocks[i])
            rank = order.index(n - 1) + 1
            where = ("the LOWEST block" if rank == 1 else "the HIGHEST block" if rank == 14
                     else f"#{rank} of 14 (1 = lowest)")
            colour = cfg.TIP_RED if abs(dev) >= BLK_WARN_DEV else cfg.TIP_GREEN if abs(dev) <= BLK_IDEAL_DEV else cfg.TIP_AMBER
            lines.append((f"{abs(dev):.3f} V {'above' if dev >= 0 else 'below'} the pack average - {where}",
                          colour, 10, True))
            lines.append((f"Pack: {sum(blocks):.1f} V total, spread {max(blocks) - min(blocks):.2f} V "
                          f"(lowest block {order[0] + 1}, highest block {order[-1] + 1})", TIP_FG, 10, False))
        cin, cout = g("chg_lim"), g("dis_lim")
        if cin is not None and cout is not None:
            lines.append((f"Pack power limits right now: can take in {abs(cin):.0f} kW, can give {cout:.0f} kW",
                          TIP_FG, 10, False))
        if ib is not None:
            lines.append((f"Current: {abs(ib):.1f} A ({'charging' if ib < 0 else 'giving power'}) - "
                          "the same for every block, they're in series", TIP_FG, 10, False))
            if v is not None:
                lines.append((f"Power through this block: {fmt_watts(abs(v * ib))}", TIP_FG, 10, False))
        lines.append((f"Internal resistance: {'--' if res is None else f'{res * 1000:.0f} mΩ'} "
                      "(higher than the others = weaker block)", TIP_FG, 10, False))
        lines.append((f"Ideal: within {BLK_IDEAL_DEV} V of the average     Flashing red: {BLK_WARN_DEV} V or more away",
                      TIP_FG, 10, False))
        lines.append(("Each block is 2 modules of 6 nickel-metal hydride cells (12 cells, about 14.4 V nominal). "
                      "All 14 are chained in series, so they all carry the same current. Voltages rise while "
                      "charging and sag while driving; a block that sags more than the rest is the weak one.",
                      TIP_FG, 10, False))
        lines.append(("Voltage: PID 2181, resistance: PID 2195 - both tested in your car", DIM, 8, False))
        lines.append(("Thresholds and description: estimates, not Toyota specs (unconfirmed)", DIM, 8, False))
        return f"Battery block {n}", lines

    def value_text(self, d, key=None):
        u = self.unit
        if u == "V":
            v = d["V"]
            if isinstance(v, tuple):
                return f"{v[0]:.0f} → {v[1]:.0f} V" if None not in v else "--"
            return "AC (not read)" if key in ("mg1", "mg2") else ("--" if v is None else f"{v:.1f} V")
        if key in ("dcdc", "aux"):
            return "n/a"
        x = d[u]
        if x is None:
            return "--"
        return f"{abs(x):.0f} A" if u == "A" else fmt_watts(abs(x))

    @staticmethod
    def direction(key, d):
        a = d["A"]
        if a is None or abs(a) < 0.5:
            return ""
        if key == "hvbatt":
            return "giving power" if a > 0 else "charging"
        if key in ("mg1", "mg2"):
            return "driving" if a > 0 else "generating"
        return ""

    def cell(self, key, values, now):
        if key.startswith("blk"):
            return self.block_cell(key, values, now)
        if key in self.LAMPS:
            on = self.on(values, now, "brake_lights" if key in ("brake_l", "brake_r") else key)
            _, colour, warning = self.LAMPS[key]
            if on is None:
                return Cell(NO_DATA, "", dashed=True)
            dark = cfg.BRAKE_LIGHT_OFF if key in ("brake_l", "brake_r") else cfg.LAMP_OFF
            return Cell(colour if on else dark, "", "warn" if on and warning else None)
        if key == "pump":
            on = self.on(values, now, "pump_on")
            if on is None:
                return Cell(NO_DATA, "--", dashed=True)
            duty = fresh(values, "pump_duty", now)
            text = ("ON" + (f" {duty:.0f}%" if duty is not None else "")) if on else "off"
            return Cell(ramp(CHARGE, cfg.ON_OFF_FILL) if on else ramp(CHARGE, 0), text, dashed=True)
        if key == "fan":
            pct = fresh(values, "fan_pct", now)
            if pct is None:
                relay = self.on(values, now, "fan_relay")
                return Cell(NO_DATA, "--" if relay is None else ("ON" if relay else "off"), dashed=True)
            return Cell(ramp(CHARGE, pct / 100), f"{pct:.0f}% effort", dashed=True)
        if key == "brake_act":
            a = self.brake_amps(values, now)
            if a is None:
                return Cell(NO_DATA, "--")
            aux = fresh(values, "aux_volts", now)
            text = (f"{aux:.1f} V" if aux is not None else "--") if self.unit == "V" else (
                f"{a:.2f} A" if self.unit == "A" else ("--" if aux is None else f"{a * aux:.0f} W"))
            ideal, too_much = AMP_LIMITS["brake_act"]
            return Cell(ramp(CHARGE, a / too_much), text,
                        "warn" if a / too_much >= WARN_AT else ("ideal" if a <= ideal else None))
        if key == "dcdc" and self.unit != "V":
            duty = fresh(values, "dcdc_duty", now)
            if duty is None:
                return Cell(NO_DATA, "n/a", dashed=True)
            return Cell(ramp(CHARGE, duty / 100), f"{duty:.0f}% effort", dashed=True)
        parts, _ = elec_state(values, now)
        d = parts[key]
        text = self.value_text(d, key)
        if key == "aux":
            v = d["V"]
            if v is None:
                return Cell(NO_DATA, "--", dashed=True)
            state = "warn" if v < AUX_LOW or v > AUX_HIGH else ("ideal" if AUX_IDEAL[0] <= v <= AUX_IDEAL[1] else None)
            return Cell(NO_DATA, f"{v:.1f} V", state, dashed=True)
        if key == "dcdc":
            return Cell(NO_DATA, text, dashed=True)
        a = d["A"]
        if a is None:
            return Cell(NO_DATA, "--")
        ideal, too_much = AMP_LIMITS[key]
        frac = abs(a) / too_much
        state = "warn" if frac >= WARN_AT or self.bad_flags(key, values, now) else ("ideal" if abs(a) <= ideal else None)
        word = self.direction(key, d)
        return Cell(ramp(CHARGE, frac), f"{text}\n{word}" if word else text, state)

    def wires(self, values, now):
        """List of (points, signed amps or None, label text, label side) for the app to draw and animate."""
        _, wires = elec_state(values, now)
        out = []
        for key, pts, kind, side in self.wire_paths:
            d = wires.get(key, dict(V=None, A=None, W=None))
            if not kind or "not measured" in kind:
                label = kind
            elif self.unit == "V" and d["V"] is None:
                label = kind
            else:
                label = f"{kind} · {self.value_text(d)}"
            out.append((pts, d["A"], label, side, None))
        active = {"lv_pump": self.on(values, now, "pump_on"),
                  "lv_fan": (fresh(values, "fan_pct", now) or 0) > 0 or bool(self.on(values, now, "fan_relay")),
                  "lv_brake_l": self.on(values, now, "brake_lights"), "lv_brake_r": self.on(values, now, "brake_lights")}
        for i, (key, pts, kind, side) in enumerate(self.wire_paths):
            if key == "lv_brake_act":
                a = self.brake_amps(values, now)
                out[i] = (pts, a, "" if a is None else f"12 V · {a:.2f} A", (59, 76.5), None)
                continue
            if key in active:
                out[i] = (pts, None, kind, side, bool(active[key]))
        return out

    ONOFF_INFO = {
        "lamp_mil": "The check-engine light on the dashboard. On = the engine computer has stored a fault.",
        "lamp_abs": "ABS warning light. On = a problem with the anti-lock brakes.",
        "lamp_brake": "Brake system warning light (also comes on with the parking brake).",
        "lamp_slip": "Slip indicator. Flashes when traction control / stability control is working.",
        "lamp_ecb": "Electronically controlled brake warning. On = a problem with the brake system.",
        "buzzer": "The brake system's warning buzzer.",
        "brake_l": "The brake lights at the back. On while the brake pedal is pressed.",
        "brake_r": "The brake lights at the back. On while the brake pedal is pressed.",
        "pump": "Electric pump for the inverter/motor coolant loop. Runs on the 12 V system.",
        "fan": "Hybrid battery cooling fan. Runs on the 12 V system; the car reports how hard it drives it (%).",
    }

    def onoff_tooltip(self, key, values, now):
        g = lambda k: fresh(values, k, now)
        sensor_key = {"brake_l": "brake_lights", "brake_r": "brake_lights", "pump": "pump_on", "fan": "fan_relay"}.get(key, key)
        on = self.on(values, now, sensor_key) if key != "fan" else self.on(values, now, "fan_relay")
        lines = [(f"Right now: {'--' if on is None else ('ON' if on else 'off')}", TIP_FG, 11, True)]
        if key == "pump" and g("pump_rpm") is not None:
            duty = g("pump_duty")
            lines.append((f"Pump speed: {g('pump_rpm'):,.0f} rpm     Effort: {'--' if duty is None else f'{duty:.0f}%'}",
                          TIP_FG, 10, False))
        if key == "fan":
            pct, volts = g("fan_pct"), g("fan_volts")
            lines.append((f"Effort: {'--' if pct is None else f'{pct:.0f}%'}     "
                          f"Fan motor voltage: {'--' if volts is None else f'{volts:.1f} V'}", TIP_FG, 10, False))
        lines.append((self.ONOFF_INFO[key], TIP_FG, 10, False))
        lines.append(("Current isn't measured - only whether it's on. Arrows on its wire move at a fixed slow "
                      "speed while it's on.", DIM, 9, False))
        s = SENSORS[sensor_key]
        lines.append((f"{s.tech} · request {s.pid} to {s.header} · "
                      + ("tested in your car" if s.tested else "NOT yet tested in your car"), DIM, 8, False))
        title = {"brake_l": "Brake lights", "brake_r": "Brake lights", "pump": "Inverter coolant pump",
                 "fan": "Battery cooling fan"}.get(key, SENSORS[key].name if key in SENSORS else key)
        return title, lines

    def tooltip(self, key, values, now):
        if key.startswith("blk"):
            return self.block_tooltip(key, values, now)
        if key in self.LAMPS or key in ("pump", "fan"):
            return self.onoff_tooltip(key, values, now)
        if key == "brake_act":
            g = lambda k: fresh(values, k, now)
            a = self.brake_amps(values, now)
            lines = [(f"Total current: {'--' if a is None else f'{a:.2f} A'}", TIP_FG, 11, True)]
            for k in self.SOLENOIDS:
                v = g(k)
                lines.append((f"{SENSORS[k].name}: {'--' if v is None else f'{v:.2f} A'}", TIP_FG, 10, False))
            ideal, too_much = AMP_LIMITS["brake_act"]
            lines.append((f"Ideal: up to {ideal} A total     Too much: {too_much} A", TIP_FG, 10, False))
            lines.append((ELEC_INFO["brake_act"][1], TIP_FG, 10, False))
            lines.append(("Measured by the brake computer (7B0 21A3) - tested in your car", DIM, 8, False))
            lines.append(("Limits: estimates, not Toyota specs (unconfirmed)", DIM, 8, False))
            return "Brake actuator", lines
        parts, _ = elec_state(values, now)
        d = parts[key]
        name, info = ELEC_INFO[key]
        g = lambda k: fresh(values, k, now)
        lines = []
        v = d["V"]
        if isinstance(v, tuple):
            vtxt = "--" if None in v else f"{v[0]:.0f} V in → {v[1]:.0f} V out"
        else:
            vtxt = "AC - not read" if key in ("mg1", "mg2") else ("--" if v is None else f"{v:.1f} V")
        lines.append((f"Voltage: {vtxt}", TIP_FG, 11, True))
        if key in ("dcdc", "aux"):
            lines.append(("Current / power: not measured (no PID for it)", DIM, 10, True))
        else:
            a, w_ = d["A"], d["W"]
            lines.append((f"Current: {'--' if a is None else f'{abs(a):.1f} A'}     "
                          f"Power: {'--' if w_ is None else fmt_watts(abs(w_))}", TIP_FG, 11, True))
            word = self.direction(key, d)
            if word:
                lines.append((f"Right now it's {word}", cfg.TIP_GREEN if word in ("charging", "generating") else cfg.TIP_AMBER,
                              10, True))
            if key in AMP_LIMITS:
                ideal, too_much = AMP_LIMITS[key]
                lines.append((f"Ideal: up to {ideal} A     Too much: {too_much} A", TIP_FG, 10, False))
        if key == "aux":
            for label, k in (("Hybrid computer", "aux_volts"), ("Battery computer", "aux_v2"), ("Dashboard meter", "aux_v3")):
                v = g(k)
                lines.append((f"{label} says: {'--' if v is None else f'{v:.2f} V'}", TIP_FG, 10, False))
            lines.append((f"Ideal: {AUX_IDEAL[0]}-{AUX_IDEAL[1]} V while READY     "
                          f"Warning: below {AUX_LOW} V or above {AUX_HIGH} V", TIP_FG, 10, False))
        if key == "boost":
            ratio = g("boost_ratio")
            lines.append((f"Boost ratio: {'--' if ratio is None else f'{ratio:.0f}%'} "
                          "(0% = passing battery voltage straight through)", TIP_FG, 10, False))
        if key in ("mg1", "mg2"):
            n = key[-1]
            rpm, nm = g(f"mg{n}_rpm"), g(f"mg{n}_nm")
            lines.append((f"Speed: {'--' if rpm is None else f'{rpm:.0f} rpm'}     "
                          f"Torque: {'--' if nm is None else f'{nm:.0f} Nm'}", TIP_FG, 10, True))
        if key == "ac":
            if g("ac_watts") is None:
                lines.append(("A/C power reading (217D) hasn't answered yet", DIM, 10, False))
            rpm, fan = g("ac_rpm"), g("blower")
            lines.append((f"Compressor speed: {'--' if rpm is None else f'{rpm:.0f} rpm'}     "
                          f"Cabin fan: {'--' if fan is None else f'level {fan:.0f} of 31'}", TIP_FG, 10, True))
            lines.append(("The cabin fan runs on the 12 V system, so its current isn't shown - only its speed level. "
                          "Heat comes from engine coolant, not electricity.", DIM, 9, False))
        for flag, bad in self.FLAGS.get(key, []):
            on = self.on(values, now, flag)
            lines.append((f"{SENSORS[flag].name}: {'--' if on is None else ('ON' if on else 'off')}",
                          cfg.TIP_RED if bad and on else TIP_FG, 10, bool(bad and on)))
        if key == "dcdc":
            duty = g("dcdc_duty")
            lines.append((f"Converter duty: {'--' if duty is None else f'{duty:.0f} %'} (how hard it's working)",
                          TIP_FG, 10, False))
        lines.append((info, TIP_FG, 10, False))
        how = {"hvbatt": "Measured directly (battery ECU)",
               "boost": "Estimated: generator power + drive motor power (torque × speed)",
               "inv1": "Estimated from generator torque × speed", "inv2": "Estimated from drive motor torque × speed",
               "mg1": "Estimated from torque × speed; amps shown as DC-side equivalent",
               "mg2": "Estimated from torque × speed; amps shown as DC-side equivalent",
               "ac": "A/C power PID 217D - tested in your car",
               "dcdc": "Duty PID 2179 - tested in your car", "aux": "Voltage measured (hybrid ECU +B)"}[key]
        lines.append((how, DIM, 8, False))
        lines.append(("Limits and description: estimates, not Toyota specs (unconfirmed)", DIM, 8, False))
        return name, lines

    PANEL_ROWS = [("soc", "Battery charge"), ("ib", "Battery current (− = charging)"), ("vb", "Battery voltage"), ("vl", "Before booster"),
                  ("vh", "After booster"), ("p1", "Generator (− = generating)"),
                  ("p2", "Drive motor (− = generating)"),
                  ("pac", "A/C power"), ("dcdc", "DC-DC effort"), ("aux", "12V battery"),
                  ("spread", "Block spread"), ("lim", "Battery power limits"), ("brake", "Brake actuator"),
                  ("regen", "Regen delivered vs asked"), ("loss", "Losses + 12 V load (rough)")]

    def build_panel(self, parent, app):
        unit_buttons(parent, self, app)
        legend(parent, app, CHARGE, "no current", "too much", "Colour = how much current (electrons) it gets")
        panel_label(parent, "Arrows show which way current flows:\nout of the battery's + wire, back on the − wire.\n"
                            "Faster + thicker = more current.\nDashed = not measured.", TEXT, 9, (6, 0))
        self.rows = reading_rows(parent, self.PANEL_ROWS, "Readings")
        panel_label(parent, "On right now", pady=(12, 0))
        self.on_now = panel_label(parent, "--", TEXT, 9)
        self.on_now.config(wraplength=int(cfg.PANEL_TEXT_WIDTH * app.ui))
        panel_label(parent, "All readings answered in your car's full test (2026-09-26)\nMotor values estimated from torque × speed\n"
                            "Limits are estimates (unconfirmed)", DIM, 9, (10, 0))

    def update_panel(self, values, now):
        parts, _ = elec_state(values, now)
        g = lambda k: fresh(values, k, now)
        ib = g("batt_amps")
        blocks = [g(f"block{i:02d}") for i in range(1, 15)]
        pw = lambda x: "--" if x is None else ("0 W" if abs(x) < 0.5 else ("+" if x > 0 else "") + fmt_watts(x))
        vals = {
            "ib": "--" if ib is None else f"{ib:+.1f} A",
            "vb": "--" if g("pack_volts") is None else f"{g('pack_volts'):.1f} V",
            "vl": "--" if g("vl") is None else f"{g('vl'):.0f} V",
            "vh": "--" if g("vh") is None else f"{g('vh'):.0f} V",
            "p1": pw(parts["mg1"]["W"]), "p2": pw(parts["mg2"]["W"]),
            "pac": "--" if g("ac_watts") is None else fmt_watts(g("ac_watts")),
            "aux": "--" if g("aux_volts") is None else f"{g('aux_volts'):.2f} V",
            "spread": "--" if None in blocks else f"{max(blocks) - min(blocks):.2f} V",
            "regen": "--" if calc.regen_delivered_pct(values, now) is None else f"{calc.regen_delivered_pct(values, now):.0f}%",
            "loss": "--" if calc.electrical_losses_kw(values, now) is None else f"{calc.electrical_losses_kw(values, now):.1f} kW",
            "lim": "--" if g("chg_lim") is None or g("dis_lim") is None else f"−{abs(g('chg_lim')):.0f} / +{g('dis_lim'):.0f} kW",
            "brake": "--" if self.brake_amps(values, now) is None else f"{self.brake_amps(values, now):.2f} A",
            "soc": "--" if g("soc") is None else f"{g('soc'):.1f}%",
            "dcdc": "--" if g("dcdc_duty") is None else f"{g('dcdc_duty'):.0f}%",
        }
        for k, lbl in self.rows.items():
            lbl.config(text=vals[k], fg=DIM if vals[k] == "--" else TEXT)
        seen = [s for s in ONOFF if g(s.key) is not None]
        on = [s.name for s in seen if g(s.key) >= 0.5]
        self.on_now.config(text="waiting for data" if not seen else (", ".join(on) if on else "nothing"),
                           fg=WARN if any("FAIL" in n or "Over-voltage" in n or "light" in n.lower() and "Brake lights" != n
                                          for n in on) else TEXT)


# ======================================================================
# Spinning view (everything in RPM; torque shown by rotor thickness + redness)
# ======================================================================
PLANET = SUN_TEETH + RING_TEETH
MG2_TO_WHEEL = MG2_REDUCTION * FINAL_DRIVE                # about 8.6 : 1

# Max RPM (full colour) and ideal range per part. Training-data estimates (unconfirmed).
SPIN_LIMITS = {   # (rpm at full colour, ideal range as text) - numbers from config.py
    "engine": (cfg.SPIN_MAX_RPM["engine"], f"0 (off) or {cfg.ENGINE_IDEAL_RPM[0]:,}-{cfg.ENGINE_IDEAL_RPM[1]:,}"),
    "mg1": (cfg.SPIN_MAX_RPM["mg1"], f"up to {cfg.MG1_IDEAL_MAX_RPM:,} either way"),
    "mg2": (cfg.SPIN_MAX_RPM["mg2"], f"up to {cfg.MG2_IDEAL_MAX_RPM:,}"),
    "ring": (cfg.SPIN_MAX_RPM["ring"], None),
    **{w: (cfg.SPIN_MAX_RPM["wheel"], f"within {cfg.SLIP_IDEAL:.0%} of the other wheels") for w in ("fl", "fr", "rl", "rr")},
    "ac": (cfg.SPIN_MAX_RPM["ac"], f"up to {cfg.AC_IDEAL_MAX_RPM:,}"),
    "pump": (cfg.SPIN_MAX_RPM["pump"], f"{cfg.PUMP_IDEAL_RPM[0]:,}-{cfg.PUMP_IDEAL_RPM[1]:,}"),
}
# Max torque (Nm) = thickest, reddest rotor. Training-data estimates (unconfirmed).
TORQUE_MAX = cfg.TORQUE_MAX_NM
WHEELS = ("fl", "fr", "rl", "rr")

SPIN_INFO = {
    "engine": ("Engine", "Engine\n(crankshaft)",
               "The gasoline engine's crankshaft. In a Prius it often stops completely while you drive; the "
               "hybrid computer starts it (using the generator) only when it's needed."),
    "mg1": ("Generator (MG1)", "Generator\n(MG1)",
            "Connected to the sun gear of the planetary gear. Its speed sets the engine's speed. It often spins "
            "BACKWARDS - for example when the engine is off and the car is moving."),
    "mg2": ("Drive motor (MG2)", "Drive motor\n(MG2)",
            "Geared straight to the front wheels (about 8.6 turns per wheel turn), so its speed is really just "
            "road speed. Negative = reversing."),
    "ring": ("Planetary ring gear (calculated)", "Ring gear",
             "The output of the power-split planetary gear: engine drives the planet carrier, the generator is "
             "the sun gear, and the ring gear goes to the wheels. It isn't measured - it's calculated two ways "
             "so you can see if the gear numbers are right."),
    "ac": ("A/C compressor", "A/C\ncompressor",
           "Electric A/C compressor motor. It changes speed to match how much cooling is needed, and stops "
           "when the A/C isn't needed."),
    "pump": ("Inverter coolant pump", "Inverter\ncoolant pump",
             "Small electric pump that circulates coolant through the inverter and motors (a separate loop "
             "from the engine's)."),
    "steer": ("Steering wheel", "Steering",
              "The steering wheel's position. It turns about 1.8 times each way from straight (about ±660° measured "
              "in your car). The rotor shows the actual angle - it only moves when you turn the wheel."),
    "fan": ("Battery cooling fan", "Battery fan",
            "Blows cabin air through the hybrid battery to cool it. The car only reports how hard it's driving "
            "the fan (%), not its RPM, so the box shows % and the rotor speed just follows that %."),
}
for _k, _n in (("fl", "Front left"), ("fr", "Front right"), ("rl", "Rear left"), ("rr", "Rear right")):
    SPIN_INFO[_k] = (f"{_n} wheel", _k.upper(),
                     "Calculated from the brake computer's wheel speed sensor and the stock 195/65R15 tire "
                     f"(about {TIRE_CIRCUMFERENCE_M:.2f} m around). All four should match unless a wheel is "
                     "slipping, locking, or the tire sizes differ.")


def fmt_rpm(r):
    return "--" if r is None else f"{r:,.0f}".replace("-", "−")


def fmt_nm(t):
    return "--" if t is None else f"{t:,.0f} Nm".replace("-", "−")


class SpinView:
    name = "Spinning"
    units = [("rpm", "RPM")]
    groups = [("Transaxle", L - 1, 50.5, R - L + 2, 34.5)]
    notes = []
    places = [   # tires first, so a steered front tire tucks under the parts next to it
        ("fl", "wheel_fl"), ("fr", "wheel_fr"), ("rl", "wheel_rl"), ("rr", "wheel_rr"),
        ("engine", "engine"), ("mg1", "mg1"), ("mg2", "mg2"), ("ring", "ring_gear"),
        ("ac", "ac_compressor"), ("pump", "coolant_pump"), ("fan", "batt_fan"),
        ("steer", "steering_wheel"),
    ]
    components, shapes = placed(places)
    shapes.update({k: "tread" for k in WHEELS})     # tires show their tread rolling instead of a rotor
    shapes["ring"] = "geartread"                    # so does the ring gear (it turns about the same axis)
    STEER_MAX = cfg.STEER_MAX_DEG

    def __init__(self):
        self.unit = "rpm"

    def sensors(self):
        return ROT + TORQUE + STEER

    @staticmethod
    def steer_angle(values, now):
        a = fresh(values, "steer", now)
        return fresh(values, "steer2", now) if a is None else a

    def label(self, key):
        return SPIN_INFO[key][1]

    # ---------- the numbers ----------
    @staticmethod
    def calc(values, now):
        g = lambda k: fresh(values, k, now)
        eng = g("eng_rpm")
        if eng is None:
            eng = g("eng_rpm_hv")
        mg1, mg2 = g("mg1_rpm"), g("mg2_rpm")
        ring_planet = (eng * PLANET - mg1 * SUN_TEETH) / RING_TEETH if eng is not None and mg1 is not None else None
        ring_mg2 = mg2 / MG2_REDUCTION if mg2 is not None else None
        wheels = {k: None if g(f"whl_{k}") is None else g(f"whl_{k}") * KMH_TO_WHEEL_RPM for k in WHEELS}
        rpm = dict(engine=eng, mg1=mg1, mg2=mg2, ring=ring_planet if ring_planet is not None else ring_mg2,
                   ac=g("ac_rpm"), pump=g("pump_rpm"), **wheels)
        return rpm, ring_planet, ring_mg2

    @staticmethod
    def torques(values, now):
        """Torque (Nm) for each part: measured where the car reports it, otherwise worked out from the gears
        (steady-state planetary gear balance: engine torque = -MG1 torque x 108/30). Returns (torques, how)."""
        g = lambda k: fresh(values, k, now)
        t1, t2, te = g("mg1_nm"), g("mg2_nm"), g("eng_nm")
        how = {"mg1": "measured", "mg2": "measured", "engine": "measured"}
        if te is None and t1 is not None:
            te, how["engine"] = max(0.0, -t1 * PLANET / SUN_TEETH), "estimated from generator torque"
        ring = te * RING_TEETH / PLANET + t2 * MG2_REDUCTION if te is not None and t2 is not None else None
        wheel = ring * FINAL_DRIVE / 2 if ring is not None else None   # split between the two front wheels
        how.update(ring="estimated", fl="estimated", fr="estimated")
        return dict(engine=te, mg1=t1, mg2=t2, ring=ring, fl=wheel, fr=wheel), how

    @staticmethod
    def wheel_state(key, rpm):
        vals = [rpm[k] for k in WHEELS if rpm[k] is not None]
        if rpm[key] is None or len(vals) < 2:
            return None, None
        avg = sum(vals) / len(vals)
        if avg < cfg.SLIP_MIN_WHEEL_RPM:  # below ~5 km/h the 1.28 km/h sensor steps are too coarse to judge slip
            return None, None
        dev = (rpm[key] - avg) / avg
        return ("warn" if abs(dev) >= SLIP_WARN else "ideal" if abs(dev) <= SLIP_IDEAL else None), dev

    def state(self, key, r, rpm):
        top, _ = SPIN_LIMITS[key]
        if abs(r) / top >= WARN_AT:
            return "warn"
        a = abs(r)
        if key == "engine":
            return "ideal" if a < 1 or cfg.ENGINE_IDEAL_RPM[0] <= a <= cfg.ENGINE_IDEAL_RPM[1] else None
        if key in WHEELS:
            return self.wheel_state(key, rpm)[0]
        ok = {"mg1": a <= cfg.MG1_IDEAL_MAX_RPM, "mg2": a <= cfg.MG2_IDEAL_MAX_RPM, "ac": a <= cfg.AC_IDEAL_MAX_RPM,
              "pump": cfg.PUMP_IDEAL_RPM[0] <= a <= cfg.PUMP_IDEAL_RPM[1]}.get(key)
        return "ideal" if ok else None

    def cell(self, key, values, now):
        if key == "steer":
            a = self.steer_angle(values, now)
            if a is None:
                return Cell(NO_DATA, "--")
            side = "straight" if abs(a) < cfg.STEER_STRAIGHT_DEG else ("left" if a > 0 else "right")
            return Cell(ramp(SPIN_FWD, abs(a) / self.STEER_MAX), f"{abs(a):.0f}° {side}")
        if key == "fan":
            pct = fresh(values, "fan_pct", now)
            if pct is None:
                return Cell(NO_DATA, "--")
            return Cell(ramp(SPIN_FWD, pct / 100), f"{pct:.0f}% power")
        rpm, _, _ = self.calc(values, now)
        r = rpm[key]
        if r is None:
            return Cell(NO_DATA, "--")
        top, _ = SPIN_LIMITS[key]
        fill = ramp(SPIN_FWD if r >= 0 else SPIN_REV, abs(r) / top)
        text = fmt_rpm(r) if key in WHEELS else f"{fmt_rpm(abs(r))} rpm" + ("\nbackwards" if r <= -1 else "")
        return Cell(fill, text, self.state(key, r, rpm))

    def spinners(self, values, now):
        """(key, signed rpm, torque 0-1 or None) for every part that should show a turning rotor."""
        rpm, _, _ = self.calc(values, now)
        tq, _ = self.torques(values, now)
        out = [(k, rpm[k], None if tq.get(k) is None else min(1.0, abs(tq[k]) / TORQUE_MAX[k]))
               for k, *_ in self.components if k in rpm and rpm[k] is not None]
        pct = fresh(values, "fan_pct", now)
        if pct is not None:  # not real RPM - the rotor just follows the fan's % power
            out.append(("fan", pct * cfg.FAN_RPM_PER_PCT, None))
        a = self.steer_angle(values, now)
        if a is not None:    # the steering wheel doesn't spin: its rotor is drawn at the real angle
            out.append(("steer", 0, None, a))
        return out

    def wires(self, values, now):
        return []

    # ---------- hover ----------
    def tooltip(self, key, values, now):
        g = lambda k: fresh(values, k, now)
        name, _, info = SPIN_INFO[key]
        if key == "steer":
            a, a2, yaw = g("steer"), g("steer2"), g("yaw")
            lines = [(f"Angle: {'--' if a is None else f'{abs(a):.1f}° ' + ('left' if a > 0 else 'right')}",
                      TIP_FG, 11, True),
                     (f"Second reading: {'--' if a2 is None else f'{a2:.1f}°'}     "
                      f"Car turning rate: {'--' if yaw is None else f'{abs(yaw):.0f}°/s'}", TIP_FG, 10, False),
                     (f"Turning radius right now (speed ÷ turning rate): "
                      f"{'--' if calc.turning_radius_m(values, now) is None else f'{calc.turning_radius_m(values, now):.0f} m'}",
                      TIP_FG, 10, True),
                     *([] if a is None else [(
                         "Front wheels turned (calculated): left {:.1f}°, right {:.1f}° - the inside wheel turns more "
                         "(Ackermann geometry, full lock set by the 5.2 m turning radius)".format(
                             *(abs(x) for x in calc.front_wheel_angles_deg(a))), TIP_FG, 10, False)]),
                     (f"Full lock is about {self.STEER_MAX}° (measured in your car). Note: Toyota lists 2.84 turns "
                      "lock-to-lock (about ±511°), so this angle reading may be scaled differently.", TIP_FG, 10, False),
                     (info, TIP_FG, 10, False),
                     ("Brake computer 7B0 2106 / 2147 - tested in your car. Unit: degrees, not rpm.", DIM, 8, False)]
            return name, lines
        if key == "fan":
            pct, relay, volts = g("fan_pct"), g("fan_relay"), g("fan_volts")
            lines = [(f"Fan power: {'--' if pct is None else f'{pct:.0f}%'}", TIP_FG, 11, True),
                     (f"Fan relay: {'--' if relay is None else ('ON' if relay else 'off')}     "
                      f"Fan motor voltage: {'--' if volts is None else f'{volts:.1f} V'}", TIP_FG, 10, False),
                     (info, TIP_FG, 10, False),
                     ("Fan % PID 218E and fan voltage PID 2181 - both tested in your car", DIM, 8, False)]
            return name, lines
        rpm, ring_planet, ring_mg2 = self.calc(values, now)
        tq, how = self.torques(values, now)
        top, ideal = SPIN_LIMITS[key]
        r = rpm[key]
        lines = []
        if r is None:
            lines.append(("No reading yet", DIM, 11, True))
        else:
            lines.append((f"{fmt_rpm(abs(r))} rpm" + ("  - turning BACKWARDS" if r <= -1 else
                                                       "  - stopped" if abs(r) < 1 else ""), TIP_FG, 11, True))
        if key in TORQUE_MAX:
            t = tq[key]
            lines.append((f"Twisting force (torque): {fmt_nm(t)}" + (f"  ({how[key]})" if t is not None else "")
                          + (f" - {abs(t) / TORQUE_MAX[key] * 100:.0f}% of max" if t is not None else ""),
                          cfg.TIP_TORQUE, 10, True))
            if key == "engine" and g("eng_nm") is not None and g("mg1_nm") is not None:
                est = max(0.0, -g("mg1_nm") * PLANET / SUN_TEETH)
                lines.append((f"Engine torque worked out from generator torque: {est:.0f} Nm", TIP_FG, 10, False))
            if key in ("mg1", "mg2") and t is not None and r is not None:
                kw = t * r * 2 * math.pi / 60 / 1000
                lines.append((f"Power = torque × speed = {abs(kw):.1f} kW ({'driving' if kw >= 0 else 'generating'})",
                              TIP_FG, 10, False))
            if key in ("ring", "fl", "fr") and t is not None and r is not None:
                kw = t * r * 2 * math.pi / 60 / 1000 * (2 if key in ("fl", "fr") else 1)
                lines.append((f"Power {'to both front wheels' if key != 'ring' else 'through the ring gear'} "
                              f"(torque × speed): {abs(kw):.1f} kW", TIP_FG, 10, False))
                p1, p2 = calc.motor_kw(values, now, 1), calc.engine_kw(values, now)
                if key == "ring" and p2 and p2 > 1:
                    mech = p2 * RING_TEETH / (SUN_TEETH + RING_TEETH)
                    lines.append((f"Engine power going straight to the wheels: {mech:.1f} kW "
                                  f"({100 * RING_TEETH / (SUN_TEETH + RING_TEETH):.0f}%); the rest ({p2 - mech:.1f} kW) "
                                  "goes through the generator as electricity", TIP_FG, 10, False))
            if key in ("fl", "fr"):
                req, op = g("regen_req"), g("regen_op")
                pct = calc.regen_delivered_pct(values, now)
                if pct is not None:
                    lines.append((f"Regen delivered {pct:.0f}% of what was asked (the rest = friction brakes)",
                                  TIP_FG, 10, True))
                lines.append((f"Regen braking asked for: {fmt_nm(req)}     delivered: {fmt_nm(op)}", TIP_FG, 10, False))
        if key == "engine":
            kw = calc.engine_kw(values, now)
            lines.append((f"Engine power (calculated): {'--' if kw is None else f'{kw:.1f} kW'}", TIP_FG, 10, True))
            srcs = [("Standard OBD (010C)", "eng_rpm"), ("Hybrid computer", "eng_rpm_hv"),
                    ("Engine computer", "eng_rpm_ecm"), ("Crank sensor", "eng_rpm_sensor")]
            got = [g(k) for _, k in srcs if g(k) is not None]
            for label, k in srcs:
                lines.append((f"{label}: {fmt_rpm(g(k))}", TIP_FG, 10, False))
            if len(got) >= 2:
                spread = max(got) - min(got)
                lines.append((f"Sources agree within {spread:.0f} rpm" if spread <= cfg.RPM_SOURCES_AGREE else
                              f"Sources differ by {spread:.0f} rpm (normal while revving - they're read at different moments)",
                              cfg.TIP_GREEN if spread <= cfg.RPM_SOURCES_AGREE else cfg.TIP_AMBER, 10, True))
            lines.append((f"Hybrid system's target engine speed: {fmt_rpm(g('eng_target'))} rpm", TIP_FG, 10, False))
        if key in ("mg1", "mg2", "ring") and None not in (ring_planet, ring_mg2):
            lines.append((f"Ring gear from engine + generator: {fmt_rpm(ring_planet)} rpm", TIP_FG, 10, False))
            lines.append((f"Ring gear from drive motor ÷ {MG2_REDUCTION}: {fmt_rpm(ring_mg2)} rpm", TIP_FG, 10, False))
            diff = abs(ring_planet - ring_mg2)
            lines.append((f"Gear numbers check out (within {cfg.GEAR_CHECK_RPM} rpm)" if diff <= cfg.GEAR_CHECK_RPM else
                          f"Off by {diff:.0f} rpm - gear numbers may be wrong, or readings taken at different moments",
                          cfg.TIP_GREEN if diff <= cfg.GEAR_CHECK_RPM else cfg.TIP_AMBER, 10, True))
        if key in WHEELS:
            kmh = g(f"whl_{key}")
            lines.append((f"Wheel speed sensor: {'--' if kmh is None else f'{kmh:.1f} km/h'}", TIP_FG, 10, False))
            state, dev = self.wheel_state(key, rpm)
            if dev is not None:
                lines.append((f"{abs(dev) * 100:.1f}% {'faster' if dev > 0 else 'slower'} than the average wheel",
                              cfg.TIP_RED if state == "warn" else cfg.TIP_GREEN if state == "ideal" else cfg.TIP_AMBER, 10, True))
            if key in ("fl", "fr"):
                calc_mg2 = None if g("mg2_rpm") is None else g("mg2_rpm") / MG2_TO_WHEEL
                calc_ring = None if ring_planet is None else ring_planet / FINAL_DRIVE
                lines.append((f"Calculated from drive motor ÷ {MG2_TO_WHEEL:.2f}: {fmt_rpm(calc_mg2)} rpm", TIP_FG, 10, False))
                lines.append((f"Calculated from engine + generator gearing: {fmt_rpm(calc_ring)} rpm", TIP_FG, 10, False))
                if r is not None and calc_mg2 is not None and r > 40:
                    off = (calc_mg2 - r) / r * 100
                    lines.append((f"Measured vs calculated: {off:+.1f}%" + (" - gear ratio + tire size confirmed"
                                                                             if abs(off) <= cfg.WHEEL_CALC_MATCH_PCT
                                  else " - tire size or gear ratio may differ"),
                                  cfg.TIP_GREEN if abs(off) <= cfg.WHEEL_CALC_MATCH_PCT else cfg.TIP_AMBER, 10, True))
            else:
                for label, k in (("hybrid computer", "spd_hv"), ("engine computer", "spd_ecm"),
                                 ("brake computer", "spd_abs"), ("dashboard meter", "spd_meter")):
                    v = g(k)
                    lines.append((f"Car speed from {label} as wheel RPM: "
                                  f"{'--' if v is None else fmt_rpm(v * KMH_TO_WHEEL_RPM)}", TIP_FG, 10, False))
        if key == "ac":
            lines.append((f"Target speed: {fmt_rpm(g('ac_target'))} rpm", TIP_FG, 10, False))
        lines.append((f"Full colour at {top:,} rpm" + (f"     Ideal: {ideal}" if ideal else "")
                      + (f"     Thickest rotor at {TORQUE_MAX[key]:,} Nm" if key in TORQUE_MAX else ""), TIP_FG, 10, False))
        lines.append((info, TIP_FG, 10, False))
        lines.append(("Gear ratios, tire size, torque limits and descriptions: estimates, not Toyota specs (unconfirmed)",
                      DIM, 8, False))
        return name, lines

    # ---------- side panel ----------
    PANEL_ROWS = [("engine", "Engine"), ("eng_target", "Engine target"), ("mg1", "Generator (MG1)"),
                  ("mg2", "Drive motor (MG2)"), ("ring", "Ring gear (calculated)"),
                  ("fl", "Front left wheel"), ("fr", "Front right wheel"), ("rl", "Rear left wheel"),
                  ("rr", "Rear right wheel"), ("front_calc", "Front wheels from MG2"),
                  ("ac", "A/C compressor"), ("pump", "Coolant pump")]

    def build_panel(self, parent, app):
        panel_label(parent, "Unit: RPM (turns per minute)", TEXT, 10, (12, 0))
        legend(parent, app, SPIN_FWD, "stopped", "max", "Colour = how fast it's turning forwards")
        c = tk.Canvas(parent, height=int(16 * app.ui), width=int(cfg.LEGEND_WIDTH * app.ui), bg=BG, highlightthickness=0)
        c.pack(anchor="w", pady=(4, 0))
        for i in range(int(cfg.LEGEND_WIDTH * app.ui)):
            c.create_line(i, 0, i, int(16 * app.ui), fill=ramp(SPIN_REV, i / (cfg.LEGEND_WIDTH * app.ui)))
        panel_label(parent, "Purple = turning backwards", DIM, 9)
        panel_label(parent, "The rotor icons spin with the part (slowed down).\n"
                            "Tires: the tread rolls towards the front going forwards.\n"
                            "Ring gear: its teeth slide left to right going forwards.\n"
                            "Thicker + redder rotor = more twisting force (torque).", TEXT, 9, (6, 0))
        self.rows = reading_rows(parent, self.PANEL_ROWS, "Readings (rpm)")
        panel_label(parent, "All readings answered in your car's full test (2026-09-26)\nWheels use the stock 195/65R15 tire\n"
                            "Battery fan is shown in %, not rpm (no rpm reading)\n"
                            "Engine torque is estimated (its own reading stays at 0)\n"
                            "Gear ratios + torque limits are estimates (unconfirmed)", DIM, 9, (10, 0))

    def update_panel(self, values, now):
        rpm, _, _ = self.calc(values, now)
        mg2 = fresh(values, "mg2_rpm", now)
        vals = dict(rpm, eng_target=fresh(values, "eng_target", now),
                    front_calc=None if mg2 is None else mg2 / MG2_TO_WHEEL)
        for k, lbl in self.rows.items():
            v = vals[k]
            lbl.config(text=fmt_rpm(v), fg=DIM if v is None else (SPIN_REV_TEXT if v <= -1 else TEXT))




# ======================================================================
# Pressure view (kPa / psi / bar)
# ======================================================================
# key: (full colour at, ideal low, ideal high, warn below, warn above) in kPa. Training-data estimates (unconfirmed).
# PRESS_LIMITS (kPa: full colour, ideal low/high, warn below/above) are in config.py
PRESS_INFO = {
    "baro": ("Outside air pressure", "Outside air\npressure",
             "The air pressure around the car (absolute). It drops as you go up in altitude and changes a little "
             "with the weather. The engine computer uses it to get the fuel mix right."),
    "map": ("Intake manifold pressure", "Intake\nmanifold",
            "Air pressure inside the engine's intake (absolute). A low number means the throttle is mostly closed "
            "and the engine is 'sucking' (vacuum); close to outside pressure means the throttle is wide open - or "
            "the engine is stopped."),
    "ac": ("A/C refrigerant pressure", "A/C\nrefrigerant",
           "Pressure in the A/C's refrigerant line (gauge = above outside pressure). High while the compressor "
           "is running on a hot day, lower when it's off. Very high pressure makes the A/C shut itself off."),
    "evap": ("Fuel tank vapour pressure", "Fuel tank\nvapour",
             "Pressure of the gasoline vapour in the fuel tank system, relative to outside. The engine computer "
             "uses it to check for leaks (like a loose gas cap). Usually very close to zero."),
    "oil": ("Engine oil pressure switch", "Oil pressure\nswitch",
            "A simple on/off switch on the engine's oil system - there's no actual pressure number. On most "
            "Toyotas it closes (ON) when oil pressure is LOW, which lights the oil warning light; oil pressure "
            "only exists while the engine is turning. Meaning not confirmed for this car."),
}
PRESS_SOURCES = {
    "map": [("Hybrid computer", "map_hv"), ("Engine computer", "map_ecm"), ("Standard OBD (010B)", "map_obd")],
    "baro": [("Hybrid computer", "baro_hv"), ("Engine computer", "baro_ecm"), ("Standard OBD (0133)", "baro_obd")],
    "ac": [("Climate computer", "ac_press")],
    "evap": [("Standard OBD (0132)", "evap_press")],
}


class PressureView:
    name = "Pressure"
    units = [("kPa", "kPa"), ("psi", "psi"), ("bar", "bar")]
    groups = []
    notes = []
    places = [
        ("baro", "outside_air"), ("map", "intake_manifold"), ("ac", "ac_compressor"),
    ]
    components, shapes = placed(places)

    def __init__(self):
        self.unit = "kPa"

    def sensors(self):
        return PRESS

    def label(self, key):
        return PRESS_INFO[key][1]

    def fmt(self, kpa):
        if kpa is None:
            return "--"
        if self.unit == "psi":
            v, small = kpa * 0.1450377, abs(kpa) < 10
            return f"{v:.2f} psi" if small else f"{v:.1f} psi"
        if self.unit == "bar":
            return f"{kpa / 100:.3f} bar" if abs(kpa) < 10 else f"{kpa / 100:.2f} bar"
        return f"{kpa:.2f} kPa" if abs(kpa) < 10 else f"{kpa:.0f} kPa"

    @staticmethod
    def value(key, values, now):
        for _, k in PRESS_SOURCES.get(key, []):
            v = fresh(values, k, now)
            if v is not None:
                return v
        return None

    def state(self, key, v):
        full, lo, hi, warn_lo, warn_hi = PRESS_LIMITS[key]
        if (warn_lo is not None and v <= warn_lo) or (warn_hi is not None and v >= warn_hi):
            return "warn"
        return "ideal" if lo <= v <= hi else None

    def cell(self, key, values, now):
        if key == "oil":
            on = fresh(values, "oil_sw", now)
            if on is None:
                return Cell(NO_DATA, "--")
            return Cell(ramp(PRESS_RAMP, 0.6 if on >= 0.5 else 0.05), "ON" if on >= 0.5 else "off")
        v = self.value(key, values, now)
        if v is None:
            return Cell(NO_DATA, "--")
        return Cell(ramp(PRESS_RAMP, abs(v) / PRESS_LIMITS[key][0]), self.fmt(v).replace("-", "−"),
                    self.state(key, v))

    def wires(self, values, now):
        return []

    def tooltip(self, key, values, now):
        g = lambda k: fresh(values, k, now)
        name, _, info = PRESS_INFO[key]
        lines = []
        if key == "oil":
            on = g("oil_sw")
            lines.append((f"Switch: {'--' if on is None else ('ON' if on >= 0.5 else 'off')}", TIP_FG, 11, True))
            eng = g("eng_rpm") or g("eng_rpm_hv")
            if eng is not None:
                lines.append((f"Engine right now: {'running' if eng > 300 else 'stopped'} ({eng:,.0f} rpm)",
                              TIP_FG, 10, False))
        else:
            v = self.value(key, values, now)
            lines.append((f"Now: {self.fmt(v)}".replace("-", "−"), TIP_FG, 11, True))
            for label, k in PRESS_SOURCES[key]:
                lines.append((f"{label}: {self.fmt(g(k))}".replace("-", "−"), TIP_FG, 10, False))
            if key == "map":
                baro = self.value("baro", values, now)
                if v is not None and baro is not None:
                    lines.append((f"Engine vacuum (outside minus manifold): {self.fmt(baro - v)}", TIP_FG, 10, True))
            if key == "baro" and v is not None and 50 < v < 110:
                alt = 44330 * (1 - (v / 101.325) ** 0.1903)   # standard-atmosphere formula
                lines.append((f"That's roughly {alt:,.0f} m above sea level (weather shifts this a bit)",
                              TIP_FG, 10, False))
            full, lo, hi, warn_lo, warn_hi = PRESS_LIMITS[key]
            warn = " / ".join(x for x in ((f"below {self.fmt(warn_lo)}" if warn_lo is not None else ""),
                                          (f"above {self.fmt(warn_hi)}" if warn_hi is not None else "")) if x)
            lines.append((f"Ideal: {self.fmt(lo)} to {self.fmt(hi)}     Flashing red: {warn}".replace("-", "−"),
                           TIP_FG, 10, False))
        lines.append((info, TIP_FG, 10, False))
        tested = "All three sources tested in your car" if key in ("map", "baro") else "Tested in your car"
        lines.append((tested, DIM, 8, False))
        lines.append(("Limits and descriptions: estimates, not Toyota specs (unconfirmed)", DIM, 8, False))
        return name, lines

    PANEL_ROWS = [("map", "Intake manifold"), ("vac", "Engine vacuum"), ("baro", "Outside air"),
                  ("ac", "A/C refrigerant")]

    def build_panel(self, parent, app):
        unit_buttons(parent, self, app)
        legend(parent, app, PRESS_RAMP, "none", "high", "Colour = how much pressure")
        self.rows = reading_rows(parent, self.PANEL_ROWS, "Readings")
        panel_label(parent, "All readings answered in your car's full test (2026-09-26)\n"
                            "Absolute = including the air around us; gauge = above it\n"
                            "Not available on this car: fuel tank vapour pressure (no\n"
                            "answer), oil pressure switch (reply too short), tire\n"
                            "pressures, brake pressure (the brake sensor only gives a\n"
                            "voltage with no known conversion)\n"
                            "Limits are estimates (unconfirmed)", DIM, 9, (10, 0))

    def update_panel(self, values, now):
        g = lambda k: fresh(values, k, now)
        m, b = self.value("map", values, now), self.value("baro", values, now)
        vals = {"map": self.fmt(m), "baro": self.fmt(b), "ac": self.fmt(self.value("ac", values, now)),
                "vac": self.fmt(b - m) if m is not None and b is not None else "--"}
        for k, lbl in self.rows.items():
            lbl.config(text=vals[k].replace("-", "−"), fg=DIM if vals[k] == "--" else TEXT)
