import pytest
from PIL import ExifTags, Image

from agents.photo_forensics.agent import run
from engine.context import AgentContext
from tests.conftest import by_metric, make_task


def photo(path, color=(40, 90, 160), date=None, gps=None, pattern=0):
    img = Image.new("RGB", (320, 240), color)
    for x in range(0, 320, 16 + pattern):       # some structure so perceptual hashes differ between patterns
        for y in range(0, 240, 3):
            img.putpixel((x, y), (255, 255, 255))
    exif = Image.Exif()
    if date:
        exif.get_ifd(ExifTags.IFD.Exif)[0x9003] = date
    if gps:
        lat, lon = gps
        exif.get_ifd(ExifTags.IFD.GPSInfo).update({1: "N", 2: (int(lat), (lat % 1) * 60, 0.0), 3: "E",
                                                   4: (int(lon), (lon % 1) * 60, 0.0)})
    img.save(path, "JPEG", exif=exif)
    return str(path)


def llm_router(vision=None, dates=None):
    def answer(system, user, kw):
        if kw.get("images"):
            return vision or {"photos": [{"index": i, "shows_declared_damage": True, "looks_generated": False,
                                          "description": "apă în interior"} for i in range(len(kw["images"]))]}
        if "prima publicare" in system.lower():
            return dates or {"pages": []}
        return {"verdict": "inconclusive", "strength": 0.3, "data_quality": 0.5, "reasoning_steps": ["ok"], "gaps": []}
    return answer


def ctx(sink, round=1):
    return AgentContext("C-1", "photo_forensics", round, sink)


WEB = {"responses": [{"webDetection": {
    "fullMatchingImages": [{"url": "https://stiri.test/img/inundatie.jpg"}],
    "pagesWithMatchingImages": [{"url": "https://stiri.test/2024/03/18/inundatii-vrancea", "pageTitle": "Inundații în Vrancea",
                                 "fullMatchingImages": [{"url": "https://stiri.test/img/inundatie.jpg"}]}]}}]}


async def test_no_photos_is_inconclusive(sink, route, fake_llm):
    route({})
    seen = fake_llm(llm_router())
    e = await run(make_task(), ctx(sink))
    assert e.verdict == "inconclusive" and e.gaps == ["Nu există fotografii în dosar"] and seen == []


async def test_exif_date_months_before_the_event_is_reported(sink, route, fake_llm, tmp_path):
    route({})
    seen = fake_llm(llm_router())
    p = photo(tmp_path / "foto1.jpg", date="2024:03:18 10:22:00", gps=(45.63, 27.80))
    e = await run(make_task(photo_paths=[p]), ctx(sink))
    m = by_metric(e)
    assert m["foto1.jpg:exif_date"].value == "2024-03-18"
    assert m["foto1.jpg:exif_days_before_event"].value == 180
    assert m["foto1.jpg:exif_distance_to_address_km"].value == pytest.approx(0, abs=0.2)
    assert "exif_days_before_event" in seen[-1][1]


async def test_missing_exif_is_stated(sink, route, fake_llm, tmp_path):
    route({})
    fake_llm(llm_router())
    e = await run(make_task(photo_paths=[photo(tmp_path / "foto1.jpg")]), ctx(sink))
    assert by_metric(e)["foto1.jpg:exif_missing"].value is True


async def test_same_image_in_another_claim_is_found(sink, route, fake_llm, tmp_path):
    route({})
    fake_llm(llm_router())
    mine = photo(tmp_path / "foto1.jpg", pattern=0)
    same = photo(tmp_path / "alt_dosar.jpg", pattern=0)
    different = photo(tmp_path / "altceva.jpg", color=(200, 30, 30), pattern=9)
    m = by_metric(await run(make_task(photo_paths=[mine], other_photo_paths=[different, same]), ctx(sink)))
    assert m["foto1.jpg:copy_in_other_claim"].value is True
    m2 = by_metric(await run(make_task(photo_paths=[mine], other_photo_paths=[different]), ctx(sink)))
    assert m2["foto1.jpg:copy_in_other_claim"].value is False


async def test_vision_findings_are_recorded_per_photo(sink, route, fake_llm, tmp_path):
    route({})
    fake_llm(llm_router(vision={"photos": [{"index": 0, "shows_declared_damage": False, "looks_generated": True,
                                            "description": "imagine netedă, fără detalii"}]}))
    m = by_metric(await run(make_task(photo_paths=[photo(tmp_path / "foto1.jpg")]), ctx(sink)))
    assert m["foto1.jpg:shows_declared_damage"].value is False and m["foto1.jpg:looks_generated"].value is True


async def test_web_search_runs_only_when_the_judge_asks(sink, route, fake_llm, tmp_path):
    calls = route({"vision.googleapis.com": WEB})
    fake_llm(llm_router())
    await run(make_task(photo_paths=[photo(tmp_path / "foto1.jpg")]), ctx(sink))
    assert calls == []


