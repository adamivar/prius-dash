"""Sensor definitions and the background poller (real car or demo)."""
import math
import random
import threading
import time
from dataclasses import dataclass
from typing import Callable


def w(d, i):
    """Two bytes as one 16-bit number (Torque's A*256+B)."""
    return d[i] * 256 + d[i + 1]


# Requests that answered in the full car test on 2026-09-26 (prius_fulltest_20260926_000411.txt).
CONFIRMED = {("7B0", "2103"), ("7B0", "2105"), ("7B0", "2106"), ("7B0", "2107"), ("7B0", "211D"), ("7B0", "211F"), ("7B0", "2121"), ("7B0", "213C"), ("7B0", "213D"), ("7B0", "2142"), ("7B0", "2146"), ("7B0", "2147"), ("7B0", "2148"), ("7B0", "2158"), ("7B0", "215A"), ("7B0", "215F"), ("7B0", "21A1"), ("7B0", "21A3"), ("7B0", "21A6"), ("7B0", "21BC"), ("7B0", "21BE"), ("7C0", "2112"), ("7C0", "2113"), ("7C0", "2121"), ("7C0", "2123"), ("7C0", "2129"), ("7C0", "2141"), ("7C0", "2168"), ("7C0", "21A1"), ("7C0", "21A7"), ("7C0", "21AC"), ("7C4", "2121"), ("7C4", "2122"), ("7C4", "2124"), ("7C4", "2126"), ("7C4", "2129"), ("7C4", "213C"), ("7C4", "213D"), ("7C4", "2141"), ("7C4", "2143"), ("7C4", "2144"), ("7C4", "2149"), ("7C4", "214A"), ("7C4", "214B"), ("7C4", "214C"), ("7C4", "2153"), ("7E0", "0100"), ("7E0", "0105"), ("7E0", "010B"), ("7E0", "010C"), ("7E0", "0120"), ("7E0", "0133"), ("7E0", "013C"), ("7E0", "0140"), ("7E0", "2101"), ("7E0", "2103"), ("7E0", "2104"), ("7E0", "2106"), ("7E0", "2124"), ("7E0", "2137"), ("7E0", "213C"), ("7E0", "2144"), ("7E0", "2145"), ("7E0", "2147"), ("7E0", "2149"), ("7E0", "2154"), ("7E0", "21C1"), ("7E2", "0100"), ("7E2", "0140"), ("7E2", "015B"), ("7E2", "2101"), ("7E2", "2121"), ("7E2", "2141"), ("7E2", "2161"), ("7E2", "2162"), ("7E2", "2167"), ("7E2", "2168"), ("7E2", "2170"), ("7E2", "2171"), ("7E2", "2174"), ("7E2", "2175"), ("7E2", "2178"), ("7E2", "2179"), ("7E2", "217C"), ("7E2", "217D"), ("7E2", "2181"), ("7E2", "2187"), ("7E2", "218A"), ("7E2", "218E"), ("7E2", "2192"), ("7E2", "2195"), ("7E2", "2198"), ("7E2", "219B"), ("7E2", "21C1"), ("7E2", "21C2"), ("7E2", "21E1")}


@dataclass
class Sensor:
    key: str
    name: str             # plain-English name (side list + hover title)
    pid: str              # mode+PID sent to `header`
    decode: Callable      # data bytes -> value (always °C for temperatures)
    unit: str
    cold: float = 0       # at/below this the box is the base colour
    danger: float = 0     # at/above this the box is full red
    tested: bool = False  # True = this PID has answered in the test car (2010 Prius)
    ideal: tuple = (0, 0) # (low, high) healthy operating range -> green border
    label: str = ""       # text inside the box on the car drawing
    info: str = ""        # hover description
    tech: str = ""        # technical name from the PID spreadsheet
    header: str = "7E2"   # which computer: 7E2 hybrid, 7E0 engine, 7C4 climate/A-C
    extras: tuple = ()    # extra hover readings: (label, header, pid, decode[, unit if not a temperature])
    slow: bool = False    # True = only read every few loops (changes slowly)

    def __post_init__(self):
        if (self.header, self.pid) in CONFIRMED:
            self.tested = True


def start_and_peak(pid, i_start, i_peak):
    """Hybrid ECU replies that also carry 'temp at IG-ON' and 'max temp' bytes."""
    return (("At start of this drive", "7E2", pid, lambda d: d[i_start] - 40),
            ("Peak this drive", "7E2", pid, lambda d: d[i_peak] - 40))


