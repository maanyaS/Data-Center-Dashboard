"""Rules engine: findings -> likely review triggers (from rules.yaml)."""
from pathlib import Path

import yaml

RULES_PATH = Path(__file__).resolve().parent.parent / "rules.yaml"


def evaluate(findings, state, mw, estimates=None):
    rules = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
    triggers = []
    for r in rules:
        states = r.get("states", ["*"])
        if ("*" not in states and state not in states) or mw < r.get("min_mw", 0):
            continue
        # min_water_gpd: compare to the HIGH end of the on-site water estimate
        water_high = (estimates or {}).get("water_gal_per_day", {}).get("high", 0)
        if "min_water_gpd" in r and water_high < r["min_water_gpd"]:
            continue
        if r.get("always"):
            ids = []
        else:
            ids = [f["id"] for f in findings
                   if f["layer"] in r["layers"] and f["buffer"] in r["buffers"]]
            if not ids:
                continue
        triggers.append({
            "rule_id": r["id"], "finding_ids": ids, "trigger": r["trigger"],
            "citation": r["citation"], "delay_risk": r["delay_risk"],
        })
    return triggers
