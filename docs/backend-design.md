# ClaimLens backend design

13 Nov 2026 · status: draft for approval · deadline Sat 14 Nov 2026, 14:00

This replaces the UiPath-heavy product mapping in `docs/proposal.md` and the team table in `README.md`.
Contracts in `docs/contracts.md` are unchanged.

## 1. Intent

An adjuster opens one web app, sees a claim investigated live by six specialist agents, reads the evidence
with sources, and makes the decision. The AI never rejects a claim; it only scores and recommends.

Team as it really is: **one backend developer (BE)**, **one frontend developer (FE)**, the rest on
**demo cases and pitch (DP)**.

### Goals
- A claim goes in and comes out with a plausibility score, evidence with sources, and a recommendation,
  end to end, live.
- All six agents call real data sources inside a real Orchestrator/Judge loop with re-dispatch.
- Every step is recorded and streamed, so the UI can show it live and replay it.
- The demo survives bad Wi-Fi or a dead API.

### Non-goals (tonight)
- Document extraction from PDFs or scans. Claims and policies are entered as structured data.
- Login, user accounts, multiple insurers.
- Landslide, snow and earthquake profiles. Flood and storm only.
- Ground-movement data (EGMS), official hazard maps (ANAR), an official weather-warning archive.

### Anti-goals
- A second tab or tool the adjuster has to open. One app only.
- Any automatic rejection, or wording that implies one.
- An LLM producing the score. The score is computed by code.
- A missing source being treated as a sign of fraud.

## 2. Approaches considered

| | Approach | Trade-off |
| --- | --- | --- |
| A | Python core with a UiPath shell: engine published as a UiPath coded agent, decision through Action Center, optional Maestro flowchart | More platform surface, but Action Center means a second inbox, and none of the pieces add a capability we lack |
| B | Everything in UiPath: Agent Builder, Maestro Case, Data Fabric, Apps, IXP | Six tools to learn in one night with no prior experience; nothing versioned in git |
| **C (chosen)** | **Our own backend (FastAPI + SQLite + LangGraph) and React app. UiPath optional, added Saturday morning if everything else works** | Least platform surface; every hard part is in plain Python and runs on a laptop |

Chosen by the backend owner: UiPath use is not a priority; a seamless, correct product is. Product
cleanliness rules out a second inbox.

**Rule that keeps UiPath possible tomorrow:** the engine is a self-contained LangGraph program
(`claim in → result out`) with no web-server code inside it. Publishing it as a UiPath coded agent is then a
packaging step, not a redesign.

## 3. Components and data flow

```
 React app (Vercel) ── HTTP + live stream ──► FastAPI backend (Railway, or laptop)
                                                │
                     ┌──────────────────────────┼───────────────────────────┐
                     │                          │                           │
                 API layer                 Engine (LangGraph)            SQLite
                 /claims ...               rules → plan → 6 agents       6 tables
                                           → score → judge → loop
                                                │
                    ┌───────────┬───────────┬───┴───────┬────────────┬───────────┐
                  meteo     satellite   risk_zones  photo_forensics street_view  news
                    │           │           │            │            │           │
                Open-Meteo    CEMS       Overpass     EXIF, Google  Mapillary,   GDELT,
                              (GFM)      Open-Meteo   Vision, LLM   Google SV    LLM search
                                         Elevation
                     every external response is written to demo/cache/
```

Flow of one claim:
1. FE posts the claim (fields + photos). Backend saves it and starts the engine in the background.
2. **Rules** (plain code): policy active, waiting period passed, risk covered, address matches, notified in
   time. A failed rule adds a flag and never stops the case.
3. **Orchestrator** (one LLM call) writes 3–5 testable hypotheses and assigns agents.
4. **Round 1:** every agent relevant to the damage type runs in parallel (all six for a flood). Each
   returns one Evidence object.
5. **Score** computed by code from the evidence and the weight profile.
6. **Judge** (separate LLM call) marks each hypothesis and either stops or sends one agent one narrow question.
7. Rounds repeat (max 3). Then the claim waits in `awaiting_decision`.
8. The adjuster clicks Approve / Modify / Investigate more in the React app. Backend stores the decision,
   and the reason if it differs from the recommendation.
9. On close, the event's flood area and weather maxima are saved as an EventFootprint for reuse.

## 4. Repository layout (backend)

```
backend/
  app/main.py            FastAPI app, routes, live stream
  app/db.py              SQLite tables and helpers
  app/trace.py           write a trace step + push it to the stream
  engine/graph.py        LangGraph: rules → plan → dispatch → score → judge
  engine/rules.py        F1 policy rules, F5 context signals
  engine/score.py        log-odds score, gates, bands
  engine/llm.py          OpenRouter client, model names
  engine/http.py         shared fetch: retry once, cache to disk, replay mode
  agents/<name>/agent.py one folder per agent, same interface
demo/cases/              the two demo claims as JSON + photos
demo/cache/              saved API responses
```

