"""Power, water, carbon and cost ranges from the estimate_params + grid tables."""
import math
import re

from . import db

LITERS_PER_GALLON = 3.785
EGRID_SOURCE = "EPA eGRID2023 rev2, subregion CO2 output rate"
PRICE_SOURCE = "EIA state average industrial electricity price, 2020"


def grid_for(state, egrid_code):
    """eGRID subregion carbon rate + state industrial price."""
    e = db.rows("SELECT * FROM egrid WHERE code=?", (egrid_code,))
    p = db.rows("SELECT * FROM power_prices WHERE state=?", (state,))
    if not e or not p:
        return None
    return {"egrid": e[0]["code"], "egrid_name": e[0]["name"], "co2_lb_per_mwh": e[0]["co2_lb_per_mwh"],
            "price_cents_kwh": p[0]["cents_kwh"]}


def estimate(mw, state=None, egrid_code=None):
    p = {r["key"]: r for r in db.rows("SELECT * FROM estimate_params")}

    def mwh_per_year(k):  # IT MW * hours * utilization * PUE
        return mw * 8760 * p["load_factor"][k] * p["pue"][k]

    def gal_per_day(k):   # IT kWh/day * liters per IT kWh -> gallons
        it_kwh_day = mw * 1000 * 24 * p["load_factor"][k]
        return it_kwh_day * p["wue_l_per_kwh"][k] / LITERS_PER_GALLON

    out = {
        "power_mwh_per_year": {"low": round(mwh_per_year("low")), "high": round(mwh_per_year("high"))},
        "water_gal_per_day": {"low": round(gal_per_day("low")), "high": round(gal_per_day("high"))},
        "sources": [f"{k}: {v['low']}-{v['high']} ({v['source']})" for k, v in p.items()],
    }
    g = grid_for(state, egrid_code)
    if g:
        def tons(k):   # short tons CO2
            return mwh_per_year(k) * g["co2_lb_per_mwh"] / 2000

        def cost(k):   # USD
            return mwh_per_year(k) * 1000 * g["price_cents_kwh"] / 100

        out["grid"] = {"egrid": g["egrid"], "egrid_name": g["egrid_name"],
                       "co2_lb_per_mwh": g["co2_lb_per_mwh"], "price_cents_kwh": g["price_cents_kwh"]}
        out["co2_tons_per_year"] = {"low": round(tons("low")), "high": round(tons("high"))}
        out["power_cost_usd_per_year"] = {"low": round(cost("low")), "high": round(cost("high"))}
        out["sources"] += [f"Grid CO2: {g['co2_lb_per_mwh']} lb/MWh, {g['egrid_name']} ({EGRID_SOURCE})",
                           f"Power price: {g['price_cents_kwh']} cents/kWh ({PRICE_SOURCE})"]
    return out


# ---------- Carbon impact score (0-10) + ways to offset ----------
# Reference numbers (metric tons, "t"):
SHORT_TO_METRIC = 0.907
CAR_T_PER_YEAR = 4.6            # EPA: typical passenger vehicle, t CO2/year
FOREST_T_PER_ACRE_YEAR = 0.84   # EPA GHG equivalencies: US forest sequestration, t CO2/acre/year
GLOBAL_T_PER_YEAR = 37.4e9      # IEA: global energy-related CO2, 2023
GHGRP_THRESHOLD_T = 25000       # EPA Greenhouse Gas Reporting Program threshold (direct emissions)
SOLAR_CAPACITY_FACTOR = 0.25    # utility-scale solar, average
SOLAR_ACRES_PER_MW = 6          # typical land use, utility-scale solar
CARBON_SOURCES = ("EPA GHG equivalencies (cars, forest acres), IEA 2023 global CO2, "
                  "EPA GHG Reporting Program 25,000 t threshold, utility-scale solar ~25% capacity factor and ~6 acres/MW")


def carbon_impact(est, findings):
    """Carbon score 0-10 for the developer: up to 6 points for size (log scale, 10k t -> 0, 1M t -> 6)
    and up to 4 for how carbon-heavy the local grid is. Plus scale comparisons and offset options."""
    if "co2_tons_per_year" not in est:
        return None
    co2 = est["co2_tons_per_year"]
    t = (co2["low"] + co2["high"]) / 2 * SHORT_TO_METRIC      # midpoint, metric tons/year
    rate = est["grid"]["co2_lb_per_mwh"]
    size_pts = min(6, max(0, 6 * (math.log10(max(t, 1)) - 4) / 2))
    grid_pts = min(4, max(0, 4 * rate / 1600))                # ~1,600 lb/MWh = coal-heavy grid
    score = round(size_pts + grid_pts, 1)
    level = "Very high" if score >= 8 else "High" if score >= 6 else "Moderate" if score >= 3 else "Low"

    mwh = sum(est["power_mwh_per_year"].values()) / 2
    solar_mw = mwh / (8760 * SOLAR_CAPACITY_FACTOR)
    at_site = {f["layer"] for f in findings if f.get("buffer") in ("site", "1km")}
    offsets = [
        {"action": "Match the load with new solar or wind (power purchase agreement)",
         "amount": f"~{solar_mw:,.0f} MW of new solar (~{solar_mw * SOLAR_ACRES_PER_MW:,.0f} acres)"},
        {"action": "Fund forest restoration or protection",
         "amount": f"~{t / FOREST_T_PER_ACRE_YEAR:,.0f} acres of forest to absorb one year of emissions"},
    ]
    if any("wetland" in l for l in at_site):
        offsets.append({"action": "Avoid filling the flagged wetlands; restore wetlands on-site or through a mitigation bank",
                        "amount": "Wetlands were found at the site or within 1 km"})
    if any(f["layer"] == "water_stress" and re.search(r"High|Extremely", f.get("detail", "")) for f in findings):
        offsets.append({"action": "Use closed-loop or air cooling and reclaimed water",
                        "amount": "Local water stress is high"})
    offsets.append({"action": "Run efficiently (low PUE) and reuse waste heat for nearby buildings",
                    "amount": "Cuts the power needed, so every number above shrinks"})
    return {
        "score": score, "level": level,
        "size_points": round(size_pts, 1), "grid_points": round(grid_pts, 1),
        "tons_per_year": round(t), "cars": round(t / CAR_T_PER_YEAR),
        "global_share_pct": t / GLOBAL_T_PER_YEAR * 100,
        "over_reporting_threshold": t >= GHGRP_THRESHOLD_T,
        "offsets": offsets, "source": CARBON_SOURCES,
    }
