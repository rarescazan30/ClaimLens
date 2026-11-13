import asyncio

import pytest

from engine import graph
from engine.graph import AgentTask, JudgeOut, run_investigation, should_stop
from engine.models import Evidence, Hypothesis, WeightConfig
from engine.thresholds import ALL_AGENTS

POLICY = {"id": "P", "address": "A 1", "valid_from": "2024-01-01", "valid_to": "2024-12-31", "waiting_days": 0,
          "covered_risks": ["flood", "storm"], "sum_insured": 100000}


def claim(damage_type="flood"):
    return {"id": "C-1", "damage_type": damage_type, "event_date": "2024-09-14", "notified_at": "2024-09-16",
            "address": "A 1", "lat": 45.6, "lon": 27.8, "amount_claimed": 1000, "photos": []}


CFG = WeightConfig(damage_type="flood", p0=0.5, weights={a: 1.0 for a in ALL_AGENTS}, context_weight=0.5)
HYP = [Hypothesis(id="H1", text="ploaie", critical=True, agents=["meteo", "news"]),
       Hypothesis(id="H2", text="zona inundata", critical=True, agents=["satellite", "risk_zones"])]


async def planner(claim, policy, flags):
    return HYP


def recording_agents(calls, verdict="supports", strength=0.5):
    def make(name):
        async def run(task: AgentTask, ctx):
            calls.append((task.round, name, task.question))
            return Evidence(agent=name, round=task.round, hypothesis=task.hypotheses[0].text, verdict=verdict,
                            strength=strength, data_quality=0.5)
        return run
    return {a: make(a) for a in ALL_AGENTS}


def judge_script(*outs):
    outs = list(outs)

    async def judge(hypotheses, evidence, score, round, question=None):
        return outs.pop(0) if outs else JudgeOut(marks={}, tensions=[], action="stop", redispatch=[])
    return judge


STOP = JudgeOut(marks={"H1": "confirmed", "H2": "confirmed"}, tensions=[], action="stop", redispatch=[])


async def test_round_one_runs_all_six_agents_for_flood(sink):
    calls = []
    await run_investigation(claim(), POLICY, CFG, sink, agents=recording_agents(calls), planner=planner,
                            judge=judge_script(STOP))
    assert sorted(n for r, n, q in calls) == sorted(ALL_AGENTS) and all(r == 1 for r, n, q in calls)


async def test_storm_runs_four_agents(sink):
    calls = []
    await run_investigation(claim("storm"), POLICY, CFG, sink, agents=recording_agents(calls), planner=planner,
                            judge=judge_script(STOP))
    assert sorted(n for r, n, q in calls) == ["meteo", "news", "photo_forensics", "street_view"]


async def test_redispatch_runs_only_the_named_agent_with_the_question(sink):
    calls = []
    again = JudgeOut(marks={"H1": "confirmed", "H2": "conflicting"}, tensions=["t"], action="redispatch",
                     redispatch=[{"agent": "risk_zones", "question": "Diferența de nivel?"}])
    # round 2 answer flips the score by a lot so the <5 rule doesn't interfere
    agents = recording_agents(calls)

    async def risk(task, ctx):
        calls.append((task.round, "risk_zones", task.question))
        v = "supports" if task.round == 1 else "contradicts"
        return Evidence(agent="risk_zones", round=task.round, hypothesis="h", verdict=v, strength=1, data_quality=1)
    agents["risk_zones"] = risk
    result = await run_investigation(claim(), POLICY, CFG, sink, agents=agents, planner=planner,
                                     judge=judge_script(again, STOP))
    assert [c for c in calls if c[0] == 2] == [(2, "risk_zones", "Diferența de nivel?")]
    assert [r for r, s in sink.scores] == [1, 2]
    assert sink.scores[1][1].score < sink.scores[0][1].score and result == sink.scores[1][1]


def test_should_stop_rules():
    conflict = JudgeOut(marks={"H1": "confirmed", "H2": "conflicting"}, tensions=["t"], action="redispatch",
                        redispatch=[{"agent": "risk_zones", "question": "q"}])
    assert should_stop(3, 40, 60, conflict, HYP, 10)[0]
    assert should_stop(2, 60, 63, conflict, HYP, 10)[0]
    assert should_stop(1, None, 60, STOP, HYP, 10)[0]
    assert should_stop(1, None, 60, conflict, HYP, 181)[0]
    assert should_stop(2, 60, 72, conflict, HYP, 10) == (False, "")
    assert should_stop(1, None, 60, conflict, HYP, 10) == (False, "")
    assert all(should_stop(*a)[1] for a in [(3, 40, 60, conflict, HYP, 10), (2, 60, 63, conflict, HYP, 10)])


async def test_agent_that_raises_becomes_inconclusive(sink):
    agents = recording_agents([])

    async def boom(task, ctx):
        raise RuntimeError("kaboom")
    agents["news"] = boom
    await run_investigation(claim(), POLICY, CFG, sink, agents=agents, planner=planner, judge=judge_script(STOP))
    news = [e for e in sink.ev if e.agent == "news"][0]
    assert news.verdict == "inconclusive" and "kaboom" in news.gaps[0]
    assert len(sink.ev) == 6


async def test_agent_past_time_limit_becomes_inconclusive(sink):
    agents = recording_agents([])

    async def slow(task, ctx):
        await asyncio.sleep(5)
    agents["satellite"] = slow
    await run_investigation(claim(), POLICY, CFG, sink, agents=agents, planner=planner, judge=judge_script(STOP),
                            agent_timeout=0.1)
    sat = [e for e in sink.ev if e.agent == "satellite"][0]
    assert sat.verdict == "inconclusive" and "timp" in sat.gaps[0]


async def test_trace_has_every_stage_and_ends_with_a_human_decision_step(sink):
    await run_investigation(claim(), POLICY, CFG, sink, agents=recording_agents([]), planner=planner,
                            judge=judge_script(STOP))
    ids = [s.step_id for s in sink.steps]
    for expected in ("rules", "plan", "r1.dispatch", "r1.score", "r1.judge", "final"):
        assert expected in ids
    assert ids[-1] == "final" and sink.steps[-1].type == "escalation"
    assert "evaluator" in sink.steps[-1].summary.lower()
    assert len(sink.rule_flags) == 5 and sink.hyp == HYP


async def test_planner_failure_falls_back_to_default_hypotheses(sink):
    async def bad_planner(claim, policy, flags):
        raise RuntimeError("llm down")
    calls = []
    await run_investigation(claim(), POLICY, CFG, sink, agents=recording_agents(calls), planner=bad_planner,
                            judge=judge_script(STOP))
    assert len(calls) == 6 and len(sink.hyp) >= 1


async def test_extra_question_runs_one_round_on_the_agent_the_judge_picks(sink):
    calls = []
    prior = [Evidence(agent=a, round=1, hypothesis="h", verdict="supports", strength=0.5, data_quality=0.5)
             for a in ALL_AGENTS]
    pick = JudgeOut(marks={}, tensions=[], action="redispatch", redispatch=[{"agent": "news", "question": "Q?"}])
    await run_investigation(claim(), POLICY, CFG, sink, agents=recording_agents(calls), planner=planner,
                            judge=judge_script(pick, STOP), extra_question="Q?", prior=prior, hypotheses=HYP)
    assert calls == [(2, "news", "Q?")]
    assert "r2.final" == sink.steps[-1].step_id   # a question run gets its own closing step id
