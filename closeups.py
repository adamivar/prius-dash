"""Close-up views: Engine and Battery.

Unlike the car views, these draw a diagram of just that system and show every reading for each part.
Units are mixed on purpose here (each number carries its own unit); temperatures follow the °C/°F switch.
"""
import tkinter as tk
from dataclasses import dataclass, field
from typing import Callable

import calc
import specs
from calc import TRACKER

from sensors import BATTERY, ELEC, ELEC_EXTRA, ENGINE, PRESS, ROT, SENSORS, SOC, TEMPS, TRIP_KEYS
from views import (BATT_X0, BG, BLK_IDEAL_DEV, BLK_WARN_DEV, DIM, HEAT, IDEAL, NO_DATA, TEXT, TIP_FG, WARN, WARN_AT,
                   AUX_HIGH, AUX_IDEAL, AUX_LOW, Cell, fresh, legend, panel_label, ramp, reading_rows, unit_buttons)

LEVEL = [(0.0, (22, 26, 32)), (1.0, (70, 190, 160))]
# line / arrow colours for what flows between parts
AIR = {"line": "#2f5872", "arrow": "#8fd3ff"}
EXHAUST = {"line": "#5a4632", "arrow": "#d9a877"}
FUEL = {"line": "#6a4a1a", "arrow": "#ffb347"}
HOT = {"line": "#6a2a2a", "arrow": "#ff6b6b"}
COOL = {"line": "#24466a", "arrow": "#6bb5ff"}
HV = {"line": "#6b5a12", "arrow": "#ffe14d"}
LV = {"line": "#a89a50", "arrow": "#ffe14d"}


@dataclass
class Flow:
    """Something passing between two parts (air, fuel, coolant, electricity) drawn as an animated line.
    amount(values, now) -> (amount or None, active): amount drives arrow speed/width (e.g. g/s of air, amps);
    None + active=True = moving but not measured (slow fixed arrows)."""
    points: list
    style: dict
    amount: Callable
    label: str = ""
    side: object = "r"     # dark -> teal: "how high is it"
DEVIATE = [(0.0, (40, 58, 70)), (1.0, (227, 23, 27))]    # battery block: even -> far from the others


@dataclass
class Part:
    key: str
    title: str                        # box label
    rect: tuple                       # x, y, w, h in the 100 x 250 close-up
    readings: list                    # (label, sensor key or function(values, now), unit, decimals)
    show: tuple = (0,)                # which readings appear in the box
    colour: Callable = None           # (values, now) -> (ramp, 0..1) or None
    state: Callable = None            # (values, now) -> None / "ideal" / "warn"
    info: str = ""
    extra_keys: tuple = field(default_factory=tuple)   # more sensors to poll for this part
    tags: tuple = ()                  # short word shown before each boxed number (same order as `show`)


def temp_state(sensor_key):
    """Ideal / warn for a temperature using the Temperature view's limits."""
    s = SENSORS[sensor_key]

    def f(values, now):
        v = fresh(values, sensor_key, now)
        if v is None:
            return None
        if (v - s.cold) / (s.danger - s.cold) >= WARN_AT:
            return "warn"
        return "ideal" if s.ideal[0] <= v <= s.ideal[1] else None
    return f


def heat(sensor_key, lo, hi):
    return lambda values, now: (None if fresh(values, sensor_key, now) is None
                                else (HEAT, (fresh(values, sensor_key, now) - lo) / (hi - lo)))


def level(sensor_key, top, scheme=LEVEL):
    return lambda values, now: (None if fresh(values, sensor_key, now) is None
                                else (scheme, abs(fresh(values, sensor_key, now)) / top))


def first(*keys):
    """Value from the first of several sources that has data."""
    def f(values, now):
        for k in keys:
            v = fresh(values, k, now)
            if v is not None:
                return v
        return None
    return f


