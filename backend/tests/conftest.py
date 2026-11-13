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


# ---- helpers for agent tests ------------------------------------------------------------------
import json  # noqa: E402
from pathlib import Path  # noqa: E402

import httpx  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def route(monkeypatch):
    """route({"substring of url": response}) where response is a dict/list (JSON), bytes, str,
    an int status code, or a callable(request) -> httpx.Response. Returns the list of requests made."""
    from engine import http
    calls = []

    def install(mapping):
        def handler(request):
            calls.append(request)
            url = str(request.url)
            for needle, resp in mapping.items():
                if needle in url:
                    if callable(resp):
                        return resp(request)
                    if isinstance(resp, int):
                        return httpx.Response(resp)
                    if isinstance(resp, bytes):
                        return httpx.Response(200, content=resp)
                    if isinstance(resp, str):
                        return httpx.Response(200, text=resp)
                    return httpx.Response(200, json=resp)
            return httpx.Response(404)
        monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(handler))
        return calls
    return install


@pytest.fixture
def fake_llm(monkeypatch):
    """fake_llm(answer) patches the LLM; answer is a dict, an Exception, or a callable(system, user, kw)."""
    from engine import llm
    seen = []

    def install(answer=None):
        answer_ = answer if answer is not None else {"verdict": "supports", "strength": 0.7, "data_quality": 0.6,
                                                    "reasoning_steps": ["ok"], "gaps": [], "suggested_followup": None}

        async def fake(system, user, **kw):
            seen.append((system, user, kw))
            if isinstance(answer_, Exception):
                raise answer_
            return answer_(system, user, kw) if callable(answer_) else answer_
        monkeypatch.setattr(llm, "llm_json", fake)
        return seen
    return install


def fixture_json(rel: str):
    return json.loads((FIX / rel).read_text())


def make_task(damage_type="flood", question=None, round=1, prior=None, **claim):
    from engine.graph import AgentTask
    from engine.models import Hypothesis
    base = {"id": "C-1", "damage_type": damage_type, "event_date": "2024-09-14", "notified_at": "2024-09-16",
            "address": "Str. X 1, Pechea", "lat": 45.63, "lon": 27.8, "description": "apă în casă, 60 cm",
            "amount_claimed": 1000, "photos": [], "photo_paths": [], "other_photo_paths": [], "footprints": []}
    return AgentTask(claim={**base, **claim}, policy={}, round=round, question=question, prior=prior or [],
                     hypotheses=[Hypothesis(id="H1", text="Ipoteza principală", critical=True, agents=[])])


def by_metric(evidence):
    return {f.metric: f for f in evidence.findings}
