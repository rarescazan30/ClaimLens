# Shared contracts

Agreed formats every part of the system uses. Change them only after telling the whole team —
agents, Judge, Data Fabric and UI all depend on them.

## Evidence (output of every specialist agent)

Same format for all agents, so the Judge and the UI never depend on a specific agent.

```json
{
  "agent": "meteo",
  "round": 1,
  "hypothesis": "Rafale >= 70 km/h la adresa, 12.11.2026 18:00-23:00",
  "verdict": "supports | contradicts | inconclusive",
  "strength": 0.8,
  "data_quality": 0.6,
  "findings": [
    {"metric": "wind_gusts_10m_max", "value": 87, "unit": "km/h",
     "source": "Open-Meteo ERA5-Land", "url": "...", "spatial_res_km": 9,
     "retrieved_at": "2026-11-13T21:40Z"}
  ],
  "reasoning_steps": ["..."],
  "gaps": ["Rezolutie 9 km, nu prinde rafale locale"],
  "suggested_followup": "Cauta statia meteo cea mai apropiata sau stiri din cartier"
}
```

- `strength` — how much the evidence moves the verdict.
- `data_quality` — how much we can trust the source (resolution, time distance, official or not).
- Kept separate because the Judge uses them differently.

## Trace event (one per step, drives the UI timeline and replay)

```json
{"case_id": "C-1042", "step_id": "r2.risk.3", "parent": "r2.judge",
 "actor": "agent:risk_zones", "type": "tool_call | observation | decision | escalation",
 "summary": "Diferenta de nivel casa vs. marginea poligonului: +6.2 m",
 "inputs": {}, "outputs": {}, "sources": ["Copernicus DEM"],
 "status": "done", "started_at": "...", "ended_at": "..."}
```

## Score

```
logit(P) = logit(P0) + Σ_i  w[t,i] · s_i · q_i · d_i
```

- `P0` base probability per damage type; `w` insurer weight per damage type × agent;
  `s` strength; `q` data_quality; `d` = +1 supports / −1 contradicts / 0 inconclusive.
- F1 (coverage) and clear fakes in F2 are **gates**, not terms in the sum.
- Bands: very likely ≥ 85 · likely 65–85 · uncertain 35–65 · unlikely < 35.
- Called the **claim plausibility score** — never "probability the company pays".
- Weights change prioritisation and the recommendation only. **Nothing is ever rejected automatically.**