# Formulas: "ZVW30 Custom PIDs for Torque" spreadsheet, Metric tab.
# cold/danger/ideal limits and the descriptions: training-data estimates, NOT from a Toyota source (unconfirmed).
TEMPS = [
    Sensor("ambient", "Outside air", "2101", lambda d: d[3] - 40, "°C", 0, 50, True, (10, 30),
           label="Outside air", tech="Ambient temperature", extras=(("Climate system's outside sensor", "7C4", "2122", lambda d: d[0] * 89.25 / 255 - 23.3), ("Climate system's adjusted outside temp", "7C4", "213D", lambda d: d[0] * 81.6 / 255 - 30.8)),
           info="Air temperature outside the car, measured near the front bumper. "
                "Can read high when parked in the sun or after slow driving (engine heat)."),
    Sensor("intake_air", "Engine air intake", "2101", lambda d: d[2] - 40, "°C", 20, 70, True, (20, 45),
           label="Engine air intake", tech="Intake Air Temperature (IAT)", extras=(("At start of this drive", "7E0", "2137", lambda d: d[1] * 159.3 / 255 - 40),),
           info="Temperature of the air being sucked into the engine. Hotter air means slightly less power "
                "and efficiency. It rises in traffic and when parked with the engine running."),
    Sensor("engine", "Engine", "2101", lambda d: d[5] - 40, "°C", 40, 110, True, (80, 95),
           label="Engine\n(coolant)", tech="Engine Coolant Temperature (ECT)", extras=(
               ("At start of this drive", "7E0", "2137", lambda d: d[0] * 159.3 / 255 - 40),
               ("Engine computer says", "7E0", "2101", lambda d: d[8] - 40),
               ("Dashboard meter says", "7C0", "2123", lambda d: d[0] / 2),
               ("Climate computer says", "7C4", "2126", lambda d: d[0] * 89.25 / 255 + 1.3),
               ("Standard OBD says", "7E0", "0105", lambda d: d[0] - 40)),
           info="Temperature of the engine's coolant - the main 'is the engine warm' number. "
                "Below about 80 °C the car runs the engine more to warm it up. "
                "Sustained readings near the danger limit mean overheating: pull over."),
    Sensor("mg1", "Generator motor", "2161", lambda d: d[0] - 40, "°C", 30, 150, True, (30, 90),
           label="Generator\n(MG1)", tech="MG1 temperature", extras=start_and_peak("2161", 1, 2),
           info="MG1 is the smaller motor-generator in the transmission. It starts the engine, "
                "turns engine power into electricity, and sets engine speed through the planetary gear."),
    Sensor("mg2", "Drive motor", "2162", lambda d: d[0] - 40, "°C", 30, 150, True, (30, 90),
           label="Drive motor\n(MG2)", tech="MG2 temperature", extras=start_and_peak("2162", 1, 2),
           info="MG2 is the main electric motor that turns the front wheels. It also acts as a "
                "generator when you brake or coast (regenerative braking). Heats up on long climbs."),
    Sensor("inv_mg1", "Generator inverter", "2170", lambda d: d[0] - 40, "°C", 30, 100, True, (30, 65),
           label="Generator\ninverter", tech="Inverter MG1 temperature", extras=start_and_peak("2170", 1, 2),
           info="Power electronics that convert between the battery's DC and the AC used by the "
                "generator motor (MG1). Cooled by the separate inverter coolant loop."),
    Sensor("inv_mg2", "Drive motor inverter", "2171", lambda d: d[0] - 40, "°C", 30, 100, True, (30, 65),
           label="Drive\ninverter", tech="Inverter MG2 temperature", extras=start_and_peak("2171", 1, 2),
           info="Power electronics that feed the drive motor (MG2). Works hardest during strong "
                "acceleration and hard regenerative braking."),
    Sensor("boost_upper", "Voltage booster (top)", "2174", lambda d: d[0] - 40, "°C", 30, 100, True, (30, 65),
           label="Booster\n(top)", tech="Boost converter temperature (upper)", extras=start_and_peak("2174", 2, 3),
           info="The boost converter raises the hybrid battery's ~200 V up to as much as ~650 V "
                "for the motors. This is its upper temperature sensor."),
    Sensor("boost_lower", "Voltage booster (bottom)", "2174", lambda d: d[1] - 40, "°C", 30, 100, True, (30, 65),
           label="Booster\n(bottom)", tech="Boost converter temperature (lower)", extras=start_and_peak("2174", 2, 3),
           info="Second temperature sensor on the boost converter (the part that raises battery "
                "voltage for the motors)."),
    Sensor("inv_coolant", "Inverter coolant", "2175", lambda d: d[3] - 40, "°C", 30, 80, False, (25, 55),
           label="Inverter\ncoolant", tech="Inverter coolant temperature",
           info="The inverter and motors have their own coolant loop and electric pump, separate "
                "from the engine's. A high reading here can mean a failing inverter coolant pump."),
    Sensor("batt_intake", "Battery cooling air", "2187", lambda d: w(d, 0) * 255.9 / 65535 - 50, "°C", 15, 45, False, (15, 30),
           label="Battery cooling air", tech="HV battery intake air temperature",
           info="Air pulled from the cabin by a fan to cool the hybrid battery. The vent is by the "
                "rear seat - keep it clear of bags and dust or the battery runs hotter."),
    Sensor("batt_tb1", "Hybrid battery sensor 1", "2187", lambda d: w(d, 2) * 255.9 / 65535 - 50, "°C", 20, 55, False, (20, 35),
           label="Hybrid battery\ntemp 1", tech="Temp of Batt TB1", extras=(("Battery time spent too hot (counter)", "7E2", "2192", lambda d: w(d, 13), " (counter, 0 = never)"),),
           info="One of three temperature sensors inside the high-voltage hybrid battery (NiMH). "
                "When it gets hot the car limits battery power to protect it."),
    Sensor("batt_tb2", "Hybrid battery sensor 2", "2187", lambda d: w(d, 4) * 255.9 / 65535 - 50, "°C", 20, 55, False, (20, 35),
           label="Hybrid battery\ntemp 2", tech="Temp of Batt TB2", extras=(("Battery time spent too hot (counter)", "7E2", "2192", lambda d: w(d, 13), " (counter, 0 = never)"),),
           info="Middle temperature sensor in the hybrid battery. A sensor much hotter than the "
                "others can point to a blocked cooling path or weak cells."),
    Sensor("batt_tb3", "Hybrid battery sensor 3", "2187", lambda d: w(d, 6) * 255.9 / 65535 - 50, "°C", 20, 55, False, (20, 35),
           label="Hybrid battery\ntemp 3", tech="Temp of Batt TB3", extras=(("Battery time spent too hot (counter)", "7E2", "2192", lambda d: w(d, 13), " (counter, 0 = never)"),),
           info="Third temperature sensor in the hybrid battery. Compare it with the other two - "
                "they should stay within a few degrees of each other."),
    Sensor("aux_batt", "12V battery", "2141", lambda d: d[4] - 40, "°C", 15, 60, False, (10, 35),
           label="12V battery", tech="Auxiliary battery temperature",
           info="The small 12 V battery in the cargo area. It powers the computers and 'boots' the "
                "hybrid system when you press POWER. Heat shortens its life."),
    Sensor("cabin", "Cabin air", "2121", lambda d: d[0] * 63.75 / 255 - 6.5, "°C", 10, 50, False, (18, 26),
           header="7C4", label="Cabin air", tech="Room temperature sensor (climate ECU)",
           extras=(("A/C set to", "7C4", "2129", lambda d: d[0] / 2 + 17.5),),
           info="Air temperature inside the car, from the climate control's sensor in the dashboard. "
                "Parked in the sun it can get far hotter than outside."),
    Sensor("evap", "A/C evaporator", "214B", lambda d: d[0] * 89.25 / 255 - 29.7, "°C", 0, 40, False, (1, 12),
           header="7C4", label="A/C evaporator", tech="Evaporator fin thermistor (climate ECU)",
           extras=(("A/C is aiming for", "7C4", "214C", lambda d: w(d, 0) / 100 - 327.68),),
           info="The ice-cold radiator behind the dashboard that chills the cabin air. With A/C on it "
                "should sit a few degrees above freezing; if it stays warm with A/C on, the A/C isn't "
                "cooling. With A/C off it just follows the cabin temperature."),
    Sensor("catalyst", "Catalytic converter", "013C", lambda d: w(d, 0) / 10 - 40, "°C", 100, 900, False, (400, 800),
           header="7E0", label="Catalytic converter", tech="Catalyst temp bank 1 sensor 1 (standard OBD PID 013C)",
           info="Cleans the exhaust. It has to be hot (roughly 400 °C or more) to work - one reason the "
                "Prius runs the engine when cold. Usually an estimate calculated by the engine computer, "
                "not a real sensor. Very high readings (often from misfires) can damage it."),
]


