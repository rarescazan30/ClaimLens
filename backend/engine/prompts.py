"""The two LLM roles of the loop, kept apart on purpose.

Orchestrator: turns a claim into testable hypotheses and assigns agents.
Judge: sees only hypotheses and evidence (never the Orchestrator's reasoning), marks each hypothesis and asks
at most two narrow follow-up questions. Neither role produces a score or a decision.
"""
from __future__ import annotations

import json

from engine.graph import JudgeOut
from engine.llm import llm_json
from engine.models import Evidence, Hypothesis, RuleFlag, ScoreResult
from engine.thresholds import AGENTS_FOR, ALL_AGENTS, THRESHOLD_TEXT

AGENT_SKILLS = {
    "meteo": "date meteo istorice la adresă: precipitații 24/72 h, rafale. La cerere: serie orară.",
    "satellite": "harta Copernicus a zonei inundate: casa în/în afara poligonului, distanța până la margine.",
    "risk_zones": "distanța până la cea mai apropiată apă. La cerere: diferența de altitudine dintre casă și "
                  "marginea zonei inundate.",
    "photo_forensics": "metadate EXIF, copii în alte dosare, verificare vizuală. La cerere: căutare pe web a "
                       "copiilor fotografiilor, cu data primei publicări.",
    "street_view": "imagine stradală dinaintea evenimentului și data ei. La cerere: comparație vizuală cu "
                   "fotografiile clientului (daună preexistentă).",
    "news": "relatări de presă independente despre eveniment în localitate.",
}

PLAN_SYSTEM = """Ești Orchestratorul unei investigații de daune pentru asigurări de locuințe.
Scrii 3–5 ipoteze TESTABILE, în română, fiecare verificabilă cu date publice, și alegi agenții care le verifică.
Nu evaluezi dosarul și nu tragi concluzii. Nu decizi nimic: decizia aparține evaluatorului uman.
Format JSON: {"hypotheses": [{"id": "H1", "text": "...", "critical": true, "agents": ["meteo"]}]}"""

JUDGE_SYSTEM = """Ești Judge-ul unei investigații de daune. Ești separat de cel care a făcut planul.
Primești ipotezele și dovezile agenților. Sarcina ta:
1. Marchează fiecare ipoteză: "confirmed", "refuted", "inconclusive" sau "conflicting".
   Folosește "conflicting" când dovezile se contrazic între ele SAU contrazic ce declară clientul în dosar
   (de exemplu: casa e în afara zonei inundate, dar clientul declară apă în casă).
2. Scrie tensiunile în cuvinte simple, în română, câte o propoziție.
3. Dacă există un gol sau un conflict pe care un agent îl poate lămuri cu o verificare „la cerere”, cere
   redispatch: cel mult 2 agenți, fiecare cu O întrebare îngustă și concretă. Altfel "stop".
Reguli: un gol de date NU înseamnă fraudă. Nu calculezi scoruri. Nu recomanzi respingerea: decide omul.
Format JSON: {"marks": {"H1": "confirmed"}, "tensions": ["..."], "action": "stop" | "redispatch",
"redispatch": [{"agent": "risk_zones", "question": "..."}]}"""


def _claim_text(claim: dict, policy: dict) -> str:
    keep = ("damage_type", "event_date", "notified_at", "address", "description", "amount_claimed")
    c = {k: claim.get(k) for k in keep} | {"photo_count": len(claim.get("photos") or [])}
    p = {k: policy.get(k) for k in ("product", "valid_from", "valid_to", "covered_risks", "sum_insured")}
    return json.dumps({"claim": c, "policy": p}, ensure_ascii=False)


def _skills(agents: list[str]) -> str:
    return "\n".join(f"- {a}: {AGENT_SKILLS[a]}" for a in agents)


async def plan_hypotheses(claim: dict, policy: dict, flags: list[RuleFlag]) -> list[Hypothesis]:
    kind = claim.get("damage_type")
    allowed = AGENTS_FOR.get(kind, ALL_AGENTS)
    user = (f"Dosar:\n{_claim_text(claim, policy)}\n\n"
            f"Pragul pentru acest tip de daună: {THRESHOLD_TEXT.get(kind, 'nedefinit')}. Scrie pragul în ipoteza meteo.\n"
            f"Reguli de poliță eșuate: {[f.reason for f in flags if not f.passed] or 'niciuna'}\n\n"
            f"Agenți disponibili (folosește doar aceste nume):\n{_skills(allowed)}\n\n"
            "Fiecare agent disponibil trebuie să apară la cel puțin o ipoteză. Include o ipoteză despre "
            "autenticitatea fotografiilor și una despre consistența dintre ce declară clientul și expunerea reală.")
    out = await llm_json(PLAN_SYSTEM, user, model="strong")
    hyps: list[Hypothesis] = []
    for i, h in enumerate(out.get("hypotheses") or [], 1):
        agents = [a for a in h.get("agents") or [] if a in allowed]
        if agents and h.get("text"):
            hyps.append(Hypothesis(id=str(h.get("id") or f"H{i}"), text=str(h["text"]),
                                   critical=bool(h.get("critical", True)), agents=agents))
    return hyps[:5]


def _evidence_text(evidence: list[Evidence]) -> str:
    rows = []
    for e in evidence:
        rows.append({"agent": e.agent, "round": e.round, "hypothesis": e.hypothesis, "verdict": e.verdict,
                     "strength": e.strength, "data_quality": e.data_quality,
                     "findings": [{"metric": f.metric, "value": f.value, "unit": f.unit, "source": f.source}
                                  for f in e.findings],
                     "gaps": e.gaps, "suggested_followup": e.suggested_followup})
    return json.dumps(rows, ensure_ascii=False)


async def judge_round(hypotheses: list[Hypothesis], evidence: list[Evidence], score: ScoreResult, round: int,
                      question: str | None = None, claim_summary: str | None = None) -> JudgeOut:
    agents = sorted({a for h in hypotheses for a in h.agents}) or ALL_AGENTS
    user = (f"Runda {round}.\n"
            + (f"Ce declară clientul: {claim_summary}\n" if claim_summary else "")
            + f"Ipoteze:\n{json.dumps([h.model_dump() for h in hypotheses], ensure_ascii=False)}\n\n"
            f"Dovezi:\n{_evidence_text(evidence)}\n\n"
            f"Ce poate verifica fiecare agent:\n{_skills([a for a in agents if a in AGENT_SKILLS])}\n")
    if question:
        user += (f"\nEvaluatorul uman întreabă: „{question}”. Alege UN agent care poate răspunde și trimite-i "
                 "întrebarea, reformulată îngust. action = \"redispatch\".")
    try:
        out = await llm_json(JUDGE_SYSTEM, user, model="strong")
    except Exception:
        return JudgeOut(tensions=["judge unavailable"], action="stop")
    valid = ("confirmed", "refuted", "inconclusive", "conflicting")
    ids = {h.id for h in hypotheses}
    return JudgeOut(
        marks={k: v for k, v in (out.get("marks") or {}).items() if k in ids and v in valid},
        tensions=[str(t) for t in out.get("tensions") or []][:4],
        action="redispatch" if out.get("action") == "redispatch" else "stop",
        redispatch=[r for r in out.get("redispatch") or [] if isinstance(r, dict)])
