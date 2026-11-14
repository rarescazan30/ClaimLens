import httpx
import pytest

from engine import http, llm


def transport(handler):
    calls = []

    def wrapped(request):
        calls.append(request)
        return handler(request)
    return httpx.MockTransport(wrapped), calls


async def test_live_mode_calls_the_source_every_time(route):
    calls = route({"example.org": {"ok": 1}})
    await http.fetch("https://example.org/a")
    await http.fetch("https://example.org/a")
    assert len(calls) == 2
    assert http.served_from_cache() is False


async def test_live_mode_does_not_write_the_cache(route, tmp_path):
    route({"example.org": {"ok": 1}})
    await http.fetch("https://example.org/a")
    assert not any((tmp_path / "cache").rglob("*.json"))


async def test_record_mode_overwrites_and_replay_reads_it(route, monkeypatch):
    monkeypatch.setenv("RECORD", "1")
    route({"example.org": {"v": 2}})
    await http.fetch("https://example.org/a")
    monkeypatch.delenv("RECORD")
    monkeypatch.setenv("REPLAY", "1")
    calls = route({"example.org": {"v": 3}})
    calls.clear()  # route() shares one list across installs
    assert await http.fetch("https://example.org/a") == {"v": 2}
    assert calls == [] and http.served_from_cache() is True


async def test_record_mode_calls_the_source_even_when_a_saved_answer_exists(route, monkeypatch):
    monkeypatch.setenv("RECORD", "1")
    calls = route({"example.org": {"v": 1}})
    await http.fetch("https://example.org/a")
    route({"example.org": {"v": 2}})
    assert await http.fetch("https://example.org/a") == {"v": 2}
    assert http.served_from_cache() is False


async def test_forced_replay_reads_the_cache_even_in_live_mode(route, monkeypatch):
    monkeypatch.setenv("RECORD", "1")
    route({"example.org": {"v": 2}})
    await http.fetch("https://example.org/a")
    monkeypatch.delenv("RECORD")
    calls = route({"example.org": {"v": 3}})
    calls.clear()
    assert await http.fetch("https://example.org/a", replay=True) == {"v": 2}
    assert calls == [] and http.served_from_cache() is True


def test_run_mode_from_environment(monkeypatch):
    from engine import modes
    assert modes.run_mode() == "live"
    monkeypatch.setenv("RECORD", "1")
    assert modes.run_mode() == "record"
    monkeypatch.setenv("RECORD", "0")
    assert modes.run_mode() == "live"
    monkeypatch.setenv("RECORD", "1")
    monkeypatch.setenv("REPLAY", "1")
    assert modes.run_mode() == "replay"


async def test_failure_is_retried_once_then_raises(monkeypatch):
    t, calls = transport(lambda r: httpx.Response(503))
    monkeypatch.setattr(http, "TRANSPORT", t)
    with pytest.raises(http.SourceError):
        await http.fetch("https://x.test/down")
    assert len(calls) == 2


async def test_replay_without_cache_is_a_cache_miss(monkeypatch):
    t, calls = transport(lambda r: httpx.Response(200, json={}))
    monkeypatch.setattr(http, "TRANSPORT", t)
    monkeypatch.setenv("REPLAY", "1")
    with pytest.raises(http.CacheMiss):
        await http.fetch("https://x.test/never")
    assert calls == []


