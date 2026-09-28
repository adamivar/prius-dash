"""Every setting, limit and constant Prius Live uses, in one place. Edit freely.

Sections: connection, polling, screen, colours, normal/danger limits, calculations, car specs, fuel, physics.
Decoding formulas (like "A*256+B") stay in sensors.py: they're the car's data format, not settings.
Box positions stay with each drawing (views.py / closeups.py).

Sources for the car and fuel numbers (checked 2026-09-26):
  [TOYOTA-ERG]  Toyota, "Prius Hybrid 2010 Model 3rd Generation" emergency response guide
                https://techinfo.toyota.com/techInfoPortal/staticcontent/en/techinfo/html/prelogin/docs/3rdprius.pdf
  [ORNL]        Oak Ridge National Laboratory, "Evaluation of the 2010 Toyota Prius Hybrid Synergy Drive System"
                https://info.ornl.gov/sites/publications/files/Pub26762.pdf
  [WIKI-XW30]   https://en.wikipedia.org/wiki/Toyota_Prius_(XW30)
  [GCR]         Green Car Reports quoting Toyota (38.5 % max thermal efficiency for the 3rd-gen engine)
                https://www.greencarreports.com/news/1098429_next-toyota-prius-hybrid-40-percent-thermal-effiency-from-engine-toyota-says
  [P410]        Toyota new-model training slides for the P410 transaxle (via web search)
                https://slideplayer.com/slide/10496178/
  [AFDC]        US DOE Alternative Fuels Data Center, Fuel Properties Comparison (March 2024)
                https://afdc.energy.gov/files/u/publication/fuel_comparison_chart.pdf
  [HPT]         HP Tuners, "Air-Fuel Ratios, Lambda, and Stoichiometry Explained"
                https://www.hptuners.com/articles/air-fuel-ratios-lambda-and-stoichiometry-explained/
  [MEASURED]    measured in the test car, a 2010 Prius (full sensor test 2026-09-26)
Anything marked ESTIMATE / ASSUMPTION is the author's guess, not from a source.
"""
import math

# ======================================================================
# Connection (ELM327 adapter)
# ======================================================================
PORT = "COM6"                    # default serial port (override with --port)
BAUD = 38400                     # the adapter's serial speed
ELM_TIMEOUT_S = 3.0              # give up waiting for a reply after this long
ELM_RESET_TIMEOUT_S = 5.0        # ATZ (adapter reset) can take longer
ELM_RESET_WAIT_S = 0.5           # pause after ATZ before the next command
SERIAL_READ_TIMEOUT_S = 0.02     # low-level read timeout (small = replies are picked up as soon as they arrive)
RECONNECT_WAIT_S = 3             # after a connection error, wait this long before trying again
MAX_FRAMES_HINT = 15             # "expect N replies" only works for 1-15 frames (one hex digit)

# ======================================================================
# Polling schedule
# ======================================================================
SLOW_EVERY = 4                   # the current view's slow readings: once every this many loops
TRIP_EVERY = 3                   # readings the trip totals need: every this many loops, whatever the view
BG_PERIOD_S = 8                  # other views' readings: refreshed about this often
BG_PER_LOOP = 3                  # at most this many background requests per loop (keeps the current view fast)
DEMO_TICK_S = 0.1                # demo mode: how often fake values update

