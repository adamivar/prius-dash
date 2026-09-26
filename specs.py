"""Car and fuel constants used by the calculations, with where each number came from (checked 2026-09-26).

Sources:
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
Anything marked ASSUMPTION is a reasonable guess, not from a source.
"""
import math

# ---------- the car ----------
CURB_KG = 1397                 # [TOYOTA-ERG] 3,080 lb / 1,397 kg
DRIVER_KG = 80                 # ASSUMPTION: one adult + a little stuff
CAR_KG = CURB_KG + DRIVER_KG
WHEELBASE_M = 2.70             # [WIKI-XW30] 2,700 mm
FUEL_TANK_L = 45.0             # [TOYOTA-ERG] 11.9 gal / 45.0 L
DISPLACEMENT_L = 1.8           # [TOYOTA-ERG] 1.8-liter engine (2ZR-FXE)
ENGINE_MAX_KW = 73             # [WIKI-XW30] [TOYOTA-ERG] 98 hp / 73 kW @ 5,200 rpm
ENGINE_MAX_NM = 142            # [WIKI-XW30] 142 Nm @ 4,000 rpm
ENGINE_PEAK_EFFICIENCY = 0.385  # [GCR] Toyota: 38.5 %
MG2_MAX_KW, MG2_MAX_NM, MG2_MAX_RPM = 60, 207, 13500   # [ORNL]
MG1_MAX_KW = 42                # [ORNL] (MG1 torque rating is "not published" per [ORNL])
BOOST_MAX_V = 650              # [TOYOTA-ERG] [ORNL]

# ---------- hybrid battery ----------
BATTERY_NOMINAL_V = 201.6      # [TOYOTA-ERG]
BATTERY_MODULES = 28           # [TOYOTA-ERG] 28 x 7.2 V modules in series (the car reports them in 14 pairs)
BATTERY_AH = 6.5               # [ORNL] 6.5 Ah
BATTERY_RATED_KW = 26.8        # [ORNL] 36 hp / 26.8 kW
BATTERY_KWH = BATTERY_NOMINAL_V * BATTERY_AH / 1000   # about 1.3 kWh, matches [WIKI-XW30]

# ---------- gearing (also in sensors.py) ----------
SUN_TEETH, RING_TEETH = 30, 78  # [P410] sun 30, ring 78
MG2_REDUCTION = 2.636          # [P410] "motor speed reduction ratio 2.64"
FINAL_DRIVE = 3.267            # [P410] "total speed reduction ratio 3.267"

# ---------- fuel: US pump gas is E10 ----------
STOICH_AFR = 14.1              # [HPT] E10 stoichiometric air-fuel ratio (pure gasoline = 14.7)
FUEL_DENSITY_KG_L = 0.745      # ASSUMPTION within the 0.71-0.77 kg/L range for gasoline
FUEL_LHV_MJ_L = 112114 * 1055.06 / 3.785411784 / 1e6   # [AFDC] E10 LHV 112,114 Btu/gal = about 31.2 MJ/L
FUEL_LHV_MJ_KG = FUEL_LHV_MJ_L / FUEL_DENSITY_KG_L       # about 41.9 MJ/kg

# ---------- physics ----------
AIR_GAS_CONSTANT = 287.05      # J/(kg K), dry air
GRAVITY = 9.81
