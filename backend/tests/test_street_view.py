import httpx
from PIL import Image

from agents.street_view.agent import run
from engine.context import AgentContext
from tests.conftest import by_metric, make_task

MS = {"2023-06-11": 1686470400000, "2022-04-02": 1648857600000, "2024-10-01": 1727740800000}


def img(id_, day, lon=27.8001):
    return {"id": id_, "captured_at": MS[day], "thumb_1024_url": f"https://mly.test/{id_}.jpg",
            "geometry": {"type": "Point", "coordinates": [lon, 45.63]}}


MAPILLARY = {"data": [img("old", "2022-04-02"), img("after", "2024-10-01"), img("latest_before", "2023-06-11")]}
GOOGLE_OK = {"status": "OK", "date": "2023-08", "pano_id": "abc", "location": {"lat": 45.6301, "lng": 27.8001}}


def jpeg():
    import io
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (120, 120, 120)).save(buf, "JPEG")
    return buf.getvalue()


def ctx(sink, round=1):
    return AgentContext("C-1", "street_view", round, sink)


async def test_latest_mapillary_image_before_the_event_is_chosen(sink, route, fake_llm):
    calls = route({"graph.mapillary.com": MAPILLARY})
    fake_llm()
    m = by_metric(await run(make_task(), ctx(sink)))
    assert m["pre_event_image_date"].value == "2023-06-11" and m["pre_event_image_source"].value == "Mapillary"
    assert m["pre_event_image_url"].value == "https://www.mapillary.com/app/?pKey=latest_before"
    assert 0 < m["distance_m"].value < 60 and len(calls) == 1 and "bbox=" in str(calls[0].url)


async def test_google_is_used_when_mapillary_has_nothing_before_the_event(sink, route, fake_llm):
    route({"graph.mapillary.com": {"data": [img("after", "2024-10-01")]}, "streetview/metadata": GOOGLE_OK})
    fake_llm()
    m = by_metric(await run(make_task(), ctx(sink)))
    assert m["pre_event_image_source"].value == "Google Street View" and m["pre_event_image_date"].value == "2023-08"
    assert "key=" not in m["pre_event_image_url"].value


async def test_google_image_taken_after_the_event_does_not_count(sink, route, fake_llm):
    route({"graph.mapillary.com": {"data": []}, "streetview/metadata": {**GOOGLE_OK, "date": "2025-05"}})
    fake_llm()
    e = await run(make_task(), ctx(sink))
    assert e.verdict == "inconclusive" and e.gaps == ["Nicio imagine stradală dinaintea evenimentului la această adresă"]


async def test_google_status_not_ok_is_treated_as_empty(sink, route, fake_llm):
    route({"graph.mapillary.com": {"data": []}, "streetview/metadata": {"status": "ZERO_RESULTS"}})
    seen = fake_llm()
    e = await run(make_task(), ctx(sink))
    assert e.verdict == "inconclusive" and "Nicio imagine stradală" in e.gaps[0] and seen == []


async def test_both_sources_down_names_the_sources(sink, route, fake_llm):
    route({"graph.mapillary.com": 500, "streetview/metadata": 500})
    fake_llm()
    e = await run(make_task(), ctx(sink))
    assert e.verdict == "inconclusive" and "Mapillary" in e.gaps[0] and "Google" in e.gaps[0]


async def test_judge_question_compares_the_old_image_with_the_client_photos(sink, route, fake_llm, tmp_path):
    client_photo = tmp_path / "foto1.jpg"
    client_photo.write_bytes(jpeg())
    route({"graph.mapillary.com": MAPILLARY, "mly.test": jpeg()})

    def answer(system, user, kw):
        if kw.get("images"):
            assert len(kw["images"]) == 2
            return {"prior_condition": "acoperiș întreg, fără urme de reparații", "preexisting_damage": False}
        return {"verdict": "supports", "strength": 0.6, "data_quality": 0.6}
    fake_llm(answer)
    e = await run(make_task(damage_type="storm", photo_paths=[str(client_photo)], question="Dauna era preexistentă?", round=2),
                  ctx(sink, 2))
    m = by_metric(e)
    assert m["preexisting_damage"].value is False and "acoperiș întreg" in m["prior_condition"].value
    assert e.verdict == "supports"


async def test_google_refusing_the_key_is_a_failed_source_not_missing_imagery(sink, route, fake_llm, tmp_path):
    route({"graph.mapillary.com": 500, "streetview/metadata": {"status": "REQUEST_DENIED", "error_message": "no key"}})
    fake_llm()
    e = await run(make_task(), ctx(sink))
    assert e.verdict == "inconclusive" and "nu au răspuns" in e.gaps[0]
    assert "Nicio imagine" not in e.gaps[0]
    # a refusal must never be saved, or it would be replayed forever once a valid key is added
    assert not [p for p in (tmp_path / "cache").rglob("*.json") if "REQUEST_DENIED" in p.read_text()]


async def test_google_is_asked_within_150_m_and_the_distance_is_reported(sink, route, fake_llm):
    calls = route({"graph.mapillary.com": {"data": []},
                   "streetview/metadata": {**GOOGLE_OK, "location": {"lat": 45.6311, "lng": 27.8001}}})
    fake_llm()
    m = by_metric(await run(make_task(), ctx(sink)))
    assert "radius=150" in str(calls[-1].url)
    assert 100 < m["distance_m"].value < 150
