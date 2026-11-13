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

## Workflow

| # | Stage | How | UiPath |
| --- | --- | --- | --- |
| 1 | Intake | Claim, policy, address, event date, photos → case ID | Apps / email → Maestro Case |
| 2 | Parsing & validation | Extract fields, ask the client for missing data | IXP |
| 3 | Policy cross-check | Deterministic rules (active, covered, address, deadline) — a failed rule flags, never rejects | API workflow + rules |
| 4 | Photo forensics | EXIF vs date/address, recycled or generated images | Agent |
| 5 | Orchestrator plan | Hypotheses + agent selection, shown in the UI | Coded agent |
| 6 | Investigation loop | Agents in parallel, Judge re-dispatches | Agents + coded agent |
| 7 | Build the case | Score, 5 factors, evidence with sources, recommendation | Data Fabric |
| 8 | Human decision | Approve / modify / investigate more; overrides logged with reason | Action Center |
| 9 | Learning | Event footprint saved and reused for the next claims in the area | Data Fabric + Context Grounding |

Stages 1–3 are fixed; 4–6 adapt to what was found. Rule of thumb: **what rules can verify is
deterministic; what needs judgement and search is agentic.**

## Demo

Anchored on the real **Galați flood, 14.09.2024** (CEMS EMSR758). Claims and people are synthetic.

- **Honest case** — roof torn off in a real storm → fast-track.
- **"Smart fraud"** — house 150 m from the flood polygon but 6 m higher, photos with EXIF from March →
  Judge re-dispatches in round 2 → antifraud referral.

## Repository layout

```
docs/          proposal, shared contracts (evidence, trace, score)
maestro/       case lifecycle (Maestro Case / BPMN), IXP, F1 rules
agents/        specialist agents, one folder each
orchestrator/  Orchestrator + Judge loop
data-fabric/   entity definitions
ui/            adjuster app
demo/          demo cases, cached API responses, backup video
```

## Team & timeline

| When (Fri → Sat) | Deliverable | Who |
| --- | --- | --- |
| 22:00–23:00 | Scope frozen, Data Fabric entities, 2 demo cases, roles | All |
| 23:00–03:00 | IXP + F1 rules; Meteo, Satellite and Risk zones agents end-to-end; trace events | A: Maestro + IXP · B: agents |
| 03:00–08:00 | Photo forensics, Street view and News agents; Orchestrator/Judge loop with all 6 agents | B: agents · C: UI |
| 08:00–11:00 | UI (timeline, trace, map); Action Center approval; 10-case eval set | C: UI · A: integration |
| 11:00–12:30 | 3 clean end-to-end runs; backup video; README + architecture | All |
| 12:30–14:00 | Pitch rehearsed 3×, Q&A prep, buffer | D: pitch |

**Deliverables by Sat 14:00:** code on GitHub, working prototype, 5-min pitch, demo ≤ 5 min.

Priority: one end-to-end run that really works beats many agents — *Working result* (30) and *User value* (25)
are 55 of 100 points.

**Goal: all 6 specialist agents implemented for real** (meteo, satellite, risk zones, photo forensics,
street view, news) and wired into the Orchestrator/Judge loop. Pre-captured data is only a fallback for an
agent that is not ready by 11:00, and we say so in the pitch.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for how we work tonight.

## Data sources & licences

Open-Meteo (free for non-commercial use only), Copernicus GFM / CEMS / DEM / EGMS (free, attribution required),
Google Street View (check Maps Platform terms), OpenStreetMap (ODbL), GDELT.

## License

[MIT](LICENSE)