# ======================================================================
# Screen
# ======================================================================
REFRESH_MS = 150                 # how often the screen picks up new readings
FRAME_MS = 40                    # animation frame time (arrows, rotors)
BLINK_MS = 500                   # warning border blink half-period
STALE_AFTER_S = 30               # a reading older than this shows "(old)" / greyed out
WARN_AT = 0.85                   # flashing red border from this fraction of the way to "danger"
WINDOW_SIZE = (1150, 1000)       # starting window size at 100% Windows scaling (grows with display scaling)
WINDOW_MARGIN = (60, 110)        # keep this much of the screen free around the window (px at 100% scaling)
WINDOW_MIN_SIZE = (760, 680)
TOOLTIP_WIDTH = 380              # hover card width (px at 100% scaling)
PANEL_TEXT_WIDTH = 310           # side panel text wraps at this width (px at 100% scaling)
LEGEND_WIDTH = 300               # side panel colour bar width
FONT_SCALE = 3.2                 # box text size, relative to the drawing scale
FONT_SCALE_SMALL = 2.8           # labels
FONT_SCALE_TINY = 2.2            # narrow boxes (battery blocks, wheels)
NARROW_BOX = 12                  # boxes narrower than this (drawing units) use the tiny font
ONE_LINE_BOX = 12                # boxes shorter than this put label and value on one line
# rotors (Spinning view): on-screen turns per second = min(MAX, GAIN x sqrt(rpm)) - slowed a lot so it can't strobe
ROTOR_MAX_TURNS_S = 2.5
ROTOR_SQRT_GAIN = 0.045
ROTOR_MAX_WIDTH = 8              # extra rotor line width at maximum torque
# wires (Electrical / close-ups)
WIRE_FULL_AMPS = 150             # wires are thickest at this current
WIRE_MIN_WIDTH = 2
WIRE_EXTRA_WIDTH = 8
ARROW_SPACING = 30               # px between moving arrows
ARROW_BASE_SPEED = 15            # px/s at ~0 A
ARROW_SPEED_PER_AMP = 3          # extra px/s per amp
ARROW_MAX_SPEED = 400
ARROW_MIN_AMPS = 0.5             # below this, no arrows (treated as no flow)
ON_OFF_AMPS = 3.0                # arrow speed used for things that only report on/off (not a real current)

# ======================================================================
# Colours
# ======================================================================
BG = "#16181c"
BODY = "#23262d"
BODY_EDGE = "#4a505c"
NO_DATA = "#33363d"
TEXT = "#e8e8e8"
DIM = "#8a8f99"
IDEAL = "#3ddc68"                # green border
WARN = "#ff3b3b"                 # flashing red border
TIP_BG = "#f4f4f0"
TIP_FG = "#1a1a1a"
FLOW = "#ffe14d"                 # default arrow colour
SPIN_REV_TEXT = "#d88cff"       # "turning backwards" numbers in the side panel
DARK_TEXT = "#111111"            # text on light-coloured boxes
TEXT_LIGHTNESS_SWITCH = 150      # boxes lighter than this (0-255) get dark text
# hover-card text colours
TIP_GREEN = "#1c8a3a"
TIP_AMBER = "#b86b00"
TIP_RED = "#d42020"
TIP_BLUE = "#2f5f8f"
TIP_TORQUE = "#b83a1a"
TIP_BORDER = "#9aa0aa"
# car drawing
OUTLINE = "#0f1013"              # normal box outline
HOVER_OUTLINE = "#c8ccd4"
GROUP_OUTLINE = "#5b6270"        # dashed outlines around groups of parts
GLASS = "#1c2a36"                # windshield / rear window
SEAT_OUTLINE = "#3a3f49"
TIRE = "#0b0c0e"
TIRE_EDGE = "#2c2f36"
CLOSEUP_PART = "#2c3139"         # close-up boxes with no colour scale
BUTTON_ACTIVE = "#3a404a"
BAR_BG = "#101114"               # battery charge bar background
# wires and arrows
WIRE_ACTIVE = "#6b5a12"          # carrying current
WIRE_IDLE = "#4a4d55"            # measured, but no current right now
WIRE_UNMEASURED = "#6a6f78"      # dashed: current not measured
WIRE_ON = "#a89a50"              # dashed: not measured, but switched on
ARROW_OUTLINE = "#1a1a1a"
ROTOR_TINT = "#ffffff"           # rotors are the box colour mixed with this ...
ROTOR_TINT_AMOUNT = 0.3
ROTOR_TORQUE = "#ff2a1a"         # ... and redder with torque
ROTOR_TORQUE_BASE = 0.25         # how red a rotor is at zero torque
# lamps (Electrical view)
LAMP_AMBER = "#ffb000"
LAMP_RED = "#ff3030"
LAMP_OFF = "#1b1c20"
LAMP_GREEN = "#34c759"
LAMP_GREEN_DIM = "#1f6b35"
LAMP_BLUE = "#3d8bff"
# Brakes & grip view: rings around a wheel while a safety system is working it
RING_ABS = "#ff3b30"             # ABS
RING_VSC = "#ff9500"             # stability control
RING_TRC = "#ffd60a"             # traction control
RING_EBD = "#5ac8fa"             # rear brake balancing (EBD)
BRAKE_LIGHT_ON = "#ff2020"
BRAKE_LIGHT_OFF = "#3a0d0d"
ON_OFF_FILL = 0.45               # Electrical view: how yellow an "on" part is when its current isn't measured
# colour ramps: (position 0-1, (r, g, b))
HEAT = [(0.0, (47, 79, 111)), (0.6, (217, 162, 27)), (1.0, (227, 23, 27))]     # cool -> danger
CHARGE = [(0.0, (12, 12, 12)), (1.0, (255, 214, 0))]                            # no current -> too much
SPIN_FWD = [(0.0, (20, 24, 30)), (1.0, (41, 199, 255))]                         # stopped -> max, forwards
SPIN_REV = [(0.0, (20, 24, 30)), (1.0, (208, 82, 255))]                         # stopped -> max, backwards
PRESS_RAMP = [(0.0, (20, 24, 30)), (1.0, (232, 236, 245))]                      # no pressure -> high
LEVEL = [(0.0, (22, 26, 32)), (1.0, (70, 190, 160))]                            # close-ups: "how high is it"
DEVIATE = [(0.0, (40, 58, 70)), (1.0, (227, 23, 27))]                           # battery block: even -> far off
# flow lines in the close-ups
FLOW_AIR = {"line": "#2f5872", "arrow": "#8fd3ff"}
FLOW_EXHAUST = {"line": "#5a4632", "arrow": "#d9a877"}
FLOW_FUEL = {"line": "#6a4a1a", "arrow": "#ffb347"}
FLOW_HOT = {"line": "#6a2a2a", "arrow": "#ff6b6b"}
FLOW_COOL = {"line": "#24466a", "arrow": "#6bb5ff"}
FLOW_HV = {"line": "#6b5a12", "arrow": "#ffe14d"}
FLOW_LV = {"line": "#a89a50", "arrow": "#ffe14d"}

