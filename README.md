# ClaimLens

> The adjuster stops doing research. They get an evidence file with sources, and they decide.

Agentic assistant for home-insurance claim adjusters after natural disasters (floods, storms), built for the
**UiPath Hackathon**. "ClaimLens" is a working name; the app's screens still say "AsigIT".

📄 Full proposal and research (Romanian): [`docs/proposal.md`](docs/proposal.md)

**Deadline: Saturday 14 November 2026, 14:00.** Deliverables: code on GitHub, working prototype, 5-minute pitch,
demo of 5 minutes or less.

Contents: [Run it](#run-it) · [What you see](#what-you-see) · [How it works](#how-it-works) ·
[What is real today](#what-is-real-today) · [Not built yet](#not-built-yet) · [Repository layout](#repository-layout)

---

## Run it

You need **git**, **Python 3.13** and **Node.js 20.19+ or 22.12+**. Mac or Linux.
Two terminals: one for the backend, one for the frontend.

### 1. Get the code

First time:

```bash
git clone https://github.com/rarescazan30/ClaimLens.git
```

```bash
cd ClaimLens
```

Already have it? Get the latest:

```bash
git checkout main && git pull
```

### 2. Backend (terminal 1)

First time only, from the `ClaimLens` folder: install it and create the settings file.

```bash
cd backend && python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]" && cp .env.example .env
```

Start it from the `backend` folder:

```bash
REPLAY=1 .venv/bin/uvicorn app.main:app --port 8000
```

Leave it running. You should see `Uvicorn running on http://127.0.0.1:8000`.

`REPLAY=1` means **saved answers**: the backend makes no outside calls and answers from `demo/cache/`, which holds
real responses recorded with our keys. No keys needed, no cost, same result every time. This is how we demo.

### 3. Frontend (terminal 2)

From the `ClaimLens` folder:

```bash
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173**.

### Live mode (real keys, real calls)

Only if you need a run fetched live. Ask the backend developer for the keys **in person or through a password manager**; never
paste them in the group chat, an issue or a commit. Put them in `backend/.env` (the file is git-ignored), then
start the backend without `REPLAY=1`:

```bash
.venv/bin/uvicorn app.main:app --port 8000
```

Every run then costs a little API credit and takes about a minute. What each key is for:
[`backend/README.md`](backend/README.md).

### If something goes wrong

| What you see | What to do |
| --- | --- |
| `address already in use` when starting the backend | A backend is already running on port 8000. Close that terminal, or run `lsof -ti:8000 \| xargs kill`. |
| Purple page with nothing on it | Check the backend terminal is still running, then reload. If still empty, open the browser console and send the red error to the backend developer. |
| "The backend is not answering" | Same: the backend is not running, or it is on another port. The frontend expects `http://localhost:8000` (change it in `frontend/.env`, see `frontend/.env.example`). |
| "Ask for more" gives a strange answer, the score jumps | Expected in saved-answers mode: a new question has no saved answer. Don't use it in a replay demo. |
| A claim is stuck after you pressed buttons | "Run again" (bottom right of the replay bar, once a run is over) erases the run and the decision and starts over. |
| `python3.13: command not found` | Install Python 3.13 (Mac: `brew install python@3.13`). |

### Tests

```bash
cd backend && .venv/bin/pytest -q
```

```bash
cd frontend && npm test
```

---

## What you see

**Queue** (`http://localhost:5173`): every claim the backend holds. "New claims" are not investigated yet;
"Verdict ready" are finished, sorted by score. Click one to open it.

**Case screen**: a rail with 7 steps, played back like a video (play, pause, scrub, speed).

| Step on screen | What it really does |
| --- | --- |
| Claim | Shows the stored claim. Nothing is checked here. |
| Policy check | Five fixed rules, no AI: policy active, waiting period over, peril covered, address matches the policy, notified in time. |
| Plan | The AI orchestrator writes 3–5 hypotheses to test. The agents sent are the fixed set for the damage type (all 6 for flood, 4 for storm). |
| Agents | Each agent fetches real data and an AI reads it and gives a verdict. Click a lane to see what it found and every source it called. |
| Judge | A separate AI call marks each hypothesis, lists contradictions, and either sends 1–2 agents back with a narrower question or stops (max 3 rounds). |
| Verdict | The score, band and recommendation, as the backend computed them. |
| Review | Your decision. The AI only recommends. |

Buttons that change something (each one is a backend call): **Start investigation**, **Run again**,
**Approve**, **Choose another route** (with a reason), **Ask for more** (one more round on your question),
**set aside** a finding in the full report (cannot be undone).

The demo claims:

| Claim | Event | Result today |
| --- | --- | --- |
| C-1042, flood, Pechea | Real flood of 14.09.2024 (Copernicus EMSR758). The house is placed 150 m outside the mapped flood and 13 m higher than its edge. | 78 after round 1 → Judge asks for the height check → ~34, **antifraud referral** |
| C-1038, storm, Galați | Real windstorm of 26.11.2023, gusts of 90 km/h | ~80, **standard review** |

People, addresses and claims are synthetic; the events and all fetched data are real. Details:
[`demo/README.md`](demo/README.md).

---

## How it works

```
 React app ── HTTP + live stream ──► FastAPI backend ──► SQLite
                                        │
                                  Engine (LangGraph)
                    rules → plan → agents in parallel → score → judge ─┐
                                        ▲                              │ one narrow question
                                        └──────── re-dispatch ◄────────┘   (max 3 rounds)
```

| Agent | Source | What it measures |
| --- | --- | --- |
| Weather | Open-Meteo reanalysis (~9 km grid) | Rain and wind gusts on the event day and around it |
| Satellite | Copernicus CEMS flood maps | Is the house inside the mapped flood; distance to its edge |
| Risk zones | OpenStreetMap, Copernicus DEM | Distance to the nearest river; house height vs the flood edge (on Judge request) |
| Photo forensics | EXIF, image hashes, AI vision, Google Vision web search | Photo date and place, copies in earlier claims, copies published online before the event |
| Street view | Mapillary, Google Street View | Is there a street image of the house from before the event |
| Local news | AI web search, GDELT | Independent press reports of the event in that place |

**The score.** Each agent's latest answer adds `weight × strength × data quality × direction` to a starting value
of 50 (in log-odds). The weights are ours, per agent and damage type. **Direction, strength and data quality are
chosen by the AI** that reads the agent's data. Bands: 85+ very likely, 65–85 likely, 35–65 uncertain, under 35
unlikely. Recommendation: under 35 → antifraud referral; 85+ with no flags → fast-track; everything else →
standard review. A failed policy rule or a photo published before the event forces the case to a person,
whatever the score.

Design: [`docs/backend-design.md`](docs/backend-design.md) · backend: [`backend/README.md`](backend/README.md) ·
frontend: [`frontend/README.md`](frontend/README.md) · how the frontend was connected and what was removed:
[`docs/frontend-integration.md`](docs/frontend-integration.md)

---

## What is real today

Honest status, so nobody says more in the pitch than the code does.

- **Real:** all six agents call their real sources; the policy rules; the plan; the Judge loop that sends agents
  back; the score; decisions stored in the backend; the live stream; the flood map drawn from real Copernicus data.
- **Timing in the demo is not real.** With saved answers a run finishes in under a second; the screen spaces the
  steps evenly (about 35 s) so they can be followed. Content and order are real.
- **The score moves between runs**, because the AI grades each agent's answer. The flood claim has scored 32.5 and
  34.4 on different runs, right under the antifraud line of 35. Demo it from saved answers.
- **"Inconclusive" counts as zero.** In the flood claim the satellite finding (house outside the flood) currently
  adds nothing; the verdict rests mostly on the height difference.
- **Fast-track is hard to reach.** Agents with no data add zero, so without photos the storm claim stops at ~80.
- **No photos in either demo claim.** Photo forensics, including "photo published online before the event", has
  never run on a real photo yet.
- **Street view finds nothing useful** at either demo address. **GDELT never answers** from our network; news
  comes from the AI web search.
- **Satellite works only where Copernicus mapped the flood.** For our event, only the Pechea area.
- **The address rule needs an exact match.** It passes because our synthetic addresses are identical; real
  addresses with a missing "Str." or diacritic will fail it.
- **"Ask for more"** works with real keys; on saved answers it gives a broken result.
- **Not tested yet:** a live run with real keys in the new UI; the light theme and phone layout after the changes.

## Not built yet

- **Client data validation, document parsing, photo pre-screen.** Planned for both backend and frontend; a plan
  will be written before any work starts.
- A screen to file a new claim (the backend supports it).
- Photos for the two demo claims.
- Users and login, undo, editing a claim, handing the decision to payment or the antifraud team.
- The cross-claim "learning" (reusing a saved flood map for the next claim nearby) exists in code but has not been
  seen working.
- One language on screen: labels are English, findings are Romanian.
- Deployment (Railway for the backend, Vercel for the frontend). UiPath (optional).

---

## Repository layout

```
backend/       API (app/), investigation engine (engine/), six agents (agents/), tests
frontend/      adjuster app (React + Vite + TypeScript)
demo/          demo claims (cases/), saved API responses for replay (cache/), old example responses (mock/)
docs/          proposal, design, plans, frontend integration notes
ui/, maestro/, data-fabric/   placeholders from the first proposal (not used)
```

## Data sources & licences

Open-Meteo (free for non-commercial use only), Copernicus CEMS Rapid Mapping and Copernicus DEM (free, attribution
required), OpenStreetMap (ODbL), Mapillary (CC BY-SA), Google Street View and Cloud Vision (Google terms), GDELT.

## License

[MIT](LICENSE)
