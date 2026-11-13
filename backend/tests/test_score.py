import math

import pytest

from engine.models import Evidence, Finding, RuleFlag, WeightConfig
from engine.score import compute_score

CFG = WeightConfig(damage_type="flood", p0=0.5, weights={"meteo": 2.0, "risk_zones": 2.0, "photo_forensics": 2.0},
                   context_weight=0.5)
OK = [RuleFlag(rule="risk_covered", passed=True, reason="ok")]


def ev(verdict="supports", agent="meteo", round=1, s=0.8, q=0.6, findings=None):
    return Evidence(agent=agent, round=round, hypothesis="h", verdict=verdict, strength=s, data_quality=q,
                    findings=findings or [])


def test_one_supporting_evidence():
    r = compute_score([ev()], CFG, OK)
    assert r.score == pytest.approx(72.3, abs=0.1) and r.band == "likely"


def test_contradicting_evidence_mirrors_it():
    assert compute_score([ev("contradicts")], CFG, OK).score == pytest.approx(27.7, abs=0.1)


def test_inconclusive_evidence_moves_nothing():
    assert compute_score([ev("inconclusive")], CFG, OK).score == pytest.approx(50.0)


def test_only_latest_round_per_agent_counts():
    r = compute_score([ev("supports", round=1), ev("contradicts", round=2)], CFG, OK)
    assert r.score == pytest.approx(27.7, abs=0.1)
    assert [(c.agent, c.round) for c in r.contributions if c.agent == "meteo"] == [("meteo", 2)]


def test_failed_coverage_rule_gates_without_changing_score():
    strong = [ev(s=1, q=1), ev(agent="risk_zones", s=1, q=1), ev(agent="photo_forensics", s=1, q=1)]
    free = compute_score(strong, CFG, OK)
    gated = compute_score(strong, CFG, [RuleFlag(rule="risk_covered", passed=False, reason="Risc neacoperit")])
    assert free.score > 95 and free.recommendation == "fast_track"
    assert gated.score == free.score
    assert gated.recommendation == "standard_review"
    assert [(g.kind, g.reason) for g in gated.gates] == [("coverage", "Risc neacoperit")]


def test_clear_fake_gates_to_antifraud():
    fake = Finding(metric="exact_copy_before_event", value=True, source="Google Vision", url="https://x")
    r = compute_score([ev(s=1, q=1), ev("contradicts", agent="photo_forensics", findings=[fake])], CFG, OK)
    assert r.recommendation == "antifraud_referral" and r.gates[0].kind == "clear_fake"


def test_recommendation_bands():
    hi = compute_score([ev(s=1, q=1), ev(agent="risk_zones", s=1, q=1)], CFG, OK)
    lo = compute_score([ev("contradicts", s=1, q=1)], CFG, OK)
    mid = compute_score([ev(s=0.3, q=0.6)], CFG, OK)
    assert (hi.score >= 85, hi.recommendation) == (True, "fast_track")
    assert (lo.score < 35, lo.recommendation) == (True, "antifraud_referral")
    assert (35 <= mid.score < 85, mid.recommendation) == (True, "standard_review")


def test_contributions_sum_to_the_logit_shift():
    r = compute_score([ev(), ev("contradicts", agent="risk_zones", s=0.5, q=0.5)], CFG, OK, context_term=-0.4)
    p = r.score / 100
    assert sum(c.delta_logit for c in r.contributions) == pytest.approx(math.log(p / (1 - p)), abs=0.01)
    assert any(c.agent == "context" and c.delta_logit == pytest.approx(-0.2) for c in r.contributions)


def test_agent_without_weight_contributes_zero():
    assert compute_score([ev(agent="satellite", s=1, q=1)], CFG, OK).score == pytest.approx(50.0)


def test_no_evidence_is_the_prior():
    r = compute_score([], CFG, OK)
    assert (r.score, r.band, r.recommendation) == (50.0, "uncertain", "standard_review")
