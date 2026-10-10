"""SQLite database: one file, data/sitecheck.db. Created and seeded from seed.yaml on first use."""
import json
import os
import shutil
import sqlite3
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parent.parent
DB_PATH = BACKEND / "data" / "sitecheck.db"
SEED_PATH = BACKEND / "seed.yaml"

# Vercel's filesystem is read-only except /tmp: copy the bundled DB there.
# (Writes on Vercel - new screenings, newly cached areas - are temporary.)
if os.getenv("VERCEL"):
    tmp = Path("/tmp/sitecheck.db")
    if not tmp.exists() and DB_PATH.exists():
        shutil.copy(DB_PATH, tmp)
    DB_PATH = tmp

SCHEMA = """
CREATE TABLE IF NOT EXISTS layers (
    name TEXT PRIMARY KEY, title TEXT, url TEXT, where_clause TEXT, label_field TEXT,
    states TEXT, scope TEXT, color TEXT
);
CREATE TABLE IF NOT EXISTS demo_sites (
    id INTEGER PRIMARY KEY, name TEXT, lat REAL, lon REAL, mw REAL
);
CREATE TABLE IF NOT EXISTS estimate_params (
    key TEXT PRIMARY KEY, low REAL, high REAL, source TEXT
);
-- Cached GIS features. Bbox columns (WGS84) let us pre-filter with plain SQL.
CREATE TABLE IF NOT EXISTS features (
    layer TEXT, src_id TEXT, label TEXT, props TEXT, geojson TEXT,
    minx REAL, miny REAL, maxx REAL, maxy REAL,
    PRIMARY KEY (layer, src_id)
);
CREATE INDEX IF NOT EXISTS features_bbox ON features (layer, minx, maxx, miny, maxy);
-- Which areas have already been downloaded for each layer.
CREATE TABLE IF NOT EXISTS coverage (
    layer TEXT, minx REAL, miny REAL, maxx REAL, maxy REAL
);
CREATE TABLE IF NOT EXISTS screenings (
    id INTEGER PRIMARY KEY, lat REAL, lon REAL, mw REAL, result TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
-- NYISO queue: last snapshot + alerts generated from new rows.
CREATE TABLE IF NOT EXISTS queue_snapshot (
    queue_id TEXT PRIMARY KEY, row TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY, queue_id TEXT, name TEXT, county TEXT, mw REAL,
    lat REAL, lon REAL, summary TEXT, result TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    """Create tables; load seed.yaml if the layers table is empty."""
    con = connect()
    con.executescript(SCHEMA)
    if con.execute("SELECT COUNT(*) FROM layers").fetchone()[0] == 0:
        seed = yaml.safe_load(SEED_PATH.read_text())
        for l in seed["layers"]:
            con.execute(
                "INSERT INTO layers VALUES (?,?,?,?,?,?,?,?)",
                (l["name"], l["title"], l["url"], l["where"], l["label_field"],
                 ",".join(l["states"]), l["scope"], l["color"]),
            )
        for s in seed["demo_sites"]:
            con.execute("INSERT INTO demo_sites (name, lat, lon, mw) VALUES (?,?,?,?)",
                        (s["name"], s["lat"], s["lon"], s["mw"]))
        for p in seed["estimate_params"]:
            con.execute("INSERT INTO estimate_params VALUES (?,?,?,?)",
                        (p["key"], p["low"], p["high"], p["source"]))
    con.commit()
    con.close()


def rows(sql, params=()):
    con = connect()
    out = [dict(r) for r in con.execute(sql, params).fetchall()]
    con.close()
    return out


def execute(sql, params=()):
    con = connect()
    cur = con.execute(sql, params)
    con.commit()
    con.close()
    return cur.lastrowid


def get_layers(scope=None):
    sql = "SELECT * FROM layers" + (" WHERE scope = ?" if scope else "")
    layers = rows(sql, (scope,) if scope else ())
    for l in layers:
        l["states"] = l["states"].split(",")
    return layers


def save_screening(lat, lon, mw, result):
    return execute("INSERT INTO screenings (lat, lon, mw, result) VALUES (?,?,?,?)",
                   (lat, lon, mw, json.dumps(result)))