class CloseupView:
    scene = "closeup"
    units = [("C", "°C"), ("F", "°F")]
    parts = []
    title = ""
    groups = []
    highlights = []                   # (label, reading function or key, unit, decimals) for the side panel
    about = ""
    poll_extra = ()                   # sensors used inside calculated readings (so they get polled too)
    flows = []

    def __init__(self):
        self.unit = "C"
        self.by_key = {p.key: p for p in self.parts}
        self.components = [(p.key, *p.rect) for p in self.parts]
        self.notes = [(self.title, 50, -3)]

    # ---------- values ----------
    def sensors(self):
        keys = []
        for p in self.parts:
            keys += [src for _, src, _, _ in p.readings if isinstance(src, str)] + list(p.extra_keys)
        for _, src, _, _ in self.highlights:
            if isinstance(src, str):
                keys.append(src)
        keys += list(self.poll_extra)
        seen, out = set(), []
        for k in keys:
            if k in SENSORS and k not in seen:
                seen.add(k)
                out.append(SENSORS[k])
        return out

    @staticmethod
    def value(src, values, now):
        return src(values, now) if callable(src) else fresh(values, src, now)

    def fmt(self, v, unit, dec):
        if v is None:
            return "--"
        if isinstance(v, str):
            return v
        if unit == "on/off":
            return "ON" if v >= 0.5 else "off"
        if unit == "°C" and self.unit == "F":
            v, unit = v * 9 / 5 + 32, "°F"
        return f"{v:,.{dec}f}{'' if unit in ('', '%') or unit.startswith('°') else ' '}{unit}".replace("-", "−")

    # ---------- the diagram ----------
    def label(self, key):
        return self.by_key[key].title

    def cell(self, key, values, now):
        p = self.by_key[key]
        texts = [self.fmt(self.value(p.readings[i][1], values, now), *p.readings[i][2:]) for i in p.show]
        if all(t == "--" for t in texts):
            return Cell(NO_DATA, "--")
        texts = [f"{tag} {t}" if tag else t for tag, t in zip(list(p.tags) + [""] * len(texts), texts)]
        c = p.colour(values, now) if p.colour else None
        fill = ramp(c[0], c[1]) if c else "#2c3139"
        return Cell(fill, "\n".join(texts), p.state(values, now) if p.state else None)

    def wires(self, values, now):
        out = []
        for f in self.flows:
            amount, active = f.amount(values, now)
            out.append((f.points, amount, f.label, f.side, active, f.style))
        return out

    # ---------- hover ----------
    def tooltip(self, key, values, now):
        p = self.by_key[key]
        lines = []
        for label, src, unit, dec in p.readings:
            v = self.value(src, values, now)
            lines.append((f"{label}: {self.fmt(v, unit, dec)}", TIP_FG, 10, True))
        st = p.state(values, now) if p.state else None
        if st == "warn":
            lines.append(("Outside its normal range - worth a look", "#d42020", 10, True))
        elif st == "ideal":
            lines.append(("In its normal range", "#1c8a3a", 10, True))
        lines.append((p.info, TIP_FG, 10, False))
        srcs = sorted({f"{SENSORS[s].header} {SENSORS[s].pid}" for _, s, _, _ in p.readings if isinstance(s, str)})
        if srcs:
            lines.append(("Requests: " + ", ".join(srcs) + " - all tested in your car", DIM, 8, False))
        lines.append(("Normal ranges and descriptions: estimates, not Toyota specs (unconfirmed)", DIM, 8, False))
        return p.title.replace("\n", " "), lines

    # ---------- side panel ----------
    def build_panel(self, parent, app):
        unit_buttons(parent, self, app)
        panel_label(parent, self.about, TEXT, 9, (12, 0)).config(wraplength=int(310 * app.ui))
        panel_label(parent, "Green border = normal range", IDEAL, 9, (6, 0))
        panel_label(parent, "Flashing red border = outside normal range", WARN, 9)
        panel_label(parent, "Hover over a part for all its readings", DIM, 9)
        self.rows = reading_rows(parent, [(str(i), h[0]) for i, h in enumerate(self.highlights)], "Highlights")

    def update_panel(self, values, now):
        for i, (label, src, unit, dec) in enumerate(self.highlights):
            t = self.fmt(self.value(src, values, now), unit, dec)
            self.rows[str(i)].config(text=t, fg=DIM if t == "--" else TEXT)


# ======================================================================
# Engine close-up
# ======================================================================
def _efficiency(values, now):
    """Engine efficiency estimate; hidden when it's clearly off (well above what the engine can do)."""
    e = calc.engine_efficiency_pct(values, now)
    return None if e is None or e > 50 else e


def _warmup(values, now):
    return TRACKER.warmup_c_per_min()


def _vacuum(values, now):
    m, b = first("map_ecm", "map_hv")(values, now), first("baro_hv", "baro_ecm")(values, now)
    return None if m is None or b is None else b - m


def _maf(share=1.0):
    """Air flow (g/s) for arrow speed/width; 0 when the engine is stopped."""
    def f(values, now):
        m = fresh(values, "e_maf", now)
        return (None, False) if m is None else (m * share, m > 0.5)
    return f


def _engine_on(values, now):
    rpm = first("eng_rpm", "eng_rpm_hv")(values, now)
    return None, bool(rpm and rpm > 300)


FUEL_STATUS = {1: "warming up / stopped (open loop)", 2: "normal (closed loop)", 4: "open loop - heavy load",
               8: "open loop - FAULT", 16: "closed loop - FAULT"}


def _fuel_status_text(values, now):
    return fresh(values, "e_fss", now)


def _misfire_state(k):
    return lambda values, now: (None if fresh(values, k, now) is None
                                else ("warn" if fresh(values, k, now) > 0 else "ideal"))


def _coolant(values, now):
    return first("e_ect", "e_ect_obd", "engine", "e_ect_meter")(values, now)


def _trim_state(values, now):
    s, l = fresh(values, "e_stft", now), fresh(values, "e_ltft", now)
    if s is None or l is None:
        return None
    if abs(l) >= 20 or abs(s) >= 25:
        return "warn"
    return "ideal" if abs(l) <= 10 and abs(s) <= 10 else None


def _ecu_state(values, now):
    mil, dtc = fresh(values, "lamp_mil", now), fresh(values, "dtc_now", now)
    if mil is None and dtc is None:
        return None
    return "warn" if (mil or 0) >= 0.5 or (dtc or 0) > 0 else "ideal"


def _oil_state(values, now):
    km = fresh(values, "oil_km", now)
    return None if km is None else ("warn" if km >= 15000 else "ideal" if km < 8000 else None)


