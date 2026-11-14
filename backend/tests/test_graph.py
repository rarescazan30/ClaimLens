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
    assert len(sink.rule_flags) == 6 and sink.hyp == HYP


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


def _prior_r3():
    return [Evidence(agent=a, round=r, hypothesis="h", verdict="supports", strength=0.5, data_quality=0.5)
            for r in (1, 2, 3) for a in ALL_AGENTS]


def _flipping_agents():
    """Every answer pulls the score the other way, so the <5 points rule never ends the run."""
    def make(name):
        async def run(task: AgentTask, ctx):
            v = "contradicts" if task.round % 2 == 0 else "supports"
            return Evidence(agent=name, round=task.round, hypothesis="h", verdict=v, strength=1, data_quality=1)
        return run
    return {a: make(a) for a in ALL_AGENTS}


NEWS_AGAIN = JudgeOut(marks={}, tensions=["Clientul declară altceva"], action="redispatch",
                      redispatch=[{"agent": "news", "question": "Mai verifică?"}])


async def test_question_after_three_rounds_lets_the_judge_send_an_agent_back(sink):
    pick = JudgeOut(marks={}, tensions=[], action="redispatch", redispatch=[{"agent": "news", "question": "De ce?"}])
    await run_investigation(claim(), POLICY, CFG, sink, agents=_flipping_agents(), planner=planner,
                            judge=judge_script(pick, NEWS_AGAIN, STOP), extra_question="De ce?",
                            prior=_prior_r3(), hypotheses=HYP)
    judges = [s for s in sink.steps if s.step_id.endswith(".judge")]
    assert judges[0].step_id == "r4.judge"
    assert judges[0].outputs["action"] == "redispatch"   # round 4 may send an agent back
    assert "Limita" not in judges[0].summary


async def test_question_run_still_stops_after_three_rounds_of_its_own(sink):
    pick = JudgeOut(marks={}, tensions=[], action="redispatch", redispatch=[{"agent": "news", "question": "De ce?"}])
    await run_investigation(claim(), POLICY, CFG, sink, agents=_flipping_agents(), planner=planner,
                            judge=judge_script(pick, NEWS_AGAIN, NEWS_AGAIN, NEWS_AGAIN), extra_question="De ce?",
                            prior=_prior_r3(), hypotheses=HYP)
    judges = [s for s in sink.steps if s.step_id.endswith(".judge")]
    assert [j.step_id for j in judges] == ["r4.judge", "r5.judge", "r6.judge"]
    assert [j.outputs["action"] for j in judges] == ["redispatch", "redispatch", "stop"]
    assert "Limita" in judges[2].summary


def test_should_stop_counts_rounds_from_first_round():
    conflict = JudgeOut(marks={"H1": "conflicting"}, tensions=["t"], action="redispatch",
                        redispatch=[{"agent": "news", "question": "q"}])
    assert should_stop(4, None, 60, conflict, HYP, 10, first_round=4) == (False, "")
    assert should_stop(6, 40, 60, conflict, HYP, 10, first_round=4)[0]


# ---- intake: five steps, the pause, resuming ---------------------------------------------------
from engine.documents import write_document  # noqa: E402
from engine.models import Flag, RuleFlag  # noqa: E402

DOC_CLAIM = {
    "numar_dosar": "C-1042", "numar_polita": "P-7731", "nume_asigurat": "Persoană Sintetică Unu",
    "cnp": "1800101123456", "telefon": "+40 700 000 000", "email": "nume@example.ro",
    "iban": "RO49AAAA1B31007593840000", "adresa_daunei": "Str. Exemplu 12, Pechea, jud. Galați",
    "tip_dauna": "inundație", "data_evenimentului": "2024-09-14", "data_notificarii": "2024-09-19",
    "descriere": "Apa a intrat în casă", "suma_solicitata": "48000", "numar_fotografii": "0",
}
DOC_POLICY = {
    "numar_polita": "P-7731", "produs": "PAD", "nume_asigurat": "Persoană Sintetică Unu",
    "cnp": "1800101123456", "adresa_asigurata": "Str. Exemplu 12, Pechea, jud. Galați",
    "valabila_de_la": "2024-02-01", "valabila_pana_la": "2025-01-31", "zile_asteptare": "0",
    "riscuri_acoperite": "inundație, cutremur, alunecare de teren", "suma_asigurata": "100000",
}
HOUSE = {"nominatim": [{"lat": "45.6", "lon": "27.7", "addresstype": "house"}]}


def _docs(tmp_path, claim_over=None, policy_over=None):
    write_document({**DOC_CLAIM, **(claim_over or {})}, "claim_form", tmp_path / "c.pdf")
    write_document({**DOC_POLICY, **(policy_over or {})}, "policy", tmp_path / "p.pdf")
    return {"claim_form": tmp_path / "c.pdf", "policy": tmp_path / "p.pdf"}


@pytest.fixture
def docs_ok(tmp_path, route):
    route(HOUSE)
    return _docs(tmp_path)


@pytest.fixture
def docs_expired(tmp_path, route):
    route(HOUSE)
    return _docs(tmp_path, policy_over={"valabila_pana_la": "2024-06-30"})


@pytest.fixture
def docs_no_date(tmp_path, route):
    route(HOUSE)
    return _docs(tmp_path, claim_over={"data_evenimentului": ""})


class Recorder:
    """A planner and a Judge that remember the early flags they were given."""

    def __init__(self, *judge_outs):
        self.plan_flags, self.judge_flags, self.outs, self.tasks = [], [], list(judge_outs), []

    async def planner(self, claim, policy, flags, early_flags=None):
        self.plan_flags.append(early_flags)
        return HYP

    async def judge(self, hypotheses, evidence, score, round, question=None, early_flags=None):
        self.judge_flags.append(early_flags)
        return self.outs.pop(0) if self.outs else STOP

    def agents(self, calls):
        base = recording_agents(calls)

        def wrap(name):
            async def run(task, ctx):
                self.tasks.append((name, task))
                return await base[name](task, ctx)
            return run
        return {a: wrap(a) for a in ALL_AGENTS}


