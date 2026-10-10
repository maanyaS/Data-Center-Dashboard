"""Rules engine: findings -> likely review triggers (from rules.yaml)."""
from pathlib import Path

import yaml

RULES_PATH = Path(__file__).resolve().parent.parent / "rules.yaml"


def evaluate(findings, state, mw):
    rules = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
    triggers = []
    for r in rules:
        if state not in r.get("states", [state]) or mw < r.get("min_mw", 0):
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