def _block(i):
    return lambda d: w(d, 2 * i) * 79.99 / 65535


# Electrical readings. Same spreadsheet; the ones marked tested=True answered in the test car (2010 Prius) on 2026-09-25.
ELEC = [
    Sensor("batt_amps", "Hybrid battery current", "218A", lambda d: w(d, 0) / 100 - 327.68, "A", tested=True,
           tech="Power Resource IB (negative = charging)"),
    Sensor("pack_volts", "Hybrid battery voltage", "2181", lambda d: w(d, 30) / 10, "V", tested=True, slow=True,
           tech="Power Resource VB"),
    *[Sensor(f"block{i + 1:02d}", f"Block {i + 1}", "2181", _block(i), "V", tested=True, slow=True)
      for i in range(14)],
    Sensor("vl", "Voltage before booster", "2174", lambda d: w(d, 5) / 2, "V", tested=True,
           tech="VL - voltage before boosting"),
    Sensor("vh", "Voltage after booster", "2174", lambda d: w(d, 7) / 2, "V", tested=True,
           tech="VH - voltage after boosting"),
    Sensor("mg1_rpm", "Generator speed", "2161", lambda d: w(d, 3) - 32768, "rpm", tested=True),
    Sensor("mg2_rpm", "Drive motor speed", "2162", lambda d: w(d, 3) - 32768, "rpm", tested=True),
    Sensor("mg1_nm", "Generator torque", "2167", lambda d: w(d, 0) / 8 - 4096, "Nm", tested=True),
    Sensor("mg2_nm", "Drive motor torque", "2168", lambda d: w(d, 0) / 8 - 4096, "Nm", tested=True),
    Sensor("ac_watts", "A/C power", "217D", lambda d: d[2] * 50, "W", slow=True,
           tech="A/C consumption power"),
    Sensor("aux_volts", "12V battery voltage", "2101", lambda d: w(d, 19) / 1000, "V", tested=True, slow=True,
           tech="+B"),
    Sensor("dcdc_duty", "DC-DC converter duty", "2179", lambda d: w(d, 0) * 399.9 / 65535, "%", slow=True,
           tech="DCDC Cnv Target Pulse Duty"),
    *[Sensor(f"res{i + 1:02d}", f"Block {i + 1} internal resistance", "2195", (lambda i: lambda d: d[i] / 1000)(i),
             "ohm", slow=True, tech=f"Internal Resistance R{i + 1:02d}") for i in range(14)],
    Sensor("ac_rpm", "A/C compressor speed", "2149", lambda d: w(d, 0), "rpm", header="7C4", slow=True,
           tech="Compressor Speed"),
    Sensor("blower", "Cabin fan speed level", "213C", lambda d: d[0], "", header="7C4", slow=True,
           tech="Blower Motor Speed Level (0-31)"),
]

def _kmh(i):
    return lambda d: d[i] * 32 / 25


# Things that spin (RPM), plus speeds in km/h that the Spinning view converts to wheel RPM.
_E = {s.key: s for s in ELEC}
ROT = [
    Sensor("eng_rpm", "Engine (standard OBD)", "010C", lambda d: w(d, 0) / 4, "rpm", header="7E0", tested=True,
           tech="Engine RPM, standard OBD PID 010C"),
    Sensor("eng_rpm_hv", "Engine (hybrid computer)", "2101", lambda d: w(d, 6) / 4, "rpm", tested=True, slow=True,
           tech="Engine Speed_7E2"),
    Sensor("eng_rpm_ecm", "Engine (engine computer)", "2101", lambda d: w(d, 9) / 4, "rpm", header="7E0", slow=True,
           tech="Engine Speed_7E0"),
    Sensor("eng_rpm_sensor", "Engine (crank sensor)", "2141", lambda d: w(d, 5) / 4, "rpm", slow=True,
           tech="Engine Rev (Sensor)"),
    Sensor("eng_target", "Engine target", "2149", lambda d: d[2] * 25, "rpm", header="7E0", slow=True,
           tech="HV Target Engine Speed"),
    _E["mg1_rpm"], _E["mg2_rpm"], _E["ac_rpm"],
    Sensor("ac_target", "A/C compressor target", "214A", lambda d: w(d, 0), "rpm", header="7C4", slow=True,
           tech="Compressor Target Speed"),
    Sensor("pump_rpm", "Inverter coolant pump", "2175", lambda d: w(d, 1), "rpm", slow=True,
           tech="Inverter Water Pump Revolution"),
    *[Sensor(f"whl_{k}", f"{name} wheel speed", "2103", _kmh(i), "km/h", header="7B0", tech=f"{k.upper()} Wheel Speed")
      for i, (k, name) in enumerate([("fr", "Front right"), ("fl", "Front left"), ("rr", "Rear right"), ("rl", "Rear left")])],
    Sensor("spd_hv", "Car speed (hybrid computer)", "2101", lambda d: d[8], "km/h", tested=True, slow=True),
    Sensor("spd_ecm", "Car speed (engine computer)", "2101", lambda d: d[11], "km/h", header="7E0", slow=True),
    Sensor("spd_abs", "Car speed (brake computer)", "2121", lambda d: d[0] * 326.4 / 255, "km/h", header="7B0", slow=True),
    Sensor("spd_meter", "Car speed (dashboard meter)", "2121", lambda d: d[0], "km/h", header="7C0", slow=True),
]