class EngineView(CloseupView):
    name = "Engine"
    title = "ENGINE close-up  ·  2ZR-FXE 1.8 L"
    about = ("Laid out roughly like the engine bay seen from above, front of the car at the top: radiator at the "
             "front, cylinder 4 next to the transmission, air filter -> throttle -> intake manifold + injectors -> cylinders -> exhaust with the air-fuel "
             "sensor and catalytic converter at the back, exhaust pipe running to the rear. Blue arrows = air, "
             "brown = exhaust (both speed up with the real air-flow reading), orange = fuel, red/blue = coolant. "
             "Positions are approximate (training data, unconfirmed). The engine is often OFF in a Prius - "
             "then the flows stop.")
    flows = [
        Flow([(3.2, -1), (3.2, 23), (4, 23)], AIR, _maf(), "air in", (4.5, 13)),
        Flow([(32, 25), (36, 25)], AIR, _maf()),
        Flow([(47, 32), (47, 35)], AIR, _maf()),
        *[Flow([(12 + 17 * k, 45), (12 + 17 * k, 57)], AIR, _maf(0.25)) for k in range(4)],
        *[Flow([(12 + 17 * k, 81), (12 + 17 * k, 89.5), (19, 89.5)], EXHAUST, _maf(0.25)) for k in range(4)],
        Flow([(19, 89.5), (19, 93)], EXHAUST, _maf()),
        Flow([(34, 101), (36, 101)], EXHAUST, _maf()),
        Flow([(52, 109), (52, 249)], EXHAUST, _maf(), "exhaust pipe to the tailpipe", "r"),
        Flow([(10, 186), (2, 186), (2, 50), (4, 50)], FUEL, _engine_on, "fuel line", (3, 150)),
        Flow([(96, 58), (98.2, 58), (98.2, 5), (90, 5)], HOT, _engine_on),
        Flow([(90, 9), (99.6, 9), (99.6, 62), (96, 62)], COOL, _engine_on),
    ]
    groups = [("Engine block (top view)", 2, 33, 68, 50),
              ("Under the rear seat", 8, 174, 40, 24)]
    poll_extra = ("map_ecm", "map_hv", "baro_hv", "baro_ecm", "eng_rpm", "eng_rpm_hv", "engine", "e_ect_obd",
                  "e_lambda", "mg1_nm", "spd_hv")
    parts = [
        Part("air", "Air filter +\nair-flow sensor", (4, 15, 28, 16),
             [("Air flow into engine", "e_maf", "g/s", 1), ("Intake air temp", "e_iat", "°C", 0),
              ("Intake air temp at start", "e_iat_start", "°C", 0), ("Outside air pressure", "baro_hv", "kPa", 0)],
             (0, 1), level("e_maf", 60),
             info="Air filter and air-flow sensor. The engine computer measures how many grams of air per second go in, "
                  "which sets how much fuel to inject."),
        Part("throttle", "Throttle", (36, 18, 22, 14),
             [("Throttle opening", "throttle", "%", 0), ("Gas pedal (sensor 1)", "pedal1", "%", 0),
              ("Gas pedal (sensor 2)", "pedal2", "%", 0)],
             (0, 1), level("throttle", 100),
             tags=("throttle", "pedal"),
             info="The electronic throttle valve and the gas pedal's two sensors. In a Prius the pedal asks the hybrid "
                  "computer for power; it decides how much comes from the engine. ~16% is the throttle's closed position."),
        Part("fuel", "Fuel tank", (10, 176, 36, 20),
             [("Fuel in tank", "fuel_l", "L", 1), ("Fuel system status code", "e_fss", "", 0)],
             (0,), level("fuel_l", 45),
             state=lambda v, n: (None if fresh(v, "fuel_l", n) is None else "warn" if fresh(v, "fuel_l", n) < 5 else None),
             info="Fuel level from the dashboard meter (the tank holds about 45 L - training data, unconfirmed). "
                  "Status code: 1 = warming up/stopped, 2 = normal closed loop, 4 = heavy load, 8/16 = fault."),
        Part("manifold", "Intake manifold", (4, 35, 64, 10),
             [("Manifold pressure", first("map_ecm", "map_hv"), "kPa", 0), ("Engine vacuum", _vacuum, "kPa", 0),
              ("Engine load", "e_load", "%", 0), ("Breathing efficiency (calculated)", calc.volumetric_eff_pct, "%", 0)],
             (0, 1), level("map_ecm", 105),
             tags=("", "vacuum"),
             info="Air pressure inside the intake after the throttle. Big vacuum = light load; close to outside "
                  "pressure = heavy load or engine stopped."),
        Part("injectors", "Injectors", (4, 47, 64, 6),
             [("Injector open time (cyl 1)", "e_inj_us", "µs", 0), ("Fuel per 10 injections", "e_inj_vol", "ml", 2),
              ("Injector duty (calculated)", calc.injector_duty_pct, "%", 1),
              ("Fuel flow (calculated)", calc.fuel_l_per_h, "L/h", 2)],
             (0,), level("e_inj_us", 10000),
             info="How long the fuel injector is held open each time. Longer = more fuel."),
        Part("vvt", "Valve timing", (71, 51, 25, 14),
             [("Target", "e_vvt_aim", "%", 0), ("Solenoid effort", "e_vvt_duty", "%", 0), ("Cam shift", "e_vvt_angle", "°", 0)],
             (2,), level("e_vvt_duty", 100),
             info="Variable valve timing: the engine shifts its intake cam to trade power for efficiency. "
                  "The Prius uses very late timing (Atkinson cycle) for economy."),
        Part("ignition", "Ignition coils", (71, 35, 25, 14),
             [("Ignition timing", "e_ign", "°", 1), ("Ignition count", "e_ign_count", "", 0)],
             (0,), lambda v, n: None if fresh(v, "e_ign", n) is None else (LEVEL, (fresh(v, "e_ign", n) + 10) / 50),
             info="When the spark plugs fire, in degrees before the piston reaches the top. More advance = more "
                  "efficient, until the engine starts to knock."),
        Part("egr", "EGR valve", (71, 83, 25, 12),
             [("EGR valve position", "e_egr", "steps", 0)],
             (0,), level("e_egr", 120),
             info="Exhaust gas recirculation: feeds some cooled exhaust back into the intake to lower combustion "
                  "temperatures and pumping losses. 0 = closed."),
        *[Part(f"cyl{i}", f"Cyl {i}", (4 + 17 * (4 - i), 57, 16, 24),
               [("Misfires counted", f"e_mis{i}", "", 0), ("All-cylinder misfires", "e_mis_all", "", 0),
                ("RPM at last misfire", "e_mis_rpm", "rpm", 0)],
               (0,), lambda v, n, k=f"e_mis{i}": None if fresh(v, k, n) is None else (HEAT, fresh(v, k, n) / 10),
               _misfire_state(f"e_mis{i}"),
               info="Misfires counted for this cylinder by the engine computer. 0 is what you want; a cylinder that "
                    "keeps counting up can point to a spark plug, coil or injector problem.")
          for i in range(1, 5)],
        Part("crank", "Crankshaft", (71, 67, 25, 14),
             [("Engine speed", first("eng_rpm", "eng_rpm_hv"), "rpm", 0), ("Target speed", "eng_target", "rpm", 0),
              ("Crank sensor", "eng_rpm_sensor", "rpm", 0), ("Engine load", "e_load", "%", 0),
              ("Power the hybrid system asks for", "e_req_kw", "kW", 1),
              ("Engine torque (calculated from generator torque)", calc.engine_torque_nm, "Nm", 0),
              ("Engine power (calculated)", calc.engine_kw, "kW", 1)],
             (0,), lambda v, n: None if first("eng_rpm", "eng_rpm_hv")(v, n) is None
             else (LEVEL, first("eng_rpm", "eng_rpm_hv")(v, n) / 5200),
             tags=("", "asked for"),
             info="Engine speed from several sensors, plus what the hybrid computer is asking the engine for."),
        Part("coolant", "Radiator / coolant", (10, 2, 80, 10),
             [("Coolant temp", _coolant, "°C", 0), ("Engine computer", "e_ect", "°C", 0),
              ("Standard OBD", "e_ect_obd", "°C", 0), ("Dashboard meter", "e_ect_meter", "°C", 1),
              ("Climate computer", "e_ect_climate", "°C", 1), ("At start of this drive", "e_ect_start", "°C", 0),
              ("Warm-up rate (calculated, °C per minute)", _warmup, "", 1)],
             (0,), lambda v, n: None if _coolant(v, n) is None else (HEAT, (_coolant(v, n) - 40) / 70),
             lambda v, n: temp_state("engine")(dict(v, engine=(_coolant(v, n), n)) if _coolant(v, n) is not None else v, n),
             info="Engine coolant temperature, as reported by four different computers (they should roughly agree)."),
        Part("catalyst", "Catalytic\nconverter", (36, 93, 32, 16),
             [("Catalyst temp", "catalyst", "°C", 0)],
             (0,), heat("catalyst", 100, 900), temp_state("catalyst"),
             info="Cleans the exhaust; it has to be hot (roughly 400 °C+) to work. Usually an estimate from the "
                  "engine computer, not a real sensor."),
        Part("afs", "Air-fuel\nsensor", (4, 93, 30, 16),
             [("Measured mix (lambda)", "e_lambda", "", 2), ("Target mix (lambda)", "e_afr_target", "", 2),
              ("Short-term fuel trim", "e_stft", "%", 1), ("Long-term fuel trim", "e_ltft", "%", 1),
              ("Sensor voltage", "e_afs_v", "V", 2)],
             (0, 3), lambda v, n: None if fresh(v, "e_ltft", n) is None else (HEAT, abs(fresh(v, "e_ltft", n)) / 25),
             _trim_state,
             tags=("mix", "long trim"),
             info="The exhaust sensor that checks the fuel mix. Lambda 1.00 = perfect mix. Fuel trims are the "
                  "computer's corrections: small (within ±10%) is healthy; big long-term trims can mean an air leak "
                  "or fuel problem."),
        Part("eff", "Efficiency\n(calculated)", (56, 140, 40, 30),
             [("Engine efficiency", _efficiency, "%", 0), ("Economy right now", calc.economy_l_100km, "L/100km", 1),
              ("Economy right now (US)", calc.economy_mpg, "mpg", 0), ("Fuel flow", calc.fuel_l_per_h, "L/h", 2),
              ("Engine power", calc.engine_kw, "kW", 1), ("Fuel per kWh (BSFC)", calc.bsfc_g_kwh, "g/kWh", 0),
              ("Breathing efficiency", calc.volumetric_eff_pct, "%", 0), ("Speed", calc.speed_kmh, "km/h", 0)],
             (0, 1), lambda v, n: None if _efficiency(v, n) is None else (LEVEL, _efficiency(v, n) / 38.5),
             tags=("engine", ""),
             info="Worked out, not measured. Fuel flow = air flow / (14.1 x lambda) for E10 pump gas; economy = fuel flow "
                  "/ speed; engine power = engine torque x rpm, with engine torque from the generator's torque through "
                  "the planetary gear (-MG1 torque x 108/30); efficiency = engine power / fuel energy (31.2 MJ/L, US DOE). "
                  "Toyota rates this engine at 38.5% at best, so readings far above that mean the estimate is off at that "
                  "moment (e.g. while the engine speeds up). See specs.py for sources."),
        Part("ecu", "Engine computer", (56, 120, 40, 16),
             [("Check-engine light", "lamp_mil", "on/off", 0), ("Trouble codes stored now", "dtc_now", "", 0),
              ("Trouble codes in history", "dtc_hist", "", 0), ("Time since READY", "e_runtime", "s", 0),
              ("Warm-up requested", "e_warmup", "on/off", 0), ("Fuel cut for engine stop", "e_fc_stop", "on/off", 0),
              ("Forced on (maintenance / racing mode)", "e_racing", "on/off", 0)],
             (0, 1), None, _ecu_state, tags=("check-engine light", "trouble codes"),
             info="What the engine computer is doing and whether it has stored any faults."),
        Part("service", "Oil (sump)", (4, 120, 34, 16),
             [("Distance since oil-change reset", "oil_km", "km", 0)],
             (0,), level("oil_km", 16000), _oil_state,
             info="Distance since the oil-change reminder was last reset (the meter counts in ~161 km steps). "
                  "Green under 8,000 km, red from 15,000 km (my estimate - follow your owner's manual)."),
    ]
    highlights = [("Economy right now", calc.economy_l_100km, "L/100km", 1), ("Engine efficiency", _efficiency, "%", 0),
                  ("Engine power", calc.engine_kw, "kW", 1),
                  ("Engine speed", first("eng_rpm", "eng_rpm_hv"), "rpm", 0), ("Engine load", "e_load", "%", 0),
                  ("Coolant", _coolant, "°C", 0), ("Catalyst", "catalyst", "°C", 0),
                  ("Air flow", "e_maf", "g/s", 1), ("Long-term fuel trim", "e_ltft", "%", 1),
                  ("Misfires (all cylinders)", "e_mis_all", "", 0), ("Trouble codes now", "dtc_now", "", 0),
                  ("Fuel in tank", "fuel_l", "L", 1), ("Since oil change", "oil_km", "km", 0)]


