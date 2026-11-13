import asyncio
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from engine.graph import JudgeOut
from engine.models import Evidence, Hypothesis
from engine.thresholds import ALL_AGENTS

HYP = [Hypothesis(id="H1", text="ploaie", critical=True, agents=ALL_AGENTS)]
POLICY = {"id": "P-1", "holder_name": "Test", "address": "Str. X 1", "lat": 45.6, "lon": 27.8,
          "valid_from": "2024-01-01", "valid_to": "2024-12-31", "waiting_days": 0, "covered_risks": ["flood"],
          "sum_insured": 100000, "product": "PAD"}
CLAIM = {"policy_id": "P-1", "damage_type": "flood", "event_date": "2024-09-14", "notified_at": "2024-09-16",
         "address": "Str. X 1", "lat": 45.6, "lon": 27.8, "description": "apa", "amount_claimed": 1000}


def engine(delay=0.0, verdicts=None):
    verdicts = verdicts or {}

    def make(name):
        async def run(task, ctx):
            await asyncio.sleep(delay)
            ctx.note("observation", f"{name} gata")
            return Evidence(agent=name, round=task.round, hypothesis="ploaie",
                            verdict=verdicts.get(name, "supports"), strength=0.5, data_quality=0.5)
        return run

    async def planner(c, p, f):
        return HYP

    async def judge(h, e, s, r, question=None):
        if question:
            return JudgeOut(action="redispatch", redispatch=[{"agent": "news", "question": question}])
        return JudgeOut(marks={"H1": "confirmed"}, action="stop")
    return {"agents": {a: make(a) for a in ALL_AGENTS}, "planner": planner, "judge": judge}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app(cases_dir=tmp_path / "nocases")
    app.state.engine_kwargs = engine()
    with TestClient(app) as c:
        app.state.store.upsert_policy(POLICY)
        yield c


