"""Site brief as three short bullet lists (key facts / community actions / developer), written ONLY from structured results.

Every bullet must cite a tag: a finding [F1], a trigger [R1], the estimate [EST], a nearby spot [ALT1],
a community action [ACT1], or say "unknown". The validator enforces this; on failure we retry, then fall back
to a template brief (always valid, works with no API key).

LLM: Gemini by default, via its OpenAI-compatible API (any compatible provider works). Set in backend/.env:
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
"""
import json
import os
import re
import time

import requests

TAG = re.compile(r"\[(F\d+|R\d+|EST|ALT\d+|ACT\d+)\]")

# Things residents can do. General civic steps (not facts about the site), so the LLM may suggest them.
COMMUNITY_ACTIONS = [
    {"id": "ACT1", "action": "Ask your town or county planning/zoning board when the site plan or zoning hearing "
                             "for this project is scheduled; those hearings are open to the public and take comments."},
    {"id": "ACT2", "action": "For each state or federal review listed, contact the agency named in its citation, "
                             "ask to be put on the public notice list, and send written comments during the comment period."},
    {"id": "ACT3", "action": "Ask the developer where the water will come from, how much is used in summer, "
                             "and whether cooling is closed-loop or air-cooled."},
    {"id": "ACT4", "action": "Ask the developer and the electric utility about backup diesel generators, noise, "
                             "new power lines, and whether local electricity rates could be affected."},
    {"id": "ACT5", "action": "Share this screening with your local environmental commission, watershed group, "
                             "or neighbors so questions can be raised early."},
]


def fmt_range(r, unit):
    return f"{r['low']:,}-{r['high']:,} {unit}"


def alt_facts(alts):
    """Nearby lower-risk spots (from alternatives.py) as ALT1.. facts."""
    if not alts or not alts.get("candidates"):
        return []
    o = alts["origin"]
    return [{"id": f"ALT{i}", "where": f"{c['label']} of the pin", "lat": c["lat"], "lon": c["lon"],
             "score": c["score"], "original_site_score": o["score"],
             "high_risk_triggers": c["high"], "original_high_risk_triggers": o["high"],
             "triggers_avoided": sorted({t["trigger"] for t in o["triggers"]} - {t["trigger"] for t in c["triggers"]}),
             "people_within_1km": c.get("people_1km"), "original_people_within_1km": o.get("people_1km")}
            for i, c in enumerate(alts["candidates"], 1)]


def facts(findings, triggers, estimates, alts=None):
    """The only information the LLM is allowed to use."""
    return {
        "nearby_lower_risk_spots": alt_facts(alts),
        "community_actions": COMMUNITY_ACTIONS,
        "findings": [{"id": f["id"], "layer": f["title"], "buffer": f["buffer"], "detail": f["detail"],
                      **({"distance_m": f["distance_m"]} if f.get("distance_m") is not None else {}),
                      **({"population": f["population"]} if f.get("population") else {})}
                     for f in findings],
        "triggers": [{"id": t["rule_id"], "trigger": t["trigger"], "citation": t["citation"],
                      "delay_risk": t["delay_risk"], "finding_ids": t["finding_ids"]} for t in triggers],
        "estimate": {"id": "EST",
                     "power": fmt_range(estimates["power_mwh_per_year"], "MWh/year"),
                     "water": fmt_range(estimates["water_gal_per_day"], "gallons/day"),
                     **({"co2": fmt_range(estimates["co2_tons_per_year"], "tons CO2/year"),
                         "power_cost": fmt_range(estimates["power_cost_usd_per_year"], "USD/year"),
                         "grid_region": estimates["grid"]["egrid_name"]} if "grid" in estimates else {})},
    }


SECTIONS = ("facts", "community", "developer")
MAX_CHARS = 220   # one short sentence per bullet
RISK_ORDER = {"high": 0, "medium": 1, "low": 2}


def validate(bullets, valid_tags):
    """Return list of problems (empty = OK). Every bullet: short, and cites a tag or says unknown."""
    if not isinstance(bullets, list) or not bullets:
        return ["Section must be a non-empty list of bullets"]
    problems = []
    for b in bullets:
        tags = TAG.findall(b)
        if not tags and "unknown" not in b.lower():
            problems.append(f"No citation: {b[:80]}")
        if len(b) > MAX_CHARS:
            problems.append(f"Too long (max {MAX_CHARS} chars): {b[:80]}")
        problems += [f"Unknown tag [{t}] in: {b[:80]}" for t in tags if t not in valid_tags]
    return problems


def agencies(triggers):
    return ", ".join(dict.fromkeys(t["citation"].split(" ")[0] for t in triggers)) or "the permitting agencies"