# ======================================================================
# Battery close-up
# ======================================================================
def _blocks(values, now):
    return [fresh(values, f"block{i:02d}", now) for i in range(1, 15)]


def _dev(i):
    def f(values, now):
        b = _blocks(values, now)
        return None if None in b else b[i - 1] - sum(b) / 14
    return f


def _block_state(i):
    def f(values, now):
        d = _dev(i)(values, now)
        return None if d is None else ("warn" if abs(d) >= BLK_WARN_DEV else "ideal" if abs(d) <= BLK_IDEAL_DEV else None)
    return f


def _spread(values, now):
    b = _blocks(values, now)
    return None if None in b else max(b) - min(b)


def _live_r(i):
    def f(values, now):
        r, _ = TRACKER.block_resistance_mohm()
        return None if r is None else r[i - 1]
    return f


def _live_pack_r(values, now):
    r, _ = TRACKER.block_resistance_mohm()
    return None if r is None else sum(r)


def _live_spread(values, now):
    r, spread = TRACKER.block_resistance_mohm()
    return spread if spread else None


def _weakest_live(values, now):
    r, _ = TRACKER.block_resistance_mohm()
    if r is None:
        return None
    i = max(range(14), key=lambda k: r[k])
    return f"block {i + 1} ({r[i]:.0f} mΩ)"


