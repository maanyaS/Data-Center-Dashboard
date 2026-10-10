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
TAG = re.compile(r"\[(F\d+|R\d+|EST)\]")


def fmt_range(r, unit):
    return f"{r['low']:,}-{r['high']:,} {unit}"


def facts(findings, triggers, estimates):
    """The only information the LLM is allowed to use."""
    return {
        "findings": [{"id": f["id"], "layer": f["title"], "buffer": f["buffer"], "detail": f["detail"]}
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


def template_briefs(findings, triggers, estimates):
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
    developer = " ".join([DISCLAIMER, *trig, est, *found])
    community = " ".join([DISCLAIMER, *found, est,
                          *(f"A review that may apply: {t['trigger'].rstrip('.')} [{t['rule_id']}]." for t in triggers)])
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
No headings, no bullet points, 4-8 sentences each. Start each brief with this exact sentence: "{disclaimer}"
- "developer": for the developer: review triggers, delay risks, what to check next.
- "community": for nearby residents: what is on/near the land, what reviews may apply, in simple words.
Reply with JSON only: {{"developer": "...", "community": "..."}}

FACTS:
{facts}
{feedback}"""


def write_briefs(findings, triggers, estimates):
    if not os.getenv("LLM_API_KEY"):
        return template_briefs(findings, triggers, estimates)
    valid = {f["id"] for f in findings} | {t["rule_id"] for t in triggers} | {"EST"}
    feedback = ""
    for _ in range(3):
        try:
            out = call_llm(PROMPT.format(disclaimer=DISCLAIMER, feedback=feedback,
                                         facts=json.dumps(facts(findings, triggers, estimates), indent=1)))
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
    return template_briefs(findings, triggers, estimates)
