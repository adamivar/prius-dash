"""Numbers worked out from the car's readings: fuel use, efficiency, battery health, trip totals.

Every function takes (values, now) like the views do and returns None when something it needs is missing.
Constants and their sources live in specs.py.
"""
import math
import time
from collections import deque

import specs

STALE_S = 30


def _g(values, key, now):
    r = values.get(key)
    return None if r is None or now - r[1] > STALE_S else r[0]


def _first(values, now, *keys):
    for k in keys:
        v = _g(values, k, now)
        if v is not None:
            return v
    return None


# ======================================================================
# instant numbers
# ======================================================================
def engine_rpm(values, now):
    return _first(values, now, "eng_rpm", "eng_rpm_hv")


def engine_running(values, now):
    rpm = engine_rpm(values, now)
    return rpm is not None and rpm > 300


def speed_kmh(values, now):
    v = _first(values, now, "spd_hv", "spd_abs", "spd_ecm")
    if v is None:
        mg2 = _g(values, "mg2_rpm", now)   # fall back to the drive motor (geared straight to the wheels)
        if mg2 is not None:
            wheel_rpm = mg2 / (specs.MG2_REDUCTION * specs.FINAL_DRIVE)
            v = abs(wheel_rpm) * 60 * math.pi * (15 * 0.0254 + 2 * 0.195 * 0.65) / 1000
    return v


def fuel_g_s(values, now):
    """Fuel mass flow from the air-flow sensor: fuel = air / (stoichiometric AFR x lambda)."""
    maf = _g(values, "e_maf", now)
    if maf is None:
        return None
    if not engine_running(values, now) and maf < 0.5:
        return 0.0
    lam = _g(values, "e_lambda", now) or 1.0
    lam = min(max(lam, 0.7), 1.5)          # ignore silly sensor values (e.g. during warm-up)
    return maf / (specs.STOICH_AFR * lam)


def fuel_l_per_h(values, now):
    f = fuel_g_s(values, now)
    return None if f is None else f * 3600 / 1000 / specs.FUEL_DENSITY_KG_L


def economy_l_100km(values, now):
    lph, v = fuel_l_per_h(values, now), speed_kmh(values, now)
    if lph is None or v is None or v < 3:
        return None
    return lph / v * 100


def economy_mpg(values, now):
    l100 = economy_l_100km(values, now)
    if l100 is None:
        return None
    return 235.215 / l100 if l100 > 0.05 else 999.0   # US mpg; engine off while moving = "infinite"


def engine_torque_nm(values, now):
    """Planetary gear balance (steady state): engine torque = -MG1 torque x (sun + ring) / sun."""
    t1 = _g(values, "mg1_nm", now)
    if t1 is None or not engine_running(values, now):
        return None if t1 is None else 0.0
    return max(0.0, -t1 * (specs.SUN_TEETH + specs.RING_TEETH) / specs.SUN_TEETH)


def engine_kw(values, now):
    t, rpm = engine_torque_nm(values, now), engine_rpm(values, now)
    return None if t is None or rpm is None else t * rpm * 2 * math.pi / 60 / 1000


def engine_efficiency_pct(values, now):
    """Engine output power / chemical power in the fuel (lower heating value)."""
    kw, f = engine_kw(values, now), fuel_g_s(values, now)
    if kw is None or f is None or f < 0.05 or kw < 1:
        return None
    return 100 * kw / (f * specs.FUEL_LHV_MJ_KG)   # g/s x MJ/kg = kW


def bsfc_g_kwh(values, now):
    kw, f = engine_kw(values, now), fuel_g_s(values, now)
    return None if kw is None or f is None or kw < 1 else f * 3600 / kw


def volumetric_eff_pct(values, now):
    """Air actually taken in vs what 1.8 L would hold at manifold pressure and intake temperature."""
    maf, rpm = _g(values, "e_maf", now), engine_rpm(values, now)
    mapk, iat = _first(values, now, "map_ecm", "map_hv"), _first(values, now, "e_iat", "intake_air")
    if None in (maf, rpm, mapk, iat) or rpm < 300:
        return None
    rho = mapk * 1000 / (specs.AIR_GAS_CONSTANT * (iat + 273.15))          # kg/m3
    ideal_g_s = rho * specs.DISPLACEMENT_L / 1000 * rpm / 120 * 1000      # 4-stroke: one intake per 2 turns
    return 100 * maf / ideal_g_s if ideal_g_s > 0 else None


