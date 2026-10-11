"""GIS: download ArcGIS REST layers into the DB (cached), then check a site against them.

Distances are computed in EPSG:5070 (Conus Albers, meters), which covers all of NJ and NY.
"""
import json
import math
from concurrent.futures import ThreadPoolExecutor

import requests
from pyproj import Transformer
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform

from . import db

TO_M = Transformer.from_crs(4326, 5070, always_xy=True).transform
TO_DEG = Transformer.from_crs(5070, 4326, always_xy=True).transform

SITE_RADIUS_M = 200          # "at site" = within 200 m of the pin (approximate footprint)
RINGS_M = {"site": SITE_RADIUS_M, "1km": 1000, "5km": 5000}
FETCH_RADIUS_KM = 8          # how much area to download around a site (a bit more than 5 km)
REGION_BBOX = (-180, 17, -64, 72)   # all US states + PR
STATE_FIPS = dict(zip(
    "01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32 33 34 35 36 37 38 39 "
    "40 41 42 44 45 46 47 48 49 50 51 53 54 55 56 72".split(),
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH "
    "OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR".split()))
NOT_SCREENED = ("counties", "egrid_subregions", "wildlife_areas")   # region layers not turned into findings

# Region overlays: every feature gets a 0-4 "level" (same 5-step color scale for both).
RATING = {"Very Low": 0, "Relatively Low": 1, "Relatively Moderate": 2, "Relatively High": 3, "Very High": 4}


def overlay_level(layer_name, props):
    if layer_name == "water_stress":
        cat = props.get("bws_cat")
        return cat if cat is not None and cat >= 0 else None   # -1 = arid / low water use
    if layer_name == "climate_risk":
        return RATING.get(props.get("RISK_RATNG"))
    if layer_name == "wildlife_areas":
        return 0   # single color
    if layer_name == POPULATION_LAYER:
        d = density_per_km2(props)
        return None if d is None else sum(d >= b for b in DENSITY_BINS)
    return None


def overlay_label(layer_name, props, label):
    """Hover text for an overlay feature."""
    if layer_name == POPULATION_LAYER:
        return f"{label}: {int(props['POP100']):,} people · {round(density_per_km2(props)):,} per km²"
    return label


def overlay_detail(layer_name, props):
    if layer_name == "water_stress":
        return (f"Baseline water stress at the site is {props.get('bws_label') or 'unknown'} "
                f"(WRI Aqueduct 4.0, share of available water already withdrawn).")
    return (f"{props.get('COUNTY')} County natural-hazard risk is {props.get('RISK_RATNG') or 'unknown'} "
            f"(FEMA National Risk Index); social vulnerability {props.get('SOVI_RATNG') or 'unknown'}, "
            f"community resilience {props.get('RESL_RATNG') or 'unknown'}."
            + (f" Heat wave risk {props.get('HWAV_RISKR') or 'unknown'}, cold wave risk "
               f"{props.get('CWAV_RISKR') or 'unknown'}, drought risk {props.get('DRGT_RISKR') or 'unknown'}."
               if any(k in props for k in ("HWAV_RISKR", "CWAV_RISKR", "DRGT_RISKR")) else ""))


def overlay_geojson(layer_name, bbox):
    """Features of a region layer inside the map view (bbox = minx, miny, maxx, maxy), with a 0-4 level."""
    feats = []
    minx, miny, maxx, maxy = bbox
    for r in db.rows("SELECT label, props, geojson FROM features WHERE layer=? "
                     "AND maxx>=? AND minx<=? AND maxy>=? AND miny<=?", (layer_name, minx, maxx, miny, maxy)):
        props = json.loads(r["props"])
        level = overlay_level(layer_name, props)
        if level is not None:
            feats.append({"type": "Feature", "geometry": json.loads(r["geojson"]),
                          "properties": {"level": level, "label": overlay_label(layer_name, props, r["label"])}})
    return {"type": "FeatureCollection", "features": feats}


# ---------- downloading ----------

