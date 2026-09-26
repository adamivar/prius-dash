"""Dashboard views. Each view decides what the car boxes show, their colour and border,
the hover card, the side panel and (electrical view) the animated wires."""
import math
import tkinter as tk

import calc
from dataclasses import dataclass

from sensors import (ELEC, FINAL_DRIVE, KMH_TO_WHEEL_RPM, MG2_REDUCTION, ONOFF, PRESS, RING_TEETH, ROT, SENSORS,
                     SOC, STEER, ELEC_EXTRA, SUN_TEETH, TEMPS, TIRE_CIRCUMFERENCE_M, TORQUE)

BG = "#16181c"
BODY = "#23262d"
NO_DATA = "#33363d"
TEXT = "#e8e8e8"
DIM = "#8a8f99"
IDEAL = "#3ddc68"
WARN = "#ff3b3b"
TIP_FG = "#1a1a1a"
STALE_AFTER_S = 30  # other views refresh every ~8 s in the background, so allow a few misses before "(old)"
WARN_AT = 0.85  # flashing red border from 85% of the way to danger (all views)

HEAT = [(0.0, (47, 79, 111)), (0.6, (217, 162, 27)), (1.0, (227, 23, 27))]
CHARGE = [(0.0, (12, 12, 12)), (1.0, (255, 214, 0))]  # black = no current, yellow = too much


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
# 100 x 250 units, front at the top, driver (left-hand drive) on the left. Positions approximate (training data).
# Left channel x 4-16 is kept free for wires; inverter assembly + transmission sit at x 16-52, engine at x 55-92.
L, M, R = 16, 34.5, 52          # left column: left edge, middle split, right edge
HALF = 17.5
BATT_X0, BATT_X1, BATT_Y0 = 16, 88, 160
BLK_W = (BATT_X1 - BATT_X0 - 6 * 2) / 7    # 14 blocks, 2 rows of 7, 2-unit gaps
TB_W = (BATT_X1 - BATT_X0 - 2 * 1.5) / 3   # 3 battery temperature sensors across the same pack
LAYOUT = {
    "coolant_pump": (L, 1.5, HALF, 12),
    "outside_air": (34, 3, 28, 9),
    "ac_compressor": (66, 4, 26, 9),
    "dcdc": (L, 15, HALF, 12),
    "inv_coolant": (M, 15, HALF, 12),
    "booster": (L, 30, R - L, 15),
    "booster_upper": (L, 30, HALF, 15),
    "booster_lower": (M, 30, HALF, 15),
    "gen_inverter": (L, 51, HALF, 17),
    "drive_inverter": (M, 51, HALF, 17),
    "mg1": (L, 78, HALF, 20),
    "mg2": (M, 78, HALF, 20),
    "ring_gear": (L, 100, R - L, 10),
    # the wheels themselves (same rectangles the app draws as tires)
    "wheel_fl": (-1, 36, 7, 24), "wheel_fr": (94, 36, 7, 24),
    "wheel_rl": (-1, 196, 7, 24), "wheel_rr": (94, 196, 7, 24),
    "intake_air": (55, 16, 37, 9),
    "engine": (55, 28, 37, 56),
    "catalyst": (55, 87, 37, 13),
    "cabin_air": (16, 131, 22, 13),
    "evaporator": (40, 131, 22, 13),
    "batt_intake": (64, 141, 26, 15),
    "batt_tb1": (BATT_X0, BATT_Y0, TB_W, 39),
    "batt_tb2": (BATT_X0 + TB_W + 1.5, BATT_Y0, TB_W, 39),
    "batt_tb3": (BATT_X0 + 2 * (TB_W + 1.5), BATT_Y0, TB_W, 39),
    "aux_batt": (64, 211, 26, 16),
    # engine parts shown in the Pressure view sit on top of the engine's own spot
    "intake_manifold": (55, 28, 37, 13),
    "oil_pressure": (55, 70, 37, 12),
    "fuel_tank": (L, 146, 36, 11),
    # dashboard warning lights (2 rows of 3) and the brake lights at the back
    **{f"lamp{i}": (64 + (i % 3) * 9.5, 127.5 + (i // 3) * 6.5, 8.5, 5.5) for i in range(6)},
    "brake_light_l": (6, 237, 10, 7), "brake_light_r": (84, 237, 10, 7),
}
LAYOUT["batt_fan"] = LAYOUT["batt_intake"]
LAYOUT["steering_wheel"] = (18, 132, 17, 17)   # driver side, behind the dashboard line
LAYOUT["brake_actuator"] = (60, 100, 30, 12)   # brake actuator, engine bay near the firewall   # the fan sits in the battery's air-intake duct


def block_rect(i):
    """Block i (0-13), snaking: top row blocks 1-7 left to right, bottom row blocks 8-14 right to left."""
    col = i if i < 7 else 13 - i
    return BATT_X0 + col * (BLK_W + 2), BATT_Y0 if i < 7 else BATT_Y0 + 23, BLK_W, 16


def block_links():
    """Series wires 1->2->...->14 (drawn direction)."""
    out = []
    for i in range(13):
        x, y, w_, h = block_rect(i)
        if i == 6:  # block 7 (top right) down to block 8 (bottom right)
            out.append([(x + w_, y + h / 2), (x + w_ + 2, y + h / 2), (x + w_ + 2, y + 23 + h / 2), (x + w_, y + 23 + h / 2)])
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
    lw, lh = int(300 * app.ui), int(16 * app.ui)
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
        ("Inverter assembly", L - 2, 13, R - L + 4, 57),
        ("Transmission", L - 2, 76, R - L + 4, 36),
        ("Hybrid battery (under rear seat)", BATT_X0 - 2, BATT_Y0 - 2, BATT_X1 - BATT_X0 + 4, 43),
    ]
    components = [(key, *LAYOUT[place]) for key, place in [  # (sensor key, place on the car)
        ("ambient", "outside_air"), ("inv_coolant", "inv_coolant"),
        ("inv_mg1", "gen_inverter"), ("inv_mg2", "drive_inverter"),
        ("boost_upper", "booster_upper"), ("boost_lower", "booster_lower"),
        ("mg1", "mg1"), ("mg2", "mg2"),
        ("intake_air", "intake_air"), ("engine", "engine"), ("catalyst", "catalyst"),
        ("cabin", "cabin_air"), ("evap", "evaporator"), ("batt_intake", "batt_intake"),
        ("batt_tb1", "batt_tb1"), ("batt_tb2", "batt_tb2"), ("batt_tb3", "batt_tb3"),
        ("aux_batt", "aux_batt"),
    ]]

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
                lines.append(("DANGER - hotter than it should ever get", "#d42020", 10, True))
            elif self.state(s, v) == "warn":
                lines.append(("Getting close to danger", "#d42020", 10, True))
            elif v > hi:
                lines.append(("Warm - above ideal, still below danger", "#b86b00", 10, True))
            elif v >= lo:
                lines.append(("Ideal - right where it should be", "#1c8a3a", 10, True))
            else:
                lines.append(("Cool - below its normal working range (normal soon after starting)",
                              "#2f5f8f", 10, True))
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
# Current limits in amps: (ideal up to, too much at). Training-data estimates (unconfirmed).
AMP_LIMITS = {"brake_act": (2, 6), "hvbatt": (40, 120), "boost": (40, 130), "inv1": (40, 100), "mg1": (40, 100),
              "inv2": (50, 150), "mg2": (50, 150), "ac": (8, 20)}
AUX_IDEAL, AUX_LOW, AUX_HIGH = (13.2, 14.8), 12.0, 15.0  # 12 V battery volts while READY (unconfirmed)

ELEC_INFO = {
    "brake_act": ("Brake actuator",
                  "The electronically controlled brake unit. Its solenoid valves meter brake fluid to the wheels "
                  "and blend friction braking with regen. One of the few 12 V parts with a real current reading."),
    "hvbatt": ("Hybrid battery",
               "The big battery under the rear seat (nickel-metal hydride, about 200 V, 14 blocks). "
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
BLK_IDEAL_DEV, BLK_WARN_DEV = 0.15, 0.30


def fmt_watts(w_):
    return f"{w_ / 1000:.1f} kW" if abs(w_) >= 1000 else f"{w_:.0f} W"


class ElectricalView:
    name = "Electrical"
    units = [("V", "Volts"), ("A", "Amps"), ("W", "Watts")]
    groups = []
    components = [(key, *LAYOUT[place]) for key, place in [  # (part key, place on the car)
        ("dcdc", "dcdc"), ("ac", "ac_compressor"), ("boost", "booster"),
        ("inv1", "gen_inverter"), ("inv2", "drive_inverter"), ("mg1", "mg1"), ("mg2", "mg2"),
        ("aux", "aux_batt"), ("pump", "coolant_pump"), ("fan", "batt_fan"), ("brake_act", "brake_actuator"),
        ("lamp_mil", "lamp0"), ("lamp_abs", "lamp1"), ("lamp_brake", "lamp2"),
        ("lamp_slip", "lamp3"), ("lamp_ecb", "lamp4"), ("buzzer", "lamp5"),
        ("brake_l", "brake_light_l"), ("brake_r", "brake_light_r"),
    ]] + [(f"blk{i + 1:02d}", *block_rect(i)) for i in range(14)]
    notes = [("Hybrid battery (under rear seat) - 14 blocks in series", 52, BATT_Y0 + 46),
             ("Warning lights", 78, 124)]
    # (wire key, points drawn in the "positive" current direction, label, where the label goes:
    #  "l"/"r" = beside the longest segment, or (x, y) = fixed spot, text to the right)
    wire_paths = [
        ("plus", [(L, 168), (13, 168), (13, 42), (L, 42)], "+ out", (15, 104)),
        ("minus", [(L, 33), (9.5, 33), (9.5, 191), (L, 191)], "− return", (15, 110)),
        *[("link", pts, "", "r") for pts in block_links()],
        ("vh_gen", [(L + HALF / 2, 45), (L + HALF / 2, 51)], "", "r"),
        ("vh_drive", [(M + HALF / 2, 45), (M + HALF / 2, 51)], "", "r"),
        ("ac_gen", [(L + HALF / 2, 68), (L + HALF / 2, 78)], "", "r"),
        ("ac_drive", [(M + HALF / 2, 68), (M + HALF / 2, 78)], "", "r"),
        ("ac_comp", [(R, 37), (58, 37), (58, 9), (66, 9)], "DC", "r"),
        ("dcdc", [(L + HALF / 2, 30), (L + HALF / 2, 27)], "", "r"),
        ("lv12", [(L, 21), (6, 21), (6, 219), (64, 219)], "12 V - not measured", (20, 216)),
        # 12 V things that only report on/off: dashed, with slow arrows while they're on
        ("lv_pump", [(6, 21), (6, 7.5), (L, 7.5)], "", "r"),
        ("lv_fan", [(90, 219), (93, 219), (93, 148.5), (90, 148.5)], "", "r"),
        ("lv_brake_l", [(11, 219), (11, 237)], "", "r"),
        ("lv_brake_r", [(77, 227), (77, 240.5), (84, 240.5)], "", "r"),
        ("lv_brake_act", [(93, 148.5), (93, 106), (90, 106)], "", "r"),
    ]
    LAMPS = {  # key: (box text, colour when on, is it a warning?)
        "lamp_mil": ("ENG", "#ffb000", True), "lamp_abs": ("ABS", "#ffb000", True),
        "lamp_brake": ("BRAKE", "#ff3030", True), "lamp_slip": ("SLIP", "#ffb000", True),
        "lamp_ecb": ("ECB", "#ff3030", True), "buzzer": ("BUZZ", "#ffb000", True),
        "brake_l": ("", "#ff2020", False), "brake_r": ("", "#ff2020", False),
    }
    FLAGS = {  # extra on/off signals that belong to a part: shown in its hover, bad ones make it flash red
        "boost": [("conv_gate", False), ("conv_shutdown", True), ("conv_fail", True), ("ov_conv", True)],
        "inv1": [("mg1_gate", False), ("mg1_inv_shutdown", True), ("mg1_inv_fail", True), ("ov_inv", True)],
        "inv2": [("mg2_gate", False), ("mg2_inv_shutdown", True), ("mg2_inv_fail", True), ("ov_inv", True)],
        "ac": [("ac_gate", False)],
        "dcdc": [("dcdc_prohibit", False)],
    }
    SOC_IDEAL = (40, 80)  # the Prius normally keeps the battery between these (training data, unconfirmed)

    def __init__(self):
        self.unit = "A"

    def sensors(self):
        return ELEC + ONOFF + [SOC] + ELEC_EXTRA + [SENSORS[k] for k in ("fan_pct", "fan_relay", "fan_volts", "pump_rpm")]

    SOLENOIDS = ("sol_sla", "sol_slr", "sol_ssc", "sol_scc", "sol_smc", "sol_src")

    def brake_amps(self, values, now):
        amps = [fresh(values, k, now) for k in self.SOLENOIDS]
        return None if None in amps else sum(amps)

    SHORT = {"brake_act": "Brake\nactuator", "dcdc": "DC-DC", "inv1": "Generator\ninverter", "inv2": "Drive\ninverter",
             "mg1": "Generator\n(MG1)", "mg2": "Drive motor\n(MG2)", "pump": "Pump", "fan": "Battery fan"}

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
        colour = "#3ddc68" if soc is not None and lo <= soc <= hi else "#ffb000"
        text = "Battery charge: --" if soc is None else f"Battery charge: {soc:.0f}%"
        cin, cout = fresh(values, "chg_lim", now), fresh(values, "dis_lim", now)
        if cin is not None and cout is not None:
            text += f"   ·   can take in {abs(cin):.0f} kW / give {cout:.0f} kW"
        return [dict(rect=(BATT_X0, BATT_Y0 + 41, BATT_X1 - BATT_X0, 4), fraction=None if soc is None else soc / 100,
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
            colour = "#d42020" if abs(dev) >= BLK_WARN_DEV else "#1c8a3a" if abs(dev) <= BLK_IDEAL_DEV else "#b86b00"
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
            dark = "#3a0d0d" if key in ("brake_l", "brake_r") else "#1b1c20"
            return Cell(colour if on else dark, "", "warn" if on and warning else None)
        if key == "pump":
            on = self.on(values, now, "pump_on")
            if on is None:
                return Cell(NO_DATA, "--", dashed=True)
            duty = fresh(values, "pump_duty", now)
            text = ("ON" + (f" {duty:.0f}%" if duty is not None else "")) if on else "off"
            return Cell(ramp(CHARGE, 0.45) if on else ramp(CHARGE, 0), text, dashed=True)
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
                out[i] = (pts, a, "" if a is None else f"12 V · {a:.2f} A", (61, 114), None)
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
                lines.append((f"Right now it's {word}", "#1c8a3a" if word in ("charging", "generating") else "#b86b00",
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
                          "#d42020" if bad and on else TIP_FG, 10, bool(bad and on)))
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
        self.on_now.config(wraplength=int(310 * app.ui))
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
SPIN_FWD = [(0.0, (20, 24, 30)), (1.0, (41, 199, 255))]   # stopped -> max, turning forwards (cyan)
SPIN_REV = [(0.0, (20, 24, 30)), (1.0, (208, 82, 255))]   # stopped -> max, turning backwards (magenta)
PLANET = SUN_TEETH + RING_TEETH
MG2_TO_WHEEL = MG2_REDUCTION * FINAL_DRIVE                # about 8.6 : 1

# Max RPM (full colour) and ideal range per part. Training-data estimates (unconfirmed).
SPIN_LIMITS = {
    "engine": (5200, "0 (off) or 1,000-2,800"), "mg1": (10000, "up to 6,000 either way"),
    "mg2": (13500, "up to 9,000"), "ring": (5000, None),
    "fl": (1400, "within 3% of the other wheels"), "fr": (1400, "within 3% of the other wheels"),
    "rl": (1400, "within 3% of the other wheels"), "rr": (1400, "within 3% of the other wheels"),
    "ac": (9000, "up to 6,000"), "pump": (6000, "500-5,000"),
}
# Max torque (Nm) = thickest, reddest rotor. Training-data estimates (unconfirmed).
TORQUE_MAX = {"engine": 142, "mg1": 100, "mg2": 207, "ring": 650, "fl": 1050, "fr": 1050}
WHEELS = ("fl", "fr", "rl", "rr")
SLIP_IDEAL, SLIP_WARN = 0.03, 0.15   # a wheel this far from the average of the four = slipping/locking

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
    "ring": ("Planetary ring gear", "Ring gear (calculated)",
             "The output of the power-split planetary gear: engine drives the planet carrier, the generator is "
             "the sun gear, and the ring gear goes to the wheels. It isn't measured - it's calculated two ways "
             "so you can see if the gear numbers are right."),
    "ac": ("A/C compressor", "A/C\ncompressor",
           "Electric A/C compressor motor. It changes speed to match how much cooling is needed, and stops "
           "when the A/C isn't needed."),
    "pump": ("Inverter coolant pump", "Pump",
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
    groups = [("Transmission", L - 2, 76, R - L + 4, 36)]
    notes = []
    components = [(key, *LAYOUT[place]) for key, place in [
        ("engine", "engine"), ("mg1", "mg1"), ("mg2", "mg2"), ("ring", "ring_gear"),
        ("ac", "ac_compressor"), ("pump", "coolant_pump"), ("fan", "batt_fan"),
        ("fl", "wheel_fl"), ("fr", "wheel_fr"), ("rl", "wheel_rl"), ("rr", "wheel_rr"),
        ("steer", "steering_wheel"),
    ]]
    STEER_MAX = 665   # full lock measured in your car (degrees)

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
        if avg < 40:  # below ~5 km/h the 1.28 km/h sensor steps are too coarse to judge slip
            return None, None
        dev = (rpm[key] - avg) / avg
        return ("warn" if abs(dev) >= SLIP_WARN else "ideal" if abs(dev) <= SLIP_IDEAL else None), dev

    def state(self, key, r, rpm):
        top, _ = SPIN_LIMITS[key]
        if abs(r) / top >= WARN_AT:
            return "warn"
        a = abs(r)
        if key == "engine":
            return "ideal" if a < 1 or 1000 <= a <= 2800 else None
        if key in WHEELS:
            return self.wheel_state(key, rpm)[0]
        ok = {"mg1": a <= 6000, "mg2": a <= 9000, "ac": a <= 6000, "pump": 500 <= a <= 5000}.get(key)
        return "ideal" if ok else None

    def cell(self, key, values, now):
        if key == "steer":
            a = self.steer_angle(values, now)
            if a is None:
                return Cell(NO_DATA, "--")
            side = "straight" if abs(a) < 5 else ("left" if a > 0 else "right")
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
            out.append(("fan", pct * 50, None))
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
                          "#b83a1a", 10, True))
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
                lines.append((f"Sources agree within {spread:.0f} rpm" if spread <= 50 else
                              f"Sources differ by {spread:.0f} rpm (normal while revving - they're read at different moments)",
                              "#1c8a3a" if spread <= 50 else "#b86b00", 10, True))
            lines.append((f"Hybrid system's target engine speed: {fmt_rpm(g('eng_target'))} rpm", TIP_FG, 10, False))
        if key in ("mg1", "mg2", "ring") and None not in (ring_planet, ring_mg2):
            lines.append((f"Ring gear from engine + generator: {fmt_rpm(ring_planet)} rpm", TIP_FG, 10, False))
            lines.append((f"Ring gear from drive motor ÷ {MG2_REDUCTION}: {fmt_rpm(ring_mg2)} rpm", TIP_FG, 10, False))
            diff = abs(ring_planet - ring_mg2)
            lines.append(("Gear numbers check out (within 30 rpm)" if diff <= 30 else
                          f"Off by {diff:.0f} rpm - gear numbers may be wrong, or readings taken at different moments",
                          "#1c8a3a" if diff <= 30 else "#b86b00", 10, True))
        if key in WHEELS:
            kmh = g(f"whl_{key}")
            lines.append((f"Wheel speed sensor: {'--' if kmh is None else f'{kmh:.1f} km/h'}", TIP_FG, 10, False))
            state, dev = self.wheel_state(key, rpm)
            if dev is not None:
                lines.append((f"{abs(dev) * 100:.1f}% {'faster' if dev > 0 else 'slower'} than the average wheel",
                              "#d42020" if state == "warn" else "#1c8a3a" if state == "ideal" else "#b86b00", 10, True))
            if key in ("fl", "fr"):
                calc_mg2 = None if g("mg2_rpm") is None else g("mg2_rpm") / MG2_TO_WHEEL
                calc_ring = None if ring_planet is None else ring_planet / FINAL_DRIVE
                lines.append((f"Calculated from drive motor ÷ {MG2_TO_WHEEL:.2f}: {fmt_rpm(calc_mg2)} rpm", TIP_FG, 10, False))
                lines.append((f"Calculated from engine + generator gearing: {fmt_rpm(calc_ring)} rpm", TIP_FG, 10, False))
                if r is not None and calc_mg2 is not None and r > 40:
                    off = (calc_mg2 - r) / r * 100
                    lines.append((f"Measured vs calculated: {off:+.1f}%" + (" - gear ratio + tire size confirmed" if abs(off) <= 3
                                  else " - tire size or gear ratio may differ"),
                                  "#1c8a3a" if abs(off) <= 3 else "#b86b00", 10, True))
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
        c = tk.Canvas(parent, height=int(16 * app.ui), width=int(300 * app.ui), bg=BG, highlightthickness=0)
        c.pack(anchor="w", pady=(4, 0))
        for i in range(int(300 * app.ui)):
            c.create_line(i, 0, i, int(16 * app.ui), fill=ramp(SPIN_REV, i / (300 * app.ui)))
        panel_label(parent, "Purple = turning backwards", DIM, 9)
        panel_label(parent, "The rotor icons spin with the part (slowed down).\n"
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


SPIN_REV_TEXT = "#d88cff"


# ======================================================================
# Pressure view (kPa / psi / bar)
# ======================================================================
PRESS_RAMP = [(0.0, (20, 24, 30)), (1.0, (232, 236, 245))]   # none -> high (white)
# key: (full colour at, ideal low, ideal high, warn below, warn above) in kPa. Training-data estimates (unconfirmed).
PRESS_LIMITS = {
    "map": (105, 20, 85, None, 110),
    "baro": (105, 80, 105, 60, 110),
    "ac": (3200, 600, 2200, None, 2700),
    "evap": (5, -2.0, 1.5, -4.0, 4.0),
}
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
    components = [(key, *LAYOUT[place]) for key, place in [
        ("baro", "outside_air"), ("map", "intake_manifold"), ("ac", "ac_compressor"),
    ]]

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
