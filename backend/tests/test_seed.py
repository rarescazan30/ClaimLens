from pathlib import Path

from app.db import Store
from app.seed import DEMO, seed
from engine.graph import JudgeOut, run_investigation
from engine.models import Evidence, Hypothesis, WeightConfig
from engine.thresholds import ALL_AGENTS

HYP = [Hypothesis(id="H1", text="ploaie", critical=True, agents=ALL_AGENTS)]
CFG = WeightConfig(damage_type="flood", p0=0.5, weights={a: 1.0 for a in ALL_AGENTS}, context_weight=0.5)


def test_demo_claims_load_from_the_team_documents(tmp_path):
    store = Store(tmp_path / "t.db")
    store.create_schema()
    seed(store)
    ids = {c["id"] for c in store.list_claims()}
    assert {"C-8001", "C-8002", "C-8003"} <= ids
    c = store.get_claim("C-8001")
    assert store.get_policy(c["policy_id"])["holder_name"] == "Mircea Popescu"


async def test_paused_demo_claim_pauses(sink, route):
    route({"nominatim": 500})   # the documents carry coordinates: nothing is geocoded

    async def agent(task, ctx):
        return Evidence(agent="x", round=task.round, hypothesis="ploaie", verdict="supports", strength=0.5,
                        data_quality=0.5)

    async def planner(c, p, f, **kw):
        return HYP

    async def judge(*a, **kw):
        return JudgeOut(action="stop")
    docs = DEMO / "documents"
    out = await run_investigation({"id": "C-8003"}, {}, CFG, sink,
                                  documents={"claim_form": docs / "paused" / "claim.pdf",
                                             "policy": docs / "paused" / "policy.pdf"},
                                  photos=[docs / "flood" / "poza.png"], agents={a: agent for a in ALL_AGENTS},
                                  planner=planner, judge=judge)
    assert out is None and sink.steps[-1].step_id == "paused"
    assert sink.steps[-1].outputs == {"failed_rules": ["policy_active"]}