def bbox_around(lat, lon, km):
    dlat = km / 111.0
    dlon = km / (111.0 * math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def fetch_arcgis(url, where, bbox, simplify_deg=0.00002, out_fields="*"):
    """Generic ArcGIS REST fetcher: layer URL + bbox -> list of GeoJSON features (paged)."""
    features, offset, seen_first, page_size = [], 0, None, 0
    for _ in range(100):  # safety cap on pages
        params = {
            "where": where, "outFields": out_fields, "f": "geojson", "outSR": 4326,
            "geometry": ",".join(map(str, bbox)), "geometryType": "esriGeometryEnvelope",
            "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
            "maxAllowableOffset": simplify_deg,
            "resultOffset": offset, "resultRecordCount": 1000,
        }
        r = requests.get(url.rstrip("/") + "/query", params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        page = data.get("features", [])
        if not page:
            break
        first = json.dumps(page[0], sort_keys=True)   # whole feature incl. geometry
        if first == seen_first:   # server ignores resultOffset -> stop instead of looping forever
            break
        seen_first = first
        features += page
        # Some servers don't flag "more pages": keep going while pages come back full
        page_size = max(page_size, len(page))
        more = data.get("exceededTransferLimit") or data.get("properties", {}).get("exceededTransferLimit")
        if not more and len(page) < page_size:
            break
        offset += len(page)
    return features


def round_coords(c, nd=5):
    """Round GeoJSON coordinates to ~1 m (5 decimals) to keep the database small."""
    return round(c, nd) if isinstance(c, (int, float)) else [round_coords(x, nd) for x in c]


def store_features(layer, features):
    con = db.connect()
    for i, f in enumerate(features):
        if not f.get("geometry"):
            continue
        geom = shape(f["geometry"])
        if layer["scope"] == "region":   # national layers: simplify to ~300 m to keep the DB small
            geom = geom.simplify(0.003, preserve_topology=True)
            f["geometry"] = mapping(geom)
        props = f.get("properties") or {}
        src_id = str(f.get("id") or props.get("OBJECTID") or props.get("objectid") or hash(geom.wkb))
        label = str(props.get(layer["label_field"]) or "")
        minx, miny, maxx, maxy = geom.bounds
        # Region layers need attributes; so do census tracts (POP100 for population counts + density)
        keep_props = props if layer["scope"] == "region" or layer["name"] == POPULATION_LAYER else {}
        gj = {"type": f["geometry"]["type"], "coordinates": round_coords(json.loads(json.dumps(f["geometry"]["coordinates"])))}
        con.execute(
            "INSERT OR IGNORE INTO features VALUES (?,?,?,?,?,?,?,?,?)",
            (layer["name"], src_id, label, json.dumps(keep_props), json.dumps(gj, separators=(",", ":")),
             minx, miny, maxx, maxy),
        )
    con.commit()
    con.close()


def is_covered(layer_name, bbox):
    return bool(db.rows(
        "SELECT 1 FROM coverage WHERE layer=? AND minx<=? AND miny<=? AND maxx>=? AND maxy>=?",
        (layer_name, *bbox)))


def download(layer, bbox, simplify_deg=0.00002):
    """Fetch one layer for a bbox and cache it. Returns error text or None."""
    if not layer["url"] or is_covered(layer["name"], bbox):
        return None
    try:
        fields = layer["out_fields"] or (layer["label_field"] if layer["scope"] == "site" else "*")
        feats = fetch_arcgis(layer["url"], layer["where_clause"], bbox, simplify_deg, fields)
    except Exception as e:
        print(f"[spatial] {layer['name']} download failed: {e}")
        return str(e)
    store_features(layer, feats)
    db.execute("INSERT INTO coverage VALUES (?,?,?,?,?)", (layer["name"], *bbox))
    print(f"[spatial] {layer['name']}: cached {len(feats)} features")
    return None


def ensure_region():
    for layer in db.get_layers("region"):
        download(layer, REGION_BBOX, simplify_deg=0.003)   # ~300 m, national layers


def ensure_area(lat, lon, state=None):
    """Make sure the site-scope layers for this state are cached around the point. Returns {layer: error}."""
    bbox = bbox_around(lat, lon, FETCH_RADIUS_KM)
    errors = {}
    for layer in db.get_layers("site"):
        if state and not applies(layer, state):
            continue
        err = download(layer, bbox)
        if err:
            errors[layer["name"]] = err
    return errors


# ---------- screening ----------

def features_near(layer_name, lat, lon, km):
    minx, miny, maxx, maxy = bbox_around(lat, lon, km)
    return db.rows(
        "SELECT src_id, label, props, geojson FROM features "
        "WHERE layer=? AND maxx>=? AND minx<=? AND maxy>=? AND miny<=?",
        (layer_name, minx, maxx, miny, maxy))


def region_props(layer_name, lat, lon):
    """Attributes of the region-layer polygon containing the point (or None)."""
    pt = Point(lon, lat)
    for f in features_near(layer_name, lat, lon, 1):
        if shape(json.loads(f["geojson"])).contains(pt):
            return json.loads(f["props"])
    return None


def locate(lat, lon):
    """Return (state, county) for a point using the cached counties layer."""
    props = region_props("counties", lat, lon)
    if not props:
        return None, None
    return STATE_FIPS.get(str(props.get("STATE"))), props.get("NAME")


def applies(layer, state):
    return "*" in layer["states"] or state in layer["states"]


def ring_geojson(lat, lon):
    center = transform(TO_M, Point(lon, lat))
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"ring": name},
             "geometry": mapping(transform(TO_DEG, center.buffer(m, 32)))}
            for name, m in RINGS_M.items()
        ],
    }