`agents/` and `orchestrator/` at the repo root become `backend/agents/` and `backend/engine/`; `maestro/`
and `data-fabric/` stay as empty placeholders until Saturday.

## 5. The six agents

Common interface: `run(claim, hypothesis, question, round) -> Evidence`. Each agent is a short fixed
sequence of tool calls followed by one LLM call that turns the numbers into a verdict, `strength`,
`data_quality`, `gaps` and `suggested_followup`. Budget: **6 tool calls per round**. Every tool call and
its result is written as a trace step. Failure path: retry once → backup source → `inconclusive` with the
gap written out.

| Agent | Tools (real endpoints) | Backup | Key findings returned |
| --- | --- | --- | --- |
| `meteo` | Open-Meteo Historical `archive-api.open-meteo.com/v1/archive` (daily and hourly precipitation, gusts, snow) for event date −2 / +7 days | Same API with the coarser ERA5 model | Max gust km/h, rain 24 h / 72 h mm, compared with the threshold for the damage type |
| `satellite` | CEMS Rapid Mapping API `mapping.emergency.copernicus.eu/activations/api/activations/` to find the activation by date and place, download the flood-area polygons, point-in-polygon and distance with `shapely` | Polygon file saved in `demo/cache/`; GFM (stretch) for dates with no CEMS activation | Inside/outside flood area, distance to edge in m, map date |
| `risk_zones` | OSM Overpass (nearest waterway within 2 km); Open-Meteo Elevation `api.open-meteo.com/v1/elevation` for the house and the nearest flood-edge point | Second Overpass server (`overpass.kumi.systems`) | Distance to water m, height difference house vs flood edge m |
| `photo_forensics` | EXIF date and GPS (local); Google Cloud Vision Web Detection (copies on the web); perceptual hash against photos of earlier claims (local); vision LLM (looks generated? shows the declared damage?) | Skip web detection, note the gap | Per-photo verdict and reason |
| `street_view` | Mapillary Graph API images near the address before the event; Google Street View metadata + static image; vision LLM compares roof and facade with the client's photos | Whichever of the two answers | Date of pre-event image, prior condition, pre-existing damage yes/no |
| `news` | GDELT DOC API `api.gdeltproject.org/api/v2/doc/doc` (Romanian and English queries, event date −1 / +7 days); LLM filters to reports naming the locality | OpenRouter web-search model | Confirmed reports: place, date, outlet, link |

**Quick checks first, deeper checks on request.** Round 1 runs each agent's cheap checks. The deeper ones run
only when the Judge asks, either because they cost more or because they need another agent's result:

| Agent | Round 1 | Only when the Judge asks |
| --- | --- | --- |
| `meteo` | Daily rain and gusts at the address | Hourly series, neighbouring grid cells |
| `satellite` | Inside/outside flood area, distance to edge | GFM for other dates (stretch) |
| `risk_zones` | Distance to nearest water | Height of the house vs the nearest flood-edge point (needs the polygon the satellite agent found) |
| `photo_forensics` | EXIF date and GPS, vision check, copies in our own claims | Web-wide copy search (Google Vision) with first-seen dates |
| `street_view` | Nearest pre-event image and its date | Vision comparison with the client's photos |
| `news` | GDELT search for the locality | Backup web search, narrower question |

This is what makes the fraud case honest: in round 1 the house is near water and near the flood, the photos
carry no usable metadata, and the score is provisional "likely". The Judge sees "outside the flood area but
60 cm of water declared" and asks risk_zones for the height difference and photo_forensics for a web search.
Round 2 finds the house well above the flood edge and the photos published months earlier. DP must build the
fraud case to match: photos with EXIF stripped, at least one of them a real flood picture already online.

**One Evidence per agent per round.** An agent receives all hypotheses assigned to it and returns one
Evidence object; its `hypothesis` field holds the main one, and findings name the others.

**Storm claims.** The Orchestrator picks agents per damage type. For a storm: meteo, news, street_view and
photo_forensics. Satellite and risk_zones are not dispatched and appear in the UI as "not relevant for this
damage type". The storm weight profile gives them weight 0.

Agent-to-factor mapping for the score: F2 ← photo_forensics; F3 ← meteo, satellite, news; F4 ← risk_zones,
street_view (and meteo intensity). F1 and F5 come from rules.

Notes from testing the sources on 13 Nov:
- **Open-Meteo** works without a key. For Pechea (45.63, 27.80) it reports 45.7 mm on 14.09.2024 and 24.0 mm
  on 15.09, max gust 45 km/h. The proposal's "140 mm in 48 h" is not what this source returns, so the demo
  script must quote the measured numbers.