def template_briefs(findings, triggers, estimates, alts=None):
    trig = sorted(triggers, key=lambda t: RISK_ORDER.get(t["delay_risk"], 3))
    near = sorted((f for f in findings if f["buffer"] in ("site", "1km")), key=lambda f: f.get("distance_m") or 0)
    est = f"Needs {fmt_range(estimates['water_gal_per_day'], 'gal/day')} of water"
    if "grid" in estimates:
        est += f" and emits {fmt_range(estimates['co2_tons_per_year'], 't CO2/yr')}"
    facts_ = [f"{f['detail'].rstrip('.')} [{f['id']}]." for f in near[:4]] + [est + " [EST]."]
    facts_ += [f"{len(trig)} likely reviews, {sum(t['delay_risk'] == 'high' for t in trig)} high delay risk [{trig[0]['rule_id']}]."] if trig else []
    community = [f"{COMMUNITY_ACTIONS[0]['action']} [ACT1]"]
    if trig:
        community.append(f"Ask {agencies(trig[:3])} to add you to the notice list for: "
                         f"{trig[0]['trigger'].rstrip('.')} [ACT2] [{trig[0]['rule_id']}].")
    community.append(f"{COMMUNITY_ACTIONS[2]['action']} [ACT3] [EST]")
    developer = [f"{t['trigger'].rstrip('.')} - {t['delay_risk']} delay risk [{t['rule_id']}]." for t in trig[:4]]
    developer += [f"Power cost about {fmt_range(estimates['power_cost_usd_per_year'], 'USD/yr')} [EST]."] if "grid" in estimates else []
    developer += [f"Consider {a['where']}: score {a['score']} vs {a['original_site_score']}, avoids "
                  f"{len(a['triggers_avoided'])} review(s); still needs zoning and land checks [{a['id']}]."
                  for a in alt_facts(alts)[:1]]
    return {"facts": facts_, "community": community, "developer": developer, "source": "template"}


def call_llm(prompt):
    base = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
    r = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {os.getenv('LLM_API_KEY')}"},
        json={"model": os.getenv("LLM_MODEL", "gemini-3.1-flash-lite"), "temperature": 0.2,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=25,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    return json.loads(re.search(r"\{.*\}", text, re.S).group(0))


PROMPT = """Write a short, scannable brief about a proposed data center site as three lists of bullets.
Use ONLY the facts in the JSON below. Never predict whether permits will be approved.
Rules for EVERY bullet: one short sentence (max 25 words), plain English, ends with its source tag(s)
([F1], [R1], [EST], [ALT1], [ACT1]) or contains the word "unknown". Never repeat a fact in two bullets or two lists.
Put the most important items first (high delay risk, things ON the site, closest distances, big numbers).
- "facts" (4-6 bullets): the key facts only: what is on/near the land with distances, people nearby,
  water and CO2 numbers, how many reviews and how many are high risk.
- "community" (3-4 bullets): actions residents can take to question or oppose the project, from
  "community_actions", each naming the specific agency/permit/hearing it applies to. Start each with a verb.
- "developer" (3-5 bullets): high-risk reviews with the agency and why, power cost, what to check next.
  If "nearby_lower_risk_spots" is not empty, the last bullet names the best spot (direction + distance),
  its score vs the original, and what it avoids, tagged [ALT#].
Reply with JSON only: {{"facts": ["..."], "community": ["..."], "developer": ["..."]}}

FACTS:
{facts}
{feedback}"""


def write_briefs(findings, triggers, estimates, alts=None):
    if not os.getenv("LLM_API_KEY"):
        return template_briefs(findings, triggers, estimates, alts)
    valid = ({f["id"] for f in findings} | {t["rule_id"] for t in triggers} | {"EST"}
             | {a["id"] for a in alt_facts(alts)} | {a["id"] for a in COMMUNITY_ACTIONS})
    feedback = ""
    for _ in range(3):
        try:
            out = call_llm(PROMPT.format(feedback=feedback,
                                         facts=json.dumps(facts(findings, triggers, estimates, alts), indent=1)))
            problems = [p for k in SECTIONS for p in validate(out.get(k), valid)]
        except Exception as e:   # 503 overloaded -> wait and retry; 429 quota / timeout -> use template now
            print(f"[briefs] LLM error: {e}")
            if "429" in str(e) or "timed out" in str(e).lower():
                break
            time.sleep(2)
            continue
        if not problems:
            return {**{k: out[k] for k in SECTIONS}, "source": "llm"}
        feedback = "Your last answer was rejected. Fix these bullets:\n" + "\n".join(problems)
    return template_briefs(findings, triggers, estimates, alts)
