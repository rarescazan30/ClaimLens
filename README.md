# ClaimLens

> The adjuster stops doing research. They get an evidence file with sources, and they decide.

Agentic assistant for home-insurance claim adjusters (natural disasters), built for the **UiPath Hackathon**.
"ClaimLens" is a working name.

📄 Full proposal and research (Romanian): [`docs/proposal.md`](docs/proposal.md)

## What it does

1. **Claim comes in** (claim form + policy + photos). Data is extracted and checked against the policy with
   deterministic rules; photos are checked for authenticity.
2. An **Orchestrator** writes testable hypotheses for the damage type and dispatches specialist agents in
   parallel: meteo, satellite, street view, local news, risk zones, photo forensics.
3. A separate **Judge** weighs the evidence. Where data is missing or agents disagree, it sends one agent back
   with one precise question (max 3 rounds).
4. Output: a **claim plausibility score**, the factors behind it, sources and a recommendation —
   fast-track, standard review or antifraud referral.
5. The **adjuster sees every reasoning step**, can correct it, and makes the decision.
   **The AI never rejects a claim on its own.**

## How it is built

```
 React app ── HTTP + live stream ──► FastAPI backend ──► SQLite
                                        │
                                  Engine (LangGraph)
                    rules → plan → 6 agents in parallel → score → judge ─┐
                                        ▲                                │ one narrow question
                                        └──────── re-dispatch ◄──────────┘   (max 3 rounds)

   meteo        satellite         risk zones            photo forensics        street view            news
   Open-Meteo   Copernicus CEMS   OpenStreetMap + DEM   EXIF + Google Vision   Mapillary + Google     GDELT
```

| # | Stage | How |
| --- | --- | --- |
| 1 | Intake | Claim, policy, address, event date, photos → case ID |
| 2 | Policy cross-check | Five deterministic rules. A failed rule flags the case, never rejects it |
| 3 | Orchestrator plan | 3–5 testable hypotheses, agents assigned, shown in the UI |
| 4 | Investigation loop | Agents in parallel; quick checks first, deeper checks only when the Judge asks |
| 5 | Score | Log-odds formula computed by code, not by a model; gates for coverage and clear fakes |
| 6 | Human decision | Approve / modify (reason required) / investigate more, in the same app |
| 7 | Learning | The event's flood area, weather maxima and news are saved and reused for the next claim nearby |

Rule of thumb: **what rules can verify is deterministic; what needs judgement and search is agentic.**
Every step is recorded as a trace event, streamed live to the UI and replayable.

The engine is a self-contained LangGraph program with no web-server code, so it can also be published as a
UiPath coded agent. Details: [`docs/backend-design.md`](docs/backend-design.md), plan:
[`docs/backend-plan.md`](docs/backend-plan.md), running it: [`backend/README.md`](backend/README.md).

## Demo

Anchored on real events. Claims and people are synthetic. Details and measured numbers: [`demo/README.md`](demo/README.md).

- **"Smart fraud"** — Galați flood of 14.09.2024 (Copernicus CEMS EMSR758). The house is 150 m outside the mapped
  flood but well above its edge, and the photos were published before the event → the Judge re-dispatches in
  round 2 → antifraud referral.
- **Honest case** — roof damaged in the windstorm of 26.11.2023 in Galați (gusts of 90 km/h) → fast-track.

## Repository layout

```
docs/          proposal, shared contracts, backend design and plan
backend/       API (app/), investigation engine (engine/), six agents (agents/), tests
frontend/      adjuster app (React + Vite + TypeScript), connected to the backend; see docs/frontend-integration.md
demo/          demo cases, saved API responses (offline replay), mock data for the UI
ui/, maestro/, data-fabric/   placeholders from the first proposal (not used)
```

## Team

One backend developer, one frontend developer, the rest on demo cases and pitch.
**Deliverables by Sat 14 Nov 2026, 14:00:** code on GitHub, working prototype, 5-min pitch, demo ≤ 5 min.

All six specialist agents are implemented against their real sources. An agent that fails on demo day runs
from its saved responses, and the pitch says which.

## Data sources & licences

Open-Meteo (free for non-commercial use only), Copernicus CEMS Rapid Mapping and Copernicus DEM (free, attribution
required), OpenStreetMap (ODbL), Mapillary (CC BY-SA), Google Street View and Cloud Vision (Google terms), GDELT.

## License

[MIT](LICENSE)
