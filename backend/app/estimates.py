"""Power and water demand ranges from the estimate_params table."""
from . import db

LITERS_PER_GALLON = 3.785


def estimate(mw):
    p = {r["key"]: r for r in db.rows("SELECT * FROM estimate_params")}

    def mwh_per_year(k):  # IT MW * hours * utilization * PUE
        return mw * 8760 * p["load_factor"][k] * p["pue"][k]

    def gal_per_day(k):   # IT kWh/day * liters per IT kWh -> gallons
        it_kwh_day = mw * 1000 * 24 * p["load_factor"][k]
        return it_kwh_day * p["wue_l_per_kwh"][k] / LITERS_PER_GALLON

    return {
        "power_mwh_per_year": {"low": round(mwh_per_year("low")), "high": round(mwh_per_year("high"))},
        "water_gal_per_day": {"low": round(gal_per_day("low")), "high": round(gal_per_day("high"))},
        "sources": [f"{k}: {v['low']}-{v['high']} ({v['source']})" for k, v in p.items()],
    }
