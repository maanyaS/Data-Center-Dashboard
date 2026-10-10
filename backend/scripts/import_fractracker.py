"""Import US data centers from the FracTracker Alliance spreadsheet into the projects table.

Download the latest file from https://www.fractracker.org/data-centers/ into backend/data/, then
run from backend/:  python -m scripts.import_fractracker [data/Data_Centers_Database.xlsx]

Terms: "Data provided by FracTracker Alliance (2026). Accessed via https://www.fractracker.org/data-centers/"
must be cited in public-facing use (shown in each project's notes).
"""
import re
import sys

from openpyxl import load_workbook

from app import db

PATH = sys.argv[1] if len(sys.argv) > 1 else "data/Data_Centers_Database.xlsx"
CITE = "Data provided by FracTracker Alliance (2026), fractracker.org/data-centers"
SKIP_STATUS = {"Cancelled"}


def parse_mw(v):
    """'300' -> 300; '300-2,000' -> 2000 (high end, kept as text in notes)."""
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", str(v or ""))]
    return max(nums) if nums else 0


ws = load_workbook(PATH, read_only=True, data_only=True)["DB_Output_V2"]
rows = list(ws.iter_rows(values_only=True))
header = list(rows[0])
records = [dict(zip(header, r)) for r in rows[1:]]

db.init_db()
db.execute("DELETE FROM projects WHERE source = 'fractracker'")
n = 0
for r in records:
    if r["status"] in SKIP_STATUS or not r["lat"]:
        continue
    notes = " ".join(f"{label}: {r[k]}." for label, k in [
        ("Reported MW", "mw"), ("Operator", "operator_name"), ("Purpose", "purpose"), ("Community pushback", "community_pushback"),
        ("Resistance", "resistance_status"), ("Expected online", "expected_date_online"),
        ("Source", "info_source_1")] if r.get(k)) + f" {CITE}."
    db.execute(
        "INSERT INTO projects (name, source, county, state, lat, lon, mw, approximate, status, notes) "
        "VALUES (?, 'fractracker', ?, ?, ?, ?, ?, ?, ?, ?)",
        (r["facility_name"], r["county"], r["state"], float(r["lat"]), float(r["long"]),
         parse_mw(r["mw"]), 0 if r["location_confidence"] == "High" else 1, r["status"], notes))
    n += 1
print(f"Imported {n} FracTracker projects (US, excluding cancelled).")
