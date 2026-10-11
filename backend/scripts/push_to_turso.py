"""Copy the local database (data/sitecheck.db) into the hosted Turso database.

Needs TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in backend/.env.
Run from backend/:  python -m scripts.push_to_turso
Safe to re-run: each table is cleared in Turso and copied again.
"""
import sqlite3
import time

from app import db

TABLES = ["projects", "features", "coverage", "alerts", "queue_snapshot", "screenings"]

if not db.TURSO_URL:
    raise SystemExit("Set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in backend/.env first.")

print("Creating tables + seed data in Turso...")
db.init_db()   # schema, layers, eGRID, prices, estimate params (from seed.yaml)

local = sqlite3.connect(db.DB_PATH)
remote = db.connect()
for table in TABLES:
    cols = [r[1] for r in local.execute(f"PRAGMA table_info({table})")]
    rows = local.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
    t = time.time()
    remote.execute(f"DELETE FROM {table}")
    one = f"({', '.join('?' * len(cols))})"
    step = 200   # rows per INSERT statement (much faster than one row at a time)
    for i in range(0, len(rows), step):
        chunk = rows[i:i + step]
        remote.execute(f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES {', '.join([one] * len(chunk))}",
                       [v for row in chunk for v in row])
        if (i // step) % 10 == 9:
            remote.commit()
            print(f"   {table}: {i + len(chunk)}/{len(rows)}", end="\r")
    remote.commit()
    print(f"{table}: {len(rows)} rows ({time.time() - t:.0f}s)          ")
print("Done. The app now uses Turso whenever TURSO_DATABASE_URL is set.")
