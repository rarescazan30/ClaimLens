"""The fraud story with all six real agents, every external service faked at the network edge.
Run once 'live', then again in replay mode with the network cut: same result, no cache misses."""
import json

import httpx
import pytest

from agents import AGENTS
from engine import http, llm
from engine.graph import run_investigation
from engine.thresholds import DEFAULT_WEIGHTS
from tests.conftest import fixture_json
from tests.test_photo_forensics import WEB, photo
from tests.test_satellite import SEARCH, SQUARE, dashboard
from tests.test_street_view import MAPILLARY

POLICY = {"id": "P", "address": "Str. X 1, Pechea, jud. Galați", "valid_from": "2024-01-01", "valid_to": "2024-12-31",
          "waiting_days": 0, "covered_risks": ["flood"], "sum_insured": 100000, "product": "PAD"}
ARTICLES = {"articles": [{"url": "https://ziar.test/pechea", "title": "Inundații la Pechea", "domain": "ziar.test"}]}


def network(request):
    url = str(request.url)
    table = {"archive-api.open-meteo.com": fixture_json("meteo/daily.json"),
             "api.open-meteo.com/v1/elevation": {"elevation": [47.0, 41.0]},
             "activations/api/activations": SEARCH, "public-activations": dashboard(), "s3.test": SQUARE,
             "overpass": fixture_json("risk_zones/overpass.json"), "api.gdeltproject.org": ARTICLES,
             "graph.mapillary.com": MAPILLARY, "vision.googleapis.com": WEB}
    for needle, body in table.items():
        if needle in url:
            return httpx.Response(200, json=body)
    return httpx.Response(404)


async def model(payload):
    system = payload["messages"][0]["content"]
    user = payload["messages"][1]["content"]
    text = user if isinstance(user, str) else user[0]["text"]
    if "Orchestratorul" in system:
        return json.dumps({"hypotheses": [
            {"id": "H1", "text": "Precipitații ≥ 30 mm în 24 h", "critical": True, "agents": ["meteo", "news"]},
            {"id": "H2", "text": "Adresa a fost inundată", "critical": True, "agents": ["satellite", "risk_zones"]},
            {"id": "H3", "text": "Fotografii autentice", "critical": True, "agents": ["photo_forensics", "street_view"]}]})
    if "Judge-ul" in system:
        if "Runda 1" in text:
            return json.dumps({"marks": {"H1": "confirmed", "H2": "conflicting", "H3": "inconclusive"},
                               "tensions": ["Casa e în afara zonei inundate, dar clientul declară apă în casă."],
                               "action": "redispatch", "redispatch": [
                                   {"agent": "risk_zones", "question": "Care e diferența de nivel față de marginea apei?"},
                                   {"agent": "photo_forensics", "question": "Au mai fost publicate aceste fotografii?"}]})
        return json.dumps({"marks": {"H1": "confirmed", "H2": "refuted", "H3": "refuted"}, "tensions": [], "action": "stop"})
    if "Analizezi fotografii" in system:
        return json.dumps({"photos": [{"index": 0, "shows_declared_damage": True, "looks_generated": False, "description": "apă"}]})
    if "prima publicare" in system:
        return json.dumps({"pages": [{"url": "https://stiri.test/2024/03/18/inundatii-vrancea", "first_seen": "2024-03-18"}]})
    if "Selectezi relatări" in system:
        return json.dumps({"relevant": [0]})
    if "elevation_diff_m" in text or "exact_copy_before_event" in text:
        return json.dumps({"verdict": "contradicts", "strength": 0.9, "data_quality": 0.8, "reasoning_steps": ["contrazice"]})
    if "inside_flood_extent" in text or "exif_missing" in text or "pre_event_image_date" in text:
        return json.dumps({"verdict": "inconclusive", "strength": 0.2, "data_quality": 0.6, "reasoning_steps": ["neconcludent"]})
    return json.dumps({"verdict": "supports", "strength": 0.7, "data_quality": 0.6, "reasoning_steps": ["susține"]})


async def investigate(sink, tmp_path):
    from math import cos, radians
    lon = 27.80 - 150 / (111_320 * cos(radians(45.635)))          # 150 m west of the fake flood square
    claim = {"id": "C-1042", "damage_type": "flood", "event_date": "2024-09-14", "notified_at": "2024-09-19",
             "address": "Str. X 1, Pechea, jud. Galați", "lat": 45.635, "lon": lon, "description": "apă în casă, 60 cm",
             "amount_claimed": 48000, "photos": ["foto1.jpg"], "photo_paths": [photo(tmp_path / "foto1.jpg")],
             "other_photo_paths": [], "footprints": []}
    return await run_investigation(claim, POLICY, DEFAULT_WEIGHTS[0], sink, agents=AGENTS)


async def test_fraud_story_live_then_offline(sink, tmp_path, monkeypatch):
    from agents.news import agent as news
    from tests.conftest import FakeSink
    monkeypatch.setattr(news, "PAUSE_S", 0)
    monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(network))
    monkeypatch.setattr(llm, "_complete", model)

    live = await investigate(sink, tmp_path)
    rounds = [r for r, _ in sink.scores]
    assert rounds == [1, 2]
    first, second = sink.scores[0][1], sink.scores[1][1]
    assert first.band in ("likely", "uncertain", "very_likely") and first.recommendation != "antifraud_referral"
    assert second.score < 35 and live.recommendation == "antifraud_referral"
    assert [g.kind for g in live.gates] == ["clear_fake"]
    assert sorted({e.agent for e in sink.ev if e.round == 1}) == sorted(AGENTS)
    assert sorted(e.agent for e in sink.ev if e.round == 2) == ["photo_forensics", "risk_zones"]
    assert all(e.verdict != "inconclusive" or e.gaps or e.findings for e in sink.ev)
    assert not [s for s in sink.steps if s.status == "failed"]
    assert sink.steps[-1].step_id == "final"

    # offline: network cut, model unreachable, everything must come from the cache
    def cut(request):
        raise httpx.ConnectError("no network")

    async def no_model(payload):
        raise llm.LLMError("no network")
    monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(cut))
    monkeypatch.setattr(llm, "_complete", no_model)
    monkeypatch.setenv("REPLAY", "1")
    offline_sink = FakeSink()
    offline = await investigate(offline_sink, tmp_path)
    assert (offline.score, offline.recommendation) == (live.score, live.recommendation)
    assert not [s for s in offline_sink.steps if s.status == "failed"]
    assert [s.step_id for s in offline_sink.steps] == [s.step_id for s in sink.steps]
