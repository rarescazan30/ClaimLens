"""Meteo: did the phenomenon happen at the address, on the date, with enough intensity?

Source: Open-Meteo Historical Weather API (reanalysis). Backup: the same API forced to the coarser ERA5 model.
Quick check: daily rain and gusts around the event. On the Judge's request: the hourly series.
"""
from __future__ import annotations

from agents.common import conclude, day_range, event_day, main_hypothesis
from engine.context import AgentContext
from engine.graph import AgentTask
from engine.http import SourceError
from engine.models import Evidence, Finding
from engine.thresholds import GUST_KMH, RAIN_24H_MM

URL = "https://archive-api.open-meteo.com/v1/archive"
ROLE = "date meteo istorice (precipitații, rafale) la adresa și data declarate."
SITE = "https://open-meteo.com/en/docs/historical-weather-api"


def _max(values) -> float | None:
    values = [v for v in values if v is not None]
    return max(values) if values else None


async def run(task: AgentTask, ctx: AgentContext) -> Evidence:
    c = task.claim
    start, end = day_range(task, 2, 7)
    base = {"latitude": c["lat"], "longitude": c["lon"], "timezone": "Europe/Bucharest"}
    daily = {**base, "start_date": start, "end_date": end,
             "daily": "precipitation_sum,wind_gusts_10m_max,snowfall_sum"}
    try:
        source, data = await ctx.fetch_first([
            ("Open-Meteo (reanaliză, ~9 km)", URL, {"params": daily}),
            ("Open-Meteo ERA5 (~25 km)", URL, {"params": {**daily, "models": "era5"}}),
        ])
    except SourceError:
        return ctx.inconclusive(main_hypothesis(task), "Open-Meteo nu a răspuns (sursa principală și cea de rezervă)")

    res = 25 if "ERA5 (" in source else 9
    d = data["daily"]
    days, rain, gust = d["time"], d["precipitation_sum"], d["wind_gusts_10m_max"]
    snow = d.get("snowfall_sum") or []
    ev = event_day(task).isoformat()
    i = days.index(ev) if ev in days else 2
    near = slice(max(i - 1, 0), i + 2)                    # event day ± 1
    rain3 = [sum(v or 0 for v in rain[k:k + 3]) for k in range(max(i - 2, 0), min(i + 1, len(rain) - 2))]

    def f(metric, value, unit):
        return Finding(metric=metric, value=value, unit=unit, source=source, url=SITE, spatial_res_km=res)

    peak = _max(rain[near])
    peak_day = days[near][rain[near].index(peak)] if peak is not None else None
    findings = [f("precipitation_event_day", rain[i], "mm"),
                f("precipitation_24h_max", peak, "mm"),
                f("precipitation_24h_max_date", peak_day, None),
                f("precipitation_72h_max", round(max(rain3), 1) if rain3 else None, "mm"),
                f("wind_gusts_event_day", gust[i], "km/h"),
                f("wind_gusts_10m_max", _max(gust[near]), "km/h"),
                f("wind_gusts_10m_max_date",
                  days[near][gust[near].index(_max(gust[near]))] if _max(gust[near]) is not None else None, None)]
    if _max(snow[near]):
        findings.append(f("snowfall_24h_max", _max(snow[near]), "cm"))

    gaps = [f"Rezoluție spațială ~{res} km: nu surprinde fenomene foarte locale"]
    if task.question:  # deeper check, only when the Judge asks
        h_start, h_end = day_range(task, 1, 1)
        try:
            hourly = (await ctx.fetch(source, URL, params={
                **base, "start_date": h_start, "end_date": h_end, "hourly": "precipitation,wind_gusts_10m"}))["hourly"]
            findings += [f("precipitation_1h_max", _max(hourly["precipitation"]), "mm"),
                         f("rain_hours_over_1mm", sum(1 for v in hourly["precipitation"] if v and v >= 1), "h"),
                         f("wind_gusts_1h_max", _max(hourly["wind_gusts_10m"]), "km/h")]
        except SourceError:
            gaps.append("Seria orară nu a putut fi obținută")

    guidance = (f"Prag pentru inundație: precipitații ≥ {RAIN_24H_MM} mm în 24 h. " if c["damage_type"] == "flood"
                else f"Prag pentru furtună: rafale ≥ {GUST_KMH} km/h. ")
    guidance += ("Maximele sunt calculate pe ziua evenimentului ± 1 zi; data maximului este în constatări. "
                 "Dacă valoarea din ziua evenimentului sau maximul din zilele vecine atinge pragul, verdictul este "
                 "'supports' cu strength 0.6–0.8. Dacă este clar sub prag, 'contradicts'. Sursa este o reanaliză "
                 "pe grilă, nu o stație meteo: asta limitează data_quality (0.5–0.7), dar nu este un motiv "
                 "pentru 'inconclusive'.")
    return await conclude(ctx, task, ROLE, findings, guidance, gaps)
