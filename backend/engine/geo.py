"""Small geometry helper shared by the engine and the agents."""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a = sin(radians(lat2 - lat1) / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * asin(sqrt(a))
