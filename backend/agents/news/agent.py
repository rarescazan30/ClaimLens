"""News: is there independent local confirmation of the event?

Source: GDELT DOC API (worldwide news index, no key, one request every 5 seconds).
Backup: a web-search model through OpenRouter. A fast model keeps only reports that name the place and the event.
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
PAUSE_S = 5          # GDELT asks for at most one request every 5 seconds
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

    # 1. GDELT, two queries
    articles: dict[str, dict] = {}
    gdelt_ok = False
    for i, query in enumerate([f"{locality} {ro}", f"{county} {en}"]):
        if i:
            await asyncio.sleep(PAUSE_S)
        try:
            text = await ctx.fetch("GDELT", GDELT, as_text=True, validate=_valid_gdelt, params={
                "query": query, "mode": "artlist", "format": "json", "maxrecords": 25, "sort": "datedesc", **window})
            gdelt_ok = True
            for a in (json.loads(text) if text.strip() else {}).get("articles") or []:
                if a.get("url") and a.get("title"):
                    articles.setdefault(a["url"], a)
        except (SourceError, ValueError):
            pass
    if not gdelt_ok:
        gaps.append("GDELT nu a răspuns (limită de cereri sau serviciu indisponibil)")

    # 2. keep only reports about this event in this place
    items = list(articles.values())[:25]
    if items:
        try:
            out = await ctx.llm(FILTER_SYSTEM, f"Fenomen: {c['damage_type']}, localitate: {locality}, județ: {county}, "
                                               f"data: {event.isoformat()}.\nRelatări:\n"
                                + "\n".join(f"{i}. {a['title']} ({a.get('domain')})" for i, a in enumerate(items)))
            for i in out.get("relevant") or []:
                if isinstance(i, int) and 0 <= i < len(items) and len(findings) < MAX_REPORTS:
                    a = items[i]
                    findings.append(Finding(metric="news_report", value=a["title"], source=a.get("domain") or "presă",
                                            url=a["url"]))
        except SourceError:
            gaps.append("Filtrarea relatărilor GDELT nu a fost disponibilă")

    # 3. backup: web search, when GDELT gave nothing usable
    used_backup = False
    if not findings:
        try:
            out = await ctx.llm(SEARCH_SYSTEM, f"Fenomen: {c['damage_type']}. Localitate: {locality}, județul {county}, România. "
                                               f"Perioada: {event.isoformat()} ± câteva zile.",
                                model=os.environ.get("MODEL_SEARCH") or "perplexity/sonar")
            for r in out.get("reports") or []:
                if isinstance(r, dict) and str(r.get("url") or "").startswith("http") and len(findings) < MAX_REPORTS:
                    findings.append(Finding(metric="news_report", value=str(r.get("title") or r["url"]),
                                            source=str(r.get("outlet") or "presă"), url=r["url"]))
            used_backup = True
            gaps.append("Relatările provin din căutare web de rezervă, nu din indexul GDELT")
        except SourceError:
            if not gdelt_ok:
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