def _ecu_pack_r(values, now):
    r = calc.pack_resistance_ohm(values, now)
    return None if r is None else r * 1000


def _power_kw(values, now):
    v, a = fresh(values, "pack_volts", now), fresh(values, "batt_amps", now)
    return None if v is None or a is None else v * a / 1000


def _soc(values, now):
    return first("soc", "soc_hv")(values, now)


def _counters_state(values, now):
    c = [fresh(values, k, now) for k in ("cnt_low", "cnt_dcinh", "cnt_high", "cnt_hot")]
    return None if None in c else ("warn" if any(c) else "ideal")


def _aux_state(values, now):
    v = fresh(values, "aux_volts", now)
    return None if v is None else ("warn" if v < AUX_LOW or v > AUX_HIGH else "ideal" if AUX_IDEAL[0] <= v <= AUX_IDEAL[1] else None)


def _hottest(values, now):
    t = [fresh(values, k, now) for k in ("batt_tb1", "batt_tb2", "batt_tb3")]
    t = [x for x in t if x is not None]
    return max(t) if t else None


BLK_STEP, BLK_W = 9.7, 8.7


def _block_rect(i):
    """Snaking like the real series chain: blocks 1-7 left to right, then 8-14 back right to left underneath."""
    col, y = (i - 1, 42) if i <= 7 else (14 - i, 68)
    return (5 + col * BLK_STEP, y, BLK_W, 24)


def _block_links():
    out = []
    for i in range(1, 14):
        x, y, w_, h = _block_rect(i)
        if i < 7:
            out.append([(x + w_, y + 12), (x + BLK_STEP, y + 12)])
        elif i == 7:
            out.append([(x + w_, 54), (72.5, 54), (72.5, 80), (x + w_, 80)])
        else:
            out.append([(x, 80), (x - (BLK_STEP - BLK_W), 80)])
    return out


def _amps(sign=1):
    def f(values, now):
        a = fresh(values, "batt_amps", now)
        return (None, False) if a is None else (sign * a, abs(a) >= 0.5)
    return f


