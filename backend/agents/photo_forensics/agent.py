"""Photo forensics: are the photos authentic, recent, from the address, and do they show the declared damage?

Quick checks (every round, local or one vision call): EXIF date and GPS, the same image in another claim
(perceptual hash), a vision model's read of each photo.
On the Judge's request: web-wide copy search (Google Cloud Vision, Web Detection) with first-published dates read from the page address.
A copy published before the event produces the finding `exact_copy_before_event`, which the score treats as a gate.
"""
from __future__ import annotations

import base64
import io
import os
import re
from datetime import date
from pathlib import Path

from PIL import Image

from agents.common import conclude, event_day, main_hypothesis
from engine.context import AgentContext, BudgetExceeded
from engine.graph import AgentTask
from engine.http import SourceError
from engine.models import Evidence, Finding
from engine.photos import HASH_DISTANCE, check_photos, image_hash, read_exif  # noqa: F401  (re-exported)

VISION_URL = "https://vision.googleapis.com/v1/images:annotate"
ROLE = "autenticitatea fotografiilor: metadate, copii în alte dosare sau pe web, ce arată imaginile."
MAX_VISION_PHOTOS = 4
GUIDANCE = ("Lipsa metadatelor EXIF este frecventă (aplicații de mesagerie le șterg): singură este 'inconclusive'. "
            "O dată EXIF cu multe zile înaintea evenimentului, o copie în alt dosar sau o copie pe web publicată "
            "înainte de eveniment contrazic puternic (strength ≥ 0.8). O copie pe web fără dată nu e concludentă.")

VISION_SYSTEM = """Analizezi fotografii dintr-un dosar de daună la o locuință. Pentru fiecare fotografie, în ordinea primită:
- shows_declared_damage: true/false/null – arată dauna descrisă de client?
- looks_generated: true/false – are semne clare de imagine generată sau editată artificial?
- description: o propoziție, în română, despre ce se vede.
Fii prudent: fără semne clare, looks_generated este false.
JSON: {"photos": [{"index": 0, "shows_declared_damage": true, "looks_generated": false, "description": "..."}]}"""

DATE_IN_URL = re.compile(r"(20\d\d)[/-](\d{1,2})[/-](\d{1,2})")


def _vision_ok(data) -> bool:
    """Vision reports a bad key or a bad image inside an HTTP 200 answer; that is a failed source."""
    responses = data.get("responses") if isinstance(data, dict) else None
    return bool(responses) and not any("error" in (r or {}) for r in responses)


