"""SiteCheck API. Run from backend/:  uvicorn app.main:app

Secrets (Turso, Gemini, ElevenLabs) are read from environment variables / backend/.env only
and are never returned by any endpoint.
"""
import math
import os
import time
from collections import defaultdict, deque

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from . import alerts, briefs, db, estimates, rules, spatial, voice  # noqa: E402

ON_SERVER = bool(os.getenv("RENDER"))   # Render sets RENDER=true
# Interactive API docs (/docs) only when running locally
app = FastAPI(title="SiteCheck", docs_url=None if ON_SERVER else "/docs",
              redoc_url=None, openapi_url=None if ON_SERVER else "/openapi.json")

# Only these websites may call the API from a browser (comma-separated), e.g. your GitHub Pages site
ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

# Simple per-visitor rate limit for the expensive endpoints (Gemini, downloads, ElevenLabs)
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "10"))
_hits = defaultdict(deque)


def rate_limit(request: Request):
    ip = (request.headers.get("x-forwarded-for") or request.client.host or "?").split(",")[0].strip()
    now, q = time.time(), _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "Too many requests - please wait a minute and try again.")
    q.append(now)


@app.on_event("startup")
def startup():
    db.init_db()
    spatial.ensure_region()   # counties (downloads once, then cached)


class ScreenRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    mw: float = Field(gt=0, le=10000)
    name: str = Field("", max_length=200)
    population: bool = False   # opt-in: downloads Census tracts around the site


def run_screen(lat, lon, mw, name="", population=False):
    state, county, findings = spatial.screen_point(lat, lon, ("census_tracts",) if population else ())
    if state is None:
        raise HTTPException(400, "Site is outside US coverage.")
    egrid = (spatial.region_props("egrid_subregions", lat, lon) or {}).get("Subregion")
    est = estimates.estimate(mw, state, egrid)
    triggers = rules.evaluate(findings, state, mw, est)
    result = {
        "site": {"name": name, "lat": lat, "lon": lon, "mw": mw, "state": state, "county": county},
        "findings": findings,
        "triggers": triggers,
        "estimates": est,
        "briefs": briefs.write_briefs(findings, triggers, est),
        "rings": spatial.ring_geojson(lat, lon),
    }
    db.save_screening(name, lat, lon, mw, result)
    return result


@app.post("/screen")
def screen(req: ScreenRequest, request: Request):
    rate_limit(request)
    return run_screen(req.lat, req.lon, req.mw, req.name, req.population)


@app.get("/projects")
def projects():
    out = db.rows("SELECT * FROM projects WHERE lat IS NOT NULL ORDER BY name")
    # Same site in two sources: FracTracker (exact location, MW, pushback info) wins over projects.csv
    ft = [p for p in out if p["source"] == "fractracker"]
    out = [p for p in out if p["source"] != "list" or not any(
        abs(p["lat"] - f["lat"]) < 0.003 and abs(p["lon"] - f["lon"]) < 0.004 for f in ft)]   # ~300 m
    seen = {}   # pins on the exact same spot are fanned out (~60 m) so each one is visible
    for p in out:
        key = (round(p["lat"], 5), round(p["lon"], 5))
        n = seen[key] = seen.get(key, -1) + 1
        if n:
            p["lat"] += 0.0006 * math.sin(n * 2.4)
            p["lon"] += 0.0006 * math.cos(n * 2.4)
    return out


@app.get("/layers")
def layers():
    return db.get_layers("site")


@app.get("/overlay/{name}")
def overlay(name: str, bbox: str = "-180,17,-64,72"):
    """bbox = minLon,minLat,maxLon,maxLat of the current map view."""
    try:
        box = [float(x) for x in bbox.split(",")]
        assert len(box) == 4 and all(math.isfinite(v) for v in box)
    except (ValueError, AssertionError):
        raise HTTPException(400, "bbox must be minLon,minLat,maxLon,maxLat")
    if name == "population":   # census tracts, downloaded for the view on demand
        return spatial.population_overlay(box)
    if name not in ("water_stress", "climate_risk", "wildlife_areas"):
        raise HTTPException(404, "Unknown overlay")
    return spatial.overlay_geojson(name, box)


@app.get("/alerts")
def get_alerts():
    return alerts.list_alerts()


class VoiceRequest(BaseModel):
    text: str = Field(max_length=5000)


@app.post("/voice")
def speak(req: VoiceRequest, request: Request):
    rate_limit(request)
    audio = voice.tts(req.text)
    if audio is None:
        raise HTTPException(404, "ElevenLabs not configured (set ELEVENLABS_API_KEY).")
    return Response(audio, media_type="audio/mpeg")


# ---------- Lower-risk spots nearby (added) ----------
from . import alternatives  # noqa: E402


class AltRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    mw: float = Field(gt=0, le=10000)


@app.post("/alternatives")
def find_alternatives(req: AltRequest, request: Request):
    rate_limit(request)
    out = alternatives.find_alternatives(req.lat, req.lon, req.mw)
    if out is None:
        raise HTTPException(400, "Site is outside US coverage.")
    return out