# ======================================================================
# Normal / danger limits (ESTIMATES unless a source is given - not Toyota specs)
# ======================================================================
# Temperatures in °C: (cold = base colour, danger = full red, ideal low, ideal high)
TEMP_LIMITS = {
    "ambient": (0, 50, 10, 30),
    "intake_air": (20, 70, 20, 45),
    "engine": (40, 110, 80, 95),
    "mg1": (30, 150, 30, 90),
    "mg2": (30, 150, 30, 90),
    "inv_mg1": (30, 100, 30, 65),
    "inv_mg2": (30, 100, 30, 65),
    "boost_upper": (30, 100, 30, 65),
    "boost_lower": (30, 100, 30, 65),
    "inv_coolant": (30, 80, 25, 55),
    "batt_intake": (15, 45, 15, 30),
    "batt_tb1": (20, 55, 20, 35),
    "batt_tb2": (20, 55, 20, 35),
    "batt_tb3": (20, 55, 20, 35),
    "aux_batt": (15, 60, 10, 35),
    "cabin": (10, 50, 18, 26),
    "evap": (0, 40, 1, 12),
    "catalyst": (100, 900, 400, 800),
}
# Electrical view currents in amps: (ideal up to, too much at)
AMP_LIMITS = {"brake_act": (2, 6), "hvbatt": (40, 120), "boost": (40, 130), "inv1": (40, 100), "mg1": (40, 100),
              "inv2": (50, 150), "mg2": (50, 150), "ac": (8, 20)}
