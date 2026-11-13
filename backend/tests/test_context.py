import httpx
import pytest

from engine import http
from engine.context import AgentContext, BudgetExceeded


@pytest.fixture
def ok(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if "down" in str(request.url):
            return httpx.Response(500)
        return httpx.Response(200, json={"v": len(calls)})
    monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(handler))
    return calls


async def test_fetch_writes_tool_call_and_observation(sink, ok):
    ctx = AgentContext("C-1", "meteo", 1, sink)
    await ctx.fetch("Open-Meteo", "https://x.test/a")
    assert [s.type for s in sink.steps] == ["tool_call", "observation"]
    assert [s.step_id for s in sink.steps] == ["r1.meteo.1", "r1.meteo.2"]
    assert sink.steps[0].parent == "r1.dispatch" and sink.steps[0].actor == "agent:meteo"
    assert sink.steps[0].sources == ["Open-Meteo"]


async def test_seventh_call_exceeds_budget(sink, ok):
    ctx = AgentContext("C-1", "meteo", 1, sink)
    for i in range(6):
        await ctx.fetch("S", f"https://x.test/{i}")
    with pytest.raises(BudgetExceeded):
        await ctx.fetch("S", "https://x.test/7")


async def test_fetch_first_falls_back_to_backup(sink, ok):
    ctx = AgentContext("C-1", "risk_zones", 1, sink)
    name, data = await ctx.fetch_first([("Main", "https://x.test/down", {}), ("Backup", "https://x.test/up", {})])
    assert name == "Backup" and "v" in data
    failed = [s for s in sink.steps if s.status == "failed"]
    assert len(failed) == 1 and failed[0].sources == ["Main"]


async def test_fetch_first_raises_when_all_fail(sink, ok):
    ctx = AgentContext("C-1", "risk_zones", 1, sink)
    with pytest.raises(http.SourceError):
        await ctx.fetch_first([("A", "https://x.test/down1", {}), ("B", "https://x.test/down2", {})])


def test_inconclusive_has_zero_strength_and_names_the_gap(sink):
    e = AgentContext("C-1", "news", 2, sink).inconclusive("H", "GDELT nu a răspuns")
    assert (e.verdict, e.strength, e.data_quality, e.gaps, e.agent, e.round) == \
        ("inconclusive", 0, 0, ["GDELT nu a răspuns"], "news", 2)


async def test_replay_agents_forces_cache_for_that_agent(sink, ok, monkeypatch):
    monkeypatch.setenv("REPLAY_AGENTS", "news,street_view")
    with pytest.raises(http.CacheMiss):
        await AgentContext("C-1", "news", 1, sink).fetch("GDELT", "https://x.test/n")
    await AgentContext("C-1", "meteo", 1, sink).fetch("Open-Meteo", "https://x.test/m")