def fmt_m(m):
    return f"{m / 1000:.1f} km" if m >= 1000 else f"{round(m)} m"


# ---------- population (added) ----------
POPULATION_LAYER = "census_tracts"
DENSITY_BINS = (100, 500, 1500, 4000)   # people per km² -> overlay levels 0-4
TILE_DEG = 0.25                          # density overlay downloads tracts in fixed tiles so they cache well
MAX_OVERLAY_DEG = 1.0                    # refuse bigger views (the map only asks at zoom >= 11)


def density_per_km2(props):
    """People per km² of land (2020 Census). None if the tract has no population or land area."""
    pop, land = props.get("POP100"), props.get("AREALAND")
    return pop / (land / 1e6) if pop is not None and land else None


def population_overlay(bbox):
    """Density overlay for the map view: download any missing tiles (in parallel), then return shaded tracts."""
    minx, miny, maxx, maxy = bbox
    if maxx - minx > MAX_OVERLAY_DEG or maxy - miny > MAX_OVERLAY_DEG:
        return {"type": "FeatureCollection", "features": []}
    layer = next(l for l in db.get_layers("site") if l["name"] == POPULATION_LAYER)
    snap = lambda v: math.floor(v / TILE_DEG) * TILE_DEG
    tiles = [(x, y, x + TILE_DEG, y + TILE_DEG)
             for x in frange(snap(minx), maxx) for y in frange(snap(miny), maxy)]
    tiles = [t for t in tiles if not is_covered(POPULATION_LAYER, t)]

    def fetch(tile):
        try:
            return tile, fetch_arcgis(layer["url"], layer["where_clause"], tile, out_fields=layer["out_fields"])
        except Exception as e:
            print(f"[spatial] {POPULATION_LAYER} overlay tile {tile} failed: {e}")
            return tile, None

    with ThreadPoolExecutor(max_workers=6) as pool:   # network in parallel, DB writes one at a time below
        for tile, feats in pool.map(fetch, tiles):
            if feats is not None:
                store_features(layer, feats)
                db.execute("INSERT INTO coverage VALUES (?,?,?,?,?)", (POPULATION_LAYER, *tile))
    return overlay_geojson(POPULATION_LAYER, bbox)


def frange(start, stop):
    while start < stop:
        yield round(start, 6)
        start += TILE_DEG


def population_near(center_m, tracts_m, radius_m):
    """Area-weighted estimate: each Census tract adds its 2020 population times the share of its area inside the circle."""
    circle = center_m.buffer(radius_m, 64)
    total = 0.0
    for g, pop in tracts_m:
        if pop and g.area > 0 and g.intersects(circle):
            total += pop * g.intersection(circle).area / g.area
    return round(total)