AUX_IDEAL = (13.2, 14.8)         # 12 V battery volts while READY
AUX_LOW, AUX_HIGH = 12.0, 15.0   # flashing red outside these
AUX_COLOUR_RANGE = (11, 15)      # battery close-up: 12 V box colour scale (volts)
BLK_IDEAL_DEV = 0.15             # battery block within this many volts of the pack average = green
BLK_WARN_DEV = 0.30              # ... this far or more = flashing red
BLK_COLOUR_FULL_DEV = 0.4        # battery close-up: block colour is full red at this deviation
SOC_IDEAL = (40, 80)             # the car normally keeps the battery between these (%)
# Spinning view: rpm at full colour, and the ideal ranges
SPIN_MAX_RPM = {"engine": 5200, "mg1": 10000, "mg2": 13500, "ring": 5000, "wheel": 1400, "ac": 9000, "pump": 6000}
ENGINE_IDEAL_RPM = (1000, 2800)  # also ideal: stopped (0)
MG1_IDEAL_MAX_RPM = 6000         # either direction
MG2_IDEAL_MAX_RPM = 9000
AC_IDEAL_MAX_RPM = 6000
PUMP_IDEAL_RPM = (500, 5000)
TORQUE_MAX_NM = {"engine": 142, "mg1": 100, "mg2": 207, "ring": 650, "fl": 1050, "fr": 1050}   # thickest rotor
SLIP_IDEAL = 0.03                # a wheel within 3% of the average of the four = green
SLIP_WARN = 0.15                 # 15% or more = slipping/locking (flashing red)
SLIP_MIN_WHEEL_RPM = 40          # below this (about 5 km/h) slip isn't judged
STEER_MAX_DEG = 665              # full lock as read in the test car [MEASURED]
FAN_RPM_PER_PCT = 50             # battery fan rotor: pretend rpm per % power (the car doesn't report fan rpm)
# Front-wheel steering geometry (for drawing the front wheels turned):
WHEELBASE_M = 2.70               # 106.3 in [Edmunds / The Car Connection 2010 Prius specs]
FRONT_TRACK_M = 1.524            # 60.0 in with 15-inch wheels [same sources]
TURN_RADIUS_M = 5.2              # 10.4 m turning circle [CarsGuide 2010 Prius dimensions]
STEER_STRAIGHT_DEG = 5           # steering within this many degrees counts as "straight"
RPM_SOURCES_AGREE = 50           # engine rpm from different computers "agree" within this
GEAR_CHECK_RPM = 30              # ring gear from two calculations "checks out" within this
WHEEL_CALC_MATCH_PCT = 3         # measured vs calculated wheel rpm "confirmed" within this %
# Pressure view, kPa: (full colour at, ideal low, ideal high, warn below, warn above)
PRESS_LIMITS = {
    "map": (105, 20, 85, None, 110),
    "baro": (105, 80, 105, 60, 110),
    "ac": (3200, 600, 2200, None, 2700),
    "evap": (5, -2.0, 1.5, -4.0, 4.0),
}
# Engine close-up
FUEL_LOW_L = 5                   # fuel box flashes red below this
OIL_OK_KM = 8000                 # green under this since the oil-change reset
OIL_DUE_KM = 15000               # red from this
FUEL_TRIM_IDEAL = 10             # |fuel trims| within this % = green
FUEL_TRIM_WARN_LONG = 20         # |long-term trim| from this % = red
FUEL_TRIM_WARN_SHORT = 25        # |short-term trim| from this % = red
FUEL_TRIM_COLOUR_FULL = 25       # air-fuel sensor box colour is full red at this |long-term trim| %
MISFIRE_COLOUR_FULL = 10         # a cylinder box is full red at this many misfires
MAF_FULL_G_S = 60                # air intake box colour scale (g/s)
INJECTOR_FULL_US = 10000         # injector box colour scale (µs)
EGR_FULL_STEPS = 120
IGNITION_COLOUR_RANGE = (-10, 40)   # degrees
COOLANT_COLOUR_RANGE = (40, 110)    # °C
CATALYST_COLOUR_RANGE = (100, 900)  # °C
OIL_COLOUR_FULL_KM = 16000
# Battery close-up
BATT_TEMP_COLOUR_RANGE = (20, 55)   # °C
BATT_AIR_COLOUR_RANGE = (15, 45)    # °C
POWER_LIMIT_COLOUR_KW = 30

