"""Deterministic policy checks (factor F1) and context signals (F5). A failed rule flags the case for a human;
it never stops or rejects it."""
from __future__ import annotations

import re
from datetime import date, timedelta

from engine.models import RuleFlag
from engine.thresholds import NOTIFY_DAYS


def _d(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _norm(address) -> str:
    return re.sub(r"[^a-z0-9ăâîșț ]", " ", str(address or "").lower()).split().__str__()


def check_policy(claim: dict, policy: dict) -> list[RuleFlag]:
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

    a, b = _norm(claim.get("address")), _norm(policy.get("address"))
    add("address_match", bool(a != "[]" and a == b), "Adresa coincide cu polița",
        "Adresa din cerere diferă de adresa din poliță")

    if not (event and notified):
        add("notified_in_time", False, "", "Lipsește data notificării")
    else:
        days = (notified - event).days
        add("notified_in_time", 0 <= days <= NOTIFY_DAYS, f"Notificat la {days} zile de la eveniment",
            f"Notificat la {days} zile de la eveniment (termen: {NOTIFY_DAYS} zile)")
    return out


def context_term(claim: dict, policy: dict) -> float:
    """F5: small negative nudge for late notification or a claim above the sum insured. In [-1, 0]."""
    term = 0.0
    event, notified = _d(claim.get("event_date")), _d(claim.get("notified_at"))
    if event and notified and (notified - event).days > 30:
        term -= 0.5
    amount, insured = claim.get("amount_claimed"), policy.get("sum_insured")
    if amount and insured and amount > insured:
        term -= 0.5
    return max(term, -1.0)
