"""Shared by all agents: turning numbers into a verdict, and small geometry helpers."""
from __future__ import annotations

import json
from datetime import date, timedelta

from engine.context import AgentContext
from engine.graph import AgentTask
from engine.geo import haversine_m  # noqa: F401  (re-exported for the agents)
from engine.http import SourceError
from engine.models import Evidence, Finding

SYSTEM = """Ești un agent specialist într-o investigație de daune la asigurări de locuințe. Ai o singură competență: {role}
Primești ipotezele de verificat și constatările obținute din surse reale. Evaluezi DOAR pe baza constatărilor.
Răspunzi în română, cu UN SINGUR obiect JSON (un singur verdict de ansamblu, chiar dacă sunt mai multe ipoteze):
{{"verdict": "supports" | "contradicts" | "inconclusive",
  "strength": 0..1  (cât de mult mută dovada verdictul asupra ipotezei),
  "data_quality": 0..1  (cât ne putem baza pe sursă: rezoluție, distanță în timp, oficială sau nu),
  "reasoning_steps": ["pași scurți, cu cifrele folosite"],
  "gaps": ["ce a lipsit sau ce limitează concluzia"],
  "suggested_followup": "o verificare suplimentară utilă, sau null"}}
Reguli: "supports" = constatările susțin că dauna declarată e plauzibilă; "contradicts" = o contrazic.
Date lipsă sau insuficiente înseamnă "inconclusive", niciodată "contradicts". Nu acuzi pe nimeni de fraudă.
Dacă cifrele răspund clar la ipoteză, dă verdictul: limitările generale ale sursei scad data_quality, nu schimbă verdictul.
Fii scurt: cel mult 3 pași de raționament și cel mult 2 goluri, fiecare sub 25 de cuvinte, doar goluri care contează."""


def main_hypothesis(task: AgentTask) -> str:
    return task.hypotheses[0].text if task.hypotheses else "Dauna declarată este plauzibilă"


def clamp01(value, default=0.0) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return default


async def conclude(ctx: AgentContext, task: AgentTask, role: str, findings: list[Finding], guidance: str = "",
                   gaps: list[str] | None = None, images: list[bytes] | None = None) -> Evidence:
    """One LLM call that reads the findings and returns the standard Evidence. If the LLM is unavailable,
    the numbers are kept and the verdict stays 'inconclusive'."""
    gaps = list(gaps or [])
    hyp = main_hypothesis(task)
    declared = {k: task.claim.get(k) for k in ("damage_type", "event_date", "address", "description")}
    user = (f"Ipoteze de verificat: {json.dumps([h.text for h in task.hypotheses], ensure_ascii=False)}\n"
            f"Ce declară clientul: {json.dumps(declared, ensure_ascii=False)}\n"
            + (f"Întrebarea Judge-ului pentru această rundă: {task.question}\n" if task.question else "")
            + f"Constatări: {json.dumps([f.model_dump(exclude={'retrieved_at'}) for f in findings], ensure_ascii=False, default=str)}\n"
            + (f"Limitări cunoscute: {json.dumps(gaps, ensure_ascii=False)}\n" if gaps else "")
            + (f"Repere: {guidance}\n" if guidance else ""))
    try:
        out = await ctx.llm(SYSTEM.format(role=role), user, **({"images": images} if images else {}))
    except SourceError as e:
        ctx.note("observation", "Interpretarea automată nu a fost disponibilă; constatările rămân în dosar",
                 {"error": str(e)[:200]})
        return Evidence(agent=ctx.agent, round=ctx.round, hypothesis=hyp, verdict="inconclusive", strength=0,
                        data_quality=0, findings=findings,
                        gaps=gaps + ["Interpretarea automată a constatărilor nu a fost disponibilă"])
    verdict = out.get("verdict") if out.get("verdict") in ("supports", "contradicts", "inconclusive") else "inconclusive"
    steps = [str(s) for s in out.get("reasoning_steps") or []][:6]
    e = Evidence(agent=ctx.agent, round=ctx.round, hypothesis=hyp, verdict=verdict,
                 strength=clamp01(out.get("strength")), data_quality=clamp01(out.get("data_quality")),
                 findings=findings, reasoning_steps=steps,
                 gaps=gaps + [str(g) for g in out.get("gaps") or [] if str(g) not in gaps][:4],
                 suggested_followup=out.get("suggested_followup") or None)
    ctx.note("observation", steps[0] if steps else f"Verdict: {verdict}",
             {"verdict": verdict, "strength": e.strength, "data_quality": e.data_quality},
             sorted({f.source for f in findings}))
    return e


def event_day(task: AgentTask) -> date:
    return date.fromisoformat(str(task.claim["event_date"])[:10])


def day_range(task: AgentTask, before: int, after: int) -> tuple[str, str]:
    d = event_day(task)
    return (d - timedelta(days=before)).isoformat(), (d + timedelta(days=after)).isoformat()