async def test_all_rules_pass_runs_through_to_the_verdict(sink, docs_ok):
    rec, calls = Recorder(), []
    out = await run_investigation({}, {}, CFG, sink, documents=docs_ok, photos=[], agents=rec.agents(calls),
                                  planner=rec.planner, judge=rec.judge)
    assert out is not None
    assert [s.step_id for s in sink.steps][:6] == ["intake", "documents", "client", "rules", "photos", "plan"]
    assert all(s.parent is None for s in sink.steps[:5])
    assert [r.step for r in sink.check_results] == ["intake", "documents", "client", "policy", "photos"]
    assert sink.read_fields["lat"] == 45.6 and sink.read_fields["lon"] == 27.7
    assert sink.read_fields["damage_type"] == "flood" and sink.read_fields["amount_claimed"] == 48000
    assert len(calls) == 6 and all(t.claim["lat"] == 45.6 for _, t in rec.tasks)
    early = [f for r in sink.check_results for f in r.flags]
    assert rec.plan_flags == [early] and rec.judge_flags == [early]
    assert sink.steps[0].case_id == "C-1042"


async def test_expired_policy_pauses_before_the_agents(sink, docs_expired):
    rec = Recorder()
    out = await run_investigation({}, {}, CFG, sink, documents=docs_expired, photos=[], agents=rec.agents([]),
                                  planner=rec.planner, judge=rec.judge)
    assert out is None and sink.steps[-1].step_id == "paused"
    assert sink.steps[-1].outputs == {"failed_rules": ["policy_active"]}
    assert [s.step_id for s in sink.steps] == ["intake", "documents", "client", "rules", "photos", "paused"]
    assert not any(s.actor.startswith("agent:") for s in sink.steps)
    assert sink.ev == [] and rec.plan_flags == [] and sink.check_results[-1].step == "photos"


async def test_resume_starts_at_the_plan_and_the_judge_gets_the_flags(sink, tmp_path):
    from PIL import Image
    Image.new("RGB", (32, 32), "white").save(tmp_path / "a.jpg")
    early = [Flag(step="client", code="cnp_mismatch", field="cnp", severity="warn", reason="CNP diferit."),
             Flag(step="policy", code="policy_active", severity="fail", reason="Expirată.")]
    rules = [RuleFlag(rule="policy_active", passed=False, reason="Expirată.")]
    again = JudgeOut(marks={}, tensions=["t"], action="redispatch",
                     redispatch=[{"agent": "news", "question": "Mai e ceva?"}])
    rec = Recorder(again, STOP)
    agents = _flipping_agents()
    seen = []

    async def photo(task, ctx):
        seen.append(task.claim.get("photo_findings"))
        return await _flipping_agents()["photo_forensics"](task, ctx)
    agents["photo_forensics"] = photo
    out = await run_investigation(claim(), POLICY, CFG, sink, photos=[tmp_path / "a.jpg"], earlier_photos=[],
                                  resume={"early_flags": [f.model_dump() for f in early],
                                          "rule_flags": [r.model_dump() for r in rules]},
                                  agents=agents, planner=rec.planner, judge=rec.judge)
    ids = [s.step_id for s in sink.steps]
    assert ids[:2] == ["continue", "plan"] and "rules" not in ids and "photos" not in ids
    assert sink.steps[0].actor == "adjuster" and sink.steps[0].type == "decision"
    assert "r1.dispatch" in ids and "r2.judge" in ids
    assert rec.plan_flags == [early] and rec.judge_flags == [early, early]
    assert sink.check_results == []
    assert seen and any(m["metric"] == "a.jpg:copy_in_other_claim" for m in seen[0])
    assert any(g.kind == "coverage" for g in out.gates) and out.recommendation != "fast_track"
    assert [c.reason for c in out.contributions if c.agent == "client"] == ["CNP diferit."]


async def test_claim_form_without_event_date_pauses_without_raising(sink, docs_no_date, tmp_path):
    from PIL import Image
    Image.new("RGB", (32, 32), "white").save(tmp_path / "a.jpg")
    rec = Recorder()
    out = await run_investigation({}, {}, CFG, sink, documents=docs_no_date, photos=[tmp_path / "a.jpg"],
                                  agents=rec.agents([]), planner=rec.planner, judge=rec.judge)
    assert out is None and sink.steps[-1].step_id == "paused"
    assert "policy_active" in sink.steps[-1].outputs["failed_rules"]
    assert [r.step for r in sink.check_results] == ["intake", "documents", "client", "policy", "photos"]


async def test_no_coordinates_makes_location_agents_inconclusive(sink):
    calls = []
    c = {k: v for k, v in claim().items() if k not in ("lat", "lon")}
    await run_investigation(c, POLICY, CFG, sink, agents=recording_agents(calls), planner=planner,
                            judge=judge_script(STOP))
    located = {"meteo", "satellite", "risk_zones", "street_view"}
    assert sorted(n for _, n, _ in calls) == ["news", "photo_forensics"]
    for e in sink.ev:
        if e.agent in located:
            assert e.verdict == "inconclusive" and e.gaps == ["Adresa nu a putut fi localizată"]
            assert e.strength == 0 and e.data_quality == 0 and e.hypothesis
    dispatch = next(s for s in sink.steps if s.step_id == "r1.dispatch")
    assert {a["agent"] for a in dispatch.outputs["agents"]} >= located
