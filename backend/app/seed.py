"""Load demo cases, weight profiles and stored event footprints. Safe to run at every startup."""
from __future__ import annotations

import json
from pathlib import Path

from app.db import Store
from engine.thresholds import DEFAULT_WEIGHTS

DEMO = Path(__file__).resolve().parents[2] / "demo"


def seed(store: Store, cases_dir: Path | None = None) -> None:
    for w in DEFAULT_WEIGHTS:
        if store.weight_config(w.damage_type) is None:
            store.save_weight_config(w)
    cases_dir = cases_dir or DEMO / "cases"
    for path in sorted(cases_dir.glob("*.json")):
        case = json.loads(path.read_text())
        if "policy" in case:
            store.upsert_policy(case["policy"])
        if "claim" in case and store.get_claim(case["claim"]["id"]) is None:
            store.upsert_claim(case["claim"])
    for path in sorted((cases_dir.parent / "footprints").glob("*.json")) if (cases_dir.parent / "footprints").exists() else []:
        store.save_footprint(json.loads(path.read_text()))
