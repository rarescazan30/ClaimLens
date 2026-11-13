"""Street view: what did the house look like before the event? Was the damage already there?

Sources: Mapillary (community street imagery), then Google Street View.
Quick check: the latest street-level image taken before the event, and its date.
On the Judge's request: a vision model compares that image with the client's photos.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from math import cos, radians
from pathlib import Path

from agents.common import conclude, event_day, haversine_m, main_hypothesis
from agents.photo_forensics.agent import small_jpeg
from engine.context import AgentContext
from engine.graph import AgentTask
from engine.http import SourceError
from engine.models import Evidence, Finding

MAPILLARY = "https://graph.mapillary.com/images"
G_META = "https://maps.googleapis.com/maps/api/streetview/metadata"
G_IMAGE = "https://maps.googleapis.com/maps/api/streetview"
BOX_M = 150         # street imagery is sparse in villages; the distance is reported so it can be weighed
ROLE = "starea locuinței înainte de eveniment, din imagini stradale: dauna era preexistentă?"
GUIDANCE = ("Doar existența unei imagini mai vechi, fără comparație, este 'inconclusive'. Dacă imaginea veche arată "
            "deja dauna declarată, verdictul este 'contradicts'. Dacă arată clădirea întreagă, 'supports' (strength moderat). "
            "Imaginile mai vechi de 3 ani sau făcute la peste 50 m de adresă au data_quality scăzut.")
COMPARE_SYSTEM = """Prima imagine este o fotografie stradală a unei locuințe, făcută ÎNAINTE de evenimentul declarat.
Celelalte sunt fotografiile clientului, făcute după. Compară starea acoperișului și a fațadei.
JSON: {"prior_condition": "o propoziție în română despre starea clădirii în imaginea veche",
"preexisting_damage": true | false | null}   (null dacă nu se poate spune, de exemplu clădirea nu se vede)"""


async def run(task: AgentTask, ctx: AgentContext) -> Evidence:
    c, event = task.claim, event_day(task)
    lat, lon = c["lat"], c["lon"]
    dlat, dlon = BOX_M / 111_320, BOX_M / (111_320 * cos(radians(lat)))
    failed: list[str] = []
    chosen: dict | None = None

    try:
        data = await ctx.fetch("Mapillary", MAPILLARY, params={
            "access_token": os.environ.get("MAPILLARY_TOKEN", ""), "fields": "id,captured_at,thumb_1024_url,geometry",
            "bbox": f"{lon - dlon:.6f},{lat - dlat:.6f},{lon + dlon:.6f},{lat + dlat:.6f}", "limit": 50})
        before = []
        for im in data.get("data") or []:
            try:
                taken = datetime.fromtimestamp(im["captured_at"] / 1000, timezone.utc).date()
                ilon, ilat = im["geometry"]["coordinates"]
            except (KeyError, TypeError, ValueError):
                continue
            if taken < event:
                before.append((taken, im, ilat, ilon))
        if before:
            taken, im, ilat, ilon = max(before, key=lambda x: x[0])
            chosen = {"date": taken.isoformat(), "source": "Mapillary", "image_url": im.get("thumb_1024_url"),
                      "url": f"https://www.mapillary.com/app/?pKey={im['id']}",
                      "distance_m": round(haversine_m(lat, lon, ilat, ilon), 1), "image_kw": {}}
    except SourceError:
        failed.append("Mapillary")

    if chosen is None:
        try:
            key = os.environ.get("GOOGLE_API_KEY", "")
            # a refused key or exhausted quota comes back as HTTP 200 with another status: that is a failed
            # source (and must not be cached), not the same as 'no imagery here'
            meta = await ctx.fetch("Google Street View", G_META, params={"location": f"{lat},{lon}", "radius": BOX_M, "key": key},
                                   validate=lambda m: m.get("status") in ("OK", "ZERO_RESULTS", "NOT_FOUND"))
            if meta.get("status") == "OK" and str(meta.get("date") or "9999") < event.isoformat()[:7]:
                loc = meta.get("location") or {}
                chosen = {"date": meta["date"], "source": "Google Street View", "image_url": G_IMAGE,
                          "url": f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={loc.get('lat', lat)},{loc.get('lng', lon)}",
                          "distance_m": round(haversine_m(lat, lon, loc.get("lat", lat), loc.get("lng", lon)), 1),
                          "image_kw": {"params": {"size": "640x640", "location": f"{lat},{lon}", "radius": BOX_M, "key": key}}}
        except SourceError:
            failed.append("Google Street View")

    if chosen is None:
        if len(failed) == 2:
            return ctx.inconclusive(main_hypothesis(task), "Mapillary și Google Street View nu au răspuns")
        return ctx.inconclusive(main_hypothesis(task), "Nicio imagine stradală dinaintea evenimentului la această adresă")

    src = chosen["source"]

    def f(metric, value, unit=None):
        return Finding(metric=metric, value=value, unit=unit, source=src, url=chosen["url"])

    findings = [f("pre_event_image_date", chosen["date"]), f("pre_event_image_source", src),
                f("pre_event_image_url", chosen["url"]), f("distance_m", chosen["distance_m"], "m")]
    gaps = [f"{s} nu a răspuns" for s in failed]
    ctx.note("observation", f"Imagine stradală din {chosen['date']} ({src}), la {chosen['distance_m']:.0f} m de adresă",
             {"url": chosen["url"]}, [src])

    if task.question:  # deeper check, only when the Judge asks
        client = []
        for p in (c.get("photo_paths") or [])[:2]:
            try:
                from PIL import Image
                with Image.open(p) as im:
                    client.append(small_jpeg(im))
            except Exception:
                pass
        if not client:
            gaps.append("Nu există fotografii ale clientului pentru comparație")
        else:
            try:
                old = await ctx.fetch(f"{src} – imagine", chosen["image_url"], as_bytes=True, **chosen["image_kw"])
                out = await ctx.llm(COMPARE_SYSTEM, f"Dauna declarată: {c.get('description')} ({c.get('damage_type')}).",
                                    images=[old] + client)
                findings += [f("prior_condition", str(out.get("prior_condition") or "")[:300]),
                             f("preexisting_damage", out.get("preexisting_damage"))]
            except SourceError:
                gaps.append("Comparația vizuală cu fotografiile clientului nu a putut fi făcută")
    return await conclude(ctx, task, ROLE, findings, GUIDANCE, gaps)