def small_jpeg(img: Image.Image, side: int = 1024) -> bytes:
    img = img.convert("RGB")
    img.thumbnail((side, side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


async def run(task: AgentTask, ctx: AgentContext) -> Evidence:
    c = task.claim
    paths = [p for p in c.get("photo_paths") or [] if Path(p).is_file()]
    if not paths:
        return ctx.inconclusive(main_hypothesis(task), "Nu există fotografii în dosar")

    event = event_day(task)
    findings: list[Finding] = []
    gaps: list[str] = []
    readable: list[tuple[str, str, bytes]] = []          # (name, path, small jpeg)
    other_count = len([h for h in map(image_hash, c.get("other_photo_paths") or []) if h is not None])

    def f(name, check, value, source, unit=None, url=None):
        findings.append(Finding(metric=f"{name}:{check}", value=value, unit=unit, source=source, url=url))

    # 1. local checks (EXIF, copies in other claims): reuse the intake step's result when it is there
    pre = c.get("photo_findings")
    if isinstance(pre, list):
        findings.extend(x if isinstance(x, Finding) else Finding(**x) for x in pre)
    else:
        house = (c["lat"], c["lon"]) if c.get("lat") is not None and c.get("lon") is not None else None
        findings.extend(check_photos([Path(p) for p in paths], str(event), house,
                                     [Path(p) for p in c.get("other_photo_paths") or []])[1])
    for path in paths:
        name = Path(path).name
        try:
            with Image.open(path) as img:
                img.load()
                jpeg = small_jpeg(img)
        except Exception:
            gaps.append(f"{name} nu a putut fi citită ca imagine")
            continue
        readable.append((name, path, jpeg))
    ctx.note("observation", f"Metadate citite pentru {len(readable)} din {len(paths)} fotografii; "
                            f"comparate cu {other_count} fotografii din alte dosare",
             {"photos": [n for n, _, _ in readable]}, ["EXIF"])
    if not readable:
        return Evidence(agent=ctx.agent, round=ctx.round, hypothesis=main_hypothesis(task), verdict="inconclusive",
                        strength=0, data_quality=0, findings=findings, gaps=gaps)

    # 2. what the photos show (one vision call)
    shown = readable[:MAX_VISION_PHOTOS]
    try:
        out = await ctx.llm(VISION_SYSTEM, f"Dauna declarată: {c.get('description')} (tip: {c.get('damage_type')}). "
                                           f"Fotografii, în ordine: {[n for n, _, _ in shown]}",
                            images=[j for _, _, j in shown])
        for i, item in enumerate(out.get("photos") or []):
            idx = item.get("index", i)
            if isinstance(idx, int) and 0 <= idx < len(shown):
                name = shown[idx][0]
                f(name, "shows_declared_damage", item.get("shows_declared_damage"), "Model de viziune")
                f(name, "looks_generated", bool(item.get("looks_generated")), "Model de viziune")
                if item.get("description"):
                    f(name, "description", str(item["description"])[:200], "Model de viziune")
        ctx.note("observation", f"Analiză vizuală pentru {len(shown)} fotografii", sources=["Model de viziune"])
    except SourceError:
        gaps.append("Analiza vizuală a fotografiilor nu a fost disponibilă")
    if len(readable) > MAX_VISION_PHOTOS:
        gaps.append(f"Doar primele {MAX_VISION_PHOTOS} fotografii au fost analizate vizual")

    # 3. web-wide copy search, only when the Judge asks
    if task.question:
        key = os.environ.get("GOOGLE_API_KEY", "")
        searched = 0
        for name, _, jpeg in readable:
            body = {"requests": [{"image": {"content": base64.b64encode(jpeg).decode()},
                                  "features": [{"type": "WEB_DETECTION", "maxResults": 10}]}]}
            try:
                data = await ctx.fetch("Google Vision – căutare copii pe web", VISION_URL, method="POST",
                                       params={"key": key}, json_body=body, timeout=30, validate=_vision_ok)
            except BudgetExceeded:
                break
            except SourceError:
                gaps.append("Google Vision nu a răspuns: căutarea de copii pe web lipsește")
                break
            searched += 1
            web = ((data.get("responses") or [{}])[0] or {}).get("webDetection") or {}
            pages = [p for p in web.get("pagesWithMatchingImages") or [] if p.get("fullMatchingImages")]
            f(name, "web_matches", len(pages), "Google Vision Web Detection")
            if not pages:
                continue
            # First-published date: only what is literally written in the page address (…/2024/03/18/…).
            # No model is asked, because this date can force an antifraud referral.
            firsts = []
            for p in pages:
                m = DATE_IN_URL.search(str(p.get("url") or ""))
                if m:
                    try:
                        firsts.append((date(int(m[1]), int(m[2]), int(m[3])), p["url"]))
                    except ValueError:
                        pass
            if firsts:
                first, url = min(firsts)
                f(name, "first_seen", first.isoformat(), "Google Vision Web Detection", url=url)
                if first < event:
                    findings.append(Finding(metric="exact_copy_before_event", value=True,
                                            source="Google Vision Web Detection", url=url))
                    ctx.note("observation", f"{name}: copie exactă publicată pe {first.isoformat()}, înainte de eveniment",
                             {"url": url}, ["Google Vision Web Detection"])
            else:
                gaps.append(f"{name}: copii găsite pe web, fără dată de publicare în adresa paginii")
        if searched < len(readable) and not any("Google Vision nu a răspuns" in g for g in gaps):
            gaps.append(f"{len(readable) - searched} fotografii nu au fost căutate pe web (buget de apeluri)")

    return await conclude(ctx, task, ROLE, findings, GUIDANCE, gaps)
