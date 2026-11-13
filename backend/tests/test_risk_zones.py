from math import cos, radians

import httpx
import pytest

from agents.risk_zones.agent import run
from engine.context import AgentContext
from engine.models import Evidence, Finding
from tests.conftest import by_metric, fixture_json, make_task

LAT, LON = 45.63, 27.80
EAST_400 = LON + 400 / (111_320 * cos(radians(LAT)))
# a north–south stream 400 m east of the house
STREAM = {"elements": [{"type": "way", "id": 1, "tags": {"waterway": "stream", "name": "Pârâul Test"},
                        "geometry": [{"lat": LAT - 0.01, "lon": EAST_400}, {"lat": LAT + 0.01, "lon": EAST_400}]}]}
EDGE = {"lat": 45.629, "lon": 27.803}
SAT = Evidence(agent="satellite", round=1, hypothesis="h", verdict="inconclusive", strength=0.2, data_quality=0.8,
               findings=[Finding(metric="nearest_edge_point", value=EDGE, source="Copernicus CEMS"),
                         Finding(metric="distance_to_flood_edge_m", value=150, unit="m", source="Copernicus CEMS")])


def ctx(sink, round=1):
    return AgentContext("C-1", "risk_zones", round, sink)


async def test_distance_to_nearest_water(sink, route, fake_llm):
    route({"overpass": STREAM})
    fake_llm()
    m = by_metric(await run(make_task(lat=LAT, lon=LON), ctx(sink)))
    assert m["distance_to_water_m"].value == pytest.approx(400, abs=10)
    assert m["water_name"].value == "Pârâul Test" and m["distance_to_water_m"].source == "OpenStreetMap (Overpass)"
    assert "elevation_diff_m" not in m


async def test_real_overpass_response_parses(sink, route, fake_llm):
    route({"overpass": fixture_json("risk_zones/overpass.json")})
    fake_llm()
    m = by_metric(await run(make_task(lat=45.6312, lon=27.7985), ctx(sink)))
    assert m["water_name"].value == "Suhurlui" and 0 < m["distance_to_water_m"].value < 2000


async def test_backup_server_is_used_and_named(sink, route, fake_llm):
    route({"overpass-api.de": 504, "overpass.private.coffee": STREAM})
    fake_llm()
    m = by_metric(await run(make_task(lat=LAT, lon=LON), ctx(sink)))
    assert m["distance_to_water_m"].source == "OpenStreetMap (Overpass, server de rezervă)"


async def test_no_water_within_two_km_is_a_finding_not_an_error(sink, route, fake_llm):
    route({"overpass": {"elements": []}})
    seen = fake_llm()
    e = await run(make_task(lat=LAT, lon=LON), ctx(sink))
    assert by_metric(e)["distance_to_water_m"].value is None and len(seen) == 1


async def test_judge_question_compares_height_with_the_flood_edge(sink, route, fake_llm):
    def elevation(request):
        assert "45.63" in str(request.url) and "45.629" in str(request.url)
        return httpx.Response(200, json={"elevation": [47.0, 41.0]})
    route({"overpass": STREAM, "api.open-meteo.com/v1/elevation": elevation})
    seen = fake_llm()
    e = await run(make_task(lat=LAT, lon=LON, question="Care e diferența de nivel?", round=2, prior=[SAT]),
                  ctx(sink, 2))
    m = by_metric(e)
    assert (m["elevation_house_m"].value, m["elevation_flood_edge_m"].value, m["elevation_diff_m"].value) == (47.0, 41.0, 6.0)
    assert m["elevation_diff_m"].spatial_res_km == 0.09
    assert "60 cm" in seen[0][1]  # the LLM sees what the client declared


async def test_without_a_flood_edge_height_is_compared_with_the_water_and_the_gap_is_stated(sink, route, fake_llm):
    route({"overpass": STREAM, "api.open-meteo.com/v1/elevation": {"elevation": [47.0, 44.0]}})
    fake_llm()
    e = await run(make_task(lat=LAT, lon=LON, question="Diferența de nivel?", round=2), ctx(sink, 2))
    m = by_metric(e)
    assert m["elevation_diff_m"].value == 3.0 and "elevation_water_m" in m
    assert any("marginea zonei inundate" in g for g in e.gaps)


async def test_everything_down_is_inconclusive(sink, route, fake_llm):
    route({"overpass": 504, "elevation": 500})
    fake_llm()
    e = await run(make_task(lat=LAT, lon=LON), ctx(sink))
    assert e.verdict == "inconclusive" and "OpenStreetMap" in e.gaps[0]