def injector_duty_pct(values, now):
    us, rpm = _g(values, "e_inj_us", now), engine_rpm(values, now)
    return None if us is None or rpm is None else us * rpm / 120 / 1e6 * 100


def regen_delivered_pct(values, now):
    req, op = _g(values, "regen_req", now), _g(values, "regen_op", now)
    return None if req is None or op is None or req < 5 else min(100.0, 100 * op / req)


def turning_radius_m(values, now):
    v, yaw = speed_kmh(values, now), _g(values, "yaw", now)
    if v is None or yaw is None or v < 5 or abs(yaw) < 2:
        return None
    return (v / 3.6) / math.radians(abs(yaw))


def battery_kw(values, now):
    v, a = _first(values, now, "pack_volts", "vl"), _g(values, "batt_amps", now)
    return None if v is None or a is None else v * a / 1000


def motor_kw(values, now, n):
    t, rpm = _g(values, f"mg{n}_nm", now), _g(values, f"mg{n}_rpm", now)
    return None if t is None or rpm is None else t * rpm * 2 * math.pi / 60 / 1000


def electrical_losses_kw(values, now):
    """Battery power minus what the motors and A/C use: inverter/booster/DC-DC losses + 12 V load (rough)."""
    pb, p1, p2 = battery_kw(values, now), motor_kw(values, now, 1), motor_kw(values, now, 2)
    ac = _g(values, "ac_watts", now) or 0
    return None if None in (pb, p1, p2) else pb - p1 - p2 - ac / 1000


def pack_resistance_ohm(values, now):
    r = [_g(values, f"res{i:02d}", now) for i in range(1, 15)]
    return None if None in r else sum(r)


def pack_heat_w(values, now):
    a, r = _g(values, "batt_amps", now), pack_resistance_ohm(values, now)
    return None if a is None or r is None else a * a * r


def c_rate(values, now):
    a = _g(values, "batt_amps", now)
    return None if a is None else abs(a) / specs.BATTERY_AH


def limit_usage_pct(values, now):
    p = battery_kw(values, now)
    lim = _g(values, "dis_lim" if (p or 0) >= 0 else "chg_lim", now)
    return None if p is None or not lim else 100 * abs(p) / abs(lim)


def cooling_delta_c(values, now):
    t = [_g(values, f"batt_tb{i}", now) for i in (1, 2, 3)]
    air = _g(values, "batt_intake", now)
    t = [x for x in t if x is not None]
    return None if not t or air is None else sum(t) / len(t) - air


