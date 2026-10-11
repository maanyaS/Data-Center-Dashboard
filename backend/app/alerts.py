"""NYISO interconnection queue alerts.

Read the queue spreadsheet (.xlsx or .csv), compare to the snapshot saved in the DB,
auto-screen NEW large-load rows at their county centroid, save them as alerts.
Queue rows give a county, not an address -> results are "approximate location".

VERIFY the column names below against the real NYISO file.
"""
import re
import csv
import json
import math
from pathlib import Path

from shapely.geometry import shape

from . import db

SHEET = "Load Projects"
ID_COL = "Queue Number"
NAME_COL = "Project: Project Name"
DEV_COL = "Developer Name"
COUNTY_COL = "County"
STATE_COL = "State"
MW_COL = "Peak MW load"
END_USE_COL = "End-Use"          # DAT, DAT-AI, DAT-CM (crypto mining) = data centers
STATUS_COL = "Project Status #"  # 0 = withdrawn


def is_data_center(row):
    end_use = str(row.get(END_USE_COL) or "").upper()
    name = str(row.get(NAME_COL) or "").lower()
    status = str(row.get(STATUS_COL) or "").strip()
    in_ny = str(row.get(STATE_COL)).strip() == "NY"
    return (end_use.startswith("DAT") or "data center" in name) and in_ny and status != "0"


def read_queue(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    from openpyxl import load_workbook
    ws = load_workbook(path, read_only=True, data_only=True)[SHEET]
    it = ws.iter_rows(values_only=True)
    header = None
    for row in it:   # header row may not be the first row
        if row and ID_COL in [str(c).strip() if c else "" for c in row]:
            header = [str(c).strip() if c else "" for c in row]
            break
    if not header:
        raise ValueError(f"Could not find header row with column '{ID_COL}'")
    return [dict(zip(header, r)) for r in it if r and r[header.index(ID_COL)]]


def norm_county(name):
    return str(name).lower().replace(".", "").replace(" county", "").strip()


def county_centroid(county):
    """Approximate location: center of the NY county (queue rows have no address)."""
    for r in db.rows("SELECT label, props, geojson FROM features WHERE layer='counties'"):
        if json.loads(r["props"]).get("STATE") == "36" and norm_county(r["label"]) == norm_county(county):
            c = shape(json.loads(r["geojson"])).centroid
            return c.y, c.x
    return None


def to_mw(row):
    try:
        return float(row.get(MW_COL) or 0)
    except ValueError:
        return 0


def sync_projects(rows):
    """Put every NY data center in the queue on the map (projects table), at its county center.
    Projects in the same county are spread in a small circle so their pins don't overlap."""
    per_county = {}
    for row in rows:
        if not is_data_center(row):
            continue
        county = str(row.get(COUNTY_COL) or "")
        loc = county_centroid(county)
        lat = lon = None
        if loc:
            n = per_county.get(county, 0)
            per_county[county] = n + 1
            angle, r = n * 2.4, 0.01 * math.sqrt(n)   # ~1 km steps outward
            lat, lon = loc[0] + r * math.sin(angle), loc[1] + r * math.cos(angle)
        db.execute(
            "INSERT OR REPLACE INTO projects (name, source, queue_id, county, state, lat, lon, mw, approximate, status, notes) "
            "VALUES (?, 'nyiso', ?, ?, 'NY', ?, ?, ?, 1, ?, ?)",
            (str(row.get(NAME_COL) or ""), str(row.get(ID_COL)).strip(), county, lat, lon, to_mw(row),
             status_label(f"NYISO status {row.get(STATUS_COL)}"), f"End use: {row.get(END_USE_COL) or 'n/a'}. "
             f"Developer: {row.get(DEV_COL) or 'n/a'}. Location is the county center (approximate)."))


def check_queue(path, screen_fn):
    """screen_fn(lat, lon, mw, name) -> screening result dict. Returns list of new alerts."""
    rows = read_queue(path)
    sync_projects(rows)
    old = {r["queue_id"] for r in db.rows("SELECT queue_id FROM queue_snapshot")}
    first_run = not old
    new_alerts = []
    for row in rows:
        qid = str(row.get(ID_COL)).strip()
        if qid in old:
            continue
        db.execute("INSERT OR REPLACE INTO queue_snapshot VALUES (?,?)", (qid, json.dumps(row, default=str)))
        if first_run or not is_data_center(row):   # first run just saves the baseline
            continue
        mw = to_mw(row)
        loc = county_centroid(row.get(COUNTY_COL, ""))
        result, summary = None, "Location unknown - county not matched."
        if loc:
            result = screen_fn(loc[0], loc[1], mw, str(row.get(NAME_COL) or ""))
            t = result.get("triggers", [])
            high = sum(1 for x in t if x["delay_risk"] == "high")
            summary = f"Approximate location (county centroid). {len(t)} likely triggers, {high} high delay risk."
        db.execute("DELETE FROM alerts WHERE queue_id = ?", (qid,))   # re-running replaces, not duplicates
        db.execute(
            "INSERT INTO alerts (queue_id, name, county, mw, lat, lon, summary, result) VALUES (?,?,?,?,?,?,?,?)",
            (qid, str(row.get(NAME_COL, "")), str(row.get(COUNTY_COL, "")), mw,
             loc[0] if loc else None, loc[1] if loc else None, summary, json.dumps(result)))
        new_alerts.append(qid)
    return {"rows": len(rows), "baseline_saved": first_run, "new_alerts": new_alerts}


def list_alerts():
    out = db.rows("SELECT * FROM alerts ORDER BY id DESC")
    for a in out:
        a["result"] = json.loads(a["result"]) if a["result"] else None
    return out


# NYISO interconnection queue status codes -> plain words
NYISO_STATUS = {0: "Withdrawn", 1: "Scoping meeting pending", 2: "Feasibility study pending",
                3: "Feasibility study in progress", 4: "System impact study pending",
                5: "System impact study in progress", 6: "System impact study approved",
                7: "Facilities study pending", 8: "Cost allocation rejected / next study",
                9: "Facilities study in progress", 10: "Cost allocation accepted, agreement in progress",
                11: "Interconnection agreement done", 12: "Under construction",
                13: "In service (testing)", 14: "In service"}


def status_label(status):
    """'NYISO status 5' -> 'Planned - System impact study in progress (NYISO step 5 of 14)'."""
    m = re.fullmatch(r"NYISO status (\d+)", str(status or ""))
    if not m:
        return status
    n = int(m.group(1))
    stage = "Withdrawn" if n == 0 else "Under construction" if n == 12 else "Operating" if n >= 13 else "Planned"
    step = NYISO_STATUS.get(n, "unknown step")
    return f"{stage}{'' if step == stage else ' - ' + step} (NYISO step {n} of 14)"
