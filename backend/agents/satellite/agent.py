"""Satellite: was the address actually inside the mapped flood?

Source: Copernicus Emergency Management Service (CEMS) Rapid Mapping. The agent finds the activation for the
event, picks the mapped area that contains the address, downloads the flood-extent polygons and measures.
If an earlier claim already investigated this event, the stored event footprint is reused (no network).
A place Copernicus did not map is 'inconclusive', never 'outside the flood'.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

from pyproj import Transformer
from shapely import wkt
from shapely.geometry import Point, shape
from shapely.ops import nearest_points, transform, unary_union

from agents.common import conclude, event_day, haversine_m, main_hypothesis
from engine.context import AgentContext
from engine.graph import AgentTask
from engine.http import SourceError
from engine.models import Evidence, Finding

SEARCH = "https://mapping.emergency.copernicus.eu/activations/api/activations/"
DASHBOARD = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/"
PAGE = "https://mapping.emergency.copernicus.eu/activations/{code}/"
ROLE = "harta Copernicus a zonei inundate: adresa este în interiorul sau în afara zonei cartografiate."
CATEGORY = {"flood": "flood", "storm": "storm"}
LAYER_PREFERENCE = ("maximumFloodExtentA", "observedEventA")
EDGE_TOLERANCE_M = 500   # outside the mapped flood but this close to its edge: never counts against the claim
GUIDANCE = ("Delimitarea din imagini radar are o incertitudine de ±20–30 m la margine, iar Copernicus ratează des "
            "apa de pe străzi și din zonele înguste (între case, sub copaci, în curți). O casă în afara zonei, la cel "
            f"mult {EDGE_TOLERANCE_M} m de margine, este în marja de incertitudine: NU infirmă dauna, marchează "
            "'inconclusive' și sugerează verificarea diferenței de nivel. O casă în interior susține puternic. "
            "Departe (> 500 m) contrazice.")
EDGE_GAP = (f"Casa este la cel mult {EDGE_TOLERANCE_M} m de marginea zonei inundate cartografiate: în marja de "
            "incertitudine (Copernicus ratează des apa de pe străzi și din zonele înguste), deci harta nu contrazice "
            "dauna.")


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def search_terms(address: str) -> list[str]:
    """Place names from the address, most general last part first: '..., Pechea, jud. Galați' → Galati, Pechea."""
    parts = [re.sub(r"\b(judetul|jud|comuna|com|satul|sat|orasul|oras|municipiul|mun)\b\.?", "", _ascii(p),
                    flags=re.I).strip(" .") for p in address.split(",")]
    names = [p for p in parts if p and not re.search(r"\d", p)]
    return list(reversed(names))[:2]


def measure(geojson: dict, lat: float, lon: float) -> dict:
    """Point-in-polygon and distance to the edge, in metres (computed in the local UTM zone)."""
    zone = int((lon + 180) // 6) + 1
    to_utm = Transformer.from_crs(4326, 32600 + zone, always_xy=True).transform
    to_wgs = Transformer.from_crs(32600 + zone, 4326, always_xy=True).transform
    flood = unary_union([transform(to_utm, shape(f["geometry"]).buffer(0)) for f in geojson["features"]])
    house = transform(to_utm, Point(lon, lat))
    inside = bool(flood.contains(house))
    edge_utm = nearest_points(flood.boundary, house)[0]
    edge = transform(to_wgs, edge_utm)
    return {"inside": inside, "distance_m": 0 if inside else round(house.distance(flood), 1),
            "edge": {"lat": round(edge.y, 6), "lon": round(edge.x, 6)}}


async def _find_activation(ctx: AgentContext, task: AgentTask) -> dict | None:
    c, day = task.claim, event_day(task)
    wanted = CATEGORY.get(c["damage_type"], "")
    for term in search_terms(c["address"]):
        data = await ctx.fetch("Copernicus CEMS – căutare activări", SEARCH, params={"q": term, "limit": 20})
        for a in data.get("results") or []:
            try:
                when = datetime.fromisoformat(a["activationTime"]).date()
                centre = wkt.loads(a["centroid"])
            except (KeyError, ValueError, TypeError):
                continue
            if wanted and wanted not in (a.get("category") or {}).get("slug", "").lower():
                continue
            if not (day - timedelta(days=3) <= when <= day + timedelta(days=10)):
                continue
            if haversine_m(c["lat"], c["lon"], centre.y, centre.x) > 150_000:
                continue
            return a
    return None


def _pick_layer(aoi: dict) -> tuple[dict, dict] | None:
    """Latest delineation product that has a flood-extent layer. Returns (product, layer)."""
    products = sorted((p for p in aoi.get("products") or [] if p.get("layers")),
                      key=lambda p: p.get("monitoringNumber") or 0, reverse=True)
    for wanted in LAYER_PREFERENCE:
        for p in products:
            for layer in p["layers"]:
                if wanted in layer.get("name", "") and layer.get("json"):
                    return p, layer
    return None


async def run(task: AgentTask, ctx: AgentContext) -> Evidence:
    c, hyp = task.claim, main_hypothesis(task)
    geojson = code = map_date = layer_url = aoi_name = None

    stored = [f for f in c.get("footprints") or [] if f.get("polygon")]
    if stored:
        fp = stored[0]
        geojson, code = fp["polygon"], fp["id"].split("-")[0]
        meta = fp.get("meteo_maxima") or {}
        map_date, layer_url, aoi_name = meta.get("map_date"), meta.get("geojson_url"), fp.get("name")
        ctx.note("observation", f"Refolosesc amprenta evenimentului deja investigat: {fp.get('name')}",
                 {"footprint": fp["id"]}, fp.get("sources") or [])
    else:
        try:
            activation = await _find_activation(ctx, task)
            if activation is None:
                return ctx.inconclusive(hyp, "Copernicus CEMS nu are o activare pentru acest eveniment și loc; "
                                             "nu există o hartă a zonei inundate")
            code = activation["code"]
            ctx.note("observation", f"Activare găsită: {code} – {activation.get('name')}", {"code": code})
            board = await ctx.fetch("Copernicus CEMS – produse", DASHBOARD, params={"code": code})
            aois = (board.get("results") or [{}])[0].get("aois") or []
            here = Point(c["lon"], c["lat"])
            aoi = next((a for a in aois if wkt.loads(a["extent"]).contains(here)), None)
            if aoi is None:
                return ctx.inconclusive(hyp, f"Adresa este în afara zonelor cartografiate de Copernicus pentru {code}")
            aoi_name = aoi.get("name")
            picked = _pick_layer(aoi)
            if picked is None:
                reasons = {(p.get("version") or {}).get("reason") for p in aoi.get("products") or []} - {"", None}
                return ctx.inconclusive(hyp, f"Copernicus nu a produs harta inundației pentru zona {aoi_name} ({code}): "
                                             + ("; ".join(sorted(reasons)) or "produs indisponibil"))
            product, layer = picked
            layer_url = layer["json"]
            map_date = max((i.get("acquisitionTime") or "" for i in product.get("images") or []), default=None) or None
            geojson = await ctx.fetch("Copernicus CEMS – poligoane", layer_url, timeout=60)
        except SourceError as e:
            return ctx.inconclusive(hyp, f"Copernicus CEMS nu a răspuns ({str(e)[:120]})")

    m = measure(geojson, c["lat"], c["lon"])
    source = f"Copernicus CEMS Rapid Mapping {code}"

    def f(metric, value, unit=None):
        return Finding(metric=metric, value=value, unit=unit, source=source, url=PAGE.format(code=code),
                       spatial_res_km=0.03)

    findings = [f("activation", code), f("mapped_area", aoi_name), f("inside_flood_extent", m["inside"]),
                f("distance_to_flood_edge_m", m["distance_m"], "m"), f("nearest_edge_point", m["edge"]),
                f("map_date", map_date), f("flood_extent_geojson_url", layer_url)]
    where = "în interiorul" if m["inside"] else f"în afara zonei inundate, la {m['distance_m']:.0f} m de"
    ctx.note("observation", f"Casa este {where} marginea zonei cartografiate ({code})", m, [source])
    e = await conclude(ctx, task, ROLE, findings, GUIDANCE,
                       ["Incertitudine a delimitării radar: ±20–30 m la marginea zonei"])
    if e.verdict == "contradicts" and not m["inside"] and m["distance_m"] <= EDGE_TOLERANCE_M:
        e = e.model_copy(update={"verdict": "inconclusive", "gaps": e.gaps + [EDGE_GAP]})
        ctx.note("observation", EDGE_GAP, {"distance_m": m["distance_m"]}, [source])
    return e