def create(client, **over):
    r = client.post("/claims", data={"data": json.dumps({"claim": {**CLAIM, **over}})})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def wait(client, cid, status="awaiting_decision", timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if client.get(f"/claims/{cid}").json()["claim"]["status"] == status:
            return
        time.sleep(0.02)
    raise AssertionError(f"claim never reached {status}")


def events(client, cid):
    out = []
    with client.stream("GET", f"/claims/{cid}/stream") as r:
        name = None
        for line in r.iter_lines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                out.append((name, json.loads(line.split(":", 1)[1])))
    return out


def test_new_claim_is_investigated_and_waits_for_a_human(client):
    cid = create(client)
    wait(client, cid)
    body = client.get(f"/claims/{cid}").json()
    assert body["score"]["score"] > 50 and len(body["evidence"]) == 6
    assert body["claim"]["decision"] is None
    assert [c["id"] for c in client.get("/claims").json()] == [cid]


def test_case_response_has_the_keys_of_the_mock(client):
    cid = create(client)
    wait(client, cid)
    body = client.get(f"/claims/{cid}").json()
    mock = json.loads((Path(__file__).resolve().parents[2] / "demo/mock/claim_fraud.json").read_text())
    assert set(body) == set(mock)
    assert set(mock["claim"]) <= set(body["claim"])
    assert set(mock["evidence"][0]) == set(body["evidence"][0])
    assert set(mock["score"]) == set(body["score"])
    assert body["score_history"] == [{"round": 1, "score": body["score"]["score"], "band": body["score"]["band"]}]


def test_stream_opened_after_the_run_replays_every_step(client):
    cid = create(client)
    wait(client, cid)
    ev = events(client, cid)
    stored = [t["step_id"] for t in client.get(f"/claims/{cid}/trace").json()]
    assert [d["step_id"] for n, d in ev if n == "trace"] == stored and stored[-1] == "final"
    assert ev[-1] == ("status", {"status": "awaiting_decision"})


def test_stream_opened_mid_run_gets_past_then_live_steps_without_duplicates(client):
    client.app.state.engine_kwargs = engine(delay=0.3)
    cid = create(client)
    time.sleep(0.1)
    ids = [d["step_id"] for n, d in events(client, cid) if n == "trace"]
    assert ids[0] == "rules" and ids[-1] == "final" and len(ids) == len(set(ids))


def test_rerun_or_question_during_a_run_is_refused(client):
    client.app.state.engine_kwargs = engine(delay=0.3)
    cid = create(client)
    assert client.post(f"/claims/{cid}/rerun").status_code == 409
    assert client.post(f"/claims/{cid}/question", json={"question": "?"}).status_code == 409
    wait(client, cid)
    assert len(client.get(f"/claims/{cid}").json()["evidence"]) == 6


def test_rerun_clears_and_investigates_again(client):
    cid = create(client)
    wait(client, cid)
    assert client.post(f"/claims/{cid}/rerun").status_code == 200
    wait(client, cid)
    assert len(client.get(f"/claims/{cid}").json()["evidence"]) == 6


def test_decision_rules(client):
    cid = create(client)
    wait(client, cid)
    assert client.post(f"/claims/{cid}/decision", json={"decision": "modify", "outcome": "fast_track"}).status_code == 422
    assert client.post(f"/claims/{cid}/decision", json={"decision": "modify", "outcome": "reject", "reason": "x"}).status_code == 422
    r = client.post(f"/claims/{cid}/decision", json={"decision": "modify", "outcome": "antifraud_referral", "reason": "Vreau verificare"})
    assert r.status_code == 200
    c = client.get(f"/claims/{cid}").json()["claim"]
    assert (c["status"], c["decision"], c["outcome"], c["decision_reason"]) == \
        ("decided", "modify", "antifraud_referral", "Vreau verificare")


def test_approve_takes_the_recommendation_and_needs_no_reason(client):
    cid = create(client)
    wait(client, cid)
    rec = client.get(f"/claims/{cid}").json()["score"]["recommendation"]
    assert client.post(f"/claims/{cid}/decision", json={"decision": "approve"}).status_code == 200
    assert client.get(f"/claims/{cid}").json()["claim"]["outcome"] == rec


def test_rejecting_the_only_contradicting_evidence_raises_the_score(client):
    client.app.state.engine_kwargs = engine(verdicts={"risk_zones": "contradicts"})
    cid = create(client)
    wait(client, cid)
    body = client.get(f"/claims/{cid}").json()
    eid = [e["id"] for e in body["evidence"] if e["agent"] == "risk_zones"][0]
    new = client.post(f"/claims/{cid}/evidence/{eid}/reject").json()
    assert new["score"] > body["score"]["score"]
    after = client.get(f"/claims/{cid}").json()
    assert after["score"]["score"] == new["score"]
    assert [e["rejected_by_adjuster"] for e in after["evidence"] if e["id"] == eid] == [True]
    assert client.post(f"/claims/{cid}/evidence/99999/reject").status_code == 404


def test_question_runs_one_more_round_on_one_agent(client):
    cid = create(client)
    wait(client, cid)
    assert client.post(f"/claims/{cid}/question", json={"question": "A plouat și pe 15?"}).status_code == 200
    time.sleep(0.05)
    wait(client, cid)
    ev = client.get(f"/claims/{cid}").json()["evidence"]
    assert [(e["agent"], e["round"]) for e in ev if e["round"] == 2] == [("news", 2)]


def test_photos_are_stored_served_and_cannot_escape_their_folder(client):
    r = client.post("/claims", data={"data": json.dumps({"claim": CLAIM})},
                    files=[("photos", ("a.jpg", b"\xff\xd8fake", "image/jpeg"))])
    cid = r.json()["id"]
    photos = client.get(f"/claims/{cid}").json()["claim"]["photos"]
    assert len(photos) == 1
    assert client.get(f"/photos/{photos[0]}").content == b"\xff\xd8fake"
    assert client.get("/photos/..%2F..%2Fpyproject.toml").status_code in (400, 404)


def test_unknown_claim_and_unknown_policy(client):
    assert client.get("/claims/nope").status_code == 404
    r = client.post("/claims", data={"data": json.dumps({"claim": {**CLAIM, "policy_id": "P-404"}})})
    assert r.status_code == 422
