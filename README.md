# Data Center (working name)

Screening tool for proposed data center sites in New Jersey. Drop a pin, enter planned capacity (MW), and get the environmental constraints near the site, likely review triggers with citations, estimated power and water demand, and two briefs: one for developers and one for the community.

> **Screening-level only.** Not a substitute for a site survey. Does not predict permit decisions.

## Problem

- Communities often learn about data center projects late and can't easily check developer claims against public environmental data.
- Developers hit environmental reviews (wetlands permits, species consultation, floodplain rules) late in the process, causing delays.
- The data exists in public GIS layers but is scattered and hard to query.

## What it does

1. **Spatial check:** intersects the site and 1 km / 5 km buffers with public GIS layers.
2. **Rules engine:** maps each finding to a likely review trigger, with a citation and a delay-risk flag.
3. **Resource estimate:** converts MW to power and water demand ranges from published sources.
4. **Briefs:** an LLM writes a developer brief and a community brief using only the structured findings. Every sentence must cite a finding ID or say "unknown."

## Features

### Existing data center map

The map shows known data center projects so a new site can be compared against what's already nearby.

| Pin color | Source | Notes |
|---|---|---|
| Purple | [FracTracker Alliance](https://www.fractracker.org/data-centers/) US data center database | Exact locations, MW, status. Imported with `python -m scripts.import_fractracker` |
| Purple | `backend/projects.csv` (hand-maintained NJ list) | Edit in Excel. Rows without lat/lon are geocoded by `python -m scripts.import_projects` |
| Orange | NYISO interconnection queue | County center only, marked approximate |

- Hover a pin to see its name and MW. Click it to load the project into the screening form.
- When FracTracker and `projects.csv` list the same site (within ~300 m), the FracTracker entry is kept.
- Pins at the exact same coordinates are fanned out slightly so each one is clickable.

### Search and pin placement

- The search box matches known projects by name or county as you type.
- Press Enter to search US addresses and towns (Geoapify if `VITE_GEOAPIFY_KEY` is set, otherwise OpenStreetMap Nominatim).
- Typing coordinates (`40.7, -74.1`) jumps straight there.
- Place a pin by clicking the map, dragging the "Drag a pin onto the map" chip, or dragging an existing pin to a new spot.

### Map overlays

Toggle in the top-right panel. Only the part of the layer inside the current view is downloaded.

- **Water stress:** WRI Aqueduct 4.0 baseline water stress, 5 levels.
- **Climate risk:** FEMA National Risk Index by county, 5 levels.
- **Wildlife refuges and habitat:** USGS PAD-US. Loads at zoom 6 and closer.

### Expanded screening

The site check now covers the whole US (lower 48, AK, HI, PR) instead of NJ only. Distances are computed in EPSG:5070 (Conus Albers). On top of the federal layers, state layers apply where they exist:

- **NJ:** NJDEP wetlands, open space, Highlands Preservation Area, Pinelands, CAFRA coastal zone
- **NY:** NYSDEC wetlands, NY Protected Areas Database
- **DE:** DNREC wetlands

Context checks added to every screening:

- **Population:** people within 1 km and 5 km. Uses 2020 Census tracts from TIGERweb (`POP100` field); each tract adds its population times the share of its area inside the circle.
- **Power access:** distance to the nearest electric substation and high-voltage transmission line (HIFLD, 69–765 kV). Substations are drawn on the map as circles.
- **Climate:** heat wave, cold wave and drought ratings for the county (FEMA National Risk Index). The county layer's filter is now `RISK_RATNG IS NOT NULL`, so existing databases re-download it once to pick up the new fields.
- **Grid carbon and cost:** CO2 per MWh for the site's EPA eGRID subregion and the state's industrial electricity price, added to the power estimate.

The results panel has a summary row for these: nearest substation, nearest transmission line and people within 1 km.

These are shown as context only. They don't create review triggers or change scores.

### Find a lower-risk spot nearby

After screening a site, **Find a lower-risk spot nearby** (`POST /alternatives`) tests 24 candidate points: 8 directions at 1.0, 1.75 and 2.5 km from the original pin.

- Candidates inside a wetland, flood zone or protected land are skipped.
- Each remaining candidate runs through the same `rules.yaml` rules. Score = 3 per high-risk trigger + 1 per medium.
- The best few appear as numbered pins on the map and in a side-by-side comparison with the original site:
  - a score bar for each spot
  - a table of triggers, people within 1 km, and distance to the nearest substation and transmission line (power distances are colored so closer is better)
  - a button for each candidate that moves the pin there
- Uses only data already cached for the original site: 2.5 km plus the 5 km check radius stays inside the ~8 km area downloaded for the first screening, so no extra downloads.

Code: `backend/app/alternatives.py` (search and scoring), `frontend/src/Alternatives.jsx` (comparison panel), with small additions to `App.jsx`, `MapView.jsx` and `api.js` for the candidate pins. The database schema is unchanged.

Request: `{ "lat": 40.5008, "lon": -74.4474, "mw": 100 }`. Returns `400` if the site is outside US coverage.

The tool can't see zoning, buildings, land ownership or power line capacity. A candidate is a lower environmental-risk area to look at, not a recommended site.

### NYISO queue alerts

The **Alerts** tab lists new data center load requests from the public NYISO interconnection queue.

```bash
# from backend/
python -m scripts.check_queue path/to/NYISO-Interconnection-Queue.xlsx
# demo: treat the last 3 data center rows as new
python -m scripts.check_queue path/to/queue.xlsx --forget 3
```

The script compares the queue to the last saved snapshot. Each new data center row (end use DAT, DAT-AI or DAT-CM) is screened automatically at its county center and saved as an alert. Click an alert to open its results.

### Listen to briefs (ElevenLabs)

The **▶ Listen** button in the Briefs panel reads the selected brief aloud. Citation tags like `[F1]` are removed before the text is sent. Requires `ELEVENLABS_API_KEY` in `backend/.env`; `ELEVENLABS_VOICE_ID` is optional.

### Data caching and deployment

- All data lives in one SQLite file, `backend/data/sitecheck.db`. GIS features are downloaded from ArcGIS REST services the first time an area is screened, then served from the cache.
- `python -m scripts.prepare_data` pre-caches the area around every planned or under-construction project in `projects.csv`.
- `python -m scripts.slim_db` drops the per-site cache and screening history to keep the file under GitHub's 100 MB limit.
- `python -m scripts.reset_db` deletes the database and rebuilds it from `seed.yaml`.
- Deploys to Vercel. The frontend is built from `frontend/`, and `api/index.py` serves the backend under `/api`. On Vercel the database is copied to `/tmp`, so new screenings and newly cached areas don't persist.

## Tech stack

| Layer | Tool |
|---|---|
| Frontend | React + Vite, Tailwind |
| Map | MapLibre GL JS |
| Backend | Python, FastAPI |
| Spatial | geopandas, shapely, pyproj |
| Data storage | NJ-clipped layers as GeoPackage / GeoParquet, loaded at startup |
| Rules | YAML rules file + Python evaluator |
| LLM | Provider-agnostic wrapper, structured JSON output |
| Voice (stretch) | ElevenLabs text-to-speech for the community brief |

## Data sources

| Layer | Source | Priority |
|---|---|---|
| Wetlands | USFWS National Wetlands Inventory (or NJDEP wetlands) | 1 |
| Flood zones | FEMA National Flood Hazard Layer (or NJDEP flood layers) | 1 |
| Protected lands | USGS PAD-US | 1 |
| Critical habitat | USFWS ECOS critical habitat | 2 |
| Water stress | WRI Aqueduct | 2 |
| Regulated facilities | EPA ECHO | 2 |
| Energy / water ranges | LBNL 2024 United States Data Center Energy Usage Report | 1 |

All layers are pre-downloaded and clipped to New Jersey. No live government API calls at runtime.

## Project structure

```
.
├── frontend/              # React app (map, input, results, briefs)
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app, /screen endpoint
│   │   ├── spatial.py     # buffers + layer intersections
│   │   ├── rules.py       # rules evaluator
│   │   ├── estimates.py   # MW -> power/water ranges
│   │   ├── briefs.py      # LLM wrapper + citation validator
│   │   └── voice.py       # ElevenLabs (stretch)
│   ├── rules/rules.yaml   # review-trigger rules
│   └── requirements.txt
├── scripts/
│   └── prepare_data.py    # download, clip to NJ, reproject, save
├── data/                  # processed layers (gitignored)
└── validation/            # known sites + results
```

## Setup

### Data

```bash
cd scripts
python prepare_data.py   # writes processed layers to ../data/
```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Environment variables (`backend/.env`)

```
LLM_PROVIDER=          # e.g. gemini, anthropic, openai
LLM_API_KEY=
ELEVENLABS_API_KEY=    # optional, stretch feature
```

## API

`POST /screen`

Request:

```json
{ "lat": 40.5008, "lon": -74.4474, "mw": 100 }
```

Response (shape):

```json
{
  "findings": [
    { "id": "F1", "layer": "wetlands", "buffer": "on_site", "detail": "...", "source": "..." }
  ],
  "triggers": [
    { "rule_id": "R1", "finding_ids": ["F1"], "trigger": "...", "citation": "...", "delay_risk": "high" }
  ],
  "estimates": { "power_mwh_per_year": [0, 0], "water_gal_per_day": [0, 0], "sources": ["..."] },
  "briefs": { "developer": "...", "community": "..." }
}
```

## Rules format

```yaml
- id: R1
  when: { layer: wetlands, buffer: on_site }
  trigger: Likely Clean Water Act Section 404 permit review
  citation: 33 U.S.C. § 1344
  delay_risk: high
```

Rules are plain if-then statements. Each rule must have a citation.

## Spatial notes

- Reproject to UTM Zone 18N (EPSG:32618) before buffering. Buffering in lat/lon degrees gives wrong distances.
- Reproject results back to EPSG:4326 for the map.

## LLM guardrails

- The LLM only receives structured findings, triggers, and estimates. No raw web content.
- Every sentence in a brief must include a finding ID (e.g. `[F2]`) or the word "unknown."
- `briefs.py` rejects and regenerates output that fails this check.

## Validation

Run 5–10 known data center projects that drew public objections through the tool. For each, record which constraints were raised publicly and whether the tool flagged them. Report hits and misses in `validation/results.md`.

## Limitations

- Public layers are coarse and may be outdated.
- Review triggers are likely, not certain. Some depend on factors the tool can't see (e.g. federal nexus for ESA consultation).
- Power and water figures are ranges, not facility-specific values.
- New Jersey only.

## Stretch goals

1. ElevenLabs audio version of the community brief.
2. Paste a planning-board document, extract applicant claims, and flag contradictions with GIS findings.
