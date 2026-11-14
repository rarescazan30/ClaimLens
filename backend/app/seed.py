"""Load demo cases, weight profiles and stored event footprints. Safe to run at every startup.

A case file is either the old format (`{"policy": {...}, "claim": {...}}`) or points to the claim's two PDFs:
`{"documents": {"claim_form": "C-1042/claim_form.pdf", "policy": "C-1042/policy.pdf"}, "claim": {"photos": [...]}}`,
paths under `<cases>/documents/`. The PDFs are only read here (no checks, no geocoding), so the queue shows the
claim before any run; the run itself reads them again from the start.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.db import Store
from engine.documents import read_document, to_claim
from engine.thresholds import DEFAULT_WEIGHTS

DEMO = Path(__file__).resolve().parents[2] / "demo"
CLAIM_COLUMNS = ("id", "policy_id", "damage_type", "event_date", "notified_at", "address", "lat", "lon",
                 "description", "amount_claimed", "photos")


def _from_documents(case: dict, docs_dir: Path) -> tuple[dict, dict]:
    names = case["documents"]

    def read(kind):
        root = docs_dir.resolve()
        path = (docs_dir / str(names.get(kind) or "")).resolve()
        return read_document(path, kind) if root in path.parents else read_document(root / "missing.pdf", kind)
    claim, policy = to_claim(read("claim_form"), read("policy"))
    given = case.get("claim") or {}
    claim = {**{k: v for k, v in claim.items() if k in CLAIM_COLUMNS},
             **{k: v for k, v in given.items() if k in CLAIM_COLUMNS}, "documents": names}
    claim.setdefault("photos", [])
    if policy.get("id"):
        claim.setdefault("policy_id", policy["id"])
    return claim, policy


def seed(store: Store, cases_dir: Path | None = None) -> None:
    for w in DEFAULT_WEIGHTS:
        if store.weight_config(w.damage_type) is None:
            store.save_weight_config(w)
    cases_dir = cases_dir or DEMO / "cases"
    for path in sorted(cases_dir.glob("*.json")):
        case = json.loads(path.read_text())
        if "documents" in case:
            claim, policy = _from_documents(case, cases_dir / "documents")
            if policy.get("id"):
                store.upsert_policy({**(store.get_policy(policy["id"]) or {}), **policy})
            if claim.get("id") and store.get_claim(claim["id"]) is None:
                store.upsert_claim(claim)
            continue
        if "policy" in case:
            store.upsert_policy(case["policy"])
        if "claim" in case and store.get_claim(case["claim"]["id"]) is None:
            store.upsert_claim(case["claim"])
    for path in sorted((cases_dir.parent / "footprints").glob("*.json")) if (cases_dir.parent / "footprints").exists() else []:
        store.save_footprint(json.loads(path.read_text()))