def _fan_air(values, now):
    pct = fresh(values, "fan_pct", now)
    return (None, False) if pct is None else (pct / 3, pct > 0)


def _dcdc_on(values, now):
    d = fresh(values, "dcdc_duty", now)
    return None, bool(d and d > 0)


def _fan_on(values, now):
    pct = fresh(values, "fan_pct", now)
    return None, bool(pct and pct > 0)


class BatteryView(CloseupView):
    name = "Battery"
    title = "BATTERIES close-up  ·  hybrid pack + 12 V"
    about = ("Laid out roughly like the back of the car seen from above, front at the top: the pack sits behind the "
             "rear seat with its cooling fan and battery computer at one end, the 12 V battery is in the cargo area, "
             "and the DC-DC converter is up front in the inverter. Yellow arrows = current (the + and - cables "
             "carry the real battery current to the front), blue = cooling air (speeds up with the fan). Blocks are "
             "coloured by how far their voltage is from the pack average. Positions are approximate (training data, "
             "unconfirmed).")
    flows = [
        Flow([(5, 54), (4.2, 54), (4.2, -1)], HV, _amps(), "+ and − cables to the booster (front)", (5, 37.5)),
        Flow([(0.2, -1), (0.2, 80), (5, 80)], HV, _amps(), "", "r"),
        *[Flow(pts, HV, _amps(-1)) for pts in _block_links()],
        Flow([(83, 18), (83, 40)], AIR, _fan_air),
        Flow([(75, 52), (73.8, 52), (73.8, 115.5), (3, 115.5)], AIR, _fan_air, "cooling air through the pack, out to the cargo area",
             (6, 117.3)),
        Flow([(38, 11), (67, 11), (67, 1.2), (98.6, 1.2), (98.6, 217), (96, 217)], LV, _dcdc_on, "12 V", (40, 9.3)),
        Flow([(98.6, 52), (96, 52)], LV, _fan_on),
    ]
    groups = [("Rear seat", 3, 22, 94, 11),
              ("Hybrid battery pack - 14 blocks in series (1-7 left to right, 8-14 back)", 3, 40, 70.5, 70),
              ("Cargo area", 3, 196, 94, 42)]
    parts = [
        Part("pack", "Whole pack", (5, 121, 66, 15),
             [("Charge", _soc, "%", 1), ("Charge (2nd reading)", "soc_hv", "%", 1), ("Current", "batt_amps", "A", 1),
              ("Pack voltage", "pack_volts", "V", 1), ("Power in/out", _power_kw, "kW", 1),
              ("Block spread (highest - lowest)", _spread, "V", 2),
              ("Heat made inside the pack (I² x R)", calc.pack_heat_w, "W", 0), ("C-rate (current / 6.5 Ah)", calc.c_rate, "C", 1),
              ("Using this much of the allowed power", calc.limit_usage_pct, "%", 0),
              ("Energy out this trip", lambda v, n: TRACKER.wh_out, "Wh", 0),
              ("Energy in this trip", lambda v, n: TRACKER.wh_in, "Wh", 0)],
             (0, 2), lambda v, n: None if _soc(v, n) is None else (LEVEL, _soc(v, n) / 100),
             lambda v, n: None if _soc(v, n) is None else ("ideal" if 40 <= _soc(v, n) <= 80 else "warn"),
             info="Negative current / power = charging. The Prius normally keeps the charge between about 40 and 80% "
                  "(training data, unconfirmed)."),
        Part("limits", "Battery computer:\nlimits", (75, 68, 21, 21),
             [("Can take in", lambda v, n: None if fresh(v, "chg_lim", n) is None else abs(fresh(v, "chg_lim", n)), "kW", 0),
              ("Can give out", "dis_lim", "kW", 0), ("Charge value at start (2198, meaning unclear)", "soc_ig", "%", 1),
              ("Charge max (2198, meaning unclear)", "soc_max", "%", 1), ("Charge min (2198, meaning unclear)", "soc_min", "%", 1)],
             (0, 1), level("dis_lim", 30),
             tags=("in", "out"),
             info="How much power the battery computer allows in and out right now. These shrink when the battery "
                  "is cold, hot, very full or very empty."),
        *[Part(f"b{i}", f"B{i}", _block_rect(i),
               [("Voltage", f"block{i:02d}", "V", 2), ("Difference from pack average", _dev(i), "V", 3),
                ("Internal resistance (battery computer)", lambda v, n, k=f"res{i:02d}": None if fresh(v, k, n) is None
                 else fresh(v, k, n) * 1000, "mΩ", 0),
                ("Internal resistance (measured live from voltage vs current)", _live_r(i), "mΩ", 1)],
               (0, 2), lambda v, n, f=_dev(i): None if f(v, n) is None else (DEVIATE, abs(f(v, n)) / 0.4),
               _block_state(i),
               info="Each block is 2 modules of 6 nickel-metal hydride cells. A block that sits lower than the others at "
                    "rest (or higher while charging) and has higher resistance is the weak one.")
          for i in range(1, 15)],
        *[Part(f"t{i}", f"Temp {i}", (5 + 22.3 * (i - 1), 94, 21.3, 14),
               [(f"Battery temp sensor {i}", f"batt_tb{i}", "°C", 1),
                ("Time spent too hot (counter)", "cnt_hot", "", 0)],
               (0,), heat(f"batt_tb{i}", 20, 55), temp_state(f"batt_tb{i}"),
               info="One of three temperature sensors inside the hybrid battery. They should stay within a few degrees "
                    "of each other.")
          for i in (1, 2, 3)],
        Part("intake", "Cooling air in\n(rear seat vent)", (70, 4, 26, 14),
             [("Air going into the battery", "batt_intake", "°C", 1),
              ("Battery average minus this (calculated)", calc.cooling_delta_c, "°C", 1)],
             (0,), heat("batt_intake", 15, 45), temp_state("batt_intake"),
             info="Cabin air pulled in to cool the battery (vent by the rear seat)."),
        Part("health", "Battery health (calculated)", (5, 140, 66, 26),
             [("Capacity estimate", lambda v, n: TRACKER.capacity_ah, "Ah", 2), ("Rated capacity", lambda v, n: specs.BATTERY_AH, "Ah", 1),
              ("Pack resistance - measured live", _live_pack_r, "mΩ", 0),
              ("Pack resistance - battery computer", _ecu_pack_r, "mΩ", 0),
              ("Weakest block (live)", _weakest_live, "", 0),
              ("Current spread used for the live measurement", _live_spread, "A", 1),
              ("Temp above cooling air", calc.cooling_delta_c, "°C", 1)],
             (0, 2), lambda v, n: None if TRACKER.capacity_ah is None else (LEVEL, TRACKER.capacity_ah / specs.BATTERY_AH),
             tags=("capacity", "resistance"),
             info="Worked out while you drive. Capacity = amp-hours counted in/out / change in the car's charge % "
                  "(needs a 5% swing; uses the car's own charge estimate, so treat it as a trend). Live resistance = how "
                  "much each block's voltage drops per amp (slope of voltage vs current); it needs about 10 A of spread "
                  "in current, so it appears after some accelerating/braking. Rated: 6.5 Ah (Oak Ridge National Lab)."),
        Part("fan", "Cooling fan", (75, 40, 21, 24),
             [("Fan power", "fan_pct", "%", 0), ("Fan relay", "fan_relay", "on/off", 0),
              ("Fan motor voltage", "fan_volts", "V", 1), ("Fan mode", "fan_mode", "", 0)],
             (0,), level("fan_pct", 100),
             info="The battery cooling fan. It speeds up as the battery warms."),
        Part("counters", "Battery computer:\ncounters", (75, 91, 21, 19),
             [("Time too LOW", "cnt_low", "", 0), ("Time DC was blocked", "cnt_dcinh", "", 0),
              ("Time too HIGH", "cnt_high", "", 0), ("Time too HOT", "cnt_hot", "", 0)],
             (0, 3), None, _counters_state,
             tags=("too low", "too hot"),
             info="Counters the battery computer keeps of how long the battery spent in bad conditions. 0 everywhere "
                  "is ideal. Units aren't documented."),
        Part("aux", "12V battery", (58, 204, 38, 26),
             [("Voltage (hybrid computer)", "aux_volts", "V", 2), ("Voltage (battery computer)", "aux_v2", "V", 2),
              ("Voltage (dashboard meter)", "aux_v3", "V", 1), ("Temperature", "aux_batt", "°C", 0)],
             (0, 3), lambda v, n: None if fresh(v, "aux_volts", n) is None else (LEVEL, (fresh(v, "aux_volts", n) - 11) / 4),
             _aux_state,
             info="The small 12 V battery in the cargo area. While READY it should read about 13.5-14.5 V because the "
                  "DC-DC converter is charging it."),
        Part("dcdc", "DC-DC converter\n(front, in inverter)", (4, 3, 34, 16),
             [("Effort", "dcdc_duty", "%", 0), ("High-voltage input", "vl", "V", 0),
              ("Told to stop", "dcdc_prohibit", "on/off", 0)],
             (0,), level("dcdc_duty", 100),
             info="Charges the 12 V battery from the hybrid battery (it replaces an alternator)."),
    ]
    highlights = [("Charge", _soc, "%", 1), ("Current", "batt_amps", "A", 1), ("Pack voltage", "pack_volts", "V", 1),
                  ("Block spread", _spread, "V", 2), ("Capacity estimate", lambda v, n: TRACKER.capacity_ah, "Ah", 2),
                  ("Weakest block (live)", _weakest_live, "", 0), ("Can take in", lambda v, n: None if fresh(v, "chg_lim", n) is None else abs(fresh(v, "chg_lim", n)), "kW", 0),
                  ("Can give out", "dis_lim", "kW", 0), ("Hottest battery temp", _hottest, "°C", 1),
                  ("Cooling fan", "fan_pct", "%", 0), ("12V battery", "aux_volts", "V", 2)]

    def sensors(self):
        keys = ([f"block{i:02d}" for i in range(1, 15)] + [f"res{i:02d}" for i in range(1, 15)]
                + ["soc", "dcdc_prohibit", "chg_lim", "dis_lim", "batt_intake"])
        extra = [SENSORS[k] for k in keys]
        base = super().sensors()
        have = {s.key for s in base}
        return base + [s for s in extra if s.key not in have]


