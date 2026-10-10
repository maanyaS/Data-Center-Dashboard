"""GIS: download ArcGIS REST layers into the DB (cached), then check a site against them.

Distances are computed in EPSG:5070 (Conus Albers, meters), which covers all of NJ and NY.
"""
import json
import math

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
REGION_BBOX = (-79.8, 38.4, -71.8, 45.1)   # NJ + NY + DE
STATE_FIPS = {"34": "NJ", "36": "NY", "10": "DE"}

# Region overlays: every feature gets a 0-4 "level" (same 5-step color scale for both).
RATING = {"Very Low": 0, "Relatively Low": 1, "Relatively Moderate": 2, "Relatively High": 3, "Very High": 4}


def overlay_level(layer_name, props):
    if layer_name == "water_stress":
        cat = props.get("bws_cat")
        return cat if cat is not None and cat >= 0 else None   # -1 = arid / low water use
    if layer_name == "climate_risk":
        return RATING.get(props.get("RISK_RATNG"))
    return None


def overlay_detail(layer_name, props):
    if layer_name == "water_stress":
        return (f"Baseline water stress at the site is {props.get('bws_label') or 'unknown'} "
                f"(WRI Aqueduct 4.0, share of available water already withdrawn).")
    return (f"{props.get('COUNTY')} County natural-hazard risk is {props.get('RISK_RATNG') or 'unknown'} "
            f"(FEMA National Risk Index); social vulnerability {props.get('SOVI_RATNG') or 'unknown'}, "
            f"community resilience {props.get('RESL_RATNG') or 'unknown'}.")


def overlay_geojson(layer_name):
    """All cached features of a region layer, with a 0-4 level, for the map overlay."""
    feats = []
    for r in db.rows("SELECT label, props, geojson FROM features WHERE layer=?", (layer_name,)):
        level = overlay_level(layer_name, json.loads(r["props"]))
        if level is not None:
            feats.append({"type": "Feature", "geometry": json.loads(r["geojson"]),
                          "properties": {"level": level, "label": r["label"]}})
    return {"type": "FeatureCollection", "features": feats}


# ---------- downloading ----------

def bbox_around(lat, lon, km):
    dlat = km / 111.0
    dlon = km / (111.0 * math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def fetch_arcgis(url, where, bbox, simplify_deg=0.00002):
    """Generic ArcGIS REST fetcher: layer URL + bbox -> list of GeoJSON features (paged)."""
    features, offset, seen_first = [], 0, None
    for _ in range(100):  # safety cap on pages
        params = {
            "where": where, "outFields": "*", "f": "geojson", "outSR": 4326,
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
        first = json.dumps(page[0].get("properties"), sort_keys=True)
        if first == seen_first:   # server ignores resultOffset -> stop instead of looping forever
            break
        seen_first = first
        features += page
        more = data.get("exceededTransferLimit") or data.get("properties", {}).get("exceededTransferLimit")
        if not more:
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
        props = f.get("properties") or {}
        src_id = str(f.get("id") or props.get("OBJECTID") or props.get("objectid") or hash(geom.wkb))
        label = str(props.get(layer["label_field"]) or "")
        minx, miny, maxx, maxy = geom.bounds
        keep_props = props if layer["scope"] == "region" else {}   # only counties need attributes
        gj = {"type": f["geometry"]["type"], "coordinates": round_coords(f["geometry"]["coordinates"])}
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
        feats = fetch_arcgis(layer["url"], layer["where_clause"], bbox, simplify_deg)
    except Exception as e:
        print(f"[spatial] {layer['name']} download failed: {e}")
        return str(e)
    store_features(layer, feats)
    db.execute("INSERT INTO coverage VALUES (?,?,?,?,?)", (layer["name"], *bbox))
    print(f"[spatial] {layer['name']}: cached {len(feats)} features")
    return None


def ensure_region():
    for layer in db.get_layers("region"):
        download(layer, REGION_BBOX, simplify_deg=0.001)


def ensure_area(lat, lon):
    """Make sure every site-scope layer is cached around this point. Returns {layer: error}."""
    bbox = bbox_around(lat, lon, FETCH_RADIUS_KM)
    errors = {}
    for layer in db.get_layers("site"):
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


def locate(lat, lon):
    """Return (state, county) for a point using the cached counties layer."""
    pt = Point(lon, lat)
    for f in features_near("counties", lat, lon, 1):
        if shape(json.loads(f["geojson"])).contains(pt):
            props = json.loads(f["props"])
            return STATE_FIPS.get(str(props.get("STATE"))), props.get("NAME")
    return None, None


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


def screen_point(lat, lon):
    """Check each layer around the point. Returns (state, county, findings)."""
    state, county = locate(lat, lon)
    if state is None:
        return None, None, []
    errors = ensure_area(lat, lon)
    center = transform(TO_M, Point(lon, lat))
    findings = []
    for layer in db.get_layers("site"):
        if state not in layer["states"]:
            continue
        base = {"id": f"F{len(findings) + 1}", "layer": layer["name"], "title": layer["title"],
                "color": layer["color"], "source": layer["url"] or "not loaded", "geometry": None}
        if not layer["url"] or layer["name"] in errors:
            why = "layer not loaded yet" if not layer["url"] else "data download failed"
            findings.append({**base, "buffer": "unknown", "distance_m": None,
                             "detail": f"Unknown - {why}; this layer was not checked."})
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
        if layer["name"] == "counties":
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
