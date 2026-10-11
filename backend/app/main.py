"""SiteCheck API. Run from backend/:  uvicorn app.main:app"""
import math

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from . import alerts, briefs, db, estimates, rules, spatial, voice  # noqa: E402

app = FastAPI(title="SiteCheck")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    db.init_db()
    spatial.ensure_region()   # counties (downloads once, then cached)


class ScreenRequest(BaseModel):
    lat: float
    lon: float
    mw: float
    name: str = ""


def run_screen(lat, lon, mw, name=""):
    state, county, findings = spatial.screen_point(lat, lon)
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
def screen(req: ScreenRequest):
    return run_screen(req.lat, req.lon, req.mw, req.name)


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
    if name not in ("water_stress", "climate_risk", "wildlife_areas"):
        raise HTTPException(404, "Unknown overlay")
    return spatial.overlay_geojson(name, [float(x) for x in bbox.split(",")])


@app.get("/alerts")
def get_alerts():
    return alerts.list_alerts()


class VoiceRequest(BaseModel):
    text: str


@app.post("/voice")
def speak(req: VoiceRequest):
    audio = voice.tts(req.text)
    if audio is None:
        raise HTTPException(404, "ElevenLabs not configured (set ELEVENLABS_API_KEY).")
    return Response(audio, media_type="audio/mpeg")


# ---------- Lower-risk spots nearby (added) ----------
from . import alternatives  # noqa: E402


class AltRequest(BaseModel):
    lat: float
    lon: float
    mw: float


@app.post("/alternatives")
def find_alternatives(req: AltRequest):
    out = alternatives.find_alternatives(req.lat, req.lon, req.mw)
    if out is None:
        raise HTTPException(400, "Site is outside US coverage.")
    return out