def _bit(byte, bit):
    """On/off flag from the spreadsheet's {X:n} notation: 1.0 = on, 0.0 = off."""
    return lambda d: float((d[byte] >> bit) & 1)


def _signed16(hi, lo):
    v = hi * 256 + lo
    return v - 65536 if v >= 32768 else v


# Twisting force (Spinning view) + battery cooling fan
TORQUE = [
    _E["mg1_nm"], _E["mg2_nm"],
    # "Actual Engine Torque" (7E0 2149) read 0 Nm in the car test even at 1,700 rpm - not used.
    Sensor("regen_req", "Regen braking requested", "2148", lambda d: w(d, 0), "Nm", header="7B0", slow=True,
           tech="FR Regenerative Request"),
    Sensor("regen_op", "Regen braking delivered", "2148", lambda d: w(d, 2), "Nm", header="7B0", slow=True,
           tech="FR Regenerative Operation"),
    Sensor("fan_pct", "Battery cooling fan", "218E", lambda d: d[0] / 2, "%", slow=True, tech="Cooling Fan 0"),
    Sensor("fan_relay", "Battery fan relay", "218E", _bit(1, 7), "on/off", slow=True, tech="Cooling Fan Relay Status"),
    Sensor("fan_volts", "Battery fan motor voltage", "2181", lambda d: d[32] / 10, "V", tested=True, slow=True,
           tech="VMF Fan Motor Voltage1"),
]

# On/off signals shown in the Electrical view: (key, name, header, pid, byte, bit)
_ONOFF = [
    ("brake_lights", "Brake lights", "7B0", "211F", 0, 7),   # Stop Light SW (relay bit 213C stayed off)
    ("lamp_abs", "ABS warning light", "7B0", "213D", 0, 7),
    ("lamp_brake", "Brake warning light", "7B0", "213D", 0, 6),
    ("lamp_slip", "Slip indicator light", "7B0", "213D", 0, 5),
    ("lamp_ecb", "ECB (brake system) warning light", "7B0", "213D", 0, 1),
    ("buzzer", "Brake system buzzer", "7B0", "213D", 0, 4),
    ("lamp_mil", "Check engine light", "7E0", "2106", 0, 7),
    ("pump_on", "Inverter coolant pump running", "7E2", "2175", 0, 4),
    ("dcdc_prohibit", "DC-DC converter told to stop", "7E2", "2175", 0, 6),
    ("ac_gate", "A/C inverter switching", "7E2", "2175", 0, 5),
    ("mg1_gate", "Generator inverter switching", "7E2", "2170", 3, 7),
    ("mg2_gate", "Drive inverter switching", "7E2", "2171", 3, 7),
    ("conv_gate", "Booster switching", "7E2", "2174", 4, 7),
    ("ov_conv", "Over-voltage into booster", "7E2", "2174", 4, 6),
    ("ov_inv", "Over-voltage into inverter", "7E2", "2174", 4, 5),
    ("mg1_inv_shutdown", "Generator inverter shut down", "7E2", "2178", 0, 7),
    ("mg1_inv_fail", "Generator inverter FAIL", "7E2", "2178", 0, 6),
    ("mg2_inv_shutdown", "Drive inverter shut down", "7E2", "2178", 1, 7),
    ("mg2_inv_fail", "Drive inverter FAIL", "7E2", "2178", 1, 6),
    ("conv_shutdown", "Booster shut down", "7E2", "2179", 3, 7),
    ("conv_fail", "Booster FAIL", "7E2", "2179", 3, 6),
]
ONOFF = [Sensor(k, n, p, _bit(byte, bit), "on/off", header=h, slow=True, tech=n) for k, n, h, p, byte, bit in _ONOFF]
# The "Water Pump Running" bit read OFF in the car test while the pump spun at 3,375 rpm - use the pump's RPM instead.
ONOFF = [Sensor("pump_on", "Inverter coolant pump running", "2175", lambda d: 1.0 if w(d, 1) > 0 else 0.0, "on/off",
                slow=True, tech="Inverter Water Pump Revolution > 0") if s.key == "pump_on" else s for s in ONOFF]
SOC = Sensor("soc", "Battery charge", "015B", lambda d: d[0] * 20 / 51, "%", tested=True,
             tech="Hybrid battery pack remaining life (standard OBD 015B)")

# Pressures (Pressure view). Stored in kPa; the view converts.
PRESS = [
    Sensor("map_hv", "Intake manifold (hybrid computer)", "2101", lambda d: d[1], "kPa", tested=True,
           tech="Manifold Air Pressure_7E2"),
    Sensor("baro_hv", "Outside air pressure (hybrid computer)", "2101", lambda d: d[4], "kPa", tested=True,
           slow=True, tech="Atmosphere Pressure_7E2"),
    Sensor("map_ecm", "Intake manifold (engine computer)", "2101", lambda d: d[5], "kPa", header="7E0", slow=True,
           tech="Manifold Air Pressure_7E0"),
    Sensor("baro_ecm", "Outside air pressure (engine computer)", "2101", lambda d: d[7], "kPa", header="7E0",
           slow=True, tech="Atmosphere Pressure_7E0"),
    Sensor("map_obd", "Intake manifold (standard OBD)", "010B", lambda d: d[0], "kPa", header="7E0", slow=True,
           tech="Standard OBD PID 010B"),
    Sensor("baro_obd", "Outside air pressure (standard OBD)", "0133", lambda d: d[0], "kPa", header="7E0",
           slow=True, tech="Standard OBD PID 0133"),
    Sensor("ac_press", "A/C refrigerant pressure", "2153", lambda d: (d[0] * 3.75105 / 255 - 0.45668) * 1000,
           "kPa", header="7C4", slow=True, tech="Regulator Pressure Sensor (gauge pressure)"),
]

