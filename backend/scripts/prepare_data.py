"""Download + cache GIS data around every planned / under-construction listed project (faster screening, no live gov API calls).

Run from backend/:  python -m scripts.prepare_data
Optional extra site:  python -m scripts.prepare_data 40.73 -74.17
"""
import sys

from app import db, spatial

db.init_db()
spatial.ensure_region()
sites = db.rows("SELECT name, lat, lon, state FROM projects WHERE source = 'list' AND status != 'Operational'")
if len(sys.argv) == 3:
    lat, lon = float(sys.argv[1]), float(sys.argv[2])
    sites.append({"name": "custom", "lat": lat, "lon": lon, "state": spatial.locate(lat, lon)[0]})
for s in sites:
    print(f"== {s['name']}")
    errors = spatial.ensure_area(s["lat"], s["lon"], s["state"])   # only layers for that state
    for layer, err in errors.items():
        print(f"   FAILED {layer}: {err}")
print("Done. Cached features per layer:")
for r in db.rows("SELECT layer, COUNT(*) n FROM features GROUP BY layer"):
    print(f"   {r['layer']}: {r['n']}")
