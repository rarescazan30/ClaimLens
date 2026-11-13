import pytest

from agents.meteo.agent import run
from engine.context import AgentContext
from tests.conftest import by_metric, fixture_json, make_task

DAILY, HOURLY = fixture_json("meteo/daily.json"), fixture_json("meteo/hourly.json")


def reply(request):
    import httpx
    return httpx.Response(200, json=HOURLY if "hourly=" in str(request.url) else DAILY)


async def test_daily_maxima_for_the_galati_flood(sink, route, fake_llm):
    calls = route({"archive-api.open-meteo.com": reply})
    seen = fake_llm()
    e = await run(make_task(), AgentContext("C-1", "meteo", 1, sink))
    m = by_metric(e)
    assert m["precipitation_24h_max"].value == 45.7 and m["precipitation_24h_max"].unit == "mm"
    assert m["precipitation_72h_max"].value == pytest.approx(75.2)
    assert m["wind_gusts_10m_max"].value == 45.0
    assert m["precipitation_24h_max"].source.startswith("Open-Meteo") and m["precipitation_24h_max"].url
    assert (e.verdict, e.strength, e.data_quality) == ("supports", 0.7, 0.6)
    assert len(calls) == 1 and "start_date=2024-09-12" in str(calls[0].url) and "end_date=2024-09-21" in str(calls[0].url)
    assert "30 mm" in seen[0][1] and "Ipoteza principală" in seen[0][1]


async def test_storm_prompt_carries_the_gust_threshold(sink, route, fake_llm):
    route({"archive-api.open-meteo.com": reply})
    seen = fake_llm()
    await run(make_task(damage_type="storm"), AgentContext("C-1", "meteo", 1, sink))
    assert "70 km/h" in seen[0][1]


async def test_backup_model_is_used_when_the_main_call_fails(sink, route, fake_llm):
    import httpx
    calls = route({"archive-api.open-meteo.com":
                   lambda r: httpx.Response(200, json=DAILY) if "models=era5" in str(r.url) else httpx.Response(500)})
    fake_llm()
    e = await run(make_task(), AgentContext("C-1", "meteo", 1, sink))
    f = by_metric(e)["precipitation_24h_max"]
    assert f.value == 45.7 and "ERA5" in f.source and f.spatial_res_km == 25


async def test_all_sources_down_is_inconclusive_with_the_gap_named(sink, route, fake_llm):
    route({"archive-api.open-meteo.com": 500})
    seen = fake_llm()
    e = await run(make_task(), AgentContext("C-1", "meteo", 1, sink))
    assert e.verdict == "inconclusive" and "Open-Meteo" in e.gaps[0] and seen == []


async def test_judge_question_adds_the_hourly_series(sink, route, fake_llm):
    calls = route({"archive-api.open-meteo.com": reply})
    seen = fake_llm()
    e = await run(make_task(question="A plouat torențial într-un interval scurt?", round=2),
                  AgentContext("C-1", "meteo", 2, sink))
    m = by_metric(e)
    assert m["precipitation_1h_max"].value == 13.7
    assert any("hourly=" in str(c.url) for c in calls)
    assert "A plouat torențial" in seen[0][1]


async def test_llm_failure_keeps_the_numbers_but_stays_inconclusive(sink, route, fake_llm):
    from engine.llm import LLMError
    route({"archive-api.open-meteo.com": reply})
    fake_llm(LLMError("down"))
    e = await run(make_task(), AgentContext("C-1", "meteo", 1, sink))
    assert e.verdict == "inconclusive" and by_metric(e)["precipitation_24h_max"].value == 45.7 and e.gaps


async def test_out_of_range_llm_numbers_are_clamped(sink, route, fake_llm):
    route({"archive-api.open-meteo.com": reply})
    fake_llm({"verdict": "maybe", "strength": 7, "data_quality": -1})
    e = await run(make_task(), AgentContext("C-1", "meteo", 1, sink))
    assert (e.verdict, e.strength, e.data_quality) == ("inconclusive", 1, 0)


async def test_findings_say_when_the_maximum_fell_and_what_the_event_day_had(sink, route, fake_llm):
    route({"archive-api.open-meteo.com": reply})
    seen = fake_llm()
    m = by_metric(await run(make_task(), AgentContext("C-1", "meteo", 1, sink)))
    assert m["precipitation_event_day"].value == 45.7
    assert m["precipitation_24h_max_date"].value == "2024-09-14"
    assert "reanaliză" in seen[0][1] and "supports" in seen[0][1]