- **CEMS EMSR758** is confirmed: "Flood in Galati and Vaslui counties, Romania", activated 14.09.2024,
  4 areas, 8 products. The exact download address of the polygon files is not yet verified; first agent task.
- **Overpass** rejected a request without a `User-Agent` header and returned nothing on the retry. Not yet
  verified working; always send a User-Agent, use both servers, cache.
- **GDELT** answered "one request every 5 seconds" twice. Not yet verified working; the news agent must
  space its calls and will lean on the backup if GDELT keeps refusing.
- **GFM** needs a free account and its API address is not verified. Stretch only.
- The Open-Meteo Elevation grid is about 90 m. A 6 m height difference over 150 m is detectable only if the
  demo house is chosen on a real slope; DP must pick the address by checking this API first.

## 6. Orchestrator, Judge and the loop

LangGraph nodes: `rules → plan → dispatch → score → judge → (dispatch | finish)`.

- **plan** (Orchestrator, strong model): input claim + rule flags; output hypotheses
  `{id, text, critical, agents[]}` with thresholds filled in (for example "rain ≥ 30 mm in 24 h at the
  address on 14.09.2024").
- **dispatch:** round 1 fans out to all six agents in parallel (LangGraph `Send`). Later rounds run only the
  agents the Judge named, each with one question. One agent failing never blocks the others; 60 s limit each.
- **score** (code): `logit(P) = logit(P0) + Σ w[t,agent] · s · q · d`. Latest evidence per agent replaces its
  earlier evidence. Sources the Judge marked as duplicates of another count once. Gates: an F1 failure forces
  "standard review"; a clear fake forces "antifraud referral". A clear fake means an exact copy of a claim
  photo found on the web or in another claim, dated before the event. Gates are shown as a banner with the
  reason and are not terms in the sum; every other photo signal (odd date, looks generated, wrong subject)
  is an ordinary score term. F5 signals (late notification, amount vs sum insured) enter as one small
  rules term stored in the weight profile.
- **judge** (separate strong-model call, never sees the Orchestrator's reasoning, only hypotheses and
  evidence): marks each hypothesis confirmed / refuted / inconclusive / conflicting, names tensions in plain
  words, and returns either `stop` or up to two re-dispatches `{agent, question}`.
- **Stop when any holds:** all critical hypotheses have a verdict and nothing conflicts; score moved < 5
  points since the previous round; 3 rounds done; 3 minutes elapsed.
- **Recommendation** (code): score ≥ 85 and no gate → fast-track; < 35 or a fake-photo gate → antifraud
  referral; otherwise standard review.
- **Adjuster controls after the loop:**
  - *Approve* the recommendation.
  - *Modify*: choose a different outcome (fast-track / standard review / antifraud referral), reason required.
  - *Investigate more*: type a question; one extra round runs with it sent to the agent the Judge picks, and
    the case returns to `awaiting_decision`.
  - *Reject one piece of evidence*: the score is recomputed without it.
- **Speed target:** a full fraud-case run in under 90 s live, under 20 s in replay mode.

Trace: every node and every tool call writes a TraceStep in the `docs/contracts.md` format. Step ids look
like `r1.meteo.2`; the parent is the round's dispatch or judge step.

Models, through OpenRouter: one fast model for agents and vision, one stronger model for Orchestrator and
Judge. Exact model ids are set in `engine/llm.py` and chosen at the first task by a quick test.

## 7. Database

SQLite, one file. JSON columns hold nested data. Our own database, not Data Fabric.

| Table | Fields | Written by | Read by |
| --- | --- | --- | --- |
| `policy` | id, holder_name, address, lat, lon, valid_from, valid_to, waiting_days, covered_risks (JSON), sum_insured, product | seed script, intake | rules, UI |
| `claim` | id, policy_id, damage_type, event_date, notified_at, address, lat, lon, description, amount_claimed, photos (JSON), status, rule_flags (JSON), hypotheses (JSON), score, band, recommendation, decision, decision_reason, decided_at, created_at | intake, engine, decision endpoint | everything |
| `evidence` | id, claim_id, agent, round, hypothesis, verdict, strength, data_quality, findings (JSON), reasoning_steps (JSON), gaps (JSON), suggested_followup, rejected_by_adjuster, created_at | agents, reject endpoint | score, judge, UI |
| `trace_step` | id, case_id, step_id, parent, actor, type, summary, inputs (JSON), outputs (JSON), sources (JSON), status, started_at, ended_at | engine, agents | UI stream and replay |
| `event_footprint` | id, name, damage_type, date_from, date_to, polygon (GeoJSON), meteo_maxima (JSON), news (JSON), sources (JSON), version | engine on close, seed | satellite agent (checked first), UI map |
| `weight_config` | damage_type, p0, weights (JSON: agent → weight), updated_at | seed | score |

`claim.status`: `received → investigating → awaiting_decision → decided`.

## 8. API for the frontend

| Method and path | Purpose |
| --- | --- |
| `POST /claims` | Create a claim (fields + photo uploads) and start the investigation |
| `GET /claims` | Queue: id, address, damage type, status, score, band, recommendation |
| `GET /claims/{id}` | Full case: claim, policy, rule flags, hypotheses, evidence, score breakdown per evidence |
| `GET /claims/{id}/trace` | All trace steps so far (for replay) |
| `GET /claims/{id}/stream` | Live stream (server-sent events) of new trace steps and score updates |
| `POST /claims/{id}/decision` | `{decision: approve | modify, outcome, reason}` |
| `POST /claims/{id}/rerun` | Clear evidence, trace and score, and run the investigation again (demo reset) |
| `POST /claims/{id}/evidence/{eid}/reject` | Reject one piece of evidence; returns the recomputed score |
| `POST /claims/{id}/question` | "Investigate more": free question from the adjuster; starts one extra round |
| `GET /footprints/{id}` | Flood polygon as GeoJSON for the map |
| `GET /photos/{name}` | Claim photos |

FE gets a mock of these responses (static JSON for the fraud case) in the first hour, so it never waits on
the engine.

## 9. Accounts and keys

| Service | Key? | How to get it tonight | Limits and licence |
| --- | --- | --- | --- |
| OpenRouter | Yes (have it) | — | Pay per use; set a spend cap |
| Open-Meteo (weather, elevation) | No | — | Free for non-commercial use; attribution |
| Copernicus CEMS | No | — | Free, attribution required |
| Copernicus GFM (stretch) | Account | Register at the GFM portal | Free, attribution |
| OSM Overpass | No | Send a User-Agent | Fair use, ODbL attribution |
| GDELT | No | — | One request per 5 s |
| Mapillary | Free token | mapillary.com/dashboard/developers | CC BY-SA images |
| Google Cloud (Street View Static + Vision) | One key | Existing Cloud account: enable both APIs, create a key restricted to them | Street View metadata free; Vision first 1,000 images a month free; Street View images may be displayed, not stored long term |
| Railway, Vercel | Accounts | Sign in with GitHub | Free or trial tier is enough |

Secrets live in a local `.env` (already git-ignored) and in Railway's variables page. `backend/.env.example`
lists the names with no values. Nothing secret reaches the React app.

## 10. Hosting

- Backend: Railway, deployed from `main`, with a small persistent volume for the SQLite file, photos and cache.
- Frontend: Vercel, with the backend address as its only setting.
- Demo: the hosted pair is the default; the same backend on the BE laptop with the React dev server is the
  fallback. Whichever was stable in the 11:00 rehearsals is used.

## 11. Demo safety

- `engine/http.py` saves every external response under `demo/cache/` keyed by request. The cache is committed.
- `REPLAY=1` makes every agent read from the cache and never touch the network. LLM calls are cached the same
  way, so a full run works with no internet.
- The two demo cases are seeded at startup, so a fresh deploy is never empty. The honest case is seeded
  already investigated and shown through replay; the fraud case is run live with `rerun`. New claims can
  still be entered through the form, but the demo does not depend on it.
- DP owns the two cases. BE gives DP a small script by 23:30 that prints rain, gusts and elevation for any
  address and date, so DP can pick a real storm above the gust threshold and a flood house on a real slope.
  Both cases are due at 01:00.
- A screen recording of both cases is made at 11:30 as the last-resort backup.

## 12. Risks and fallback order

| Risk | Mitigation |
| --- | --- |
| One backend person, six agents plus loop | Fixed agent template; loop built with stub agents first; agents swapped in one by one |
| Flood polygon download harder than expected | Download once by hand, store as EventFootprint; agent still does the real geometry |
| Elevation too coarse for the "6 m higher" story | DP picks the house using the elevation API before writing the case |
| GDELT or Overpass refusing requests | Backup sources; cache |
| LLM returns malformed output | Structured output with one retry, then `inconclusive` |
| Hosting trouble | Laptop fallback |

If we fall behind, agents drop to pre-captured data in this order, and the pitch says which:
**news → street_view → photo_forensics web search (EXIF and vision stay real) → satellite's GFM part**.
Meteo, risk_zones and satellite on CEMS polygons are never faked; without them there is no demo.

## 13. Optional UiPath step (Saturday, only if 3 clean runs are done)

Publish `backend/engine` as a UiPath coded agent with the `uipath-langchain` package, so the same
investigation can also be started and inspected from the UiPath dashboard. The app does not depend on it.

## 14. Left to the builder

Exact prompts, model ids, weight values and thresholds per damage type, step-id details, error messages.
