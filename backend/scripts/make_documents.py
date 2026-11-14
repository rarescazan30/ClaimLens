"""Writes the demo PDFs that are not the team's own: one claim per `demo/cases/sources/*.json`.

Each source gives the fields of the claim form and of the policy (names as in CLAIM_FIELDS / POLICY_FIELDS) and
`out`, the folder under `demo/documents/` that receives `claim.pdf` and `policy.pdf`.

    cd backend && .venv/bin/python scripts/make_documents.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.documents import has_unicode_font, write_document  # noqa: E402

DEMO = Path(__file__).resolve().parents[2] / "demo"


def main() -> None:
    if not has_unicode_font():
        sys.exit("No Unicode TrueType font found: the PDFs would lose their diacritics. Not writing them.")
    for src in sorted((DEMO / "cases" / "sources").glob("*.json")):
        case = json.loads(src.read_text())
        out = DEMO / "documents" / case["out"]
        out.mkdir(parents=True, exist_ok=True)
        write_document(case["claim_form"], "claim_form", out / "claim.pdf")
        write_document(case["policy"], "policy", out / "policy.pdf")
        print(f"{src.name} → {out.relative_to(DEMO.parent)}/claim.pdf, policy.pdf")


if __name__ == "__main__":
    main()