async def test_api_keys_do_not_change_the_cache_key_or_reach_disk(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORD", "1")
    t, calls = transport(lambda r: httpx.Response(200, json={"ok": 1}))
    monkeypatch.setattr(http, "TRANSPORT", t)
    await http.fetch("https://x.test/k", params={"key": "SECRET1", "q": 1}, headers={"Authorization": "Bearer SECRET2"})
    monkeypatch.delenv("RECORD")
    monkeypatch.setenv("REPLAY", "1")
    assert await http.fetch("https://x.test/k", params={"key": "other", "q": 1}) == {"ok": 1}
    blob = "".join(p.read_text() for p in (tmp_path / "cache").rglob("*.json"))
    assert "SECRET1" not in blob and "SECRET2" not in blob


async def test_user_agent_is_always_sent(monkeypatch):
    t, calls = transport(lambda r: httpx.Response(200, json={}))
    monkeypatch.setattr(http, "TRANSPORT", t)
    await http.fetch("https://x.test/ua")
    assert calls[0].headers["user-agent"] == "ClaimLens-hackathon/0.1"


async def test_bytes_round_trip_through_cache(monkeypatch):
    monkeypatch.setenv("RECORD", "1")
    t, calls = transport(lambda r: httpx.Response(200, content=b"\x89PNG"))
    monkeypatch.setattr(http, "TRANSPORT", t)
    assert await http.fetch("https://x.test/img", as_bytes=True) == b"\x89PNG"
    monkeypatch.delenv("RECORD")
    monkeypatch.setenv("REPLAY", "1")
    assert await http.fetch("https://x.test/img", as_bytes=True) == b"\x89PNG"
    assert len(calls) == 1


async def test_llm_invalid_json_twice_raises(monkeypatch):
    n = []

    async def bad(payload):
        n.append(1)
        return "this is not json"
    monkeypatch.setattr(llm, "_complete", bad)
    with pytest.raises(llm.LLMError):
        await llm.llm_json("s", "u")
    assert len(n) == 2


async def test_llm_parses_fenced_json_and_record_mode_caches(monkeypatch):
    monkeypatch.setenv("RECORD", "1")
    n = []

    async def good(payload):
        n.append(1)
        return '```json\n{"verdict": "supports"}\n```'
    monkeypatch.setattr(llm, "_complete", good)
    assert await llm.llm_json("s", "u") == {"verdict": "supports"}
    monkeypatch.delenv("RECORD")
    monkeypatch.setenv("REPLAY", "1")
    assert await llm.llm_json("s", "u") == {"verdict": "supports"}
    assert len(n) == 1


async def test_llm_live_mode_asks_the_provider_every_time(monkeypatch, tmp_path):
    n = []

    async def good(payload):
        n.append(1)
        return '{"verdict": "supports"}'
    monkeypatch.setattr(llm, "_complete", good)
    await llm.llm_json("s", "u")
    await llm.llm_json("s", "u")
    assert len(n) == 2 and not any((tmp_path / "cache").rglob("*.json"))
    assert http.served_from_cache() is False


async def test_response_failing_validation_is_an_error_and_is_not_cached(monkeypatch, tmp_path):
    t, calls = transport(lambda r: httpx.Response(200, text="Please limit requests"))
    monkeypatch.setattr(http, "TRANSPORT", t)
    with pytest.raises(http.SourceError):
        await http.fetch("https://x.test/limited", as_text=True, validate=lambda body: body.startswith("{"))
    assert len(calls) == 2 and not list((tmp_path / "cache").rglob("*.json"))


async def test_error_messages_never_contain_secret_params(monkeypatch):
    t, calls = transport(lambda r: httpx.Response(403))
    monkeypatch.setattr(http, "TRANSPORT", t)
    with pytest.raises(http.SourceError) as err:
        await http.fetch("https://maps.test/meta", params={"key": "AIzaSECRET", "access_token": "MLYSECRET", "q": "x"})
    assert "AIzaSECRET" not in str(err.value) and "MLYSECRET" not in str(err.value)
    assert "403" in str(err.value) and "maps.test/meta" in str(err.value)


async def test_llm_provider_error_is_retried_once(monkeypatch):
    n = []

    async def flaky(payload):
        n.append(1)
        if len(n) == 1:
            raise llm.LLMError("OpenRouter failed: ReadTimeout")
        return '{"verdict": "supports"}'
    monkeypatch.setattr(llm, "_complete", flaky)
    assert await llm.llm_json("s", "u2") == {"verdict": "supports"}
    assert len(n) == 2


async def test_llm_answer_with_two_objects_or_trailing_text_uses_the_first_object(monkeypatch):
    async def two(payload):
        return '{"verdict": "supports", "note": "a } brace"}\n\n{"verdict": "inconclusive"}\nExplicație suplimentară.'
    monkeypatch.setattr(llm, "_complete", two)
    assert await llm.llm_json("s", "u3") == {"verdict": "supports", "note": "a } brace"}
