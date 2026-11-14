"""Address -> coordinates through Nominatim, with how precisely the address was found."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from engine import http

NOMINATIM = "https://nominatim.openstreetmap.org/search"


class GeoHit(BaseModel):
    lat: float
    lon: float
    precision: Literal["house", "street", "town"]


def _precision(addresstype: str | None) -> str:
    if addresstype in ("house", "building"):
        return "house"
    if addresstype == "road":
        return "street"
    return "town"


async def geocode(address: str) -> GeoHit | None:
    """None when the address is not found or the source fails (the caller turns that into a flag)."""
    try:
        hits = await http.fetch(NOMINATIM, params={"q": address, "format": "json", "limit": 1, "addressdetails": 1},
                                validate=lambda b: isinstance(b, list))
        top = hits[0]
        return GeoHit(lat=float(top["lat"]), lon=float(top["lon"]), precision=_precision(top.get("addresstype")))
    except (http.SourceError, IndexError, KeyError, TypeError, ValueError):
        return None
