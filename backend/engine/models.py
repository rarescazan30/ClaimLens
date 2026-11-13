"""Types shared by the engine, the agents and the API. Field names follow docs/contracts.md."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

Verdict = Literal["supports", "contradicts", "inconclusive"]
Outcome = Literal["fast_track", "standard_review", "antifraud_referral"]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Finding(BaseModel):
    metric: str
    value: Any = None
    unit: str | None = None
    source: str
    url: str | None = None
    spatial_res_km: float | None = None
    retrieved_at: str = Field(default_factory=now_iso)


class Evidence(BaseModel):
    agent: str
    round: int
    hypothesis: str
    verdict: Verdict
    strength: float = Field(ge=0, le=1)
    data_quality: float = Field(ge=0, le=1)
    findings: list[Finding] = []
    reasoning_steps: list[str] = []
    gaps: list[str] = []
    suggested_followup: str | None = None


class TraceStep(BaseModel):
    case_id: str
    step_id: str
    parent: str | None = None
    actor: str
    type: Literal["tool_call", "observation", "decision", "escalation"]
    summary: str
    inputs: dict = {}
    outputs: dict = {}
    sources: list[str] = []
    status: str = "done"
    started_at: str = Field(default_factory=now_iso)
    ended_at: str | None = None


class Hypothesis(BaseModel):
    id: str
    text: str
    critical: bool = True
    agents: list[str] = []


class RuleFlag(BaseModel):
    rule: str
    passed: bool
    reason: str


class WeightConfig(BaseModel):
    damage_type: str
    p0: float
    weights: dict[str, float]
    context_weight: float = 0.5


class Gate(BaseModel):
    kind: Literal["coverage", "clear_fake"]
    reason: str


class Contribution(BaseModel):
    agent: str
    round: int
    delta_logit: float


class ScoreResult(BaseModel):
    score: float
    band: str
    recommendation: Outcome
    contributions: list[Contribution] = []
    gates: list[Gate] = []


class Sink(Protocol):
    """Everything the engine tells the outside world. The API implements it with SQLite + the live stream."""

    def trace(self, step: TraceStep) -> None: ...
    def evidence(self, e: Evidence) -> int: ...
    def score(self, s: ScoreResult, round: int) -> None: ...
    def hypotheses(self, h: list[Hypothesis]) -> None: ...
    def flags(self, f: list[RuleFlag]) -> None: ...
