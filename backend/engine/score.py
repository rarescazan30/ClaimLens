"""Claim plausibility score. Plain arithmetic, no LLM:  logit(P) = logit(P0) + Σ w·s·q·d  (docs/contracts.md).

Gates (coverage rules, clear fakes) never change the number. They only force the recommendation
towards a human: 'standard_review' or 'antifraud_referral'. Nothing is ever rejected here.
"""
from __future__ import annotations

import math

from engine.models import Contribution, Evidence, Flag, Gate, RuleFlag, ScoreResult, WeightConfig

DIRECTION = {"supports": 1, "contradicts": -1, "inconclusive": 0}
CLEAR_FAKE_METRIC = "exact_copy_before_event"
CLIENT_FLAG_STEPS = ("documents", "client")
CLIENT_FLAG_COST = 0.25  # logit per flag
CLIENT_FLAG_MAX_COUNT = 4  # total cap: -1.0


def band_of(score: float) -> str:
    if score >= 85:
        return "very_likely"
    if score >= 65:
        return "likely"
    if score >= 35:
        return "uncertain"
    return "unlikely"


def latest_per_agent(evidence: list[Evidence]) -> list[Evidence]:
    latest: dict[str, Evidence] = {}
    for e in evidence:
        if e.agent not in latest or e.round >= latest[e.agent].round:
            latest[e.agent] = e
    return list(latest.values())


def compute_score(evidence: list[Evidence], cfg: WeightConfig, flags: list[RuleFlag],
                  context_term: float = 0.0, data_flags: list[Flag] | None = None) -> ScoreResult:
    logit = math.log(cfg.p0 / (1 - cfg.p0))
    contributions: list[Contribution] = []
    for e in latest_per_agent(evidence):
        delta = cfg.weights.get(e.agent, 0) * e.strength * e.data_quality * DIRECTION[e.verdict]
        contributions.append(Contribution(agent=e.agent, round=e.round, delta_logit=round(delta, 4)))
        logit += delta
    ctx = cfg.context_weight * context_term
    contributions.append(Contribution(agent="context", round=0, delta_logit=round(ctx, 4)))
    logit += ctx
    charged = 0  # counted in whole flags, so four give exactly -1.0 and the rest exactly 0.0
    for f in data_flags or []:
        if f.step not in CLIENT_FLAG_STEPS:
            continue
        delta = -CLIENT_FLAG_COST if charged < CLIENT_FLAG_MAX_COUNT else 0.0
        charged += 1
        contributions.append(Contribution(agent="client", round=0, delta_logit=delta, reason=f.reason))
        logit += delta
    score = round(100 / (1 + math.exp(-logit)), 1)

    gates = [Gate(kind="coverage", reason=f.reason) for f in flags if not f.passed]
    for e in evidence:  # a fake found in any round stays a fake
        for f in e.findings:
            if f.metric == CLEAR_FAKE_METRIC and f.value is True:
                gates.append(Gate(kind="clear_fake",
                                  reason=f"Copie exactă a unei fotografii, publicată înainte de eveniment ({f.url or f.source})"))

    if any(g.kind == "clear_fake" for g in gates) or score < 35:
        recommendation = "antifraud_referral"
    elif any(g.kind == "coverage" for g in gates) or score < 85:
        recommendation = "standard_review"
    else:
        recommendation = "fast_track"
    return ScoreResult(score=score, band=band_of(score), recommendation=recommendation,
                       contributions=contributions, gates=gates)
