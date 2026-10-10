"""Shrink the database before committing (GitHub rejects files over 100 MB).

Removes the per-site GIS cache (re-downloaded automatically when a site is screened) and the
screening history. Keeps layers, national region layers, projects, alerts and seed tables.

Run from backend/:  python -m scripts.slim_db
Then optionally:    python -m scripts.prepare_data   (re-caches planned listed projects for speed)
"""
from app import db

site_layers = [l["name"] for l in db.get_layers("site")]
con = db.connect()
for name in site_layers:
    con.execute("DELETE FROM features WHERE layer = ?", (name,))
    con.execute("DELETE FROM coverage WHERE layer = ?", (name,))
con.execute("DELETE FROM screenings")
con.commit()
con.execute("VACUUM")
con.close()
print(f"Slimmed {db.DB_PATH}: {db.DB_PATH.stat().st_size / 1e6:.1f} MB")
