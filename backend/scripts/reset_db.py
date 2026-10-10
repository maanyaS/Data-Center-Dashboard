"""Delete the database so it is re-created from seed.yaml (cached GIS data is lost too).

Run from backend/:  python -m scripts.reset_db
"""
from app import db

db.DB_PATH.unlink(missing_ok=True)
db.init_db()
print(f"Reset {db.DB_PATH}")
