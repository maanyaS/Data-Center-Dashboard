# Before the Build

See what's on the land before a data center is built. Drop a pin anywhere in the US, enter a size in MW, and get:

- **Findings:** wetlands, flood zones, protected land, critical habitat, power lines and substations, with distances
- **Likely permit triggers:** each with a citation and delay-risk level
- **Estimates:** power, water, CO₂ and electricity cost as ranges
- **Carbon impact score (0–10):** how heavy the site's footprint is (emissions size + local grid), with real-world scale and ways to offset or restore it
- **Lower-risk spots nearby:** same rules, side-by-side comparison
- **A plain-language brief:** key facts, what residents can do, what developers should check. Every bullet cites its source.
- **Audio:** listen to either brief (ElevenLabs)

> **Screening-level only.** Not a site survey. Does not predict permit outcomes. Anything not checked is marked "unknown".

Built at HackRU Fall 2026.

## Features

- **Project map:** about 1,700 known and proposed data centers (FracTracker, SJ Climate News NJ list, NYISO grid queue). Click one to screen it.
- **Search:** project names, addresses, towns, or `lat, lon`. Or click or drag a pin anywhere.
- **Try an example:** one-click demo sites on the start screen.
- **Search radius 5–100 km:** exact distances within 5 km. Beyond that, each map server is asked how far away the nearest feature is (10 / 25 / 50 / 100 km bands).
- **State rules:** federal layers everywhere, plus NJ (wetlands, Green Acres, Highlands, Pinelands, CAFRA), NY (wetlands, SEQRA, parkland) and DE (wetlands).
- **National overlays:** water stress, climate risk, population density, wildlife refuges. Loaded once for the whole US.
- **NYISO alerts:** new data center requests in the NY grid queue, screened automatically.
- **Light / dark theme**, full screen and map-only views.
- **Accessibility:** keyboard navigation, screen-reader labels, WCAG AA contrast in both themes, reduced motion, audio briefs.

## How it works

1. **Spatial check** (`backend/app/spatial.py`): downloads each layer for an ~8 km box around the pin from public ArcGIS servers, in parallel, and caches it. Distances use EPSG:5070 (equal-area, meters).
2. **Rules** (`backend/rules.yaml`): plain if-then rules map findings to permit triggers. Each rule needs a citation.
3. **Estimates** (`backend/app/estimates.py`): MW to power/water ranges (LBNL 2024), CO₂ from the local EPA eGRID subregion, cost from EIA state prices.
4. **Brief** (`backend/app/briefs.py`): Gemini writes three bullet lists from the structured results only. A validator rejects any bullet without a valid tag (`[F1]`, `[R2]`, `[EST]`…) and retries. If the model fails, a template brief is used.
5. **Voice** (`backend/app/voice.py`): ElevenLabs Flash model, made only when you press play, cached so replays are free.

## Tech stack

| Part | Tools |
|---|---|
| Frontend | React, Vite, Tailwind CSS 4, MapLibre GL |
| Backend | Python, FastAPI, Shapely, PyProj |
| Database | SQLite schema on Turso (local SQLite file if Turso isn't set) |
| AI | Google Gemini (OpenAI-compatible API), ElevenLabs TTS |
| Hosting | Render (API), GitHub Pages (site) |

## Data sources

FEMA National Flood Hazard Layer · USFWS National Wetlands Inventory · USFWS critical habitat · USGS PAD-US · NJDEP, NYSDEC, DNREC state layers · HIFLD transmission lines and substations · US Census 2020 (TIGERweb) · WRI Aqueduct 4.0 · FEMA National Risk Index · EPA eGRID · EIA · LBNL 2024 Data Center Energy Report · FracTracker Alliance · NYISO interconnection queue

## Run locally

Backend (Python 3.12+):

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in keys (all optional)
uvicorn app.main:app --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173, proxies /api to :8000
```

The database is created on first start from `backend/seed.yaml`. National layers download once (a few minutes); site layers download the first time an area is screened.

### Environment variables (`backend/.env`)

| Variable | Purpose |
|---|---|
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | Gemini for briefs. Without a key, template briefs are used. |
| `ELEVENLABS_API_KEY` | Audio briefs. Free plan works with the default voices. |
| `ELEVENLABS_VOICE_ID`, `ELEVENLABS_DEV_VOICE_ID` | Optional. Community voice (default Sarah) and developer voice (default George). |
| `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` | Hosted database. Without them, a local `backend/data/sitecheck.db` is used. |
| `ALLOWED_ORIGINS` | Sites allowed to call the API (comma-separated). |
| `RATE_LIMIT_PER_MIN` | Screenings per visitor per minute (default 10). |

Never commit `.env`. To enable the pre-commit secret check: `git config core.hooksPath .githooks`.

## Scripts (`backend/`)

| Command | What it does |
|---|---|
| `python -m scripts.import_fractracker` | Import the FracTracker US data center list |
| `python -m scripts.import_projects` | Load and geocode `projects.csv` |
| `python -m scripts.check_queue <queue.xlsx>` | Diff the NYISO queue and create alerts |
| `python -m scripts.prepare_data` | Pre-cache areas around planned projects |
| `python -m scripts.push_to_turso` | Copy the local database to Turso |
| `python -m scripts.slim_db` / `reset_db` | Shrink or rebuild the database |

## API

| Endpoint | Purpose |
|---|---|
| `POST /screen` `{lat, lon, mw, name?, population?, radius_km?}` | Findings, triggers, estimates, rings |
| `POST /briefs/{screening_id}` | Writes the brief for a saved screening |
| `POST /alternatives` `{lat, lon, mw, radius_km?}` | Lower-risk spots nearby |
| `POST /voice` `{text, voice: community or developer}` | MP3 of the brief |
| `GET /projects`, `/alerts`, `/overlay/{name}` | Map pins, NYISO alerts, national overlays |

## Rules format

```yaml
- id: R1
  layers: [nwi_wetlands]
  buffers: [site]
  states: ["*"]
  trigger: Likely Clean Water Act Section 404 permit review
  citation: 33 U.S.C. § 1344
  delay_risk: high
```

## Limitations

- Public layers can be coarse or outdated. A server that doesn't answer shows as "unknown".
- Triggers are likely, not certain. The tool can't see zoning, ownership, buildings or grid capacity.
- Power, water and CO₂ are ranges, not facility-specific values.
- Lower-risk spots are areas to look at, not recommended sites.

### Notes
vercel.json is unused; the frontend deploys from frontend/ and the API runs on Render
