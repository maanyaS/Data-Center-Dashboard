"""Developer + community briefs, written ONLY from structured results.

Every sentence must cite a tag: a finding [F1], a trigger [R1], the estimate [EST],
or say "unknown". The validator enforces this; on failure we retry, then fall back
to a template brief (always valid, works with no API key).

LLM: Gemini by default, via its OpenAI-compatible API (any compatible provider works). Set in backend/.env:
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
"""
import json
import os
import re
import time

import requests

DISCLAIMER = ("This is a screening-level summary from public map data, not a site survey, "
              "and it does not predict permit outcomes; anything not checked is marked unknown.")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
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


def validate(text, valid_tags):
    """Return list of problems (empty = OK)."""
    problems = []
    for s in SENTENCE_SPLIT.split(text.strip()):
        if not s.strip():
            continue
        tags = TAG.findall(s)
        if not tags and "unknown" not in s.lower():
            problems.append(f"No citation: {s[:80]}")
        for t in tags:
            if t not in valid_tags:
                problems.append(f"Unknown tag [{t}] in: {s[:80]}")
    return problems


def template_briefs(findings, triggers, estimates, alts=None):
    est = (f"Estimated demand is {fmt_range(estimates['power_mwh_per_year'], 'MWh per year')} of electricity "
           f"and {fmt_range(estimates['water_gal_per_day'], 'gallons per day')} of on-site water [EST].")
    if "grid" in estimates:
        est += (f" On the {estimates['grid']['egrid_name']} grid that is about "
                f"{fmt_range(estimates['co2_tons_per_year'], 'tons of CO2 per year')} and "
                f"{fmt_range(estimates['power_cost_usd_per_year'], 'US dollars per year')} in electricity [EST].")
    found = [f"{f['detail'].rstrip('.')} [{f['id']}]." if f["buffer"] != "unknown"
             else f"{f['title']}: unknown, not checked [{f['id']}]." for f in findings]
    trig = [f"{t['trigger'].rstrip('.')} ({t['citation']}; delay risk {t['delay_risk']}) [{t['rule_id']}]." for t in triggers]
    if not trig:
        trig = ["No likely review triggers were flagged from the layers checked; layers not checked are unknown."]
    moves = [f"A spot {a['where']} scores {a['score']} instead of {a['original_site_score']} on the same rules "
             f"and avoids: {', '.join(a['triggers_avoided']) or 'no specific trigger, only lower risk'} [{a['id']}]."
             for a in alt_facts(alts)]
    developer = " ".join([DISCLAIMER, *trig, est, *found, *moves])
    community = " ".join([DISCLAIMER, *found, est,
                          *(f"A review that may apply: {t['trigger'].rstrip('.')} [{t['rule_id']}]." for t in triggers),
                          *(f"You can: {a['action']} [{a['id']}]" for a in COMMUNITY_ACTIONS[:3])])
    return {"developer": developer, "community": community, "source": "template"}


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


PROMPT = """You write two short plain-English briefs about a proposed data center site.
Use ONLY the facts in the JSON below. Do not add any other facts.
Every sentence MUST end with a tag citing its source: a finding id like [F1], a trigger id like [R1], or [EST],
or else the sentence must contain the word "unknown". Never predict whether permits will be approved.
No headings, no bullet points. Start each brief with this exact sentence: "{disclaimer}"
- "developer" (6-10 sentences): for the developer, specific and numeric. Give exact distances (meters/km),
  people nearby, power/water/CO2/cost ranges, each review trigger with its delay risk and agency, and what to
  check next. If "nearby_lower_risk_spots" is not empty, end by naming the best spot (direction + distance),
  how its score compares, and which triggers it avoids, cited with its [ALT#] tag; say it still needs zoning
  and land checks. If the list is empty, say no nearby spot scored lower on the layers checked [EST].
- "community" (6-10 sentences): for nearby residents, in simple words. Say what is on/near the land and what
  it means for them, then give 3-4 concrete things they can do, picked from "community_actions" and tied to
  the specific reviews listed (name the agency or permit), each cited with its [ACT#] tag (and the [R#] tag).
Reply with JSON only: {{"developer": "...", "community": "..."}}

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
            out = call_llm(PROMPT.format(disclaimer=DISCLAIMER, feedback=feedback,
                                         facts=json.dumps(facts(findings, triggers, estimates, alts), indent=1)))
            problems = validate(out["developer"], valid) + validate(out["community"], valid)
        except Exception as e:   # 503 overloaded -> wait and retry; 429 quota / timeout -> use template now
            print(f"[briefs] LLM error: {e}")
            if "429" in str(e) or "timed out" in str(e).lower():
                break
            time.sleep(2)
            continue
        if not problems:
            return {"developer": out["developer"], "community": out["community"], "source": "llm"}
        feedback = "Your last answer was rejected. Fix these sentences:\n" + "\n".join(problems)
    return template_briefs(findings, triggers, estimates, alts)
