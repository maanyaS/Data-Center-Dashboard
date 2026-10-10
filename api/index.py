"""Vercel entry point: serves the FastAPI backend under /api (same paths the frontend uses locally)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi import FastAPI  # noqa: E402

from app import db, spatial  # noqa: E402
from app.main import app as backend  # noqa: E402

# Mounted apps don't run startup events, so initialize here.
db.init_db()
spatial.ensure_region()

app = FastAPI()
app.mount("/api", backend)
