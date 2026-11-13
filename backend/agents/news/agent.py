"""News: is there independent local confirmation of the event?

Sources, queried side by side: GDELT DOC API (worldwide news index, no key, often rate-limited) and a
web-search model through OpenRouter. GDELT's reports are preferred when it has any. A fast model keeps only reports that name the place and the event.
No reports found is 'inconclusive': small local events often go unreported.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta

from agents.common import conclude, event_day, main_hypothesis
from agents.satellite.agent import search_terms
from engine.context import AgentContext
from engine.graph import AgentTask
from engine.http import SourceError
from engine.models import Evidence, Finding

GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_REPORTS = 5
ROLE = "confirmări independente din presă ale evenimentului, în localitatea și la data declarate."
WORDS = {"flood": ("(inundatii OR inundații OR viitura OR inundate)", "flood"),
         "storm": ("(furtuna OR furtună OR vijelie OR rafale)", "storm")}
FILTER_SYSTEM = """Selectezi relatări de presă relevante pentru o daună la o locuință.
O relatare e relevantă DOAR dacă titlul se referă la fenomenul declarat (inundație, furtună) în localitatea sau județul indicat.
JSON: {"relevant": [indicii relatărilor relevante]}"""
SEARCH_SYSTEM = """Cauți pe web relatări de presă despre un fenomen natural într-o localitate, la o dată.
Returnezi cel mult 5 relatări reale, fiecare cu link. Nu inventa: dacă nu găsești, lista e goală.
JSON: {"reports": [{"title": "...", "outlet": "...", "url": "https://...", "date": "YYYY-MM-DD"}]}"""


def _valid_gdelt(text: str) -> bool:
    return text.strip() == "" or text.lstrip().startswith("{")


async def run(task: AgentTask, ctx: AgentContext) -> Evidence:
    c, event = task.claim, event_day(task)
    places = search_terms(c["address"]) or [c["address"]]
    county, locality = places[0], places[-1]
    ro, en = WORDS.get(c["damage_type"], WORDS["flood"])
    window = {"startdatetime": (event - timedelta(days=1)).strftime("%Y%m%d000000"),
              "enddatetime": (event + timedelta(days=7)).strftime("%Y%m%d235959")}
    gaps: list[str] = []
    findings: list[Finding] = []

    place = locality if locality == county else f"({locality} OR {county})"

    async def from_gdelt() -> tuple[bool, list[Finding]]:
        """One query for village and county. Returns (GDELT answered, confirmed reports)."""
        try:
            text = await ctx.fetch("GDELT", GDELT, as_text=True, validate=_valid_gdelt, timeout=8, params={
                "query": f"{place} {ro}", "mode": "artlist", "format": "json", "maxrecords": 25,
                "sort": "datedesc", **window})
            items = [a for a in (json.loads(text) if text.strip() else {}).get("articles") or []
                     if a.get("url") and a.get("title")][:25]
        except (SourceError, ValueError):
            return False, []
        if not items:
            return True, []
        try:
            out = await ctx.llm(FILTER_SYSTEM, f"Fenomen: {c['damage_type']}, localitate: {locality}, județ: {county}, "
                                               f"data: {event.isoformat()}.\nRelatări:\n"
                                + "\n".join(f"{i}. {a['title']} ({a.get('domain')})" for i, a in enumerate(items)))
        except SourceError:
            gaps.append("Filtrarea relatărilor GDELT nu a fost disponibilă")
            return True, []
        picked = [items[i] for i in out.get("relevant") or [] if isinstance(i, int) and 0 <= i < len(items)]
        return True, [Finding(metric="news_report", value=a["title"], source=a.get("domain") or "presă", url=a["url"])
                      for a in picked[:MAX_REPORTS]]

    async def from_web_search() -> tuple[bool, list[Finding]]:
        try:
            out = await ctx.llm(SEARCH_SYSTEM, f"Fenomen: {c['damage_type']}. Localitate: {locality}, județul {county}, România. "
                                               f"Perioada: {event.isoformat()} ± câteva zile.",
                                model=os.environ.get("MODEL_SEARCH") or "perplexity/sonar")
        except SourceError:
            return False, []
        return True, [Finding(metric="news_report", value=str(r.get("title") or r["url"]),
                              source=str(r.get("outlet") or "presă"), url=r["url"])
                      for r in out.get("reports") or []
                      if isinstance(r, dict) and str(r.get("url") or "").startswith("http")][:MAX_REPORTS]

    # GDELT is slow and rate-limited, so the web search runs at the same time instead of waiting for it to fail.
    (gdelt_ok, gdelt_reports), (search_ok, search_reports) = await asyncio.gather(from_gdelt(), from_web_search())
    if not gdelt_ok:
        gaps.append("GDELT nu a răspuns (limită de cereri sau serviciu indisponibil)")
    used_backup = not gdelt_reports
    if gdelt_reports:
        findings = gdelt_reports
    elif search_ok:
        findings = search_reports
        if findings:
            gaps.append("Relatările provin din căutare web de rezervă, nu din indexul GDELT")
    elif not gdelt_ok:
        return ctx.inconclusive(main_hypothesis(task), "GDELT și căutarea web de rezervă nu au răspuns")

    count = len(findings)
    findings.append(Finding(metric="reports_confirmed", value=count,
                            source="Căutare web" if used_backup else "GDELT", url="https://www.gdeltproject.org/"))
    ctx.note("observation", f"{count} relatări independente despre eveniment în {locality}",
             {"urls": [f.url for f in findings[:-1]]}, ["Căutare web" if used_backup else "GDELT"])
    if count == 0:
        return Evidence(agent=ctx.agent, round=ctx.round, hypothesis=main_hypothesis(task), verdict="inconclusive",
                        strength=0, data_quality=0.3, findings=findings,
                        gaps=gaps + ["Nicio relatare găsită; evenimentele locale mici rămân adesea neraportate"])
    guidance = ("Mai multe relatări independente care numesc localitatea susțin că fenomenul a avut loc (factor F3). "
                "Presa confirmă evenimentul, nu dauna la această casă: strength rareori peste 0.7. "
                + ("Relatările provin din căutarea web de rezervă: data_quality ≤ 0.5." if used_backup else ""))
    return await conclude(ctx, task, ROLE, findings, guidance, gaps)