async def test_web_copy_published_before_the_event_is_a_clear_fake(sink, route, fake_llm, tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    calls = route({"vision.googleapis.com": WEB})
    fake_llm(llm_router(dates={"pages": [{"url": "https://stiri.test/2024/03/18/inundatii-vrancea", "first_seen": "2024-03-18"}]}))
    e = await run(make_task(photo_paths=[photo(tmp_path / "foto1.jpg")], question="Au mai fost publicate pozele?", round=2),
                  ctx(sink, 2))
    m = by_metric(e)
    assert m["exact_copy_before_event"].value is True
    assert m["exact_copy_before_event"].url == "https://stiri.test/2024/03/18/inundatii-vrancea"
    assert m["foto1.jpg:first_seen"].value == "2024-03-18" and m["foto1.jpg:web_matches"].value == 1
    assert len(calls) == 1 and b"WEB_DETECTION" in calls[0].content


UNDATED = {"responses": [{"webDetection": {"pagesWithMatchingImages": [
    {"url": "https://stiri.test/articol/inundatii-vrancea", "pageTitle": "Inundații în Vrancea",
     "fullMatchingImages": [{"url": "https://stiri.test/img/inundatie.jpg"}]}]}}]}


async def test_web_copy_without_a_date_in_its_address_is_not_a_clear_fake_whatever_a_model_says(sink, route, fake_llm, tmp_path):
    route({"vision.googleapis.com": UNDATED})
    fake_llm(llm_router(dates={"pages": [{"url": "https://stiri.test/articol/inundatii-vrancea", "first_seen": "2019-05-01"},
                                         {"url": "https://invented.test/2019/05/01/x", "first_seen": "2019-05-01"}]}))
    m = by_metric(await run(make_task(photo_paths=[photo(tmp_path / "foto1.jpg")], question="?", round=2), ctx(sink, 2)))
    assert "exact_copy_before_event" not in m and m["foto1.jpg:web_matches"].value == 1


async def test_vision_api_down_keeps_the_other_checks_and_names_the_gap(sink, route, fake_llm, tmp_path):
    route({"vision.googleapis.com": 403})
    fake_llm(llm_router())
    e = await run(make_task(photo_paths=[photo(tmp_path / "foto1.jpg")], question="?", round=2), ctx(sink, 2))
    assert "foto1.jpg:exif_missing" in by_metric(e) and any("Google Vision" in g for g in e.gaps)


async def test_at_most_six_tool_calls_with_many_photos(sink, route, fake_llm, tmp_path):
    calls = route({"vision.googleapis.com": {"responses": [{"webDetection": {}}]}})
    fake_llm(llm_router())
    paths = [photo(tmp_path / f"foto{i}.jpg", pattern=i) for i in range(8)]
    e = await run(make_task(photo_paths=paths, question="?", round=2), ctx(sink, 2))
    assert len(calls) <= 6 and any("fotografii" in g and "nu au fost căutate" in g for g in e.gaps)


async def test_unreadable_file_does_not_break_the_agent(sink, route, fake_llm, tmp_path):
    route({})
    fake_llm(llm_router())
    bad = tmp_path / "stricat.jpg"
    bad.write_bytes(b"not an image")
    e = await run(make_task(photo_paths=[str(bad), photo(tmp_path / "foto1.jpg")]), ctx(sink))
    m = by_metric(e)
    assert m["stricat.jpg:unreadable"].value is True and "foto1.jpg:exif_missing" in m


async def test_web_copy_dated_after_the_event_is_not_a_clear_fake(sink, route, fake_llm, tmp_path):
    later = {"responses": [{"webDetection": {"pagesWithMatchingImages": [
        {"url": "https://stiri.test/2024/09/20/dupa-inundatii", "pageTitle": "După inundații",
         "fullMatchingImages": [{"url": "https://stiri.test/img/x.jpg"}]}]}}]}
    route({"vision.googleapis.com": later})
    fake_llm(llm_router())
    m = by_metric(await run(make_task(photo_paths=[photo(tmp_path / "foto1.jpg")], question="?", round=2), ctx(sink, 2)))
    assert "exact_copy_before_event" not in m and m["foto1.jpg:first_seen"].value == "2024-09-20"


async def test_vision_per_image_error_is_a_gap_not_zero_matches(sink, route, fake_llm, tmp_path):
    route({"vision.googleapis.com": {"responses": [{"error": {"code": 7, "message": "API key not valid"}}]}})
    fake_llm(llm_router())
    e = await run(make_task(photo_paths=[photo(tmp_path / "foto1.jpg")], question="?", round=2), ctx(sink, 2))
    assert "foto1.jpg:web_matches" not in by_metric(e) and any("Google Vision" in g for g in e.gaps)
    assert not [p for p in (tmp_path / "cache").rglob("*.json") if "API key not valid" in p.read_text()]
