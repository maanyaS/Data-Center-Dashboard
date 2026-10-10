"""SiteCheck API. Run from backend/:  uvicorn app.main:app --reload"""
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


def run_screen(lat, lon, mw):
    state, county, findings = spatial.screen_point(lat, lon)
    if state is None:
        raise HTTPException(400, "Site is outside New Jersey / New York coverage.")
    triggers = rules.evaluate(findings, state, mw)
    est = estimates.estimate(mw)
    result = {
        "site": {"lat": lat, "lon": lon, "mw": mw, "state": state, "county": county},
        "findings": findings,
        "triggers": triggers,
        "estimates": est,
        "briefs": briefs.write_briefs(findings, triggers, est),
        "rings": spatial.ring_geojson(lat, lon),
    }
    db.save_screening(lat, lon, mw, result)
    return result


@app.post("/screen")
def screen(req: ScreenRequest):
    return run_screen(req.lat, req.lon, req.mw)


@app.get("/demo-sites")
def demo_sites():
    return db.rows("SELECT * FROM demo_sites ORDER BY id")


@app.get("/layers")
def layers():
    return db.get_layers("site")


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