def _S(key, name, pid, decode, unit, header="7E2", tech="", slow=True):
    return Sensor(key, name, pid, decode, unit, header=header, slow=slow, tech=tech or name)


# Steering (Spinning view)
STEER = [
    _S("steer", "Steering wheel angle", "2106", lambda d: w(d, 2) / 10 - 3276.8, "°", "7B0", "Steering Angle Sensor", False),
    _S("steer2", "Steering wheel angle (2nd reading)", "2147", lambda d: w(d, 3) / 10 - 3276.8, "°", "7B0",
       "Steering Angle Value"),
    _S("yaw", "Turning rate (yaw)", "2106", lambda d: d[0] - 128, "°/s", "7B0", "Yaw Rate Sensor", False),
]

# Extra electrical readings found in the full car test
ELEC_EXTRA = [
    _S("chg_lim", "Battery can take in (limit)", "2198", lambda d: d[2] / 2 - 64, "kW", tech="HV battery charge control"),
    _S("dis_lim", "Battery can give out (limit)", "2198", lambda d: d[3] / 2 - 64, "kW",
       tech="HV battery discharge control"),
    *[_S(f"sol_{n.lower()}", f"Brake actuator {n} solenoid", "21A3", (lambda i: lambda d: d[i] * 3 / 255)(i), "A", "7B0",
         f"{n} Solenoid Current") for i, n in enumerate(["SLA", "SLR", "SSC", "SCC", "SMC", "SRC"])],
    _S("pump_duty", "Coolant pump effort", "2179", lambda d: d[2] * 6.25, "%", tech="Water Pump Run Control Duty"),
    _S("boost_ratio", "Booster ratio", "217D", lambda d: d[0] / 2, "%", tech="Boost Ratio"),
    _S("aux_v2", "12V battery (battery ECU)", "2181", lambda d: w(d, 28) * 79.9 / 65535 - 40, "V",
       tech="Auxiliary Battery Voltage"),
    _S("aux_v3", "12V battery (dashboard meter)", "2113", lambda d: d[0] / 10, "V", "7C0", "+B Voltage Value"),
]

# Engine close-up (engine computer 7E0 unless noted)
ENGINE = [
    _S("e_load", "Engine load", "2101", lambda d: d[0] * 20 / 51, "%", "7E0", "Calculated Load_7E0", False),
    _S("e_maf", "Air flow into engine", "2101", lambda d: w(d, 3) / 100, "g/s", "7E0", "Mass Air Flow", False),
    _S("e_iat", "Intake air temp", "2101", lambda d: d[6] - 40, "°C", "7E0", "Intake Air Temperature_7E0"),
    _S("e_ect", "Coolant temp (engine computer)", "2101", lambda d: d[8] - 40, "°C", "7E0", "Coolant Temperature_7E0"),
    _S("e_runtime", "Time since READY", "2101", lambda d: w(d, 12), "s", "7E0", "Engine Run Time (Time since Ign-On)"),
    _S("e_fss", "Fuel system status", "2103", lambda d: d[0], "", "7E0", "Fuel System Status #1"),
    _S("e_stft", "Short-term fuel trim", "2103", lambda d: d[2] * 199.2 / 255 - 100, "%", "7E0", "Short FT #1", False),
    _S("e_ltft", "Long-term fuel trim", "2103", lambda d: d[3] * 199.2 / 255 - 100, "%", "7E0", "Long FT #1"),
    _S("e_ign", "Ignition timing", "2103", lambda d: d[4] / 2 - 64, "°", "7E0", "IGN Advance", False),
    _S("e_afr_target", "Target air-fuel ratio (lambda)", "2104", lambda d: w(d, 0) * 1.99 / 65535, "", "7E0",
       "Target Air-Fuel Ratio"),
    _S("e_lambda", "Measured air-fuel ratio (lambda)", "2104", lambda d: w(d, 2) * 1.99 / 65535, "", "7E0",
       "AF Lambda B1S1"),
    _S("e_afs_v", "Air-fuel sensor voltage", "2104", lambda d: w(d, 4) * 7.99 / 65535, "V", "7E0", "AFS Voltage B1S1"),
    _S("e_ect_start", "Coolant temp at start", "2137", lambda d: d[0] * 159.3 / 255 - 40, "°C", "7E0",
       "Initial Engine Coolant Temp"),
    _S("e_iat_start", "Intake air temp at start", "2137", lambda d: d[1] * 159.3 / 255 - 40, "°C", "7E0",
       "Initial Intake Air Temp"),
    _S("e_inj_vol", "Fuel per 10 injections (cyl 1)", "213C", lambda d: w(d, 0) * 2.047 / 65535, "ml", "7E0",
       "Injection volume (Cylinder 1) for 10 times"),
    _S("e_inj_us", "Injector open time (cyl 1)", "213C", lambda d: w(d, 2), "µs", "7E0", "Injection duration for cylinder 1"),
    _S("e_vvt_aim", "Valve timing target", "2144", lambda d: w(d, 0) * 399.9 / 65535, "%", "7E0", "VVT Aim Angle #1"),
    _S("e_vvt_duty", "Valve timing solenoid effort", "2144", lambda d: w(d, 2) * 399.9 / 65535, "%", "7E0",
       "VVT OCV Duty #1"),
    _S("e_vvt_angle", "Valve timing shift", "2144", lambda d: w(d, 4) * 639.9 / 65535, "°", "7E0", "VVT Change Angle #1"),
    *[_S(f"e_mis{i + 1}", f"Cylinder {i + 1} misfires", "2145", (lambda i: lambda d: d[3 + i])(i), "", "7E0",
         f"Cylinder #{i + 1} Misfire Count") for i in range(4)],
    _S("e_mis_all", "All-cylinder misfires", "2145", lambda d: d[7], "", "7E0", "All Cylinders Misfire Count"),
    _S("e_mis_rpm", "RPM at last misfire", "2145", lambda d: d[1] * 25, "rpm", "7E0", "Misfire RPM"),
    _S("e_ign_count", "Ignition count", "2145", lambda d: w(d, 8), "", "7E0", "Ignition Trig. Count"),
    _S("e_egr", "EGR valve position", "2147", lambda d: d[0], "steps", "7E0", "EGR Step Position"),
    _S("e_req_kw", "Power the hybrid system asks for", "2149", lambda d: w(d, 0) / 4, "kW", "7E0",
       "Requested Engine Torque (actually kW)", False),
    _S("e_warmup", "Warm-up requested", "2149", _bit(11, 6), "on/off", "7E0", "Request Warm-up"),
    _S("e_racing", "Engine forced on (maintenance / racing mode)", "2149", _bit(11, 5), "on/off", "7E0",
       "Racing Operation"),
    _S("e_fc_stop", "Fuel cut for engine stop", "2149", _bit(11, 3), "on/off", "7E0", "F/C for Engine Stop Req"),
    _S("e_ect_meter", "Coolant temp (dashboard meter)", "2123", lambda d: d[0] / 2, "°C", "7C0",
       "Coolant Temperature_7C0"),
    _S("e_ect_climate", "Coolant temp (climate computer)", "2126", lambda d: d[0] * 89.25 / 255 + 1.3, "°C", "7C4",
       "Engine Coolant Temp_7C4"),
    _S("e_ect_obd", "Coolant temp (standard OBD)", "0105", lambda d: d[0] - 40, "°C", "7E0", "Standard OBD PID 0105"),
    _S("throttle", "Throttle opening", "2101", lambda d: d[11] * 20 / 51, "%", tech="Throttle Position", slow=False),
    _S("pedal1", "Gas pedal (sensor 1)", "2101", lambda d: d[12] * 20 / 51, "%", tech="Accel Pedal Pos #1", slow=False),
    _S("pedal2", "Gas pedal (sensor 2)", "2101", lambda d: d[13] * 20 / 51, "%", tech="Accel Pedal Pos #2", slow=False),
    _S("fuel_l", "Fuel in tank", "2129", lambda d: d[0] / 2, "L", "7C0", "Fuel Input"),
    _S("oil_km", "Distance since oil-change reset", "2141", lambda d: d[0] * 2514600 / 15625, "km", "7C0",
       "Distance Since Oil Change (reset)"),
    _S("dtc_now", "Trouble codes stored now", "21E1", lambda d: d[0], "", tech="Number of Current Code"),
    _S("dtc_hist", "Trouble codes in history", "21E1", lambda d: d[1], "", tech="Number of History Code"),
]

