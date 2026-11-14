"""The investigation loop:  rules → plan → dispatch → score → judge → (dispatch again | finish).

With the claim's documents:  intake → documents → client → rules → photos → (plan … | paused). A failed policy rule
pauses the claim before the agents; the adjuster can resume it, which starts again at the plan.

Self-contained on purpose: a claim goes in, a ScoreResult comes out, and everything the outside world needs
is pushed through a Sink. No web-server code here, so the same graph can be published as a UiPath coded agent.
The loop ends by handing the case to a human. It never decides.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Awaitable, Callable, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from engine import intake
from engine.client import check_client
from engine.context import AgentContext
from engine.documents import check_documents, check_intake, to_claim
from engine.models import Evidence, Flag, Hypothesis, RuleFlag, ScoreResult, Sink, TraceStep, WeightConfig, now_iso
from engine.rules import check_policy, context_term, policy_flags
from engine.score import compute_score
from engine.thresholds import AGENTS_FOR, ALL_AGENTS, THRESHOLD_TEXT

MAX_ROUNDS = 3
MAX_SECONDS = 180
MIN_SCORE_MOVE = 5
MAX_REDISPATCH = 2
LOCATED_AGENTS = ("meteo", "satellite", "risk_zones", "street_view")   # need the house's coordinates
NO_LOCATION = "Adresa nu a putut fi localizată"

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
    early_flags: list[Flag]    # every flag of the intake steps (only on the documents and resume paths)
    points: tuple              # (claim point, policy point) from the client step
    evidence: list[Evidence]
    round: int
    first_round: int           # first round of THIS run (a question run continues the numbering)
    pending: list[dict]        # [{"agent", "question"}] for the next dispatch
    prev_score: float | None
    score: ScoreResult
    stop_reason: str


def should_stop(round: int, prev_score: float | None, score: float, judge: JudgeOut,
                hypotheses: list[Hypothesis], elapsed_s: float, first_round: int = 1) -> tuple[bool, str]:
    if round - first_round + 1 >= MAX_ROUNDS:   # rounds of this run only
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
                            documents: dict[str, Path | None] | None = None, photos: list[Path] | None = None,
                            earlier_photos: list[Path] | None = None, resume: dict | None = None,
                            agent_timeout: float = 60) -> ScoreResult | None:
    """Returns None when the claim pauses on a failed policy rule (documents path only)."""
    if agents is None:
        from agents import AGENTS as agents  # noqa: N811
    claim, policy = dict(claim), dict(policy)   # the intake steps fill these in place; the caller's stay untouched
    if planner is None or judge is None:
        from engine import prompts
        planner = planner or prompts.plan_hypotheses
        if judge is None:
            async def judge(*args, **kw):   # the claim summary is built when asked: the documents may fill it in
                declared = f"{claim.get('description') or ''} (sumă cerută: {claim.get('amount_claimed')})"
                return await prompts.judge_round(*args, claim_summary=declared, **kw)

    reading = documents is not None and resume is None and not extra_question
    resuming = resume is not None and not extra_question
    if reading:
        claim_doc, policy_doc = intake.read_documents(documents)
        claim["id"] = claim.get("id") or claim_doc.fields.get("numar_dosar") or "necunoscut"
    if (reading or resuming) and photos is not None:
        claim["photo_paths"] = [str(p) for p in photos]
        if earlier_photos is not None:
            claim["other_photo_paths"] = [str(p) for p in earlier_photos]

    case_id = claim["id"]
    allowed: list[str] = []

    def set_allowed():
        allowed[:] = [a for a in AGENTS_FOR.get(claim.get("damage_type"), ALL_AGENTS) if a in agents]
    set_allowed()
    started = time.monotonic()

    def trace(step_id, parent, actor, type_, summary, outputs=None, inputs=None, t0=None):
        sink.trace(TraceStep(case_id=case_id, step_id=step_id, parent=parent, actor=actor, type=type_,
                             summary=summary, inputs=inputs or {}, outputs=outputs or {},
                             started_at=t0 or now_iso(), ended_at=now_iso()))

    def early_kw(state: State) -> dict:
        return {"early_flags": state["early_flags"]} if "early_flags" in state else {}

    def report(step_id: str, actor: str, type_: str, title: str, result, outputs=None, t0=None) -> None:
        sink.checks(result)
        trace(step_id, None, actor, type_, intake.step_summary(title, result),
              {"items": [i.model_dump() for i in result.items], "flags": [f.model_dump() for f in result.flags],
               **(outputs or {})}, t0=t0)

    async def intake_node(state: State) -> State:
        result = check_intake(documents, photos or [], to_claim(claim_doc, policy_doc)[0].get("declared_photos"))
        report("intake", "intake", "observation", "Dosar primit", result)
        return {"early_flags": list(result.flags)}

    async def documents_node(state: State) -> State:
        result = check_documents(claim_doc, policy_doc)
        intake.apply_read(claim, policy, claim_doc, policy_doc)
        set_allowed()
        report("documents", "documents", "observation", "Documente citite", result)
        return {"early_flags": state["early_flags"] + result.flags}

    async def client_node(state: State) -> State:
        t0 = now_iso()
        result, claim_point, policy_point = await check_client(claim_doc, policy_doc)
        point = claim_point or policy_point
        if point is not None:
            claim["lat"], claim["lon"] = point.lat, point.lon
        report("client", "client", "observation", "Datele clientului", result,
               {"coordinates": {"lat": claim.get("lat"), "lon": claim.get("lon"),
                                "from": "claim" if claim_point else ("policy" if policy_point else None)}}, t0=t0)
        sink.claim_read(intake.read_fields(claim))
        return {"early_flags": state["early_flags"] + result.flags, "points": (claim_point, policy_point)}

    async def rules_node(state: State) -> State:
        flags = check_policy(claim, policy, *state.get("points", (None, None)))
        sink.flags(flags)
        passed = sum(f.passed for f in flags)
        summary = f"Verificare poliță: {passed} din {len(flags)} reguli trecute"
        if not reading:
            trace("rules", None, "rules", "decision", summary, {"flags": [f.model_dump() for f in flags]})
            return {"flags": flags}
        result = policy_flags(flags)
        sink.checks(result)
        trace("rules", None, "rules", "decision", summary,
              {"flags": [f.model_dump() for f in flags], "items": [i.model_dump() for i in result.items]})
        return {"flags": flags, "early_flags": state["early_flags"] + result.flags}

    async def photos_node(state: State) -> State:
        result, findings = intake.photo_step(photos or [], claim, earlier_photos or [])
        if findings is not None:
            claim["photo_findings"] = [f.model_dump() for f in findings]
        report("photos", "photos", "observation", "Verificarea fotografiilor", result)
        return {"early_flags": state["early_flags"] + result.flags}

    async def paused_node(state: State) -> State:
        failed = [f for f in state["flags"] if not f.passed]
        trace("paused", None, "engine", "escalation",
              f"Investigația este oprită înainte de agenți: {len(failed)} "
              f"{'regulă de poliță eșuată' if len(failed) == 1 else 'reguli de poliță eșuate'} "
              f"({'; '.join(f.reason for f in failed)}). Evaluatorul poate continua investigația sau poate decide.",
              {"failed_rules": [f.rule for f in failed]})
        return {}

    async def continue_node(state: State) -> State:
        early, flags = intake.as_flags(resume.get("early_flags")), intake.as_rule_flags(resume.get("rule_flags"))
        if photos and claim.get("event_date"):   # same deterministic check as before the pause, not reported again
            claim["photo_findings"] = [f.model_dump() for f in intake.photo_step(photos, claim, earlier_photos or [])[1]]
        failed = [f.rule for f in flags if not f.passed]
        trace("continue", None, "adjuster", "decision",
              "Evaluatorul a cerut continuarea investigației"
              + (f" în ciuda regulilor de poliță eșuate ({', '.join(failed)})." if failed else "."),
              {"failed_rules": failed})
        return {"flags": flags, "early_flags": early}

    async def plan_node(state: State) -> State:
        t0 = now_iso()
        try:
            hyps = await planner(claim, policy, state["flags"], **early_kw(state))
            note = ""
        except Exception as e:  # the plan must never block the investigation
            hyps, note = default_hypotheses(claim), f" (plan implicit: {type(e).__name__})"
        hyps = hyps or default_hypotheses(claim)
        sink.hypotheses(hyps)
        trace("plan", "continue" if resuming else ("photos" if reading else "rules"), "orchestrator", "decision",
              f"Plan: {len(hyps)} ipoteze, {len(allowed)} agenți{note}",
              {"hypotheses": [h.model_dump() for h in hyps]}, t0=t0)
        return {"hypotheses": hyps, "round": 0, "first_round": 1, "evidence": [], "prev_score": None,
                "pending": [{"agent": a, "question": None} for a in allowed]}

    async def run_agent(name: str, question: str | None, round_: int, state: State) -> Evidence:
        ctx = AgentContext(case_id, name, round_, sink)
        mine = [h for h in state["hypotheses"] if name in h.agents] or state["hypotheses"]
        if name in LOCATED_AGENTS and intake.house_of(claim) is None:   # not called: nothing to look up
            e = ctx.inconclusive(mine[0].text, NO_LOCATION)
            sink.evidence(e)
            return e
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
        result = compute_score(state["evidence"], cfg, state["flags"], context_term(claim, policy),
                               data_flags=state.get("early_flags"))
        prev = state.get("score")
        sink.score(result, state["round"])
        trace(f"r{state['round']}.score", f"r{state['round']}.dispatch", "score", "observation",
              f"Scor după runda {state['round']}: {result.score} ({BAND_LABEL[result.band]})",
              result.model_dump())
        return {"score": result, "prev_score": prev.score if prev else state.get("prev_score")}

    async def judge_node(state: State) -> State:
        round_, t0 = state["round"], now_iso()
        try:
            out = await judge(state["hypotheses"], state["evidence"], state["score"], round_, **early_kw(state))
        except Exception as e:
            out = JudgeOut(tensions=[f"judge unavailable ({type(e).__name__})"], action="stop")
        out.redispatch = _clean_redispatch(out.redispatch, allowed)
        stop, reason = should_stop(round_, state.get("prev_score"), state["score"].score, out,
                                   state["hypotheses"], time.monotonic() - started, state.get("first_round", 1))
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
        if resume is not None:   # a claim read from documents: its stored flags, not a re-run without the map points
            flags, early = intake.as_rule_flags(resume.get("rule_flags")), intake.as_flags(resume.get("early_flags"))
            stored = {"early_flags": early}
        else:                    # legacy claim: exactly as before
            flags, stored = check_policy(claim, policy), {}
        score = compute_score(evidence, cfg, flags, context_term(claim, policy), data_flags=stored.get("early_flags"))
        round_ = max((e.round for e in evidence), default=0)
        try:
            out = await judge(hyps, evidence, score, round_, question=extra_question, **stored)
            picks = _clean_redispatch(out.redispatch, allowed)[:1]
        except Exception:
            picks = []
        picks = picks or [{"agent": allowed[0], "question": extra_question}]
        trace(f"r{round_}.question", None, "adjuster", "decision",
              f"Întrebarea evaluatorului: {extra_question} → {AGENT_LABEL.get(picks[0]['agent'], picks[0]['agent'])}",
              {"question": extra_question, "agent": picks[0]["agent"]})
        return {"hypotheses": hyps, "flags": flags, "evidence": evidence, "round": round_, "first_round": round_ + 1,
                "score": score, "prev_score": None, "pending": picks, **stored}

    async def finish_node(state: State) -> State:
        s = state["score"]
        gates = " ".join(f"[{g.reason}]" for g in s.gates)
        step_id = f"r{state['round']}.final" if extra_question else "final"   # ids stay unique across runs
        trace(step_id, f"r{state['round']}.judge", "engine", "escalation",
              f"Scor de plauzibilitate {s.score} ({BAND_LABEL[s.band]}). Recomandare: {OUTCOME_LABEL[s.recommendation]}. "
              f"{gates} Decizia aparține evaluatorului.".replace("  ", " "),
              s.model_dump())
        return {}

    g = StateGraph(State)
    g.add_node("intake", intake_node)
    g.add_node("documents", documents_node)
    g.add_node("client", client_node)
    g.add_node("photos", photos_node)
    g.add_node("paused", paused_node)
    g.add_node("continue", continue_node)
    g.add_node("rules", rules_node)
    g.add_node("plan", plan_node)
    g.add_node("question", question_node)
    g.add_node("dispatch", dispatch_node)
    g.add_node("score", score_node)
    g.add_node("judge", judge_node)
    g.add_node("finish", finish_node)
    if extra_question:
        g.add_edge(START, "question")
    elif resuming:
        g.add_edge(START, "continue")
    elif reading:
        g.add_edge(START, "intake")
    else:
        g.add_edge(START, "rules")
    g.add_edge("intake", "documents")
    g.add_edge("documents", "client")
    g.add_edge("client", "rules")
    if reading:
        g.add_edge("rules", "photos")
        g.add_conditional_edges("photos", lambda s: "paused" if any(not f.passed for f in s["flags"]) else "plan",
                                {"paused": "paused", "plan": "plan"})
    else:
        g.add_edge("rules", "plan")
    g.add_edge("paused", END)
    g.add_edge("continue", "plan")
    g.add_edge("plan", "dispatch")
    g.add_edge("question", "dispatch")
    g.add_edge("dispatch", "score")
    g.add_edge("score", "judge")
    g.add_conditional_edges("judge", lambda s: "dispatch" if s["pending"] else "finish",
                            {"dispatch": "dispatch", "finish": "finish"})
    g.add_edge("finish", END)
    final = await g.compile().ainvoke({}, {"recursion_limit": 40})
    return final.get("score")   # None when paused