# ======================================================================
# running totals ("trip") and slow-moving estimates
# ======================================================================
class Tracker:
    """Fed the latest readings every screen refresh; integrates over time. Gaps over 5 s are skipped."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.start = time.time()
        self.last = None
        self.km = self.ev_km = self.fuel_l = 0.0
        self.moving_s = self.engine_on_s = 0.0
        self.wh_out = self.wh_in = self.ac_wh = 0.0
        self.brake_kinetic_wh = self.brake_regen_wh = 0.0
        self.prev_speed = None
        self.max_amps_out = self.max_amps_in = 0.0
        self.max_kw_out = self.max_kw_in = 0.0
        self.max_batt_temp = self.max_coolant = None
        self.ah_since_ref = 0.0
        self.soc_ref = None
        self.capacity_ah = None
        self.block_samples = deque(maxlen=150)   # (amps, [14 block volts]) taken when new block readings arrive
        self.last_block_stamp = None
        self.coolant_hist = deque(maxlen=400)    # (time, coolant)

    def update(self, values, now):
        g = lambda k: _g(values, k, now)
        dt = 0.0 if self.last is None else now - self.last
        self.last = now
        if dt <= 0 or dt > 5:
            dt = 0.0
        v = speed_kmh(values, now)
        rpm = engine_rpm(values, now)
        if v is not None:
            self.km += v * dt / 3600
            if v > 1:
                self.moving_s += dt
                if rpm is not None and rpm < 100:
                    self.ev_km += v * dt / 3600
        if rpm is not None and rpm > 300:
            self.engine_on_s += dt
        lph = fuel_l_per_h(values, now)
        if lph is not None:
            self.fuel_l += lph * dt / 3600
        p = battery_kw(values, now)
        a = g("batt_amps")
        if p is not None:
            if p > 0:
                self.wh_out += p * 1000 * dt / 3600
                self.max_kw_out = max(self.max_kw_out, p)
            else:
                self.wh_in += -p * 1000 * dt / 3600
                self.max_kw_in = max(self.max_kw_in, -p)
        if a is not None:
            self.max_amps_out = max(self.max_amps_out, a)
            self.max_amps_in = max(self.max_amps_in, -a)
            self.ah_since_ref += a * dt / 3600
        ac = g("ac_watts")
        if ac is not None:
            self.ac_wh += ac * dt / 3600
        # regen: motion energy lost while slowing down with the brake / regen active vs energy into the battery
        braking = (g("brake_lights") or 0) >= 0.5 or (g("regen_op") or 0) > 1 or (g("mg2_nm") or 0) < -5
        if v is not None and self.prev_speed is not None and braking and v < self.prev_speed and v > 0.5:
            ms0, ms1 = self.prev_speed / 3.6, v / 3.6
            self.brake_kinetic_wh += 0.5 * specs.CAR_KG * (ms0 * ms0 - ms1 * ms1) / 3600
            if p is not None and p < 0:
                self.brake_regen_wh += -p * 1000 * dt / 3600
        if v is not None:
            self.prev_speed = v
        # temperatures
        temps = [x for x in (g("batt_tb1"), g("batt_tb2"), g("batt_tb3")) if x is not None]
        if temps:
            self.max_batt_temp = max(temps + ([self.max_batt_temp] if self.max_batt_temp is not None else []))
        cool = _first(values, now, "e_ect", "engine")
        if cool is not None:
            self.max_coolant = cool if self.max_coolant is None else max(self.max_coolant, cool)
            self.coolant_hist.append((now, cool))
        # capacity: amp-hours counted vs change in the car's charge %
        soc = _first(values, now, "soc", "soc_hv")
        if soc is not None:
            if self.soc_ref is None:
                self.soc_ref, self.ah_since_ref = soc, 0.0
            elif abs(soc - self.soc_ref) >= 5:
                est = abs(self.ah_since_ref) / (abs(soc - self.soc_ref) / 100)
                if 3 < est < 12:   # ignore nonsense (e.g. SOC jumps); rated is 6.5 Ah
                    self.capacity_ah = est if self.capacity_ah is None else 0.7 * self.capacity_ah + 0.3 * est
                self.soc_ref, self.ah_since_ref = soc, 0.0
        # live block resistance: pair each NEW set of block voltages with the current at that moment
        stamp = values.get("block01", (None, None))[1]
        if stamp is not None and stamp != self.last_block_stamp and a is not None:
            blocks = [g(f"block{i:02d}") for i in range(1, 15)]
            if None not in blocks:
                self.block_samples.append((a, blocks))
            self.last_block_stamp = stamp

    # ---------- results ----------
    def elapsed_s(self):
        return time.time() - self.start

    def avg_speed(self):
        return self.km / (self.moving_s / 3600) if self.moving_s > 10 else None

    def avg_l_100km(self):
        return 100 * self.fuel_l / self.km if self.km > 0.2 else None

    def avg_mpg(self):
        l100 = self.avg_l_100km()
        return None if l100 is None else (235.215 / l100 if l100 > 0.05 else 999.0)

    def ev_share_pct(self):
        return 100 * self.ev_km / self.km if self.km > 0.2 else None

    def regen_recovered_pct(self):
        return 100 * self.brake_regen_wh / self.brake_kinetic_wh if self.brake_kinetic_wh > 5 else None

    def warmup_c_per_min(self):
        h = [x for x in self.coolant_hist if x[0] > time.time() - 120]
        if len(h) < 5 or h[-1][0] - h[0][0] < 30:
            return None
        return (h[-1][1] - h[0][1]) / ((h[-1][0] - h[0][0]) / 60)

    def block_resistance_mohm(self):
        """Least-squares slope of block voltage vs current: R = -dV/dI (voltage sags when current flows out).
        Needs samples at clearly different currents (spread over about 10 A)."""
        s = list(self.block_samples)
        if len(s) < 8:
            return None, 0.0
        amps = [x[0] for x in s]
        mean_a = sum(amps) / len(amps)
        var = sum((x - mean_a) ** 2 for x in amps) / len(amps)
        spread = math.sqrt(var)
        if spread < 5:
            return None, spread
        out = []
        for i in range(14):
            vs = [x[1][i] for x in s]
            mean_v = sum(vs) / len(vs)
            cov = sum((ax - mean_a) * (vx - mean_v) for ax, vx in zip(amps, vs)) / len(vs)
            out.append(-cov / var * 1000)
        return out, spread


TRACKER = Tracker()