# Battery close-up (hybrid computer 7E2)
BATTERY = [
    _S("soc_hv", "Battery charge (hybrid computer)", "2101", lambda d: d[21] * 20 / 51, "%", tech="State of Charge (All Bat)"),
    _S("soc_ig", "Battery charge at start (2198)", "2198", lambda d: d[5] / 2, "%", tech="SOC after IG-ON"),
    _S("soc_max", "Battery charge max (2198)", "2198", lambda d: d[6] / 2, "%", tech="SOC Max"),
    _S("soc_min", "Battery charge min (2198)", "2198", lambda d: d[7] / 2, "%", tech="SOC Min"),
    _S("cnt_low", "Time battery was too LOW (counter)", "2192", lambda d: w(d, 7), "", tech="Accumulated Time of Battery Low"),
    _S("cnt_dcinh", "Time DC was inhibited (counter)", "2192", lambda d: w(d, 9), "", tech="Accumulated Time of DC Inhibit"),
    _S("cnt_high", "Time battery was too HIGH (counter)", "2192", lambda d: w(d, 11), "",
       tech="Accumulated Time of Battery too High"),
    _S("cnt_hot", "Time battery was too HOT (counter)", "2192", lambda d: w(d, 13), "",
       tech="Accumulated Time of Hot Temperature"),
    _S("fan_mode", "Battery fan mode", "219B", lambda d: d[1], "", tech="Cooling Fan Mode 1"),
]

TRIP_KEYS = ("spd_hv", "eng_rpm_hv", "e_maf", "e_lambda", "batt_amps", "vl", "brake_lights", "regen_op",
             "ac_watts", "mg2_nm", "soc")

SENSORS = {s.key: s for s in TEMPS + ELEC + ROT + TORQUE + ONOFF + [SOC] + PRESS + STEER + ELEC_EXTRA
           + ENGINE + BATTERY}
SLOW_EVERY = 4    # current view's slow readings: once every this many loops
BG_PERIOD_S = 8   # other views' readings: refreshed about this often, in the background
TRIP_EVERY = 3    # readings the trip totals need: read every this many loops, whatever the view
BG_PER_LOOP = 3   # at most this many background requests per loop, so the current view stays fast


def _jobs(sensors):
    out = []
    for s in sensors:
        out.append((s.header, s.pid, s.key, s.decode, s.slow))
        for label, header, pid, decode, *_ in s.extras:
            out.append((header, pid, f"{s.key}|{label}", decode, s.slow))
    return out


