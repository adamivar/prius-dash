"""Close-up views: Engine and Battery.

Unlike the car views, these draw a diagram of just that system and show every reading for each part.
Units are mixed on purpose here (each number carries its own unit); temperatures follow the °C/°F switch.
"""
import tkinter as tk
from dataclasses import dataclass, field
from typing import Callable

import calc
import config as cfg
from calc import TRACKER

from sensors import BATTERY, ELEC, ELEC_EXTRA, ENGINE, PRESS, ROT, SENSORS, SOC, TEMPS, TRIP_KEYS
from views import (BATT_X0, BG, BLK_IDEAL_DEV, BLK_WARN_DEV, DIM, HEAT, IDEAL, NO_DATA, TEXT, TIP_FG, WARN, WARN_AT,
                   AUX_HIGH, AUX_IDEAL, AUX_LOW, Cell, fresh, legend, panel_label, ramp, reading_rows, unit_buttons)

from config import DEVIATE, LEVEL  # noqa: E402  (colour ramps)
# line / arrow colours for what flows between parts
AIR, EXHAUST, FUEL = cfg.FLOW_AIR, cfg.FLOW_EXHAUST, cfg.FLOW_FUEL
HOT, COOL, HV, LV = cfg.FLOW_HOT, cfg.FLOW_COOL, cfg.FLOW_HV, cfg.FLOW_LV


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
    part_shapes = {}                  # part key -> outline shape (see shapes.py)
    default_shape = "box"

    def __init__(self):
        self.unit = "C"
        self.by_key = {p.key: p for p in self.parts}
        self.components = [(p.key, *p.rect) for p in self.parts]
        self.shapes = {p.key: self.part_shapes.get(p.key, self.default_shape) for p in self.parts}
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
        fill = ramp(c[0], c[1]) if c else cfg.CLOSEUP_PART
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
            lines.append(("Outside its normal range - worth a look", cfg.TIP_RED, 10, True))
        elif st == "ideal":
            lines.append(("In its normal range", cfg.TIP_GREEN, 10, True))
        lines.append((p.info, TIP_FG, 10, False))
        srcs = sorted({f"{SENSORS[s].header} {SENSORS[s].pid}" for _, s, _, _ in p.readings if isinstance(s, str)})
        if srcs:
            lines.append(("Requests: " + ", ".join(srcs) + " - all tested in your car", DIM, 8, False))
        lines.append(("Normal ranges and descriptions: estimates, not Toyota specs (unconfirmed)", DIM, 8, False))
        return p.title.replace("\n", " "), lines

    # ---------- side panel ----------
    def build_panel(self, parent, app):
        unit_buttons(parent, self, app)
        panel_label(parent, self.about, TEXT, 9, (12, 0)).config(wraplength=int(cfg.PANEL_TEXT_WIDTH * app.ui))
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
    return None if e is None or e > cfg.EFFICIENCY_HIDE_ABOVE else e


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
    if abs(l) >= cfg.FUEL_TRIM_WARN_LONG or abs(s) >= cfg.FUEL_TRIM_WARN_SHORT:
        return "warn"
    return "ideal" if abs(l) <= cfg.FUEL_TRIM_IDEAL and abs(s) <= cfg.FUEL_TRIM_IDEAL else None


COMM_KEYS = ("e_comm_hv", "e_comm_brake", "e_comm_ac")


def _ecu_state(values, now):
    """Red if the check-engine light is on, a code is stored, or it can't hear another computer."""
    mil, dtc = fresh(values, "lamp_mil", now), fresh(values, "dtc_now", now)
    comm = [fresh(values, k, now) for k in COMM_KEYS]
    if mil is None and dtc is None:
        return None
    lost = any(c is not None and c < 0.5 for c in comm)
    return "warn" if (mil or 0) >= 0.5 or (dtc or 0) > 0 or lost else "ideal"


def _yes_no(key):
    return lambda v, n: None if fresh(v, key, n) is None else ("yes" if fresh(v, key, n) >= 0.5 else "NO")


BATT_MODES = {1: "driving", 2: "current-sensor calibration", 3: "external charging", 4: "shutting down"}


def _batt_mode(values, now):
    m = fresh(values, "batt_mode", now)
    return None if m is None else BATT_MODES.get(int(m), f"mode {m:.0f}")


def _oil_state(values, now):
    km = fresh(values, "oil_km", now)
    return None if km is None else ("warn" if km >= cfg.OIL_DUE_KM else "ideal" if km < cfg.OIL_OK_KM else None)


