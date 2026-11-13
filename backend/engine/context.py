"""What an agent is handed for one round: a call budget, traced fetching, the LLM, and a way to say 'I don't know'."""
from __future__ import annotations

import os
from typing import Any

from engine import http, llm
from engine.models import Evidence, Sink, TraceStep, now_iso


class BudgetExceeded(http.SourceError):
    """The agent used all its tool calls for this round."""


def _preview(value: Any, limit: int = 400) -> Any:
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    text = str(value)
    return value if len(text) <= limit else text[:limit] + "…"


class AgentContext:
    def __init__(self, case_id: str, agent: str, round: int, sink: Sink, max_calls: int = 6):
        self.case_id, self.agent, self.round, self.sink, self.max_calls = case_id, agent, round, sink, max_calls
        self.calls = 0
        self._n = 0

    def _step(self, type_: str, summary: str, *, inputs=None, outputs=None, sources=None, status="done",
              started_at: str | None = None) -> None:
        self._n += 1
        self.sink.trace(TraceStep(
            case_id=self.case_id, step_id=f"r{self.round}.{self.agent}.{self._n}", parent=f"r{self.round}.dispatch",
            actor=f"agent:{self.agent}", type=type_, summary=summary, inputs=inputs or {}, outputs=outputs or {},
            sources=sources or [], status=status, started_at=started_at or now_iso(), ended_at=now_iso()))

    def _forced_replay(self) -> bool | None:
        forced = [a.strip() for a in os.environ.get("REPLAY_AGENTS", "").split(",") if a.strip()]
        return True if self.agent in forced else None

    async def fetch(self, source_name: str, url: str, **kw) -> Any:
        """One tool call: counted against the budget, written to the trace, cached."""
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"{self.agent}: buget de {self.max_calls} apeluri epuizat")
        self.calls += 1
        started = now_iso()
        shown = {"url": url, "params": {k: v for k, v in (kw.get("params") or {}).items()
                                        if k.lower() not in http.SECRET_PARAMS}}
        self._step("tool_call", f"Interogare {source_name}", inputs=shown, sources=[source_name], started_at=started)
        try:
            data = await http.fetch(url, replay=self._forced_replay(), **kw)
        except http.SourceError as e:
            self._step("observation", f"{source_name} nu a răspuns", outputs={"error": str(e)[:300]},
                       sources=[source_name], status="failed")
            raise
        self._step("observation", f"Răspuns de la {source_name}", outputs={"preview": _preview(data)},
                   sources=[source_name])
        return data

    async def fetch_first(self, attempts: list[tuple[str, str, dict]]) -> tuple[str, Any]:
        """Try the main source, then each backup. Returns (source name that answered, data)."""
        last: Exception | None = None
        for name, url, kw in attempts:
            try:
                return name, await self.fetch(name, url, **kw)
            except BudgetExceeded:
                raise
            except http.SourceError as e:
                last = e
        raise http.SourceError(f"toate sursele au eșuat: {last}")

    async def llm(self, system: str, user: str, **kw) -> dict:
        return await llm.llm_json(system, user, **kw)

    def note(self, type_: str, summary: str, outputs: dict | None = None, sources: list[str] | None = None) -> None:
        self._step(type_, summary, outputs=outputs, sources=sources)

    def inconclusive(self, hypothesis: str, gap: str) -> Evidence:
        return Evidence(agent=self.agent, round=self.round, hypothesis=hypothesis, verdict="inconclusive",
                        strength=0, data_quality=0, gaps=[gap])
