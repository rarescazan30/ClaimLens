"""Risk zones: is the house plausibly exposed?

Quick check: distance to the nearest river, stream or lake (OpenStreetMap through Overpass, two servers).
On the Judge's request: height of the house against the nearest point of the flood edge found by the
satellite agent (Copernicus DEM through the Open-Meteo elevation API, ~90 m grid).
"""
from __future__ import annotations

from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

from agents.common import conclude, main_hypothesis
from engine.context import AgentContext
from engine.graph import AgentTask
from engine.http import SourceError
from engine.models import Evidence, Finding

OVERPASS = [("OpenStreetMap (Overpass)", "https://overpass-api.de/api/interpreter"),
            ("OpenStreetMap (Overpass, server de rezervă)", "https://overpass.private.coffee/api/interpreter")]
ELEVATION = "https://api.open-meteo.com/v1/elevation"
DEM = "Copernicus DEM GLO-90 (Open-Meteo Elevation)"
ROLE = "expunerea locuinței: distanța până la apă și diferența de nivel față de zona inundată."
RADIUS_M = 2000
GUIDANCE = ("Apa urcă greu: o casă cu câțiva metri deasupra marginii zonei inundate nu putea avea apă în interior "
            "din revărsare, deci dacă clientul declară apă în casă și casa e cu ≥ 3 m mai sus, verdictul este "
            "'contradicts' cu strength mare. Grila de altitudine are ~90 m, deci diferențe sub 2 m sunt neconcludente. "
            "Doar distanța până la apă, fără altitudine, este un indiciu slab (strength ≤ 0.4).")


def _query(lat: float, lon: float) -> str:
    a = f"(around:{RADIUS_M},{lat},{lon})"
    return (f"[out:json][timeout:25];(way{a}[waterway~\"^(river|stream|canal|drain|ditch)$\"];"
            f"way{a}[natural=water];);out tags geom;")


def _answered(data) -> bool:
    """A busy Overpass server answers HTTP 200 with no elements and a 'remark' saying the query timed out."""
    return isinstance(data, dict) and "elements" in data and "error" not in str(data.get("remark", "")).lower()


def nearest_water(elements: list[dict], lat: float, lon: float) -> dict | None:
    zone = int((lon + 180) // 6) + 1
    fwd = Transformer.from_crs(4326, 32600 + zone, always_xy=True).transform
    back = Transformer.from_crs(32600 + zone, 4326, always_xy=True).transform
    house = Point(*fwd(lon, lat))
    best = None
    for el in elements:
        pts = [fwd(p["lon"], p["lat"]) for p in el.get("geometry") or []]
        if len(pts) < 2:
            continue
        line = LineString(pts)
        d = house.distance(line)
        if best is None or d < best["distance_m"]:
            near = nearest_points(line, house)[0]
            lon2, lat2 = back(near.x, near.y)
            tags = el.get("tags") or {}
            best = {"distance_m": round(d, 1), "name": tags.get("name"),
                    "kind": tags.get("waterway") or tags.get("natural"),
                    "point": {"lat": round(lat2, 6), "lon": round(lon2, 6)}}
    return best


def _flood_edge(task: AgentTask) -> dict | None:
    for e in sorted(task.prior, key=lambda e: e.round, reverse=True):
        if e.agent == "satellite":
            for f in e.findings:
                if f.metric == "nearest_edge_point" and isinstance(f.value, dict):
                    return f.value
    return None


async def run(task: AgentTask, ctx: AgentContext) -> Evidence:
    c = task.claim
    lat, lon = c["lat"], c["lon"]
    findings: list[Finding] = []
    gaps: list[str] = []

    water = None
    try:
        source, data = await ctx.fetch_first([
            (name, url, {"method": "POST", "data": {"data": _query(lat, lon)}, "timeout": 40, "validate": _answered})
            for name, url in OVERPASS])
        water = nearest_water(data.get("elements") or [], lat, lon)
        osm = "https://www.openstreetmap.org/copyright"
        findings.append(Finding(metric="distance_to_water_m", value=water["distance_m"] if water else None, unit="m",
                                source=source, url=osm))
        if water:
            findings += [Finding(metric="water_name", value=water["name"] or f"({water['kind']}, fără nume)", source=source, url=osm),
                         Finding(metric="nearest_water_point", value=water["point"], source=source, url=osm)]
            ctx.note("observation", f"Cea mai apropiată apă: {water['name'] or water['kind']}, la {water['distance_m']:.0f} m",
                     water, [source])
        else:
            ctx.note("observation", f"Nicio apă cartografiată pe o rază de {RADIUS_M} m", sources=[source])
    except SourceError:
        gaps.append("OpenStreetMap (Overpass) nu a răspuns pe niciunul dintre servere: distanța până la apă lipsește")

    if task.question:  # deeper check, only when the Judge asks
        edge = _flood_edge(task)
        other = edge or (water or {}).get("point")
        if other is None:
            gaps.append("Nu există un punct de referință (margine de inundație sau apă) pentru comparația de altitudine")
        else:
            if edge is None:
                gaps.append("Nu se cunoaște marginea zonei inundate; comparația s-a făcut cu cea mai apropiată apă")
            try:
                el = (await ctx.fetch(DEM, ELEVATION, params={"latitude": f"{lat},{other['lat']}",
                                                             "longitude": f"{lon},{other['lon']}"}))["elevation"]
                site = "https://open-meteo.com/en/docs/elevation-api"

                def f(metric, value):
                    return Finding(metric=metric, value=value, unit="m", source=DEM, url=site, spatial_res_km=0.09)
                findings += [f("elevation_house_m", el[0]),
                             f("elevation_flood_edge_m" if edge else "elevation_water_m", el[1]),
                             f("elevation_diff_m", round(el[0] - el[1], 1))]
                gaps.append("Grila de altitudine are ~90 m: diferențele mici de nivel nu sunt de încredere")
                what = "marginea zonei inundate" if edge else "cea mai apropiată apă"
                ctx.note("observation", f"Diferența de nivel casă vs. {what}: {el[0] - el[1]:+.1f} m",
                         {"house_m": el[0], "reference_m": el[1]}, [DEM])
            except (SourceError, KeyError, IndexError, TypeError):
                gaps.append("Serviciul de altitudine nu a răspuns: diferența de nivel lipsește")

    if not findings:
        return ctx.inconclusive(main_hypothesis(task), gaps[0])
    return await conclude(ctx, task, ROLE, findings, GUIDANCE, gaps)