# ======================================================================
# Trip (running totals since the app started or the last reset)
# ======================================================================
def _t(fn):
    return lambda values, now: fn()


def _tile(key, title, col, row, readings, show=(0,), info="", span=1, tags=()):
    x = 5 + col * 46
    return Part(key, title, (x, 5 + row * 25, 44 + (46 if span == 2 else 0), 22), readings, show, None, None, info, tags=tags)


class TripView(CloseupView):
    name = "Trip"
    units = [("C", "°C"), ("F", "°F")]
    title = "TRIP  ·  since the app started (or the last reset)"
    about = ("Running totals worked out from the live readings. They're only as good as how often each reading "
             "arrives (every ~1-2 s), so short events like quick stops are approximate. Fuel is estimated from air "
             "flow (E10 gas), braking energy from the car's speed and weight (1,397 kg + 80 kg driver).")
    poll_extra = TRIP_KEYS + ("batt_tb1", "batt_tb2", "batt_tb3", "e_ect", "engine")
    parts = [
        _tile("dist", "Distance", 0, 0, [("Distance", _t(lambda: TRACKER.km), "km", 2),
                                        ("Distance (miles)", _t(lambda: TRACKER.km * 0.621371), "mi", 2)], (0, 1)),
        _tile("speed", "Average speed", 1, 0, [("Average while moving", _t(TRACKER.avg_speed), "km/h", 0),
                                               ("Time moving", _t(lambda: TRACKER.moving_s / 60), "min", 1)], (0, 1)),
        _tile("fuel", "Fuel used", 0, 1, [("Fuel used", _t(lambda: TRACKER.fuel_l), "L", 2),
                                          ("Fuel used (US gal)", _t(lambda: TRACKER.fuel_l / 3.785411784), "gal", 3)], (0,)),
        _tile("econ", "Average economy", 1, 1, [("Average", _t(TRACKER.avg_l_100km), "L/100km", 1),
                                                ("Average (US)", _t(TRACKER.avg_mpg), "mpg", 0)], (0, 1)),
        _tile("ev", "Driven on electricity", 0, 2, [("Share of distance with the engine off", _t(TRACKER.ev_share_pct), "%", 0),
                                                    ("Distance with the engine off", _t(lambda: TRACKER.ev_km), "km", 2)],
              (0,), "Distance covered while the engine was stopped (engine rpm under 100) - a Prius specialty."),
        _tile("engon", "Engine running", 1, 2, [("Engine-on time", _t(lambda: TRACKER.engine_on_s / 60), "min", 1)], (0,)),
        _tile("out", "Battery gave out", 0, 3, [("Energy out", _t(lambda: TRACKER.wh_out), "Wh", 0)], (0,)),
        _tile("in", "Battery took in", 1, 3, [("Energy in", _t(lambda: TRACKER.wh_in), "Wh", 0)], (0,)),
        _tile("regen", "Braking energy recovered", 0, 4,
              [("Recovered into the battery", _t(TRACKER.regen_recovered_pct), "%", 0),
               ("Motion energy lost while braking", _t(lambda: TRACKER.brake_kinetic_wh), "Wh", 0),
               ("Energy into the battery while braking", _t(lambda: TRACKER.brake_regen_wh), "Wh", 0)],
              (0, 1), "Motion energy lost while braking = ½ x mass x (speed before² - speed after²). Some is always lost to "
                      "friction brakes, rolling and air drag, so 100% isn't possible; gentle, early braking scores higher.",
              span=2, tags=("", "of")),
        _tile("ac", "A/C used", 0, 5, [("A/C energy", _t(lambda: TRACKER.ac_wh), "Wh", 0)], (0,)),
        _tile("time", "Trip time", 1, 5, [("Since start/reset", _t(lambda: TRACKER.elapsed_s() / 60), "min", 1)], (0,)),
        _tile("maxa", "Biggest battery current", 0, 6, [("Out (driving)", _t(lambda: TRACKER.max_amps_out), "A", 0),
                                                         ("In (charging)", _t(lambda: TRACKER.max_amps_in), "A", 0)],
              (0, 1), tags=("out", "in")),
        _tile("maxp", "Biggest battery power", 1, 6, [("Out", _t(lambda: TRACKER.max_kw_out), "kW", 1),
                                                       ("In", _t(lambda: TRACKER.max_kw_in), "kW", 1)],
              (0, 1), tags=("out", "in")),
        _tile("hotb", "Hottest battery", 0, 7, [("Highest battery temperature", _t(lambda: TRACKER.max_batt_temp), "°C", 1)], (0,)),
        _tile("hotc", "Hottest coolant", 1, 7, [("Highest engine coolant", _t(lambda: TRACKER.max_coolant), "°C", 0)], (0,)),
        _tile("cap", "Battery capacity (est.)", 0, 8, [("Capacity estimate", _t(lambda: TRACKER.capacity_ah), "Ah", 2),
                                                        ("Rated", _t(lambda: specs.BATTERY_AH), "Ah", 1)], (0,)),
        _tile("weak", "Weakest block (live)", 1, 8, [("Highest live resistance", _weakest_live, "", 0)], (0,)),
    ]
    highlights = [("Distance", _t(lambda: TRACKER.km), "km", 2), ("Average economy", _t(TRACKER.avg_l_100km), "L/100km", 1),
                  ("Driven on electricity", _t(TRACKER.ev_share_pct), "%", 0),
                  ("Braking energy recovered", _t(TRACKER.regen_recovered_pct), "%", 0)]

    def build_panel(self, parent, app):
        super().build_panel(parent, app)
        tk.Button(parent, text="Reset trip", command=lambda: (TRACKER.reset(), app.refresh()), bg="#2c3139", fg=TEXT,
                  activebackground="#3a404a", activeforeground=TEXT, relief="flat", padx=10, pady=4,
                  font=("Segoe UI", 10)).pack(anchor="w", pady=(12, 0))
