"""The investigation loop:  rules → plan → dispatch → score → judge → (dispatch again | finish).

Self-contained on purpose: a claim goes in, a ScoreResult comes out, and everything the outside world needs
is pushed through a Sink. No web-server code here, so the same graph can be published as a UiPath coded agent.
The loop ends by handing the case to a human. It never decides.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from engine.context import AgentContext
from engine.models import Evidence, Hypothesis, RuleFlag, ScoreResult, Sink, TraceStep, WeightConfig, now_iso
from engine.rules import check_policy, context_term
from engine.score import compute_score
from engine.thresholds import AGENTS_FOR, ALL_AGENTS, THRESHOLD_TEXT

MAX_ROUNDS = 3
MAX_SECONDS = 180
MIN_SCORE_MOVE = 5
MAX_REDISPATCH = 2

AGENT_LABEL = {"meteo": "Meteo", "satellite": "Satelit", "risk_zones": "Zone de risc",
               "photo_forensics": "Foto-forensic", "street_view": "Street view", "news": "Știri locale"}
BAND_LABEL = {"very_likely": "foarte probabil", "likely": "probabil", "uncertain": "incert", "unlikely": "improbabil"}
OUTCOME_LABEL = {"fast_track": "fast-track", "standard_review": "evaluare standard",
                 "antifraud_referral": "trimitere la antifraudă"}


class AgentTask(BaseModel):
    claim: dict
    policy: dict
    hypotheses: list[Hypothesis]
    question: str | None = None
    round: int
    prior: list[Evidence] = []


class JudgeOut(BaseModel):
    marks: dict[str, Literal["confirmed", "refuted", "inconclusive", "conflicting"]] = {}
    tensions: list[str] = []
    action: Literal["stop", "redispatch"] = "stop"
    redispatch: list[dict] = []  # [{"agent": ..., "question": ...}], at most MAX_REDISPATCH


AgentFn = Callable[[AgentTask, AgentContext], Awaitable[Evidence]]
Planner = Callable[[dict, dict, list[RuleFlag]], Awaitable[list[Hypothesis]]]
Judge = Callable[..., Awaitable[JudgeOut]]


class State(TypedDict, total=False):
    hypotheses: list[Hypothesis]
    flags: list[RuleFlag]
    evidence: list[Evidence]
    round: int
    pending: list[dict]        # [{"agent", "question"}] for the next dispatch
    prev_score: float | None
    score: ScoreResult
    stop_reason: str


def should_stop(round: int, prev_score: float | None, score: float, judge: JudgeOut,
                hypotheses: list[Hypothesis], elapsed_s: float) -> tuple[bool, str]:
    if round >= MAX_ROUNDS:
        return True, f"Limita de {MAX_ROUNDS} runde a fost atinsă."
    if elapsed_s > MAX_SECONDS:
        return True, "Bugetul de timp al investigației a fost depășit."
    if judge.action == "stop" or not judge.redispatch:
        return True, "Judge-ul nu mai are întrebări deschise."
    if prev_score is not None and abs(score - prev_score) < MIN_SCORE_MOVE:
        return True, f"Scorul s-a mișcat cu mai puțin de {MIN_SCORE_MOVE} puncte față de runda anterioară."
    critical = [h.id for h in hypotheses if h.critical]
    settled = all(judge.marks.get(h) in ("confirmed", "refuted") for h in critical)
    if critical and settled and "conflicting" not in judge.marks.values():
        return True, "Toate ipotezele critice au verdict."
    return False, ""


def default_hypotheses(claim: dict) -> list[Hypothesis]:
    """Used when the Orchestrator's LLM call fails: one plain hypothesis per factor."""
    kind = claim.get("damage_type", "flood")
    agents = AGENTS_FOR.get(kind, ALL_AGENTS)

    def only(*names):
        return [a for a in names if a in agents]
    hyps = [
        Hypothesis(id="H1", critical=True, agents=only("meteo", "news", "satellite"),
                   text=f"Fenomenul a avut loc la adresă pe {claim.get('event_date')} ({THRESHOLD_TEXT.get(kind, '')})"),
        Hypothesis(id="H2", critical=True, agents=only("risk_zones", "street_view"),
                   text="Expunerea locuinței face dauna declarată plauzibilă și dauna nu era preexistentă"),
        Hypothesis(id="H3", critical=True, agents=only("photo_forensics"),
                   text="Fotografiile sunt autentice, recente și arată dauna declarată"),
    ]
    return [h for h in hyps if h.agents]


