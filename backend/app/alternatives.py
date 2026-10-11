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
from concurrent.futures import ThreadPoolExecutor

from shapely import STRtree
from shapely.geometry import Point, shape
from shapely.ops import transform

from . import db, estimates, rules, spatial

RINGS_KM = (1.0, 1.75, 2.5)
FAR_SHARES = (0.5, 1.0)        # wider search: extra rings at these shares of the search radius
FAR_CHECK_KM = 1               # far spots are checked out to 1 km (all the rules need: site + 1 km)
BEARINGS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
RISK_POINTS = {"high": 3, "medium": 1}
REGION_CONTEXT = {"water_stress", "climate_risk", "census_tracts"}   # shown separately, not as distances
# A candidate whose point is INSIDE one of these shapes is skipped (can't build in a wetland, flood zone or park).
NO_BUILD_LAYERS = {"fema_flood", "nwi_wetlands", "nj_wetlands", "ny_wetlands", "de_wetlands",
                   "protected_areas", "nj_open_space", "ny_protected", "critical_habitat"}
CAVEAT = ("Screening-level only. Candidates are scored on the same public environmental layers and rules "
          "as the original site. Power line, substation and population distances are shown for context "
          "but do not change the score. The tool cannot see zoning, buildings, land ownership or "
          "whether land is for sale, so these are areas to look at, not recommended sites.")


