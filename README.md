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
