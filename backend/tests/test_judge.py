import pytest

from engine import llm, prompts
from engine.graph import run_investigation
from engine.models import Evidence, Flag, Hypothesis, ScoreResult, WeightConfig
from engine.thresholds import ALL_AGENTS

HYP = [Hypothesis(id="H1", text="ploaie", critical=True, agents=["meteo"])]
SCORE = ScoreResult(score=60, band="uncertain", recommendation="standard_review")
EV = [Evidence(agent="meteo", round=1, hypothesis="ploaie", verdict="supports", strength=0.5, data_quality=0.5)]
CLAIM = {"id": "C-1", "damage_type": "flood", "event_date": "2024-09-14", "notified_at": "2024-09-16",
         "address": "A 1", "lat": 45.6, "lon": 27.8, "description": "apa in casa", "amount_claimed": 1, "photos": []}
POLICY = {"address": "A 1", "valid_from": "2024-01-01", "valid_to": "2024-12-31", "covered_risks": ["flood"],
          "sum_insured": 10}


def answer(monkeypatch, out, seen=None):
    async def fake(system, user, **kw):
        if seen is not None:
            seen.append((system, user, kw))
        if isinstance(out, Exception):
            raise out
        return out
    monkeypatch.setattr(prompts, "llm_json", fake)


async def test_judge_unavailable_stops(monkeypatch):
    answer(monkeypatch, llm.LLMError("bad json"))
    out = await prompts.judge_round(HYP, EV, SCORE, 1)
    assert out.action == "stop" and out.tensions == ["judge unavailable"]


async def test_judge_keeps_valid_marks_and_drops_unknown_ones(monkeypatch):
    answer(monkeypatch, {"marks": {"H1": "conflicting", "H9": "banana"}, "tensions": ["t"],
                         "action": "redispatch", "redispatch": [{"agent": "meteo", "question": "q"}]})
    out = await prompts.judge_round(HYP, EV, SCORE, 1)
    assert out.marks == {"H1": "conflicting"} and out.action == "redispatch"


async def test_judge_uses_the_strong_model_and_never_sees_planner_reasoning(monkeypatch):
    seen = []
    answer(monkeypatch, {"marks": {}, "tensions": [], "action": "stop", "redispatch": []}, seen)
    await prompts.judge_round(HYP, EV, SCORE, 1)
    system, user, kw = seen[0]
    assert kw["model"] == "strong" and "ploaie" in user and "meteo" in user


async def test_planner_limits_agents_to_the_damage_type(monkeypatch):
    answer(monkeypatch, {"hypotheses": [
        {"id": "H1", "text": "rafale", "critical": True, "agents": ["meteo", "satellite", "bogus"]},
        {"id": "H2", "text": "fara agenti valizi", "critical": True, "agents": ["risk_zones"]}]})
    hyps = await prompts.plan_hypotheses({**CLAIM, "damage_type": "storm"}, POLICY, [])
    assert [(h.id, h.agents) for h in hyps] == [("H1", ["meteo"])]


async def test_planner_prompt_carries_the_threshold(monkeypatch):
    seen = []
    answer(monkeypatch, {"hypotheses": [{"id": "H1", "text": "x", "critical": True, "agents": ["meteo"]}]}, seen)
    await prompts.plan_hypotheses(CLAIM, POLICY, [])
    assert "30 mm" in seen[0][1] and seen[0][2]["model"] == "strong"


async def test_engine_drops_bad_redispatch_and_caps_at_two(monkeypatch, sink):
    calls = []

    def make(name):
        async def run(task, ctx):
            calls.append((task.round, name))
            v = "supports" if task.round == 1 else "contradicts"
            return Evidence(agent=name, round=task.round, hypothesis="h", verdict=v, strength=1, data_quality=1)
        return run
    answers = [{"marks": {"H1": "conflicting"}, "tensions": ["t"], "action": "redispatch", "redispatch": [
        {"agent": "nonexistent", "question": "q"}, {"agent": "meteo", "question": "q1"},
        {"agent": "news", "question": "q2"}, {"agent": "satellite", "question": "q3"}]},
        {"marks": {"H1": "refuted"}, "tensions": [], "action": "stop", "redispatch": []}]

    users = []

    async def fake(system, user, **kw):
        users.append(user)
        return answers.pop(0)
    monkeypatch.setattr(prompts, "llm_json", fake)

    async def planner(c, p, f):
        return HYP
    cfg = WeightConfig(damage_type="flood", p0=0.5, weights={a: 1.0 for a in ALL_AGENTS})
    await run_investigation(CLAIM, POLICY, cfg, sink, agents={a: make(a) for a in ALL_AGENTS}, planner=planner)
    assert [c for c in calls if c[0] == 2] == [(2, "meteo"), (2, "news")]
    assert "apa in casa" in users[0]  # the Judge must know what the client declared to spot tensions


EARLY = [Flag(step="client", code="cnp_mismatch", severity="warn", reason="CNP diferit")]


async def test_judge_sees_early_flags(monkeypatch):
    seen = []
    answer(monkeypatch, {"marks": {}, "tensions": [], "action": "stop", "redispatch": []}, seen)
    await prompts.judge_round(HYP, EV, SCORE, 1, early_flags=EARLY)
    system, user, _ = seen[0]
    assert "Semnale din verificările inițiale:\n- [client] CNP diferit" in user
    assert "Foto-forensic" not in user
    assert "niciodată un motiv" in system


async def test_judge_photo_flag_adds_forensic_sentence(monkeypatch):
    seen = []
    answer(monkeypatch, {"marks": {}, "tensions": [], "action": "stop", "redispatch": []}, seen)
    await prompts.judge_round(HYP, EV, SCORE, 1, early_flags=[
        Flag(step="photos", code="exif", severity="warn", reason="EXIF lipsă")])
    assert "Constatările agentului Foto-forensic provin din aceleași verificări ale fotografiilor." in seen[0][1]


@pytest.mark.parametrize("flags", [None, []])
async def test_judge_without_flags_says_niciunul(monkeypatch, flags):
    seen = []
    answer(monkeypatch, {"marks": {}, "tensions": [], "action": "stop", "redispatch": []}, seen)
    await prompts.judge_round(HYP, EV, SCORE, 1, early_flags=flags)
    assert "Semnale din verificările inițiale: niciunul" in seen[0][1]


async def test_orchestrator_sees_early_flags(monkeypatch):
    seen = []
    answer(monkeypatch, {"hypotheses": []}, seen)
    await prompts.plan_hypotheses(CLAIM, POLICY, [], early_flags=EARLY)
    assert "Semnale din verificările inițiale:\n- [client] CNP diferit" in seen[0][1]
    seen.clear()
    await prompts.plan_hypotheses(CLAIM, POLICY, [])
    assert "Semnale din verificările inițiale: niciunul" in seen[0][1]
