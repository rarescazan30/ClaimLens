import pytest

from engine.models import Evidence, Hypothesis, RuleFlag, ScoreResult, TraceStep


class FakeSink:
    def __init__(self):
        self.steps: list[TraceStep] = []
        self.ev: list[Evidence] = []
        self.scores: list[tuple[int, ScoreResult]] = []
        self.hyp: list[Hypothesis] = []
        self.rule_flags: list[RuleFlag] = []

    def trace(self, step): self.steps.append(step)
    def evidence(self, e): self.ev.append(e); return len(self.ev)
    def score(self, s, round): self.scores.append((round, s))
    def hypotheses(self, h): self.hyp = h
    def flags(self, f): self.rule_flags = f


@pytest.fixture
def sink():
    return FakeSink()


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Every test gets an empty cache and live mode unless it says otherwise."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("REPLAY", raising=False)
    monkeypatch.delenv("REPLAY_AGENTS", raising=False)
