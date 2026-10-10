"""Diff the NYISO queue against the saved snapshot and create alerts for new large loads.

Run from backend/:
    python -m scripts.check_queue path/to/NYISO-Interconnection-Queue.xlsx
Test alerts (pretend the last N NY data center rows are new):
    python -m scripts.check_queue path/to/queue.xlsx --forget 3
"""
import sys

from app import alerts, db
from app.main import run_screen

db.init_db()
path = sys.argv[1]
if "--forget" in sys.argv:
    n = int(sys.argv[sys.argv.index("--forget") + 1])
    ids = [r[alerts.ID_COL] for r in alerts.read_queue(path) if alerts.is_data_center(r)][-n:]
    for qid in ids:
        db.execute("DELETE FROM queue_snapshot WHERE queue_id = ?", (str(qid).strip(),))
    print(f"Forgot {len(ids)} rows from snapshot: {ids}")


def screen(lat, lon, mw, name):
    try:
        return run_screen(lat, lon, mw, name)
    except Exception as e:
        return {"error": str(e), "triggers": []}


print(alerts.check_queue(path, screen))
