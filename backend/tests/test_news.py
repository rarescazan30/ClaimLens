from agents.news import agent as news
from agents.news.agent import run
from engine.context import AgentContext
from tests.conftest import by_metric, make_task

ARTICLES = {"articles": [
    {"url": f"https://ziar{i}.test/inundatii-pechea", "title": t, "seendate": "20240914T120000Z", "domain": f"ziar{i}.test", "language": "Romanian"}
    for i, t in enumerate(["Inundații la Pechea: zeci de case sub apă", "Cod roșu în Galați, sate inundate",
                           "Pechea, Galați: oameni evacuați după viitură", "Meci amânat la Galați",
                           "Prețul grâului scade", "Festival la Brăila", "Accident pe DN25", "Horoscop"])]}
RATE_LIMIT = "Please limit requests to one every 5 seconds or contact kalev.leetaru5@gmail.com for larger queries."


def ctx(sink):
    return AgentContext("C-1", "news", 1, sink)


def filter_llm(relevant=(0, 1, 2)):
    def answer(system, user, kw):
        if "relatări" in system.lower() and "selectezi" in system.lower():
            return {"relevant": list(relevant)}
        if kw.get("model", "fast") not in ("fast", "strong"):   # web-search model
            return {"reports": [{"title": "Viitură la Pechea", "outlet": "Presa Test", "url": "https://presa.test/pechea",
                                 "date": "2024-09-14"}]}
        return {"verdict": "supports", "strength": 0.6, "data_quality": 0.7}
    return answer


async def test_only_articles_the_filter_confirms_become_findings(sink, route, fake_llm, monkeypatch):
    calls = route({"api.gdeltproject.org": ARTICLES})
    seen = fake_llm(filter_llm())
    e = await run(make_task(address="Str. X 1, Pechea, jud. Galați"), ctx(sink))
    m = by_metric(e)
    reports = [f for f in e.findings if f.metric == "news_report"]
    assert m["reports_confirmed"].value == 3 and len(reports) == 3
    assert reports[0].url == "https://ziar0.test/inundatii-pechea" and reports[0].source == "ziar0.test"
    assert len(calls) == 1 and "startdatetime=20240913" in str(calls[0].url) and "enddatetime=20240921" in str(calls[0].url)
    assert "Pechea" in str(calls[0].url) and "Galati" in str(calls[0].url)      # one query covers village and county
    assert not any("rezervă" in g for g in e.gaps)                             # GDELT answered, so its reports are used
    assert any("Pechea" in user for _, user, _ in seen)


async def test_rate_limit_text_switches_to_the_web_search_backup(sink, route, fake_llm, monkeypatch):
    route({"api.gdeltproject.org": RATE_LIMIT})
    seen = fake_llm(filter_llm())
    e = await run(make_task(), ctx(sink))
    reports = [f for f in e.findings if f.metric == "news_report"]
    assert [r.url for r in reports] == ["https://presa.test/pechea"]
    assert any("căutare web" in g.lower() for g in e.gaps)
    assert "0.5" in seen[-1][1]  # the concluding prompt is told backup reports cap data quality


async def test_no_reports_anywhere_is_inconclusive_not_contradicting(sink, route, fake_llm, monkeypatch):
    route({"api.gdeltproject.org": {"articles": []}})

    def answer(system, user, kw):
        return {"reports": []} if kw.get("model", "fast") not in ("fast", "strong") else {"relevant": []}
    fake_llm(answer)
    e = await run(make_task(), ctx(sink))
    assert e.verdict == "inconclusive" and by_metric(e)["reports_confirmed"].value == 0


async def test_everything_down_is_inconclusive(sink, route, fake_llm, monkeypatch):
    from engine.llm import LLMError
    route({"api.gdeltproject.org": 500})
    fake_llm(LLMError("down"))
    e = await run(make_task(), ctx(sink))
    assert e.verdict == "inconclusive" and "GDELT" in e.gaps[0]


async def test_reports_without_a_link_are_dropped(sink, route, fake_llm, monkeypatch):
    route({"api.gdeltproject.org": {"articles": []}})

    def answer(system, user, kw):
        if kw.get("model", "fast") not in ("fast", "strong"):
            return {"reports": [{"title": "fără link", "outlet": "x", "url": None}, {"title": "ok", "outlet": "y", "url": "https://y.test/a"}]}
        return {"verdict": "supports", "strength": 0.4, "data_quality": 0.4}
    fake_llm(answer)
    e = await run(make_task(), ctx(sink))
    assert [f.url for f in e.findings if f.metric == "news_report"] == ["https://y.test/a"]


async def test_gdelt_and_web_search_run_side_by_side_so_a_slow_gdelt_does_not_hold_the_round(sink, route, fake_llm):
    import asyncio
    import time

    import httpx

    async def slow(request):
        await asyncio.sleep(0.4)
        return httpx.Response(200, json={"articles": []})
    from engine import http
    http.TRANSPORT = httpx.MockTransport(slow)

    async def answer_slowly(system, user, **kw):
        await asyncio.sleep(0.4)
        if kw.get("model", "fast") not in ("fast", "strong"):
            return {"reports": [{"title": "Viitură la Pechea", "outlet": "Presa", "url": "https://presa.test/p"}]}
        return {"verdict": "supports", "strength": 0.5, "data_quality": 0.4}
    from engine import llm
    orig = llm.llm_json
    llm.llm_json = answer_slowly
    try:
        t0 = time.monotonic()
        e = await run(make_task(), ctx(sink))
        took = time.monotonic() - t0
    finally:
        llm.llm_json, http.TRANSPORT = orig, None
    assert [f.url for f in e.findings if f.metric == "news_report"] == ["https://presa.test/p"]
    assert took < 1.1          # 0.4 (GDELT and search together) + 0.4 (verdict); in sequence it would be 1.2+


async def test_query_does_not_repeat_the_place_when_the_address_has_no_county(sink, route, fake_llm):
    calls = route({"api.gdeltproject.org": {"articles": []}})
    fake_llm(filter_llm())
    await run(make_task(address="Str. X 1, Pechea"), ctx(sink))
    assert "Pechea+OR+Pechea" not in str(calls[0].url)
