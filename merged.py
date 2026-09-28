"""Everything view: the Temperature, Electrical, Spinning and Pressure views laid over one car.

Each part merges every reading the other views have for it, and shows them in different ways at once:
  fill colour  = temperature where the part has one (otherwise current, speed or pressure)
  rotor / tread / teeth = how fast it turns; thicker + redder = more torque
  bar along the top edge = pressure
  wires + arrows = current, exactly as in the Electrical view (thicker + faster = more amps)
  flashing red border = any reading near danger.
The text shows the part's first readings; the hover card stacks every reading from every view.
"""
import tkinter as tk
from dataclasses import dataclass

import calc
import config as cfg
from config import DIM, IDEAL, PRESS_LIMITS, PRESS_RAMP, TEXT, WARN
from views import (BATT_X0, BG, BODY, LAYOUT, TB_W, WHEELS_RECT, Cell, ElectricalView, L, PressureView, R,
                   SpinView, TemperatureView, block_rect, fresh, panel_label, ramp, reading_rows)


@dataclass
class MergedPart:
    key: str
    label: str
    rect: tuple
    shape: str
    sources: list          # [(view code, that view's key)] in priority order: t / e / s / p / b (brakes)
    show: int = 1          # how many readings the text shows
    sep: str = "\n"        # between those readings
    top: str = None        # top-edge bar: pressure key in the Pressure view, "brake" (brake pressure), or None


# Where things go. Mostly the shared car map; a few parts that would sit on top of each other move:
# outside air sits beside the engine's air intake, the brake actuator drops to the cowl under the ring gear, cabin air
# goes to the passenger side of the dash, the evaporator behind the warning lights, and the 3 battery temperature
# sensors become a strip along the front edge of the pack (their real spots are inside it).
E0 = LAYOUT["engine"][0]
TB_Y = 174.5
PARTS = [
    MergedPart("dcdc", "DC-DC", LAYOUT["dcdc"], "finned", [("e", "dcdc")]),
    MergedPart("pump", "Inverter\ncoolant pump", LAYOUT["coolant_pump"], "rounded",
               [("t", "inv_coolant"), ("s", "pump"), ("e", "pump")]),
    MergedPart("ac", "A/C compressor", LAYOUT["ac_compressor"], "drum", [("e", "ac"), ("s", "ac"), ("p", "ac")],
               top="ac"),
    MergedPart("boost_top", "Booster (top)", LAYOUT["booster_upper"], "finned", [("t", "boost_upper"), ("e", "boost")]),
    MergedPart("boost_bottom", "Booster (bottom)", LAYOUT["booster_lower"], "finned",
               [("t", "boost_lower"), ("e", "boost")]),
    MergedPart("inv2", "Drive inverter", LAYOUT["drive_inverter"], "finned", [("t", "inv_mg2"), ("e", "inv2")]),
    MergedPart("inv1", "Generator inverter", LAYOUT["gen_inverter"], "finned", [("t", "inv_mg1"), ("e", "inv1")]),
    MergedPart("mg2", "Drive motor\n(MG2)", LAYOUT["mg2"], "drum", [("t", "mg2"), ("e", "mg2"), ("s", "mg2")]),
    MergedPart("mg1", "Generator\n(MG1)", LAYOUT["mg1"], "drum", [("t", "mg1"), ("e", "mg1"), ("s", "mg1")]),
    MergedPart("ring", "Ring gear", (L, 74, R - L, 7.5), "geartread", [("s", "ring")]),
    MergedPart("brake_act", "Brake actuator", (L, 82.5, R - L, 10.5), "valveblock",
               [("e", "brake_act"), ("b", "brake_act")], top="brake"),
    MergedPart("outside", "Outside air", (E0, 17.5, 18, 13), "rounded", [("t", "ambient"), ("p", "baro")],
               top="baro"),
    MergedPart("intake", "Air box", (E0 + 19, 17.5, 15, 13), "airbox", [("t", "intake_air")]),
    MergedPart("engine", "Engine", (E0, 31.5, 34, 38.5), "engine", [("t", "engine"), ("s", "engine"), ("p", "map")],
               show=3, top="map"),
    MergedPart("catalyst", "Catalytic converter", LAYOUT["catalyst"], "canister", [("t", "catalyst")]),
    # tires a touch narrower than elsewhere so the 12 V wire down the left side clears them
    *[MergedPart(k, k.upper(), WHEELS_RECT[k] if cfg.PHONE_LAYOUT else
                 (WHEELS_RECT[k][0] + (-0.5 if k[1] == "l" else 0.5), WHEELS_RECT[k][1], 6.5, WHEELS_RECT[k][3]),
                 "tread", [("s", k), ("b", k)]) for k in ("fl", "fr", "rl", "rr")],
    MergedPart("steer", "Steering", LAYOUT["steering_wheel"], "circle", [("s", "steer")]),
    *[MergedPart(k, "", LAYOUT[f"lamp{i}"], "lamp", [("e", k)]) for i, k in
      enumerate(("lamp_mil", "lamp_abs", "lamp_brake", "lamp_slip", "lamp_ecb", "buzzer", "lamp_cruise", "lamp_belt"))],
    MergedPart("cabin", "Cabin air", (66, 99, 24, 13), "pill", [("t", "cabin")]),
    MergedPart("evap", "A/C evaporator", (39, 122.5, 22, 13), "core", [("t", "evap")]),
    MergedPart("inlet", "Air inlet", (66, 114, 24, 13), "vent", [("t", "inlet")]),
    MergedPart("blend", "Heater mix", (39, 137.5, 22, 13), "rounded", [("t", "blend")]),
    MergedPart("sun", "Sun", (62, 93.5, 16, 5.5), "pill", [("t", "sun")]),
    MergedPart("fan", "Battery fan", (64, 160, 26, 13), "fan", [("t", "batt_intake"), ("s", "fan"), ("e", "fan")]),
    *[MergedPart(f"tb{i}", f"Temp {i}", (BATT_X0 + (i - 1) * (TB_W + 1.5), TB_Y, TB_W, 9), "rounded",
                 [("t", f"batt_tb{i}")]) for i in (1, 2, 3)],
    *[MergedPart(f"blk{i + 1:02d}", "", block_rect(i), "module", [("e", f"blk{i + 1:02d}")]) for i in range(14)],
    MergedPart("aux", "12V battery", LAYOUT["aux_batt"], "battery", [("t", "aux_batt"), ("e", "aux")], show=2,
               sep="   "),
    MergedPart("brake_l", "", LAYOUT["brake_light_l"], "taillight_l", [("e", "brake_l")]),
    MergedPart("brake_r", "", LAYOUT["brake_light_r"], "taillight_r", [("e", "brake_r")]),
]
BAR_H = 1.4   # pressure bar height, drawing units