class EngineView(CloseupView):
    name = "Engine"
    title = "ENGINE close-up  ·  2ZR-FXE 1.8 L"
    about = ("Laid out like the engine seen from above, front of the car at the top, driver's side on the left. "
             "The 2ZR-FXE sits across the car with its intake at the front and its exhaust at the back against "
             "the firewall: radiator -> air filter (in the middle of the engine bay, so over the transaxle end of "
             "the engine) -> throttle -> intake manifold + injectors -> cylinders (4 next to the transaxle, 1 at "
             "the timing-chain end, where the valve timing and crank pulley are) -> exhaust manifold with the "
             "air-fuel sensor, catalytic converter and EGR cooler -> exhaust pipe under the middle of the car. "
             "The fuel tank is under the rear seat. Blue arrows = air, brown = exhaust (both speed up with the "
             "real air-flow reading), orange = fuel, red/blue = coolant. Exact spots are approximate. The engine "
             "is often OFF in a Prius - then the flows stop.")
    flows = [
        Flow([(2, -1), (2, 23), (4, 23)], AIR, _maf(), "air in", (3, 5)),
        Flow([(32, 25), (36, 25)], AIR, _maf()),
        Flow([(47, 32), (47, 35)], AIR, _maf()),
        *[Flow([(12 + 17 * k, 45), (12 + 17 * k, 62)], AIR, _maf(0.25)) for k in range(4)],
        *[Flow([(12 + 17 * k, 78), (12 + 17 * k, 89.5), (19, 89.5)], EXHAUST, _maf(0.25)) for k in range(4)],
        Flow([(19, 89.5), (19, 93)], EXHAUST, _maf()),
        Flow([(36, 101), (38, 101)], EXHAUST, _maf()),
        Flow([(52, 109), (52, 249)], EXHAUST, _maf(), "exhaust pipe to the tailpipe", "r"),
        Flow([(10, 186), (2, 186), (2, 49), (4, 49)], FUEL, _engine_on, "fuel line", (3, 150)),
        Flow([(96, 55), (98.2, 55), (98.2, 5), (88, 5)], HOT, _engine_on),
        Flow([(88, 9), (99.6, 9), (99.6, 57.5), (96, 57.5)], COOL, _engine_on),
    ]
    part_shapes = {"air": "airbox", "throttle": "throttle", "fuel": "tank", "manifold": "manifold", "injectors": "strip4",
                   "vvt": "gear", "ignition": "strip4", "egr": "drum", **{f"cyl{i}": "circle" for i in range(1, 5)},
                   "crank": "pulley", "coolant": "radiator", "catalyst": "canister", "afs": "pill", "eff": "rounded",
                   "ecu": "ecu", "service": "sump"}
    flow_over = ("injectors", "ignition")   # seen from above, the air to each cylinder passes under these
    groups = [("Engine (top view)", 2, 33, 96, 78),
              ("Under the rear seat", 8, 174, 40, 24)]
    poll_extra = ("e_comm_hv", "e_comm_brake", "e_comm_ac", "map_ecm", "map_hv", "baro_hv", "baro_ecm", "eng_rpm",
                  "eng_rpm_hv", "engine", "e_ect_obd",
                  "e_lambda", "mg1_nm", "spd_hv")
    parts = [
        Part("air", "Air filter +\nair-flow sensor", (4, 14, 28, 17.5),
             [("Air flow into engine", "e_maf", "g/s", 1), ("Intake air temp", "e_iat", "°C", 0),
              ("Intake air temp at start", "e_iat_start", "°C", 0), ("Outside air pressure", "baro_hv", "kPa", 0)],
             (0, 1), level("e_maf", cfg.MAF_FULL_G_S),
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
             (0,), level("fuel_l", cfg.FUEL_TANK_L),
             state=lambda v, n: (None if fresh(v, "fuel_l", n) is None else "warn" if fresh(v, "fuel_l", n) < cfg.FUEL_LOW_L else None),
             info="Fuel level from the dashboard meter (the tank holds about 45 L - training data, unconfirmed). "
                  "Status code: 1 = warming up/stopped, 2 = normal closed loop, 4 = heavy load, 8/16 = fault."),
        Part("manifold", "Intake manifold", (4, 35, 64, 10),
             [("Manifold pressure", first("map_ecm", "map_hv"), "kPa", 0), ("Engine vacuum", _vacuum, "kPa", 0),
              ("Engine load", "e_load", "%", 0), ("Breathing efficiency (calculated)", calc.volumetric_eff_pct, "%", 0)],
             (0, 1), level("map_ecm", cfg.PRESS_LIMITS["map"][0]),
             tags=("", "vacuum"),
             info="Air pressure inside the intake after the throttle. Big vacuum = light load; close to outside "
                  "pressure = heavy load or engine stopped."),
        Part("injectors", "Injectors", (4, 46.5, 64, 6),
             [("Injector open time (cyl 1)", "e_inj_us", "µs", 0), ("Fuel per 10 injections", "e_inj_vol", "ml", 2),
              ("Injector duty (calculated)", calc.injector_duty_pct, "%", 1),
              ("Fuel flow (calculated)", calc.fuel_l_per_h, "L/h", 2)],
             (0,), level("e_inj_us", cfg.INJECTOR_FULL_US),
             info="How long the fuel injector is held open each time. Longer = more fuel."),
        Part("vvt", "Valve\ntiming", (71, 34, 25, 24),
             [("Target", "e_vvt_aim", "%", 0), ("Solenoid effort", "e_vvt_duty", "%", 0), ("Cam shift", "e_vvt_angle", "°", 0)],
             (2,), level("e_vvt_duty", 100),
             info="Variable valve timing: the engine shifts its intake cam to trade power for efficiency. "
                  "The Prius uses very late timing (Atkinson cycle) for economy."),
        Part("ignition", "Ignition coils", (4, 53, 64, 6),
             [("Ignition timing", "e_ign", "°", 1), ("Ignition count", "e_ign_count", "", 0)],
             (0,), lambda v, n: None if fresh(v, "e_ign", n) is None else (LEVEL, (fresh(v, "e_ign", n) - cfg.IGNITION_COLOUR_RANGE[0])
                                                  / (cfg.IGNITION_COLOUR_RANGE[1] - cfg.IGNITION_COLOUR_RANGE[0])),
             info="When the spark plugs fire, in degrees before the piston reaches the top. More advance = more "
                  "efficient, until the engine starts to knock."),
        Part("egr", "EGR valve\n+ cooler", (71, 93, 25, 16),
             [("EGR valve position", "e_egr", "steps", 0)],
             (0,), level("e_egr", cfg.EGR_FULL_STEPS),
             info="Exhaust gas recirculation: feeds some cooled exhaust back into the intake to lower combustion "
                  "temperatures and pumping losses. 0 = closed."),
        *[Part(f"cyl{i}", f"Cyl {i}", (4 + 17 * (4 - i), 62, 16, 16),
               [("Misfires counted", f"e_mis{i}", "", 0), ("All-cylinder misfires", "e_mis_all", "", 0),
                ("RPM at last misfire", "e_mis_rpm", "rpm", 0)],
               (0,), lambda v, n, k=f"e_mis{i}": None if fresh(v, k, n) is None else (HEAT, fresh(v, k, n) / cfg.MISFIRE_COLOUR_FULL),
               _misfire_state(f"e_mis{i}"),
               info="Misfires counted for this cylinder by the engine computer. 0 is what you want; a cylinder that "
                    "keeps counting up can point to a spark plug, coil or injector problem.")
          for i in range(1, 5)],
        Part("crank", "Crankshaft\n(pulley end)", (71, 60, 25, 24),
             [("Engine speed", first("eng_rpm", "eng_rpm_hv"), "rpm", 0), ("Target speed", "eng_target", "rpm", 0),
              ("Crank sensor", "eng_rpm_sensor", "rpm", 0), ("Engine load", "e_load", "%", 0),
              ("Power the hybrid system asks for", "e_req_kw", "kW", 1),
              ("Engine torque (calculated from generator torque)", calc.engine_torque_nm, "Nm", 0),
              ("Engine power (calculated)", calc.engine_kw, "kW", 1)],
             (0,), lambda v, n: None if first("eng_rpm", "eng_rpm_hv")(v, n) is None
             else (LEVEL, first("eng_rpm", "eng_rpm_hv")(v, n) / cfg.SPIN_MAX_RPM["engine"]),
             tags=("", "asked for"),
             info="Engine speed from several sensors, plus what the hybrid computer is asking the engine for."),
        Part("coolant", "Radiator / coolant", (12, 2, 76, 9.5),
             [("Coolant temp", _coolant, "°C", 0), ("Engine computer", "e_ect", "°C", 0),
              ("Standard OBD", "e_ect_obd", "°C", 0), ("Dashboard meter", "e_ect_meter", "°C", 1),
              ("Climate computer", "e_ect_climate", "°C", 1), ("At start of this drive", "e_ect_start", "°C", 0),
              ("Warm-up rate (calculated, °C per minute)", _warmup, "", 1)],
             (0,), lambda v, n: None if _coolant(v, n) is None else (HEAT, (_coolant(v, n) - cfg.COOLANT_COLOUR_RANGE[0])
                                                   / (cfg.COOLANT_COLOUR_RANGE[1] - cfg.COOLANT_COLOUR_RANGE[0])),
             lambda v, n: temp_state("engine")(dict(v, engine=(_coolant(v, n), n)) if _coolant(v, n) is not None else v, n),
             info="Engine coolant temperature, as reported by four different computers (they should roughly agree)."),
        Part("catalyst", "Catalytic\nconverter", (38, 93, 30, 16),
             [("Catalyst temp", "catalyst", "°C", 0)],
             (0,), heat("catalyst", *cfg.CATALYST_COLOUR_RANGE), temp_state("catalyst"),
             info="Cleans the exhaust; it has to be hot (roughly 400 °C+) to work. Usually an estimate from the "
                  "engine computer, not a real sensor."),
        Part("afs", "Air-fuel\nsensor", (4, 93, 32, 17.5),
             [("Measured mix (lambda)", "e_lambda", "", 2), ("Target mix (lambda)", "e_afr_target", "", 2),
              ("Short-term fuel trim", "e_stft", "%", 1), ("Long-term fuel trim", "e_ltft", "%", 1),
              ("Sensor voltage", "e_afs_v", "V", 2)],
             (0, 3), lambda v, n: None if fresh(v, "e_ltft", n) is None else (HEAT, abs(fresh(v, "e_ltft", n)) / cfg.FUEL_TRIM_COLOUR_FULL),
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
             (0, 1), lambda v, n: None if _efficiency(v, n) is None else (LEVEL, _efficiency(v, n) / (cfg.ENGINE_PEAK_EFFICIENCY * 100)),
             tags=("engine", ""),
             info=f"Worked out, not measured. Fuel flow = air flow / ({cfg.STOICH_AFR} x lambda) for E10 pump gas; "
                  "economy = fuel flow / speed; engine power = engine torque x rpm, with engine torque from the generator's "
                  f"torque through the planetary gear (-MG1 torque x {cfg.SUN_TEETH + cfg.RING_TEETH}/{cfg.SUN_TEETH}); "
                  f"efficiency = engine power / fuel energy ({cfg.FUEL_LHV_MJ_L:.1f} MJ/L, US DOE). Toyota rates this engine "
                  f"at {cfg.ENGINE_PEAK_EFFICIENCY * 100:.1f}% at best, so readings far above that mean the estimate is off "
                  "at that moment (e.g. while the engine speeds up). See config.py for sources."),
        Part("ecu", "Engine computer", (56, 120, 40, 16),
             [("Check-engine light", "lamp_mil", "on/off", 0), ("Trouble codes stored now", "dtc_now", "", 0),
              ("Trouble codes in history", "dtc_hist", "", 0), ("Time since READY", "e_runtime", "s", 0),
              ("Warm-up requested", "e_warmup", "on/off", 0), ("Fuel cut for engine stop", "e_fc_stop", "on/off", 0),
              ("Forced on (maintenance / racing mode)", "e_racing", "on/off", 0),
              ("Hears the hybrid computer", _yes_no("e_comm_hv"), "", 0),
              ("Hears the brake computer", _yes_no("e_comm_brake"), "", 0),
              ("Hears the climate computer", _yes_no("e_comm_ac"), "", 0),
              ("Warm-ups since codes were cleared", "dtc_warmups", "", 0),
              ("Distance since codes were cleared", "dtc_km", "km", 0),
              ("Time since codes were cleared", "dtc_min", "min", 0)],
             (0, 1), None, _ecu_state, tags=("check-engine light", "trouble codes"),
             info="What the engine computer is doing, whether it has stored any faults, and whether it can hear the "
                  "other computers (any 'NO' turns the box red). 'Since codes were cleared' counts from the last "
                  "time trouble codes were erased (or the 12 V battery was disconnected)."),
        Part("service", "Oil (sump)", (4, 120, 34, 16),
             [("Distance since oil-change reset", "oil_km", "km", 0)],
             (0,), level("oil_km", cfg.OIL_COLOUR_FULL_KM), _oil_state,
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


BLK_STEP, BLK_W = 9.45, 8.7


def _block_rect(i):
    """Snaking like the real series chain: blocks 1-7 left to right, then 8-14 back right to left underneath."""
    col, y = (i - 1, 42) if i <= 7 else (14 - i, 68)
    return (8 + col * BLK_STEP, y, BLK_W, 24)


def _block_links():
    out = []
    for i in range(1, 14):
        x, y, w_, h = _block_rect(i)
        if i < 7:
            out.append([(x + w_, y + 12), (x + BLK_STEP, y + 12)])
        elif i == 7:
            out.append([(x + w_, 54), (74.2, 54), (74.2, 80), (x + w_, 80)])
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
    poll_extra = ("batt_mode",)
    title = "BATTERIES close-up  ·  hybrid pack + 12 V"
    about = ("Laid out like the back half of the car seen from above, front at the top, driver's side on the left "
             "(Toyota's Gen 3 emergency response guide): the pack is bolted to the cross member in the cargo area "
             "right behind the rear seat, it breathes cabin air through the vent by the passenger-side rear seat "
             "and the warm air leaves through the passenger-side quarter duct, the 12 V battery is on the "
             "passenger side of the cargo area, and the DC-DC converter is up front in the inverter. Yellow arrows "
             "= current (the + and - cables carry the real battery current forward under the floor), blue = "
             "cooling air (speeds up with the fan). Blocks are coloured by how far their voltage is from the pack "
             "average. The real pack is one row of 28 modules across the car; it's drawn as 2 rows of 7 blocks so "
             "each block stays readable. Exact spots of the fan and battery computer are unconfirmed.")
    flows = [
        Flow([(8, 54), (6, 54), (6, -1)], HV, _amps(), "+ and − cables to the booster (front)", "r"),
        Flow([(3.5, -1), (3.5, 80), (8, 80)], HV, _amps(), "", "r"),
        *[Flow(pts, HV, _amps(-1)) for pts in _block_links()],
        Flow([(83, 34), (83, 40)], AIR, _fan_air),
        Flow([(76, 52), (75.1, 52), (75.1, 115.5), (96, 115.5)], AIR, _fan_air,
             "cooling air through the pack, out the passenger-side quarter duct", (9, 117.8)),
        Flow([(62, 9), (98.6, 9), (98.6, 217), (96, 217)], LV, _dcdc_on, "12 V", (64, 7)),
        Flow([(98.6, 52), (96, 52)], LV, _fan_on),
    ]
    part_shapes = {"pack": "rounded", "limits": "ecu", **{f"b{i}": "module" for i in range(1, 15)},
                   **{f"t{i}": "pill" for i in (1, 2, 3)}, "intake": "vent", "health": "rounded", "fan": "fan",
                   "counters": "ecu", "aux": "battery", "dcdc": "finned"}
    groups = [("Rear seat", 9, 19, 88, 16),
              ("Hybrid battery - 14 blocks in series (1-7, then 8-14 back)", 3, 40, 71.5, 70),
              ("Cargo area", 3, 196, 94, 42)]
    parts = [
        Part("pack", "Whole pack", (5, 121, 66, 15),
             [("Charge", _soc, "%", 1), ("Charge (2nd reading)", "soc_hv", "%", 1), ("Current", "batt_amps", "A", 1),
              ("Pack voltage", "pack_volts", "V", 1), ("Power in/out", _power_kw, "kW", 1),
              ("Block spread (highest - lowest)", _spread, "V", 2),
              ("Heat made inside the pack (I² x R)", calc.pack_heat_w, "W", 0), (f"C-rate (current / {cfg.BATTERY_AH} Ah)", calc.c_rate, "C", 1),
              ("Using this much of the allowed power", calc.limit_usage_pct, "%", 0),
              ("Energy out this trip", lambda v, n: TRACKER.wh_out, "Wh", 0),
              ("Energy in this trip", lambda v, n: TRACKER.wh_in, "Wh", 0)],
             (0, 2), lambda v, n: None if _soc(v, n) is None else (LEVEL, _soc(v, n) / 100),
             lambda v, n: None if _soc(v, n) is None else ("ideal" if cfg.SOC_IDEAL[0] <= _soc(v, n) <= cfg.SOC_IDEAL[1] else "warn"),
             info="Negative current / power = charging. The Prius normally keeps the charge between about 40 and 80% "
                  "(training data, unconfirmed)."),
        Part("limits", "Battery computer:\nlimits", (76, 61.5, 20, 25),
             [("Can take in", lambda v, n: None if fresh(v, "chg_lim", n) is None else abs(fresh(v, "chg_lim", n)), "kW", 0),
              ("Can give out", "dis_lim", "kW", 0), ("Charge value at start (2198, meaning unclear)", "soc_ig", "%", 1),
              ("Charge max (2198, meaning unclear)", "soc_max", "%", 1), ("Charge min (2198, meaning unclear)", "soc_min", "%", 1)],
             (0, 1), level("dis_lim", cfg.POWER_LIMIT_COLOUR_KW),
             tags=("in", "out"),
             info="How much power the battery computer allows in and out right now. These shrink when the battery "
                  "is cold, hot, very full or very empty."),
        *[Part(f"b{i}", f"B{i}", _block_rect(i),
               [("Voltage", f"block{i:02d}", "V", 2), ("Difference from pack average", _dev(i), "V", 3),
                ("Internal resistance (battery computer)", lambda v, n, k=f"res{i:02d}": None if fresh(v, k, n) is None
                 else fresh(v, k, n) * 1000, "mΩ", 0),
                ("Internal resistance (measured live from voltage vs current)", _live_r(i), "mΩ", 1)],
               (0, 2), lambda v, n, f=_dev(i): None if f(v, n) is None else (DEVIATE, abs(f(v, n)) / cfg.BLK_COLOUR_FULL_DEV),
               _block_state(i),
               info="Each block is 2 modules of 6 nickel-metal hydride cells. A block that sits lower than the others at "
                    "rest (or higher while charging) and has higher resistance is the weak one.")
          for i in range(1, 15)],
        *[Part(f"t{i}", f"Temp {i}", (8 + 22 * (i - 1), 94, 21, 14),
               [(f"Battery temp sensor {i}", f"batt_tb{i}", "°C", 1),
                ("Time spent too hot (counter)", "cnt_hot", "", 0)],
               (0,), heat(f"batt_tb{i}", *cfg.BATT_TEMP_COLOUR_RANGE), temp_state(f"batt_tb{i}"),
               info="One of three temperature sensors inside the hybrid battery. They should stay within a few degrees "
                    "of each other.")
          for i in (1, 2, 3)],
        Part("intake", "Cooling air in\n(rear seat vent)", (68, 20, 28, 14),
             [("Air going into the battery", "batt_intake", "°C", 1),
              ("Battery average minus this (calculated)", calc.cooling_delta_c, "°C", 1)],
             (0,), heat("batt_intake", *cfg.BATT_AIR_COLOUR_RANGE), temp_state("batt_intake"),
             info="Cabin air pulled in to cool the battery (vent by the rear seat)."),
        Part("health", "Battery health (calculated)", (5, 140, 66, 26),
             [("Capacity estimate", lambda v, n: TRACKER.capacity_ah, "Ah", 2), ("Rated capacity", lambda v, n: cfg.BATTERY_AH, "Ah", 1),
              ("Pack resistance - measured live", _live_pack_r, "mΩ", 0),
              ("Pack resistance - battery computer", _ecu_pack_r, "mΩ", 0),
              ("Weakest block (live)", _weakest_live, "", 0),
              ("Current spread used for the live measurement", _live_spread, "A", 1),
              ("Temp above cooling air", calc.cooling_delta_c, "°C", 1)],
             (0, 2), lambda v, n: None if TRACKER.capacity_ah is None else (LEVEL, TRACKER.capacity_ah / cfg.BATTERY_AH),
             tags=("capacity", "resistance"),
             info="Worked out while you drive. Capacity = amp-hours counted in/out / change in the car's charge % "
                  "(needs a 5% swing; uses the car's own charge estimate, so treat it as a trend). Live resistance = how "
                  "much each block's voltage drops per amp (slope of voltage vs current); it needs about 10 A of spread "
                  f"in current, so it appears after some accelerating/braking. Rated: {cfg.BATTERY_AH} Ah (Oak Ridge National Lab)."),
        Part("fan", "Cooling fan", (76, 40, 20, 20),
             [("Fan power", "fan_pct", "%", 0), ("Fan relay", "fan_relay", "on/off", 0),
              ("Fan motor voltage", "fan_volts", "V", 1), ("Fan mode", "fan_mode", "", 0)],
             (0,), level("fan_pct", 100),
             info="The battery cooling fan. It speeds up as the battery warms."),
        Part("counters", "Battery computer:\ncounters", (76, 88, 20, 25),
             [("Time too LOW", "cnt_low", "", 0), ("Time DC was blocked", "cnt_dcinh", "", 0),
              ("Time too HIGH", "cnt_high", "", 0), ("Time too HOT", "cnt_hot", "", 0),
              ("Battery computer mode", _batt_mode, "", 0),
              ("Asking for the fan on standby", "batt_standby", "on/off", 0)],
             (0, 3), None, _counters_state,
             tags=("too low", "too hot"),
             info="Counters the battery computer keeps of how long the battery spent in bad conditions. 0 everywhere "
                  "is ideal. Units aren't documented. Mode: normally 'driving'; 'current-sensor calibration' "
                  "happens briefly at start-up."),
        Part("aux", "12V battery", (58, 204, 38, 26),
             [("Voltage (hybrid computer)", "aux_volts", "V", 2), ("Voltage (battery computer)", "aux_v2", "V", 2),
              ("Voltage (dashboard meter)", "aux_v3", "V", 1), ("Temperature", "aux_batt", "°C", 0)],
             (0, 3), lambda v, n: None if fresh(v, "aux_volts", n) is None else (LEVEL, (fresh(v, "aux_volts", n) - cfg.AUX_COLOUR_RANGE[0])
                                                        / (cfg.AUX_COLOUR_RANGE[1] - cfg.AUX_COLOUR_RANGE[0])),
             _aux_state,
             info="The small 12 V battery in the cargo area. While READY it should read about 13.5-14.5 V because the "
                  "DC-DC converter is charging it."),
        Part("dcdc", "DC-DC converter\n(front, in inverter)", (22, 2, 40, 14),
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
    default_shape = "rounded"
    about = ("Running totals worked out from the live readings. They're only as good as how often each reading "
             "arrives (every ~1-2 s), so short events like quick stops are approximate. Fuel is estimated from air "
             f"flow (E10 gas), braking energy from the car's speed and weight ({cfg.CURB_KG:,} kg + {cfg.DRIVER_KG} kg driver).")
    poll_extra = TRIP_KEYS + ("batt_tb1", "batt_tb2", "batt_tb3", "e_ect", "engine")
    parts = [
        _tile("dist", "Distance", 0, 0, [("Distance", _t(lambda: TRACKER.km), "km", 2),
                                        ("Distance (miles)", _t(lambda: TRACKER.km * cfg.MI_PER_KM), "mi", 2)], (0, 1)),
        _tile("speed", "Average speed", 1, 0, [("Average while moving", _t(TRACKER.avg_speed), "km/h", 0),
                                               ("Time moving", _t(lambda: TRACKER.moving_s / 60), "min", 1)], (0, 1)),
        _tile("fuel", "Fuel used", 0, 1, [("Fuel used", _t(lambda: TRACKER.fuel_l), "L", 2),
                                          ("Fuel used (US gal)", _t(lambda: TRACKER.fuel_l / cfg.L_PER_US_GAL), "gal", 3)], (0,)),
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
                                                        ("Rated", _t(lambda: cfg.BATTERY_AH), "Ah", 1)], (0,)),
        _tile("weak", "Weakest block (live)", 1, 8, [("Highest live resistance", _weakest_live, "", 0)], (0,)),
    ]
    highlights = [("Distance", _t(lambda: TRACKER.km), "km", 2), ("Average economy", _t(TRACKER.avg_l_100km), "L/100km", 1),
                  ("Driven on electricity", _t(TRACKER.ev_share_pct), "%", 0),
                  ("Braking energy recovered", _t(TRACKER.regen_recovered_pct), "%", 0)]

    def build_panel(self, parent, app):
        super().build_panel(parent, app)
        tk.Button(parent, text="Reset trip", command=lambda: (TRACKER.reset(), app.refresh()), bg=cfg.CLOSEUP_PART, fg=TEXT,
                  activebackground=cfg.BUTTON_ACTIVE, activeforeground=TEXT, relief="flat", padx=10, pady=4,
                  font=("Segoe UI", 10)).pack(anchor="w", pady=(12, 0))
