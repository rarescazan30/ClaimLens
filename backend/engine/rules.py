"""Deterministic policy checks (factor F1) and context signals (F5). A failed rule flags the case for a human;
it never stops or rejects it."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from engine.geo import haversine_m
from engine.geocode import GeoHit
from engine.models import CheckItem, Flag, RuleFlag, StepResult
from engine.thresholds import NOTIFY_DAYS


def _d(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


_DROP = {"str", "strada", "nr", "jud", "judetul"}
ADDRESS_MATCH_M = 100


def _norm(address) -> str:
    text = unicodedata.normalize("NFD", str(address or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(t for t in re.sub(r"[^a-z0-9 ]", " ", text).split() if t not in _DROP)


def check_policy(claim: dict, policy: dict, claim_point: GeoHit | None = None,
                 policy_point: GeoHit | None = None) -> list[RuleFlag]:
    event, notified = _d(claim.get("event_date")), _d(claim.get("notified_at"))
    start, end = _d(policy.get("valid_from")), _d(policy.get("valid_to"))
    out: list[RuleFlag] = []

    def add(rule: str, passed: bool, ok: str, bad: str) -> None:
        out.append(RuleFlag(rule=rule, passed=bool(passed), reason=ok if passed else bad))

    if not (event and start and end):
        add("policy_active", False, "", "Lipsește data evenimentului sau perioada poliței")
        add("waiting_period", False, "", "Lipsește data evenimentului sau perioada poliței")
    else:
        add("policy_active", start <= event <= end, "Poliță activă la data evenimentului",
            f"Evenimentul ({event}) este în afara perioadei poliței ({start} – {end})")
        wait_end = start + timedelta(days=int(policy.get("waiting_days") or 0))
        add("waiting_period", event >= wait_end, "Perioada de așteptare a trecut",
            f"Eveniment în perioada de așteptare (până la {wait_end})")

    covered = policy.get("covered_risks") or []
    add("risk_covered", claim.get("damage_type") in covered, "Riscul declarat este acoperit",
        f"Riscul „{claim.get('damage_type')}” nu este acoperit de poliță")

    if claim_point and policy_point:
        dist = haversine_m(claim_point.lat, claim_point.lon, policy_point.lat, policy_point.lon)
        add("address_match", dist <= ADDRESS_MATCH_M, f"Adresa daunei coincide cu adresa asigurată (la {dist:.0f} m)",
            f"Adresa daunei este la {dist:.0f} m de adresa asigurată (limită: {ADDRESS_MATCH_M} m)")
    else:
        a, b = _norm(claim.get("address")), _norm(policy.get("address"))
        add("address_match", bool(a and a == b), "Adresa daunei coincide cu adresa asigurată",
            "Adresa din cerere diferă de adresa din poliță")

    if not (event and notified):
        add("notified_in_time", False, "", "Lipsește data notificării")
    else:
        days = (notified - event).days
        add("notified_in_time", 0 <= days <= NOTIFY_DAYS, f"Notificat la {days} zile de la eveniment",
            f"Notificat la {days} zile de la eveniment (termen: {NOTIFY_DAYS} zile)")

    amount, insured = claim.get("amount_claimed"), policy.get("sum_insured")
    if amount is None or insured is None:
        add("amount_within_sum_insured", False, "", "Lipsește suma cerută sau suma asigurată")
    else:
        add("amount_within_sum_insured", amount <= insured,
            f"Suma cerută ({amount}) este în limita sumei asigurate ({insured})",
            f"Suma cerută ({amount}) depășește suma asigurată ({insured})")
    return out


_LABELS = {
    "policy_active": "Poliță activă la data evenimentului",
    "waiting_period": "Perioada de așteptare a trecut",
    "risk_covered": "Riscul declarat este acoperit",
    "address_match": "Adresa daunei coincide cu adresa asigurată",
    "notified_in_time": "Notificat în termen",
    "amount_within_sum_insured": "Suma cerută în limita sumei asigurate",
}


def policy_flags(rules: list[RuleFlag]) -> StepResult:
    items = [CheckItem(id=r.rule, label=_LABELS.get(r.rule, r.rule), status="ok" if r.passed else "fail",
                       reason=r.reason) for r in rules]
    flags = [Flag(step="policy", code=r.rule, severity="fail", reason=r.reason) for r in rules if not r.passed]
    return StepResult(step="policy", items=items, flags=flags)


def context_term(claim: dict, policy: dict) -> float:
    """F5: small negative nudge for late notification (the amount is a policy rule now). In [-1, 0]."""
    event, notified = _d(claim.get("event_date")), _d(claim.get("notified_at"))
    return -0.5 if event and notified and (notified - event).days > 30 else 0.0
