"""Database: hosted Turso (if TURSO_DATABASE_URL is set in backend/.env) or the local file data/sitecheck.db.
Created on first use; seeded from seed.yaml + projects.csv."""
import csv
import json
import os
import shutil
import sqlite3
from pathlib import Path

import yaml
from dotenv import load_dotenv

from . import turso

BACKEND = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND / ".env")   # scripts import this module directly, so load settings here too
TURSO_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN")
DB_PATH = BACKEND / "data" / "sitecheck.db"
SEED_PATH = BACKEND / "seed.yaml"
PROJECTS_CSV = BACKEND / "projects.csv"   # hand-maintained project list (opens in Excel)

# Vercel's filesystem is read-only except /tmp: copy the bundled DB there.
# (Writes on Vercel - new screenings, newly cached areas - are temporary.)
if os.getenv("VERCEL") and not TURSO_URL:
    tmp = Path("/tmp/sitecheck.db")
    if not tmp.exists() and DB_PATH.exists():
        shutil.copy(DB_PATH, tmp)
    DB_PATH = tmp

SCHEMA = """
CREATE TABLE IF NOT EXISTS layers (
    name TEXT PRIMARY KEY, title TEXT, url TEXT, where_clause TEXT, label_field TEXT,
    states TEXT, scope TEXT, color TEXT, out_fields TEXT
);
-- Data center projects shown on the map. source: "list" (projects.csv) or "nyiso" (queue file).
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY, name TEXT, source TEXT, queue_id TEXT UNIQUE, county TEXT, state TEXT,
    lat REAL, lon REAL, mw REAL, approximate INTEGER, status TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS egrid (
    code TEXT PRIMARY KEY, name TEXT, co2_lb_per_mwh REAL
);
CREATE TABLE IF NOT EXISTS power_prices (
    state TEXT PRIMARY KEY, cents_kwh REAL
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
    id INTEGER PRIMARY KEY, name TEXT, lat REAL, lon REAL, mw REAL, result TEXT,
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
    if TURSO_URL:
        return turso.Connection(TURSO_URL, TURSO_TOKEN)
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)   # wait (don't fail) if the server is writing at the same time
    con.row_factory = sqlite3.Row
    return con


def init_db():
    """Create tables; load seed.yaml if the layers table is empty."""
    con = connect()
    con.executescript(SCHEMA)
    for sql in ["ALTER TABLE layers ADD COLUMN out_fields TEXT", "ALTER TABLE screenings ADD COLUMN name TEXT"]:
        try:   # columns added after the first version of the database
            con.execute(sql)
        except sqlite3.OperationalError:
            pass
    seed = yaml.safe_load(SEED_PATH.read_text())
    # Layers are synced from seed.yaml on every start. If a layer's URL/filter changed,
    # drop its cached data so it is downloaded again.
    for l in seed["layers"]:
        old = con.execute("SELECT url, where_clause FROM layers WHERE name=?", (l["name"],)).fetchone()
        if old and (old["url"], old["where_clause"]) != (l["url"], l["where"]):
            con.execute("DELETE FROM features WHERE layer=?", (l["name"],))
            con.execute("DELETE FROM coverage WHERE layer=?", (l["name"],))
        con.execute(
            "INSERT OR REPLACE INTO layers (name, title, url, where_clause, label_field, states, scope, color, out_fields) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (l["name"], l["title"], l["url"], l["where"], l["label_field"],
             ",".join(l["states"]), l["scope"], l["color"], l.get("out_fields")),
        )
    if con.execute("SELECT COUNT(*) FROM estimate_params").fetchone()[0] == 0:
        for p in seed["estimate_params"]:
            con.execute("INSERT INTO estimate_params VALUES (?,?,?,?)",
                        (p["key"], p["low"], p["high"], p["source"]))
    con.execute("DELETE FROM egrid")
    for g in seed["egrid"]:
        con.execute("INSERT INTO egrid VALUES (?,?,?)", (g["code"], g["name"], g["co2_lb_per_mwh"]))
    con.execute("DELETE FROM power_prices")
    for p in seed["power_prices"]:
        con.execute("INSERT INTO power_prices VALUES (?,?)", (p["state"], p["cents_kwh"]))
    con.execute("DELETE FROM projects WHERE source = 'known'")   # old format, now in projects.csv
    if con.execute("SELECT COUNT(*) FROM projects WHERE source='list'").fetchone()[0] == 0:
        load_project_list(con)
    con.commit()
    con.close()


def load_project_list(con):
    """(Re)load projects.csv into the projects table. Rows without lat/lon are skipped
    (run `python -m scripts.import_projects` to geocode them)."""
    con.execute("DELETE FROM projects WHERE source = 'list'")
    with open(PROJECTS_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not r["lat"]:
                continue
            notes = " ".join(x for x in [r["notes"], f"Source: {r['source']}."] if x)
            con.execute(
                "INSERT INTO projects (name, source, county, state, lat, lon, mw, approximate, status, notes) "
                "VALUES (?, 'list', ?, ?, ?, ?, ?, ?, ?, ?)",
                (r["name"], r["county"], r["state"], float(r["lat"]), float(r["lon"]),
                 float(r["mw"] or 0), int(r["approximate"] or 0), r["status"], notes))


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


def save_screening(name, lat, lon, mw, result):
    return execute("INSERT INTO screenings (name, lat, lon, mw, result) VALUES (?,?,?,?,?)",
                   (name, lat, lon, mw, json.dumps(result)))
