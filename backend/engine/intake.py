"""Helpers for the five intake steps the graph runs before the plan (claim, documents, client, policy, photos).

Plain functions, no sink and no trace: the graph nodes call them and do the reporting.
"""
from __future__ import annotations

from pathlib import Path

from engine.documents import _unreadable, read_document, to_claim
from engine.models import CheckItem, Finding, Flag, ReadDocument, RuleFlag, StepResult
from engine.photos import check_photos

# Claim keys whose value comes from the documents. A key the documents leave empty is dropped, never kept from
# an older copy of the claim. "id" stays the caller's (the API's claim id).
CLAIM_READ_KEYS = ("policy_id", "damage_type", "event_date", "notified_at", "address", "description",
                   "amount_claimed", "declared_photos", "lat", "lon")
POLICY_READ_KEYS = ("id", "holder_name", "address", "valid_from", "valid_to", "waiting_days", "covered_risks",
                    "sum_insured", "product")


def read_documents(documents: dict[str, Path | None]) -> tuple[ReadDocument, ReadDocument]:
    def one(kind):
        path = documents.get(kind)
        return read_document(Path(path), kind) if path is not None else _unreadable(kind)
    return one("claim_form"), one("policy")


def apply_read(claim: dict, policy: dict, claim_doc: ReadDocument, policy_doc: ReadDocument) -> None:
    """Puts the read values into claim and policy, in place (the graph's nodes share these dicts)."""
    read_claim, read_policy = to_claim(claim_doc, policy_doc)
    case_id = claim.get("id") or read_claim.get("id")
    for k in CLAIM_READ_KEYS:
        claim.pop(k, None)
    claim.update({k: v for k, v in read_claim.items() if k != "id"})
    if case_id:
        claim["id"] = case_id
    for k in POLICY_READ_KEYS:
        policy.pop(k, None)
    policy.update(read_policy)


def read_fields(claim: dict) -> dict:
    """What the API stores as the claim's read values (sink.claim_read)."""
    return {k: claim[k] for k in CLAIM_READ_KEYS if k in claim}


def house_of(claim: dict) -> tuple[float, float] | None:
    lat, lon = claim.get("lat"), claim.get("lon")
    return (lat, lon) if lat is not None and lon is not None else None


def photo_step(paths: list[Path], claim: dict, earlier: list[Path]) -> tuple[StepResult, list[Finding] | None]:
    """The photo check, or an info line when there is no event date to compare the capture dates with."""
    if not claim.get("event_date"):
        item = CheckItem(id="photos", label="Verificarea fotografiilor", status="info",
                         reason="Lipsește data evenimentului; datele fotografiilor nu pot fi comparate.")
        return StepResult(step="photos", items=[item]), None
    return check_photos([Path(p) for p in paths], claim["event_date"], house_of(claim), [Path(p) for p in earlier])


def as_flags(items) -> list[Flag]:
    return [Flag.model_validate(f) for f in items or []]


def as_rule_flags(items) -> list[RuleFlag]:
    return [RuleFlag.model_validate(f) for f in items or []]


def step_summary(title: str, result: StepResult) -> str:
    ok = sum(i.status == "ok" for i in result.items)
    n = len(result.flags)
    signals = "niciun semnal" if n == 0 else ("1 semnal" if n == 1 else f"{n} semnale")
    return f"{title}: {ok} din {len(result.items)} verificări în regulă, {signals}"
