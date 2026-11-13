"""Check a candidate demo address: rain, gusts and terrain height around it. No API key needed.

    python scripts/check_site.py 45.63 27.80 2024-09-14

Use it to pick (a) a flood house that sits clearly higher than its surroundings and
(b) a storm date and place where gusts reach 70 km/h in this data source.
"""
import sys
from datetime import date, timedelta
from math import cos, radians, sin, pi

import httpx

UA = {"User-Agent": "ClaimLens-hackathon/0.1"}


def main(lat: float, lon: float, day: str) -> None:
    d = date.fromisoformat(day)
    w = httpx.get("https://archive-api.open-meteo.com/v1/archive", headers=UA, timeout=30, params={
        "latitude": lat, "longitude": lon, "start_date": d - timedelta(days=2), "end_date": d + timedelta(days=2),
        "daily": "precipitation_sum,wind_gusts_10m_max", "timezone": "Europe/Bucharest"}).json()["daily"]
    print(f"Weather at {lat}, {lon} (Open-Meteo archive)")
    print(f"  {'date':<12}{'rain mm':>9}{'gust km/h':>11}")
    for t, r, g in zip(w["time"], w["precipitation_sum"], w["wind_gusts_10m_max"]):
        print(f"  {t:<12}{r:>9}{g:>11}{'   <- event day' if t == day else ''}")

    pts = [(lat, lon)]
    for k in range(8):  # 8 points on a 150 m circle
        a = 2 * pi * k / 8
        pts.append((lat + 150 * cos(a) / 111_320, lon + 150 * sin(a) / (111_320 * cos(radians(lat)))))
    e = httpx.get("https://api.open-meteo.com/v1/elevation", headers=UA, timeout=30, params={
        "latitude": ",".join(f"{p[0]:.6f}" for p in pts), "longitude": ",".join(f"{p[1]:.6f}" for p in pts)}).json()["elevation"]
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    print(f"\nHeight above sea level: house {e[0]} m")
    for name, h in zip(names, e[1:]):
        print(f"  150 m {name:<3}{h:>7} m   ({h - e[0]:+.0f} m vs house)")
    print(f"\nLowest point nearby is {e[0] - min(e[1:]):.0f} m below the house. "
          "For the fraud case this should be 5 m or more, on the side facing the flooded area.")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(float(sys.argv[1]), float(sys.argv[2]), sys.argv[3])