def population_finding(center_m, rows):
    """Finding for the census tract layer: people living within 1 km and 5 km (estimate)."""
    tracts = []
    for f in rows:
        pop = (json.loads(f["props"]) or {}).get("POP100")
        tracts.append((transform(TO_M, shape(json.loads(f["geojson"]))), float(pop) if pop is not None else None))
    if not tracts:
        return {"buffer": "unknown", "distance_m": None, "population": None,
                "detail": "Unknown - no Census tract data loaded for this area."}
    if all(p is None for _, p in tracts):
        return {"buffer": "unknown", "distance_m": None, "population": None,
                "detail": "Unknown - Census tracts loaded without population counts."}
    p1, p5 = population_near(center_m, tracts, 1000), population_near(center_m, tracts, 5000)
    return {"buffer": "site", "distance_m": None, "population": {"within_1km": p1, "within_5km": p5},
            "detail": (f"About {p1:,} people live within 1 km of the site and about {p5:,} within 5 km "
                       f"(2020 Census tract populations, estimated by area share).")}


def screen_point(lat, lon):
    """Check each layer around the point. Returns (state, county, findings)."""
    state, county = locate(lat, lon)
    if state is None:
        return None, None, []
    errors = ensure_area(lat, lon, state)
    center = transform(TO_M, Point(lon, lat))
    findings = []
    for layer in db.get_layers("site"):
        if not applies(layer, state):
            continue
        base = {"id": f"F{len(findings) + 1}", "layer": layer["name"], "title": layer["title"],
                "color": layer["color"], "source": layer["url"] or "not loaded", "geometry": None}
        if not layer["url"] or layer["name"] in errors:
            why = "layer not loaded yet" if not layer["url"] else "data download failed"
            findings.append({**base, "buffer": "unknown", "distance_m": None,
                             "detail": f"Unknown - {why}; this layer was not checked."})
            continue
        if layer["name"] == POPULATION_LAYER:
            findings.append({**base, **population_finding(center, features_near(layer["name"], lat, lon, 5.5))})
            continue
        hits = []
        for f in features_near(layer["name"], lat, lon, 5.5):
            g = shape(json.loads(f["geojson"]))
            d = center.distance(transform(TO_M, g))
            if d <= 5000:
                hits.append((d, f["label"], g))
        if not hits:
            findings.append({**base, "buffer": "none", "distance_m": None,
                             "detail": f"No {layer['title']} features found within 5 km."})
            continue
        hits.sort(key=lambda h: h[0])
        d, label, g = hits[0]
        buffer = next(name for name, m in RINGS_M.items() if d <= m)
        n1 = sum(1 for h in hits if h[0] <= 1000)
        where = "at the site" if buffer == "site" else f"{fmt_m(d)} from the site"
        nearby = {}   # every named feature within 5 km, closest distance per name
        for hd, hl, _ in hits:
            if hl and hl.lower() != "unknown" and hl not in nearby:
                nearby[hl] = round(hd)
        findings.append({
            **base, "buffer": buffer, "distance_m": round(d),
            "nearby": [{"name": n, "distance_m": m} for n, m in list(nearby.items())[:15]],
            "geometry": mapping(g),
            "detail": (f"Nearest {layer['title']} feature{f' ({label})' if label else ''} is {where}. "
                       f"{n1} feature(s) within 1 km, {len(hits)} within 5 km."),
        })
    # Context at the pin from region layers (water stress, climate risk)
    pt = Point(lon, lat)
    for layer in db.get_layers("region"):
        if layer["name"] in NOT_SCREENED:
            continue
        base = {"id": f"F{len(findings) + 1}", "layer": layer["name"], "title": layer["title"],
                "color": layer["color"], "source": layer["url"], "geometry": None, "distance_m": None}
        hit = next((f for f in features_near(layer["name"], lat, lon, 1)
                    if shape(json.loads(f["geojson"])).contains(pt)), None)
        if hit:
            props = json.loads(hit["props"])
            findings.append({**base, "buffer": "site", "level": overlay_level(layer["name"], props),
                             "detail": overlay_detail(layer["name"], props)})
        else:
            findings.append({**base, "buffer": "unknown", "detail": f"Unknown - no {layer['title']} data at this point."})
    return state, county, findings