def _clean_redispatch(items: list[dict], allowed: list[str]) -> list[dict]:
    out = [{"agent": i.get("agent"), "question": str(i.get("question") or "").strip()}
           for i in items if isinstance(i, dict) and i.get("agent") in allowed and i.get("question")]
    return out[:MAX_REDISPATCH]


async def run_investigation(claim: dict, policy: dict, cfg: WeightConfig, sink: Sink, *,
                            agents: dict[str, AgentFn] | None = None, planner: Planner | None = None,
                            judge: Judge | None = None, extra_question: str | None = None,
                            prior: list[Evidence] | None = None, hypotheses: list[Hypothesis] | None = None,
                            agent_timeout: float = 60) -> ScoreResult:
    if agents is None:
        from agents import AGENTS as agents  # noqa: N811
    if planner is None or judge is None:
        from engine import prompts
        from functools import partial
        planner = planner or prompts.plan_hypotheses
        declared = f"{claim.get('description') or ''} (sumă cerută: {claim.get('amount_claimed')})"
        judge = judge or partial(prompts.judge_round, claim_summary=declared)

    case_id = claim["id"]
    allowed = [a for a in AGENTS_FOR.get(claim.get("damage_type"), ALL_AGENTS) if a in agents]
    started = time.monotonic()

    def trace(step_id, parent, actor, type_, summary, outputs=None, inputs=None, t0=None):
        sink.trace(TraceStep(case_id=case_id, step_id=step_id, parent=parent, actor=actor, type=type_,
                             summary=summary, inputs=inputs or {}, outputs=outputs or {},
                             started_at=t0 or now_iso(), ended_at=now_iso()))

    async def rules_node(state: State) -> State:
        flags = check_policy(claim, policy)
        sink.flags(flags)
        passed = sum(f.passed for f in flags)
        trace("rules", None, "rules", "decision", f"Verificare poliță: {passed} din {len(flags)} reguli trecute",
              {"flags": [f.model_dump() for f in flags]})
        return {"flags": flags}

    async def plan_node(state: State) -> State:
        t0 = now_iso()
        try:
            hyps = await planner(claim, policy, state["flags"])
            note = ""
        except Exception as e:  # the plan must never block the investigation
            hyps, note = default_hypotheses(claim), f" (plan implicit: {type(e).__name__})"
        hyps = hyps or default_hypotheses(claim)
        sink.hypotheses(hyps)
        trace("plan", "rules", "orchestrator", "decision",
              f"Plan: {len(hyps)} ipoteze, {len(allowed)} agenți{note}",
              {"hypotheses": [h.model_dump() for h in hyps]}, t0=t0)
        return {"hypotheses": hyps, "round": 0, "evidence": [], "prev_score": None,
                "pending": [{"agent": a, "question": None} for a in allowed]}

    async def run_agent(name: str, question: str | None, round_: int, state: State) -> Evidence:
        ctx = AgentContext(case_id, name, round_, sink)
        mine = [h for h in state["hypotheses"] if name in h.agents] or state["hypotheses"]
        task = AgentTask(claim=claim, policy=policy, hypotheses=mine, question=question, round=round_,
                         prior=state["evidence"])
        try:
            e = await asyncio.wait_for(agents[name](task, ctx), agent_timeout)
            if not isinstance(e, Evidence):
                raise TypeError("agentul nu a returnat Evidence")
            e = e.model_copy(update={"agent": name, "round": round_})
        except asyncio.TimeoutError:
            e = ctx.inconclusive(mine[0].text, f"{AGENT_LABEL.get(name, name)}: limita de timp a fost depășită")
        except Exception as ex:  # one failing agent never blocks the others; a gap is not fraud
            e = ctx.inconclusive(mine[0].text, f"{AGENT_LABEL.get(name, name)}: eroare ({type(ex).__name__}: {ex})")
        sink.evidence(e)
        return e

    async def dispatch_node(state: State) -> State:
        round_ = state["round"] + 1
        pending = state["pending"]
        names = ", ".join(AGENT_LABEL.get(p["agent"], p["agent"]) for p in pending)
        parent = "plan" if round_ == 1 else f"r{round_ - 1}.judge"
        trace(f"r{round_}.dispatch", parent, "orchestrator", "decision",
              f"Runda {round_}: {names}" + (" în paralel" if len(pending) > 1 else ""),
              {"agents": pending, "not_relevant": [a for a in ALL_AGENTS if a not in allowed]})
        new = await asyncio.gather(*(run_agent(p["agent"], p["question"], round_, state) for p in pending))
        return {"round": round_, "evidence": state["evidence"] + list(new), "pending": []}

    async def score_node(state: State) -> State:
        result = compute_score(state["evidence"], cfg, state["flags"], context_term(claim, policy))
        prev = state.get("score")
        sink.score(result, state["round"])
        trace(f"r{state['round']}.score", f"r{state['round']}.dispatch", "score", "observation",
              f"Scor după runda {state['round']}: {result.score} ({BAND_LABEL[result.band]})",
              result.model_dump())
        return {"score": result, "prev_score": prev.score if prev else state.get("prev_score")}

    async def judge_node(state: State) -> State:
        round_, t0 = state["round"], now_iso()
        try:
            out = await judge(state["hypotheses"], state["evidence"], state["score"], round_)
        except Exception as e:
            out = JudgeOut(tensions=[f"judge unavailable ({type(e).__name__})"], action="stop")
        out.redispatch = _clean_redispatch(out.redispatch, allowed)
        stop, reason = should_stop(round_, state.get("prev_score"), state["score"].score, out,
                                   state["hypotheses"], time.monotonic() - started)
        if stop:
            summary = " ".join(out.tensions + [reason, "Opresc investigația."])
        else:
            asks = "; ".join(f"{AGENT_LABEL.get(r['agent'], r['agent'])}: {r['question']}" for r in out.redispatch)
            summary = " ".join(out.tensions + [f"Retrimit {len(out.redispatch)} agent(i) — {asks}"])
        trace(f"r{round_}.judge", f"r{round_}.dispatch", "judge", "decision", summary,
              {**out.model_dump(), "action": "stop" if stop else "redispatch", "stop_reason": reason}, t0=t0)
        return {"pending": [] if stop else out.redispatch, "stop_reason": reason}

    async def question_node(state: State) -> State:
        """Adjuster asked a free question: the Judge picks which agent answers it."""
        evidence, hyps = list(prior or []), list(hypotheses or default_hypotheses(claim))
        flags = check_policy(claim, policy)
        score = compute_score(evidence, cfg, flags, context_term(claim, policy))
        round_ = max((e.round for e in evidence), default=0)
        try:
            out = await judge(hyps, evidence, score, round_, question=extra_question)
            picks = _clean_redispatch(out.redispatch, allowed)[:1]
        except Exception:
            picks = []
        picks = picks or [{"agent": allowed[0], "question": extra_question}]
        trace(f"r{round_}.question", None, "adjuster", "decision",
              f"Întrebarea evaluatorului: {extra_question} → {AGENT_LABEL.get(picks[0]['agent'], picks[0]['agent'])}",
              {"question": extra_question, "agent": picks[0]["agent"]})
        return {"hypotheses": hyps, "flags": flags, "evidence": evidence, "round": round_, "score": score,
                "prev_score": None, "pending": picks}

    async def finish_node(state: State) -> State:
        s = state["score"]
        gates = " ".join(f"[{g.reason}]" for g in s.gates)
        trace("final", f"r{state['round']}.judge", "engine", "escalation",
              f"Scor de plauzibilitate {s.score} ({BAND_LABEL[s.band]}). Recomandare: {OUTCOME_LABEL[s.recommendation]}. "
              f"{gates} Decizia aparține evaluatorului.".replace("  ", " "),
              s.model_dump())
        return {}

    g = StateGraph(State)
    g.add_node("rules", rules_node)
    g.add_node("plan", plan_node)
    g.add_node("question", question_node)
    g.add_node("dispatch", dispatch_node)
    g.add_node("score", score_node)
    g.add_node("judge", judge_node)
    g.add_node("finish", finish_node)
    if extra_question:
        g.add_edge(START, "question")
    else:
        g.add_edge(START, "rules")
    g.add_edge("rules", "plan")
    g.add_edge("plan", "dispatch")
    g.add_edge("question", "dispatch")
    g.add_edge("dispatch", "score")
    g.add_edge("score", "judge")
    g.add_conditional_edges("judge", lambda s: "dispatch" if s["pending"] else "finish",
                            {"dispatch": "dispatch", "finish": "finish"})
    g.add_edge("finish", END)
    final = await g.compile().ainvoke({}, {"recursion_limit": 40})
    return final["score"]