class Poller(threading.Thread):
    """Reads the current view's sensors over and over, and every other view's sensors in the
    background every few seconds. Latest values land in self.values."""

    def __init__(self, sensors, port="COM6", demo=False):
        super().__init__(daemon=True)
        self.port = port
        self.demo = demo
        self.lock = threading.Lock()
        self.values = {}          # key -> (value, time.time())
        self.status = "starting"
        self.cycle_ms = 0
        self.stop_flag = threading.Event()
        self.last_bg = {}         # (header, pid) -> time of last background read
        self.set_sensors(sensors)

    def set_sensors(self, active, background=(), trip=()):
        """active = the current view's sensors (fast); trip = needed for trip totals (every few loops);
        background = everything else (slow refresh)."""
        active_jobs, bg_jobs, trip_jobs = _jobs(active), _jobs(background), _jobs(trip)
        kind = {}  # (header, pid) -> "fast" | "slow" | "trip" | "bg"
        for h, p, _, _, slow in active_jobs:
            kind[(h, p)] = "fast" if not slow or kind.get((h, p)) == "fast" else "slow"
        for h, p, _, _, _ in trip_jobs:
            if kind.get((h, p)) != "fast":
                kind[(h, p)] = "trip"
        for h, p, _, _, _ in bg_jobs:
            kind.setdefault((h, p), "bg")
        with self.lock:
            self.sensors = list(active) + list(background) + list(trip)
            self.jobs = active_jobs + bg_jobs + trip_jobs
            self.requests = sorted(kind.items())  # sorted by header -> few computer switches

    def _due(self, requests, loop, now):
        """Which requests to send this loop."""
        due = [r for r, k in requests if k == "fast" or (k == "slow" and loop % SLOW_EVERY == 0)
               or (k == "trip" and loop % TRIP_EVERY == 0)]
        bg = sorted((self.last_bg.get(r, 0), r) for r, k in requests if k == "bg")
        due += [r for last, r in bg if now - last >= BG_PERIOD_S][:BG_PER_LOOP]
        return sorted(due)

    def snapshot(self):
        with self.lock:
            return dict(self.values), self.status, self.cycle_ms

    def _store(self, key, value):
        with self.lock:
            self.values[key] = (value, time.time())

    def _set_status(self, text):
        with self.lock:
            self.status = text

    def run(self):
        if self.demo:
            self._run_demo()
        else:
            self._run_car()

    def _run_car(self):
        try:
            from elm import Elm327  # imported here so demo mode works without pyserial
        except ImportError:
            self._set_status("pyserial is not installed - run:\npython -m pip install pyserial")
            return
        while not self.stop_flag.is_set():
            elm = Elm327(self.port)
            try:
                self._set_status(f"connecting to {self.port}...")
                elm.open()
                self._set_status(f"connected on {self.port}")
                loop = 0
                while not self.stop_flag.is_set():
                    t0 = time.monotonic()
                    with self.lock:
                        requests, jobs = self.requests, self.jobs
                    for header, pid in self._due(requests, loop, time.time()):
                        self.last_bg[(header, pid)] = time.time()
                        elm.set_header(header)
                        data = elm.query(pid)
                        if data is None:
                            continue
                        for h, p, key, decode, _ in jobs:
                            if (h, p) != (header, pid):
                                continue
                            try:
                                self._store(key, round(decode(data), 2))
                            except IndexError:
                                pass  # reply shorter than the formula expects
                    loop += 1
                    self.cycle_ms = int((time.monotonic() - t0) * 1000)
            except Exception as e:  # adapter unplugged, car off, port busy...
                self._set_status(f"error: {e} - retrying in 3 s")
                time.sleep(3)
            finally:
                elm.close()

    def _run_demo(self):
        """Fake data: temperatures sweep cold -> past danger; electrical follows a made-up drive."""
        self._set_status("DEMO MODE (fake data)")
        phase, peak, smooth = {}, {}, {}
        while not self.stop_flag.is_set():
            t = time.time()
            elec = demo_electrical(t, smooth)
            with self.lock:
                sensors = list(self.sensors)
            for s in sensors:
                if s.key in elec:
                    self._store(s.key, round(elec[s.key], 2))
                    continue
                if s.unit != "°C":
                    continue
                phase.setdefault(s.key, random.uniform(0, 2 * math.pi))
                span = s.danger - s.cold
                wave = (math.sin(t / 6 + phase[s.key]) + 1) / 2          # 0..1
                v = round(s.cold - 0.1 * span + wave * 1.2 * span, 1)
                self._store(s.key, v)
                peak[s.key] = max(v, peak.get(s.key, v))
                for label, *_ in s.extras:
                    fake = peak[s.key] if label.startswith("Peak") else round(s.cold + 0.2 * span, 1)
                    self._store(f"{s.key}|{label}", fake)
            self.cycle_ms = 0
            time.sleep(0.1)


# Gen 3 Prius gearing and stock tire - training data, NOT from a Toyota source (unconfirmed).
SUN_TEETH, RING_TEETH = 30, 78       # power-split planetary gear: MG1 = sun, engine = carrier, ring = output
MG2_REDUCTION = 2.636                # MG2 -> ring gear
FINAL_DRIVE = 3.267                  # ring gear -> front wheels
TIRE_CIRCUMFERENCE_M = math.pi * (15 * 0.0254 + 2 * 0.195 * 0.65)   # stock 195/65R15, about 1.99 m
KMH_TO_WHEEL_RPM = 1000 / 60 / TIRE_CIRCUMFERENCE_M                 # about 8.36


