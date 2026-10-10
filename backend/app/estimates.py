"""Power, water, carbon and cost ranges from the estimate_params + grid tables."""
from . import db

LITERS_PER_GALLON = 3.785
EGRID_SOURCE = "EPA eGRID2023 rev2, subregion CO2 output rate"
PRICE_SOURCE = "EIA state average industrial electricity price, 2020"


def grid_for(state, county):
    county = (county or "").replace(" County", "")
    rows = db.rows("SELECT * FROM grid WHERE state=? AND county IN (?, '*') ORDER BY county = '*'", (state, county))
    return rows[0] if rows else None


def estimate(mw, state=None, county=None):
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
    g = grid_for(state, county)
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