# ======================================================================
# Calculations (calc.py)
# ======================================================================
ENGINE_RUNNING_RPM = 300         # above this the engine counts as running
EV_RPM = 100                     # below this (while moving) counts as "driven on electricity"
MOVING_KMH = 1                   # above this the car counts as moving
ECONOMY_MIN_KMH = 3              # below this, L/100 km isn't shown (would be huge)
MAF_OFF_G_S = 0.5                # air flow below this with the engine stopped = no fuel
LAMBDA_RANGE = (0.7, 1.5)        # air-fuel sensor values outside this are ignored for fuel flow
EFFICIENCY_MIN_KW = 1            # engine efficiency only shown above this engine power
EFFICIENCY_MIN_FUEL_G_S = 0.05
EFFICIENCY_HIDE_ABOVE = 50       # % - clearly impossible (Toyota rates the engine at 38.5 % best)
REGEN_MIN_REQUEST_NM = 5         # regen share only shown when at least this much is asked for
TURN_MIN_KMH = 5                 # turning radius only shown above this speed ...
TURN_MIN_YAW_DEG_S = 2           # ... and this turning rate
TRACKER_MAX_GAP_S = 5            # gaps longer than this (e.g. connection drop) aren't added to the totals
BRAKING_REGEN_NM = 1             # counts as braking: brake switch on, regen above this, ...
BRAKING_MG2_NM = -5              # ... or drive-motor torque below this
BRAKING_MIN_KMH = 0.5
CAPACITY_SOC_SWING = 5           # % of charge change needed for one capacity estimate
CAPACITY_SANE_AH = (3, 12)       # estimates outside this are thrown away
CAPACITY_SMOOTHING = 0.3         # weight of each new capacity estimate
LIVE_R_SAMPLES = 150             # battery samples kept for the live resistance fit
LIVE_R_MIN_SAMPLES = 8
LIVE_R_MIN_SPREAD_A = 5          # current must vary by at least this (standard deviation) for a live resistance
WARMUP_WINDOW_S = 120            # warm-up rate looks at the last this many seconds ...
WARMUP_MIN_SPAN_S = 30           # ... and needs at least this much history
TRIP_MIN_KM = 0.2                # trip averages shown after this distance
TRIP_MIN_MOVING_S = 10
REGEN_MIN_WH = 5                 # braking-recovered % shown after this much braking energy

# ======================================================================
# The car
# ======================================================================
CURB_KG = 1397                   # [TOYOTA-ERG] 3,080 lb / 1,397 kg
DRIVER_KG = 80                   # ASSUMPTION: one adult + a little stuff
CAR_KG = CURB_KG + DRIVER_KG
WHEELBASE_M = 2.70               # [WIKI-XW30] 2,700 mm
FUEL_TANK_L = 45.0               # [TOYOTA-ERG] 11.9 gal / 45.0 L
DISPLACEMENT_L = 1.8             # [TOYOTA-ERG] 1.8-liter engine (2ZR-FXE)
ENGINE_MAX_KW = 73               # [WIKI-XW30] [TOYOTA-ERG] 98 hp / 73 kW @ 5,200 rpm
ENGINE_MAX_NM = 142              # [WIKI-XW30] 142 Nm @ 4,000 rpm
ENGINE_PEAK_EFFICIENCY = 0.385   # [GCR] Toyota: 38.5 %
MG2_MAX_KW, MG2_MAX_NM, MG2_MAX_RPM = 60, 207, 13500   # [ORNL]
MG1_MAX_KW = 42                  # [ORNL] (MG1 torque rating is "not published" per [ORNL])
BOOST_MAX_V = 650                # [TOYOTA-ERG] [ORNL]
BATTERY_NOMINAL_V = 201.6        # [TOYOTA-ERG]
BATTERY_MODULES = 28             # [TOYOTA-ERG] 28 x 7.2 V modules in series (the car reports them in 14 pairs)
BATTERY_BLOCKS = 14
BATTERY_AH = 6.5                 # [ORNL] 6.5 Ah
BATTERY_RATED_KW = 26.8          # [ORNL] 36 hp / 26.8 kW
BATTERY_KWH = BATTERY_NOMINAL_V * BATTERY_AH / 1000   # about 1.3 kWh, matches [WIKI-XW30]
# gearing
SUN_TEETH, RING_TEETH = 30, 78   # [P410] power-split planetary: MG1 = sun, engine = carrier, ring = output
MG2_REDUCTION = 2.636            # [P410] "motor speed reduction ratio 2.64" (MG2 -> ring gear)
FINAL_DRIVE = 3.267              # [P410] "total speed reduction ratio 3.267" (ring gear -> wheels)
# tires: stock 195/65R15
TIRE_WIDTH_MM, TIRE_ASPECT_PCT, RIM_IN = 195, 65, 15
TIRE_CIRCUMFERENCE_M = math.pi * (RIM_IN * 0.0254 + 2 * TIRE_WIDTH_MM / 1000 * TIRE_ASPECT_PCT / 100)   # about 1.99 m
KMH_TO_WHEEL_RPM = 1000 / 60 / TIRE_CIRCUMFERENCE_M   # about 8.36