def demo_electrical(t, smooth):
    """A made-up 40 s drive: electric launch, engine cruise, regen braking, stopped + charging.
    Engine, MG1 and MG2 follow the real planetary gear relationship."""
    p = t % 40
    if p < 10:    # pulling away on electricity only
        target = dict(eng=0, mg2_rpm=300 * p, mg2_nm=140, mg1_nm=0)
    elif p < 22:  # cruising, engine running: MG1 makes power, MG2 uses it
        target = dict(eng=1500, mg2_rpm=3000, mg2_nm=35, mg1_nm=-35)
    elif p < 30:  # braking: MG2 becomes a generator, engine off
        target = dict(eng=0, mg2_rpm=3000 - (p - 22) * 375, mg2_nm=-90, mg1_nm=0)
    else:         # stopped, engine charging the battery (like the real test log)
        target = dict(eng=1077, mg2_rpm=0, mg2_nm=0, mg1_nm=-17.3)
    for k, v in target.items():
        smooth[k] = smooth.get(k, v) + (v - smooth.get(k, v)) * 0.15
    d = dict(smooth)
    ring = d["mg2_rpm"] / MG2_REDUCTION
    d["mg1_rpm"] = (d["eng"] * (SUN_TEETH + RING_TEETH) - ring * RING_TEETH) / SUN_TEETH
    p1 = d["mg1_nm"] * d["mg1_rpm"] * 2 * math.pi / 60
    p2 = d["mg2_nm"] * d["mg2_rpm"] * 2 * math.pi / 60
    ac = 800 + 150 * math.sin(t / 5)
    batt_w = p1 + p2 + ac + 250                    # +250 W for the 12 V system
    vb = 232 - batt_w / 1000 * 0.9
    d.update(pack_volts=vb, batt_amps=batt_w / vb, vl=vb + 0.5,
             vh=min(650, vb + 60 + (abs(p1) + abs(p2)) / 80), ac_watts=ac,
             aux_volts=13.9 + 0.05 * math.sin(t), dcdc_duty=45)
    for i in range(14):
        d[f"block{i + 1:02d}"] = vb / 14 + (-0.25 if i == 10 else 0.03 * math.sin(i))
        d[f"res{i + 1:02d}"] = 0.021 + (0.009 if i == 10 else 0.001 * (i % 3))
    d.update(ac_rpm=2400 + 300 * math.sin(t / 5), ac_target=2500, blower=9, pump_rpm=2800)
    # engine RPM from 4 computers (tiny differences), wheel + car speeds from the gearing
    eng = d.pop("eng")
    d.update(eng_rpm=eng, eng_rpm_hv=eng + 3, eng_rpm_ecm=eng - 2, eng_rpm_sensor=eng + 1,
             eng_target=round(eng / 25) * 25)
    kmh = ring / FINAL_DRIVE / KMH_TO_WHEEL_RPM
    for k, bump in (("fr", 0), ("fl", 0.003), ("rr", 0.006), ("rl", 0.004)):
        d[f"whl_{k}"] = round(kmh * (1 + bump) / 1.28) * 1.28     # wheel speed sensors step in 1.28 km/h
    d.update(spd_hv=round(kmh), spd_ecm=round(kmh), spd_abs=kmh, spd_meter=round(kmh * 1.02))
    # torque, fan, on/off signals, battery charge and pressures
    braking = d["mg2_nm"] < -5
    engine_on = eng > 300
    d.update(eng_nm=max(0.0, -d["mg1_nm"] * (SUN_TEETH + RING_TEETH) / SUN_TEETH) if engine_on else 0.0,
             regen_req=max(0.0, -d["mg2_nm"] * MG2_REDUCTION), regen_op=max(0.0, -d["mg2_nm"] * MG2_REDUCTION) * 0.97,
             fan_pct=30 + 10 * math.sin(t / 7), fan_relay=1.0, fan_volts=6.5,
             brake_lights=1.0 if braking else 0.0, pump_on=1.0, dcdc_prohibit=0.0, ac_gate=1.0,
             mg1_gate=1.0 if engine_on else 0.0, mg2_gate=1.0, conv_gate=1.0,
             soc=55 + 8 * math.sin(t / 20))
    for k in ("lamp_abs", "lamp_brake", "lamp_slip", "lamp_ecb", "buzzer", "lamp_mil", "ov_conv", "ov_inv",
              "mg1_inv_shutdown", "mg1_inv_fail", "mg2_inv_shutdown", "mg2_inv_fail", "conv_shutdown", "conv_fail"):
        d[k] = 0.0
    baro = 99.5
    d.update(baro_hv=round(baro), baro_ecm=round(baro), baro_obd=round(baro),
             map_hv=round(38 + d["eng_nm"] * 0.35) if engine_on else round(baro),
             ac_press=1350 + 150 * math.sin(t / 5), evap_press=-0.6 + 0.2 * math.sin(t / 9), oil_sw=1.0 if engine_on else 0.0)
    d.update(map_ecm=d["map_hv"], map_obd=d["map_hv"])
    # steering, extra electrical, engine close-up and battery close-up (all made up)
    d.update(steer=300 * math.sin(t / 4), steer2=300 * math.sin(t / 4), yaw=10 * math.sin(t / 4),
             chg_lim=-25.0, dis_lim=21.0, sol_sla=0.0, sol_slr=0.0, sol_ssc=0.41, sol_scc=0.6 + (0.5 if braking else 0),
             sol_smc=0.0, sol_src=0.0, pump_duty=62.5, boost_ratio=40.0 if engine_on else 0.0,
             aux_v2=13.8, aux_v3=14.0)
    load = min(100.0, d["eng_nm"] / 1.4) if engine_on else 0.0
    d.update(e_load=load, e_maf=eng * load / 2000, e_iat=55.0, e_ect=88.0, e_runtime=t % 10000, e_fss=2.0 if engine_on else 1.0,
             e_stft=2 * math.sin(t), e_ltft=3.1, e_ign=12.0 if engine_on else 5.0, e_afr_target=1.0,
             e_lambda=1.0 + 0.02 * math.sin(t), e_afs_v=3.3, e_ect_start=60.6, e_iat_start=56.8,
             e_inj_vol=0.18, e_inj_us=2400 if engine_on else 0.0, e_vvt_aim=10.0, e_vvt_duty=45.0, e_vvt_angle=20.0,
             e_mis1=0.0, e_mis2=0.0, e_mis3=0.0, e_mis4=0.0, e_mis_all=0.0, e_mis_rpm=0.0, e_ign_count=296.0, e_egr=0.0,
             e_req_kw=eng * load / 12000, e_warmup=0.0, e_racing=0.0, e_fc_stop=0.0 if engine_on else 1.0,
             e_ect_meter=86.5, e_ect_climate=89.5, e_ect_obd=88.0, throttle=15.7 + load * 0.5,
             pedal1=16 + 20 * max(0.0, math.sin(t / 6)), pedal2=32 + 20 * max(0.0, math.sin(t / 6)),
             fuel_l=11.5, oil_km=2897.0, dtc_now=0.0, dtc_hist=0.0,
             soc_hv=d["soc"], soc_ig=68.5, soc_max=68.5, soc_min=38.5, cnt_low=0.0, cnt_dcinh=0.0, cnt_high=0.0,
             cnt_hot=0.0, fan_mode=1.0)
    return d
