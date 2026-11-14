from math import cos, radians

import pytest

from agents.satellite.agent import run
from engine.context import AgentContext
from tests.conftest import by_metric, make_task

SQUARE = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"notation": "Maximum flood extent"},
          "geometry": {"type": "Polygon", "coordinates": [[[27.80, 45.63], [27.81, 45.63], [27.81, 45.64], [27.80, 45.64], [27.80, 45.63]]]}}]}
LAYER_URL = "https://s3.test/EMSR758/AOI03/DEL_MONIT01/maximumFloodExtentA_v1.json"
SEARCH = {"count": 1, "results": [{"code": "EMSR758", "category": {"slug": "flood", "name": "Flood"},
          "name": "Flood in Galati and Vaslui counties, Romania", "centroid": "POINT (27.668568 45.788551)",
          "activationTime": "2024-09-14T13:44:00"}]}


def dashboard(layers=True, reason=""):
    product = {"type": "DEL", "monitoringNumber": 1, "downloadPath": "x.zip" if layers else "",
               "version": {"reason": reason},
               "images": [{"sensorName": "COSMO-SkyMed", "acquisitionTime": "2024-09-17T16:13:00"}],
               "layers": [{"name": "EMSR758/AOI03/DEL_MONIT01/EMSR758_AOI03_DEL_MONIT01_floodDepthA_v1_VT", "json": "https://s3.test/depth.json"},
                          {"name": "EMSR758/AOI03/DEL_MONIT01/EMSR758_AOI03_DEL_MONIT01_maximumFloodExtentA_v1_VT", "json": LAYER_URL}] if layers else []}
    return {"results": [{"code": "EMSR758", "name": "Flood in Galati and Vaslui counties, Romania", "aois": [
        {"number": 3, "name": "Pechea", "extent": "POLYGON ((27.6 45.4, 27.9 45.4, 27.9 45.8, 27.6 45.8, 27.6 45.4))",
         "products": [product]}]}]}


def routes(**over):
    base = {"activations/api/activations": SEARCH, "public-activations": dashboard(), "s3.test": SQUARE}
    return {**base, **over}


async def go(sink, **claim):
    return await run(make_task(**claim), AgentContext("C-1", "satellite", 1, sink))


async def test_point_inside_the_flood_extent(sink, route, fake_llm):
    route(routes())
    fake_llm()
    m = by_metric(await go(sink, lat=45.635, lon=27.805))
    assert m["inside_flood_extent"].value is True and m["distance_to_flood_edge_m"].value == 0
    assert m["activation"].value == "EMSR758" and m["map_date"].value == "2024-09-17T16:13:00"
    assert "Copernicus" in m["inside_flood_extent"].source and m["flood_extent_geojson_url"].value == LAYER_URL


async def test_point_150_m_outside(sink, route, fake_llm):
    route(routes())
    seen = fake_llm()
    lon = 27.80 - 150 / (111_320 * cos(radians(45.635)))
    m = by_metric(await go(sink, lat=45.635, lon=lon))
    assert m["inside_flood_extent"].value is False
    assert m["distance_to_flood_edge_m"].value == pytest.approx(150, abs=5)
    edge = m["nearest_edge_point"].value
    assert edge["lon"] == pytest.approx(27.80, abs=1e-4) and edge["lat"] == pytest.approx(45.635, abs=1e-4)
    assert "±" in seen[0][1] or "incertitudine" in seen[0][1].lower()


async def test_contradicts_within_300_m_of_the_edge_becomes_inconclusive(sink, route, fake_llm):
    route(routes())
    fake_llm({"verdict": "contradicts", "strength": 0.8, "data_quality": 0.7, "reasoning_steps": ["afară"], "gaps": []})
    lon = 27.80 - 250 / (111_320 * cos(radians(45.635)))
    e = await go(sink, lat=45.635, lon=lon)
    assert e.verdict == "inconclusive" and any("300 m" in g for g in e.gaps)


async def test_contradicts_beyond_300_m_stays(sink, route, fake_llm):
    route(routes())
    seen = fake_llm({"verdict": "contradicts", "strength": 0.8, "data_quality": 0.7, "reasoning_steps": ["afară"], "gaps": []})
    lon = 27.80 - 600 / (111_320 * cos(radians(45.635)))
    e = await go(sink, lat=45.635, lon=lon)
    assert e.verdict == "contradicts" and "300 m" in seen[0][1]


async def test_no_activation_for_the_event_is_inconclusive_never_outside(sink, route, fake_llm):
    route(routes(**{"activations/api/activations": {"count": 0, "results": []}}))
    seen = fake_llm()
    e = await go(sink, lat=45.635, lon=27.805)
    assert e.verdict == "inconclusive" and e.gaps and seen == []
    assert "inside_flood_extent" not in by_metric(e)


async def test_activation_of_another_date_is_ignored(sink, route, fake_llm):
    route(routes())
    fake_llm()
    e = await go(sink, lat=45.635, lon=27.805, event_date="2023-05-01")
    assert e.verdict == "inconclusive" and "inside_flood_extent" not in by_metric(e)


async def test_area_where_copernicus_produced_no_map_is_inconclusive_with_the_reason(sink, route, fake_llm):
    route(routes(**{"public-activations": dashboard(layers=False, reason="Not produced because of remote sensing limitations")}))
    fake_llm()
    e = await go(sink, lat=45.635, lon=27.805)
    assert e.verdict == "inconclusive" and "remote sensing limitations" in e.gaps[0]


async def test_address_outside_every_mapped_area_is_inconclusive(sink, route, fake_llm):
    route(routes())
    fake_llm()
    e = await go(sink, lat=44.0, lon=26.0)
    assert e.verdict == "inconclusive" and "inside_flood_extent" not in by_metric(e)


async def test_stored_footprint_is_used_without_any_network_call(sink, route, fake_llm):
    calls = route(routes())
    fake_llm()
    fp = {"id": "EMSR758-AOI03", "name": "Flood in Galati", "polygon": SQUARE, "sources": ["Copernicus CEMS EMSR758"],
          "meteo_maxima": {"map_date": "2024-09-17T16:13:00", "geojson_url": LAYER_URL}}
    m = by_metric(await go(sink, lat=45.635, lon=27.805, footprints=[fp]))
    assert m["inside_flood_extent"].value is True and calls == []
    assert any("amprent" in s.summary.lower() for s in sink.steps)


async def test_copernicus_down_is_inconclusive(sink, route, fake_llm):
    route(routes(**{"public-activations": 503}))
    fake_llm()
    e = await go(sink, lat=45.635, lon=27.805)
    assert e.verdict == "inconclusive" and "Copernicus" in e.gaps[0]


def test_search_terms_come_from_the_address():
    from agents.satellite.agent import search_terms
    assert search_terms("Str. Exemplu 12, Pechea, jud. Galați") == ["Galati", "Pechea"]
    assert search_terms("Str. Lalelelor 3, com. Slobozia Conachi, județul Galați") == ["Galati", "Slobozia Conachi"]