class EverythingView:
    name = "Everything"
    units = []

    def __init__(self):
        from brakes import BrakesView   # here, not at the top: brakes.py imports views too
        self.src = {"t": TemperatureView(), "e": ElectricalView(), "s": SpinView(), "p": PressureView(),
                    "b": BrakesView()}
        self.parts = {p.key: p for p in PARTS}
        self.components = [(p.key, *p.rect) for p in PARTS]
        self.shapes = {p.key: p.shape for p in PARTS}
        self.from_spin = {k: p.key for p in PARTS for code, k in p.sources if code == "s"}
        self.groups = []
        self.notes = [(t if not t.startswith("Warning") else "Warning lights", x, y) for t, x, y in self.src["e"].notes]

    def sensors(self):
        seen, out = set(), []
        for v in self.src.values():
            for s in v.sensors():
                if s.key not in seen:
                    seen.add(s.key)
                    out.append(s)
        return out

    def label(self, key):
        p = self.parts[key]
        return self.src["e"].label(key) if p.key.startswith(("lamp_", "buzzer", "blk")) else p.label

    # ---------- the parts ----------
    def cell(self, key, values, now):
        p = self.parts[key]
        cells = [self.src[code].cell(k, values, now) for code, k in p.sources]
        have = [c for c in cells if c.text not in ("--",)]
        first = have[0] if have else cells[0]
        states = [c.state for c in cells]
        state = "warn" if "warn" in states else ("ideal" if "ideal" in states else None)
        texts = [c.text.replace("\n", " ") for c in have if c.text]
        ring = next((c.ring for c in cells if c.ring), None)
        return Cell(first.fill, p.sep.join(texts[:p.show]) if texts else ("" if not first.text else "--"), state,
                    first.dashed, ring)

    def spinners(self, values, now):
        return [(self.from_spin[k], *rest) for k, *rest in self.src["s"].spinners(values, now) if k in self.from_spin]

    def wires(self, values, now):
        out = self.src["e"].wires(values, now)
        keys = [k for k, *_ in self.src["e"].wire_paths]
        i = keys.index("lv_brake_act")           # the brake actuator moved: re-route its 12 V feed
        pts = [(self.src["e"].RIGHT_X, 174.5), (self.src["e"].RIGHT_X, 87.75), (R, 87.75)]
        out[i] = (pts, out[i][1], out[i][2], (E0 + 1, 90.5), *out[i][4:])
        i = keys.index("ac_comp")                # its label would hide under the outside-air part; the A/C shows amps
        out[i] = (out[i][0], out[i][1], "", *out[i][3:])
        return out

    def overlays(self, values, now):
        """The battery charge bar, plus a thin pressure bar along the top edge of the parts that have a pressure."""
        bars = list(self.src["e"].overlays(values, now))
        for p in PARTS:
            x, y, w, h = p.rect
            inset = min(w, h) * (0.35 if p.shape in ("drum", "rounded", "pill", "fan", "canister") else 0.12)
            if p.top == "brake":
                v = fresh(values, "brake_v", now)
                lo, hi = cfg.BRAKE_V_RANGE
                frac = None if v is None else max(0.0, (v - lo) / (hi - lo))
                bars.append(dict(rect=(x + inset, y + 0.6, w - 2 * inset, BAR_H), fraction=frac,
                                 colour=ramp(PRESS_RAMP, frac or 0), text=""))
            elif p.top:
                v = PressureView.value(p.top, values, now)
                frac = None if v is None else abs(v) / PRESS_LIMITS[p.top][0]
                bars.append(dict(rect=(x + inset, y + 0.6, w - 2 * inset, BAR_H), fraction=frac,
                                 colour=ramp(PRESS_RAMP, frac or 0), text=""))
        return bars

    # ---------- hover: every reading from every view ----------
    def tooltip(self, key, values, now):
        p = self.parts[key]
        lines = []
        names = {"t": "TEMPERATURE", "e": "ELECTRICAL", "s": "SPINNING", "p": "PRESSURE", "b": "BRAKES"}
        for code, k in p.sources:
            title, sub = self.src[code].tooltip(k, values, now)
            if len(p.sources) > 1:
                lines.append((f"{names[code]}  ·  {title}", cfg.TIP_AMBER, 10, True))
            lines += sub
        return (p.label or self.label(key)).replace("\n", " "), lines

    # ---------- side panel ----------
    PANEL_ROWS = [("soc", "Battery charge"), ("amps", "Battery current (− = charging)"), ("speed", "Speed"),
                  ("rpm", "Engine speed"), ("coolant", "Engine coolant"), ("econ", "Economy right now")]

    def build_panel(self, parent, app):
        for code, title in (("t", "Temperature"), ("e", "Electrical"), ("p", "Pressure")):
            view = self.src[code]
            panel_label(parent, title, pady=(8, 0))
            row = tk.Frame(parent, bg=BG)
            row.pack(anchor="w")
            var = tk.StringVar(value=view.unit)

            def pick(v=view, var=var):
                v.unit = var.get()
                app.refresh()
            for unit, text in view.units:
                tk.Radiobutton(row, text=text, value=unit, variable=var, command=pick, bg=BG, fg=TEXT,
                               selectcolor=BODY, activebackground=BG, activeforeground=TEXT,
                               font=("Segoe UI", 10), indicatoron=False, padx=6, pady=2).pack(side="left", padx=(0, 4))
            setattr(self, f"_var_{code}", var)
        panel_label(parent, "How to read it", pady=(12, 2))
        for text, colour in (("Fill colour = temperature (blue cool → red hot);\nparts without one use current / speed",
                              TEXT),
                             ("Top-edge bar = pressure (engine, A/C, air, brakes)", TEXT),
                             ("Wheel ring = ABS / stability / traction control\nworking it (see the Brakes view)", TEXT),
                             ("Rotor / tread / teeth = turning; redder = more torque", TEXT),
                             ("Wire arrows = current direction and size", TEXT),
                             ("Green border = all readings ideal", IDEAL),
                             ("Flashing red border = a reading near danger", WARN),
                             ("Hover over a part for every reading", DIM)):
            panel_label(parent, text, colour, 9)
        self.rows = reading_rows(parent, self.PANEL_ROWS, "Highlights")
        panel_label(parent, "Reads every car view's sensors at once, so each\nreading updates a bit slower than in "
                            "its own view", DIM, 9, (10, 0))

    def update_panel(self, values, now):
        g = lambda k: fresh(values, k, now)
        t = self.src["t"]
        rpm = g("eng_rpm") if g("eng_rpm") is not None else g("eng_rpm_hv")
        coolant, spd, econ = g("engine"), calc.speed_kmh(values, now), calc.economy_l_100km(values, now)
        vals = {"soc": None if g("soc") is None else f"{g('soc'):.1f}%",
                "amps": None if g("batt_amps") is None else f"{g('batt_amps'):+.1f} A",
                "speed": None if spd is None else f"{spd:.0f} km/h",
                "rpm": None if rpm is None else f"{rpm:,.0f} rpm",
                "coolant": None if coolant is None else t.fmt(coolant),
                "econ": None if econ is None else f"{econ:.1f} L/100km"}
        for k, lbl in self.rows.items():
            lbl.config(text=vals[k] or "--", fg=DIM if vals[k] is None else TEXT)
