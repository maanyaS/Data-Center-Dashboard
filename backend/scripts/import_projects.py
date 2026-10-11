"""Geocode projects.csv (rows with an address but no lat/lon) and load it into the database.

Run from backend/:  python -m scripts.import_projects
Edit projects.csv in Excel / VS Code to add projects. Leave lat/lon empty to geocode the address,
or fill them in yourself (set approximate=1 if they are rough).
"""
import csv
import time

import requests

from app import db

CENSUS = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM = "https://nominatim.openstreetmap.org/search"


def census(query):
    res = requests.get(CENSUS, params={"address": query, "benchmark": "Public_AR_Current", "format": "json"},
                       timeout=30).json()
    m = res["result"]["addressMatches"]
    return (m[0]["coordinates"]["y"], m[0]["coordinates"]["x"]) if m else None


def osm(query):
    time.sleep(1)   # OpenStreetMap Nominatim allows 1 request/second
    res = requests.get(NOMINATIM, params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
                       headers={"User-Agent": "BeforeTheBuild/1.0 (hackathon project)"}, timeout=30).json()
    return (float(res[0]["lat"]), float(res[0]["lon"])) if res else None


def geocode(r):
    """Try the street address (Census, then OpenStreetMap); else the town center (marked approximate)."""
    full, town = f"{r['address']}, {r['town']}, {r['state']}", f"{r['town']}, {r['county']} County, {r['state']}"
    tries = [(census, full, "0"), (osm, full, "0")] if r["address"] else []
    for fn, query, approx in tries + [(osm, town, "1")]:
        hit = fn(query)
        if hit:
            return round(hit[0], 6), round(hit[1], 6), approx
    return None


with open(db.PROJECTS_CSV, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
    cols = list(rows[0].keys())

for r in rows:
    if r["lat"]:
        continue
    hit = geocode(r)
    if hit:
        r["lat"], r["lon"], r["approximate"] = hit
        print(f"ok    {r['name']}" + ("  (approximate)" if hit[2] == "1" else ""))
    else:
        print(f"MISS  {r['name']} - add lat/lon by hand")

with open(db.PROJECTS_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

db.init_db()
con = db.connect()
db.load_project_list(con)
con.commit()
con.close()
print(f"Loaded {sum(1 for r in rows if r['lat'])} of {len(rows)} projects into the database.")