def offset(lat, lon, km, bearing_deg):
    b = math.radians(bearing_deg)
    dlat = km * math.cos(b) / 111.0
    dlon = km * math.sin(b) / (111.0 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def score(triggers):
    return sum(RISK_POINTS.get(t["delay_risk"], 0) for t in triggers)


def load_layers(lat, lon, state, checked, km=spatial.FETCH_RADIUS_KM):
    """Load each cached site layer around a point once, in meters, with a spatial index."""
    out = {}
    for layer in db.get_layers("site"):
        if not spatial.applies(layer, state) or layer["name"] not in checked:
            continue
        geoms, labels, pops = [], [], []
        for f in spatial.features_near(layer["name"], lat, lon, km):
            geoms.append(transform(spatial.TO_M, shape(json.loads(f["geojson"]))))
            labels.append(f["label"])
            pop = (json.loads(f["props"]) or {}).get("POP100")
            pops.append(float(pop) if pop is not None else None)
        out[layer["name"]] = {"layer": layer, "geoms": geoms, "labels": labels, "pops": pops,
                              "tree": STRtree(geoms) if geoms else None}
    return out


def screen_cached(lat, lon, layers, max_m=5000):
    """Same finding format as spatial.screen_point, but only from data already loaded (no downloads)."""
    center = transform(spatial.TO_M, Point(lon, lat))
    findings, inside = [], []
    for name, L in layers.items():
        layer = L["layer"]
        base = {"id": f"F{len(findings) + 1}", "layer": name, "title": layer["title"],
                "color": layer["color"], "source": layer["url"], "geometry": None}
        if name == spatial.POPULATION_LAYER:
            if L["geoms"] and any(p is not None for p in L["pops"]):
                tracts = list(zip(L["geoms"], L["pops"]))
                p1 = spatial.population_near(center, tracts, 1000)
                p5 = spatial.population_near(center, tracts, 5000)
                findings.append({**base, "buffer": "site", "distance_m": None,
                                 "population": {"within_1km": p1, "within_5km": p5},
                                 "detail": f"About {p1:,} people within 1 km and {p5:,} within 5 km (2020 Census, estimate)."})
            else:
                findings.append({**base, "buffer": "unknown", "distance_m": None, "detail": "Unknown - no population data."})
            continue
        if L["tree"] is None:
            findings.append({**base, "buffer": "none", "distance_m": None,
                             "detail": f"No {layer['title']} features found within 5 km."})
            continue
        idx = L["tree"].query(center, predicate="dwithin", distance=max_m)
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
    pop = next((f.get("population") for f in findings if f["layer"] == spatial.POPULATION_LAYER), None)
    s["people_1km"] = (pop or {}).get("within_1km")
    s["people_5km"] = (pop or {}).get("within_5km")
    ws = spatial.region_props("water_stress", lat, lon)
    s["water_stress"] = (ws or {}).get("bws_label")
    return s


def find_alternatives(lat, lon, mw, top=3, radius_km=5):
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

    def score_spot(clat, clon, km, name, cf, inside):
        if set(inside) & NO_BUILD_LAYERS:
            return None
        c = summarize(clat, clon, cf, rules.evaluate(cf, state, mw, est))
        c["label"] = f"{km:g} km {name}"
        c["distance_km"] = km
        return c

    # Near spots (within 2.5 km): scored from the origin's cached data
    tests = []
    for km in RINGS_KM:
        for k, name in enumerate(BEARINGS):
            clat, clon = offset(lat, lon, km, k * 45)
            if spatial.locate(clat, clon)[0] != state:   # stay in the same state (same rules)
                tests.append(None)
                continue
            tests.append(score_spot(clat, clon, km, name, *screen_cached(clat, clon, layers)))

    # Far spots (wider search): ask each map server "anything within 1 km / 200 m?" - no downloads
    if radius_km > 5:
        far_layers = [L["layer"] for n, L in layers.items() if n != spatial.POPULATION_LAYER]
        # One quick test per server first; a server that doesn't answer is left out (listed as not checked)
        with ThreadPoolExecutor(max_workers=16) as pool:
            ok = list(pool.map(lambda l: _safe(spatial.count_within, l, lat, lon, 1) is not None, far_layers))
        down = [l["title"] for l, good in zip(far_layers, ok) if not good]
        far_layers = [l for l, good in zip(far_layers, ok) if good]
        if down:
            unchecked = sorted(set(unchecked) | {f"{t} (far spots)" for t in down})
        spots = []
        for s in FAR_SHARES:
            for k, name in enumerate(BEARINGS):
                km = round(radius_km * s, 1)
                clat, clon = offset(lat, lon, km, k * 45)
                if spatial.locate(clat, clon)[0] == state:
                    spots.append((clat, clon, km, name))
                else:
                    tests.append(None)
        jobs = [(s, l) for s in spots for l in far_layers]
        with ThreadPoolExecutor(max_workers=16) as pool:
            status = dict(zip(((s[:2], l["name"]) for s, l in jobs),
                              pool.map(lambda j: _safe(layer_status, j[1], *j[0][:2]), jobs)))
        for clat, clon, km, name in spots:
            res = [(l, status[((clat, clon), l["name"])]) for l in far_layers]
            if any(r is None for _, r in res):   # a server didn't answer: don't guess
                tests.append(None)
                continue
            cf = [{"id": f"F{i + 1}", "layer": l["name"], "title": l["title"], "color": l["color"],
                   "source": l["url"], "geometry": None, "buffer": b, "distance_m": d, "detail": ""}
                  for i, (l, (b, d, _)) in enumerate(res)]
            c = score_spot(clat, clon, km, name, cf, [l["name"] for l, r in res if r[2]])
            if c:
                c["checked_km"] = FAR_CHECK_KM
            tests.append(c)
    candidates = [c for c in tests if c]
    skipped = len(tests) - len(candidates)

    candidates.sort(key=lambda c: (c["score"], c["high"], c["distance_km"]))
    best = [c for c in candidates if c["score"] < origin["score"]][:top]
    if best:
        msg = (f"Found {len(best)} nearby spot(s) with fewer flagged review triggers than the original site "
               f"(score {origin['score']} -> {best[0]['score']}).")
    else:
        msg = (f"No nearby spot within {max(radius_km, 2.5):g} km scored lower than the original site "
               "on the layers checked.")
    return {
        "origin": origin, "candidates": best, "tested": len(candidates), "skipped": skipped,
        "message": msg, "caveat": CAVEAT, "unchecked_layers": unchecked,
        "scoring": "Score = 3 per high-delay trigger + 1 per medium. Lower is better. Same rules.yaml as the main screen.",
    }


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:   # one far spot failing shouldn't stop the search
        print(f"[alternatives] spot {args} failed: {e}")
        return None


def layer_status(layer, lat, lon):
    """(buffer, rough distance m, point inside a shape?) from quick count queries - used for far spots."""
    if not spatial.count_within(layer, lat, lon, 1):
        return "none", None, False
    if not spatial.count_within(layer, lat, lon, spatial.SITE_RADIUS_M / 1000):
        return "1km", 1000, False
    inside = spatial.count_within(layer, lat, lon, 0.01) > 0
    return "site", 0 if inside else spatial.SITE_RADIUS_M, inside
