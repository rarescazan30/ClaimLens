import pytest

from app.db import Store
from engine.models import Evidence, Finding, TraceStep, ScoreResult


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    s.create_schema()
    s.upsert_policy({"id": "P-1", "holder_name": "Ion Test", "address": "Str. X 1", "lat": 45.6, "lon": 27.8,
                     "valid_from": "2024-01-01", "valid_to": "2024-12-31", "waiting_days": 0,
                     "covered_risks": ["flood"], "sum_insured": 100000, "product": "PAD"})
    s.upsert_claim({"id": "C-1", "policy_id": "P-1", "damage_type": "flood", "event_date": "2024-09-14",
                    "notified_at": "2024-09-20", "address": "Str. X 1", "lat": 45.6, "lon": 27.8,
                    "description": "apa in casa", "amount_claimed": 20000, "photos": []})
    return s


def ev(**kw):
    base = dict(agent="meteo", round=1, hypothesis="h", verdict="supports", strength=0.8, data_quality=0.6,
                findings=[Finding(metric="m", value=1, unit="mm", source="s", url=None, spatial_res_km=9,
                                  retrieved_at="2026-11-13T21:40Z")],
                reasoning_steps=["a"], gaps=[], suggested_followup=None)
    base.update(kw)
    return Evidence(**base)


def test_evidence_round_trips(store):
    e = ev()
    store.for_claim("C-1").evidence(e)
    assert store.evidence_for("C-1") == [e]


def test_rejected_evidence_is_hidden_by_default(store):
    eid = store.for_claim("C-1").evidence(ev())
    store.reject_evidence(eid)
    assert store.evidence_for("C-1") == []
    assert len(store.evidence_for("C-1", include_rejected=True)) == 1


def test_trace_round_trips_in_order(store):
    sink = store.for_claim("C-1")
    for n in (1, 2):
        sink.trace(TraceStep(case_id="C-1", step_id=f"r1.meteo.{n}", parent="r1.dispatch", actor="agent:meteo",
                             type="tool_call", summary="x", inputs={}, outputs={}, sources=[], status="done",
                             started_at="t", ended_at="t"))
    assert [t.step_id for t in store.trace_for("C-1")] == ["r1.meteo.1", "r1.meteo.2"]


def test_reset_claim_clears_run_state(store):
    sink = store.for_claim("C-1")
    sink.evidence(ev())
    sink.score(ScoreResult(score=72.3, band="likely", recommendation="standard_review", contributions=[], gates=[]), 1)
    store.set_status("C-1", "awaiting_decision")
    store.reset_claim("C-1")
    c = store.get_claim("C-1")
    assert store.evidence_for("C-1") == [] and store.trace_for("C-1") == []
    assert c["score"] is None and c["status"] == "received"


def test_score_is_saved_on_claim(store):
    store.for_claim("C-1").score(
        ScoreResult(score=72.3, band="likely", recommendation="standard_review", contributions=[], gates=[]), 1)
    c = store.get_claim("C-1")
    assert (c["score"], c["band"], c["recommendation"]) == (72.3, "likely", "standard_review")


def test_seed_is_idempotent(store, tmp_path):
    from app.seed import seed
    seed(store, cases_dir=tmp_path)
    seed(store, cases_dir=tmp_path)
    assert store.weight_config("flood").weights["satellite"] == 2.5
    assert store.weight_config("storm").weights["satellite"] == 0