# ======================================================================
# Fuel: US pump gas is E10
# ======================================================================
STOICH_AFR = 14.1                # [HPT] E10 stoichiometric air-fuel ratio (pure gasoline = 14.7)
FUEL_DENSITY_KG_L = 0.745        # ASSUMPTION within the 0.71-0.77 kg/L range for gasoline
FUEL_LHV_BTU_GAL = 112114        # [AFDC] E10 lower heating value
FUEL_LHV_MJ_L = FUEL_LHV_BTU_GAL * 1055.06 / 3.785411784 / 1e6   # about 31.2 MJ/L
FUEL_LHV_MJ_KG = FUEL_LHV_MJ_L / FUEL_DENSITY_KG_L                 # about 41.9 MJ/kg

# ======================================================================
# Physics and unit conversions
# ======================================================================
AIR_GAS_CONSTANT = 287.05        # J/(kg K), dry air
GRAVITY = 9.81
KELVIN = 273.15
MPG_FROM_L100KM = 235.215        # US mpg = 235.215 / (L/100 km)
L_PER_US_GAL = 3.785411784
MI_PER_KM = 0.621371
MPG_ENGINE_OFF = 999.0           # shown as mpg when moving with the engine off ("infinite")

# Phone layout: set by main.py before the views load. The car body fills the screen edge to edge, so the tires
# are drawn inside the body outline (as seen from above, they sit under the fenders) instead of sticking out.
PHONE_LAYOUT = False

# ---------- Brakes & grip view, climate doors, dashboard ----------
BRAKE_V_RANGE = (0.47, 2.5)      # brake pressure sensor volts: released .. hard stop [MEASURED 2026-09-26: 0.47..2.41]
BRAKE_PRESSED_V = 0.7            # above this the brakes count as applied (unconfirmed)
G_FULL_MS2 = 7.85                # g-ball edge = 0.8 g
G_TRAIL_S = 3.0                  # the g-ball leaves a trail this long
WHEEL_ACC_FULL = 6.0             # wheel acceleration (m/s²) at full colour in the Brakes view
WHEEL_SLIP_WARN = 4.7            # |wheel acceleration| from this (3 sensor steps, ~0.5 g) counts as spin / lock-up
BLEND_PULSES = (6, 93)           # heater blend door: full cold .. full hot [MEASURED 2026-09-26: 6 cold, 93 heater hot]
INLET_RECIRC_ABOVE = 15          # air inlet door pulses above this = recirculate [GUESS: 19 during max A/C, 7-10 otherwise]
OUTLET_FEET_BELOW = 30           # air outlet door pulses below this = feet [GUESS: 17 heater hot, 47 normal]
