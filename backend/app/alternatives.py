"""Find lower-risk spots near a site, using only data already cached for that site.

How it works:
  1. Screen the original site normally (this caches every layer in an ~8 km box around it).
  2. Test candidate points on rings 1.0 / 1.75 / 2.5 km away in 8 directions (24 points).
     2.5 km + the 5 km check radius stays inside the cached 8 km box, so no new downloads are needed.
  3. Skip candidates that sit inside a wetland, flood zone, or protected land shape.
  4. Run the same rules.yaml rules on each candidate and score it: high trigger = 3, medium = 1.
  5. Return the original site plus the best few candidates, side by side.

Screening-level only: the tool cannot see zoning, buildings, land ownership, or power lines,
so a candidate is a "lower environmental-risk area to look at", not a recommended site.
"""
import json
import math

from shapely import STRtree
from shapely.geometry import Point, shape
from shapely.ops import transform

from . import db, estimates, rules, spatial

RINGS_KM = (1.0, 1.75, 2.5)
BEARINGS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
RISK_POINTS = {"high": 3, "medium": 1}
REGION_CONTEXT = {"water_stress", "climate_risk"}   # shown separately, not as distances
# A candidate whose point is INSIDE one of these shapes is skipped (can't build in a wetland, flood zone or park).
NO_BUILD_LAYERS = {"fema_flood", "nwi_wetlands", "nj_wetlands", "ny_wetlands", "de_wetlands",
                   "protected_areas", "nj_open_space", "ny_protected", "critical_habitat"}
CAVEAT = ("Screening-level only. Candidates are scored on the same public environmental layers and rules "
          "as the original site. The tool cannot see zoning, homes, land ownership, power lines or "
          "whether land is for sale, so these are areas to look at, not recommended sites.")


def offset(lat, lon, km, bearing_deg):
    b = math.radians(bearing_deg)
    dlat = km * math.cos(b) / 111.0
    dlon = km * math.sin(b) / (111.0 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def score(triggers):
    return sum(RISK_POINTS.get(t["delay_risk"], 0) for t in triggers)


def load_layers(lat, lon, state, checked):
    """Load each cached site layer around the origin once, in meters, with a spatial index."""
    out = {}
    for layer in db.get_layers("site"):
        if not spatial.applies(layer, state) or layer["name"] not in checked:
            continue
        geoms, labels = [], []
        for f in spatial.features_near(layer["name"], lat, lon, spatial.FETCH_RADIUS_KM):
            geoms.append(transform(spatial.TO_M, shape(json.loads(f["geojson"]))))
            labels.append(f["label"])
        out[layer["name"]] = {"layer": layer, "geoms": geoms, "labels": labels,
                              "tree": STRtree(geoms) if geoms else None}
    return out


def screen_cached(lat, lon, layers):
    """Same finding format as spatial.screen_point, but only from data already loaded (no downloads)."""
    center = transform(spatial.TO_M, Point(lon, lat))
    findings, inside = [], []
    for name, L in layers.items():
        layer = L["layer"]
        base = {"id": f"F{len(findings) + 1}", "layer": name, "title": layer["title"],
                "color": layer["color"], "source": layer["url"], "geometry": None}
        if L["tree"] is None:
            findings.append({**base, "buffer": "none", "distance_m": None,
                             "detail": f"No {layer['title']} features found within 5 km."})
            continue
        idx = L["tree"].query(center, predicate="dwithin", distance=5000)
        if len(idx) == 0:
            findings.append({**base, "buffer": "none", "distance_m": None,
                             "detail": f"No {layer['title']} features found within 5 km."})
            continue
        dists = sorted((center.distance(L["geoms"][i]), i) for i in idx)
        d, i = dists[0]
        if d == 0:
            inside.append(name)
        buffer = next(n for n, m in spatial.RINGS_M.items() if d <= m)
        n1 = sum(1 for dd, _ in dists if dd <= 1000)
        label = L["labels"][i]
        where = (f"within {spatial.SITE_RADIUS_M} m of the point" if buffer == "site"
                 else f"{spatial.fmt_m(d)} from the point")
        findings.append({**base, "buffer": buffer, "distance_m": round(d),
                         "detail": (f"Nearest {layer['title']} feature{f' ({label})' if label else ''} is {where}. "
                                    f"{n1} feature(s) within 1 km, {len(dists)} within 5 km.")})
    return findings, inside


def summarize(lat, lon, findings, triggers, origin=None):
    s = {
        "lat": round(lat, 6), "lon": round(lon, 6),
        "score": score(triggers),
        "high": sum(1 for t in triggers if t["delay_risk"] == "high"),
        "medium": sum(1 for t in triggers if t["delay_risk"] == "medium"),
        "triggers": [{"rule_id": t["rule_id"], "trigger": t["trigger"], "delay_risk": t["delay_risk"]}
                     for t in triggers],
        # nearest distance per layer (None = nothing within 5 km) for the comparison table
        "nearest": {f["layer"]: f.get("distance_m") for f in findings
                    if f["buffer"] != "unknown" and f["layer"] not in REGION_CONTEXT},
        "titles": {f["layer"]: f["title"] for f in findings},
    }
    ws = spatial.region_props("water_stress", lat, lon)
    s["water_stress"] = (ws or {}).get("bws_label")
    return s


def find_alternatives(lat, lon, mw, top=3):
    # 1. Origin, screened normally (also makes sure the area is cached)
    state, county, findings = spatial.screen_point(lat, lon)
    if state is None:
        return None
    egrid = (spatial.region_props("egrid_subregions", lat, lon) or {}).get("Subregion")
    est = estimates.estimate(mw, state, egrid)
    origin_triggers = rules.evaluate(findings, state, mw, est)
    checked = {f["layer"] for f in findings if f["buffer"] != "unknown"}
    unchecked = sorted({f["title"] for f in findings if f["buffer"] == "unknown"})
    origin = summarize(lat, lon, findings, origin_triggers)
    origin["label"] = "Original site"

    # 2-4. Candidates
    layers = load_layers(lat, lon, state, checked)
    candidates, skipped = [], 0
    for km in RINGS_KM:
        for k, name in enumerate(BEARINGS):
            clat, clon = offset(lat, lon, km, k * 45)
            if spatial.locate(clat, clon)[0] != state:   # stay in the same state (same rules)
                skipped += 1
                continue
            cf, inside = screen_cached(clat, clon, layers)
            if set(inside) & NO_BUILD_LAYERS:
                skipped += 1
                continue
            ct = rules.evaluate(cf, state, mw, est)
            c = summarize(clat, clon, cf, ct)
            c["label"] = f"{km:g} km {name}"
            c["distance_km"] = km
            candidates.append(c)

    candidates.sort(key=lambda c: (c["score"], c["high"], c["distance_km"]))
    best = [c for c in candidates if c["score"] < origin["score"]][:top]
    if best:
        msg = (f"Found {len(best)} nearby spot(s) with fewer flagged review triggers than the original site "
               f"(score {origin['score']} -> {best[0]['score']}).")
    else:
        msg = "No nearby spot within 2.5 km scored lower than the original site on the layers checked."
    return {
        "origin": origin, "candidates": best, "tested": len(candidates), "skipped": skipped,
        "message": msg, "caveat": CAVEAT, "unchecked_layers": unchecked,
        "scoring": "Score = 3 per high-delay trigger + 1 per medium. Lower is better. Same rules.yaml as the main screen.",
    }
