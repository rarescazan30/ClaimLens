# ClaimLens Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A hosted Python backend that investigates a home-insurance claim with six real agents in an Orchestrator/Judge loop, streams every step to the React app, and records the adjuster's decision.

**Architecture:** FastAPI + SQLite serve the React app. A self-contained LangGraph engine (rules → plan → dispatch → score → judge → loop) runs inside the backend and talks to it only through a small `Sink` interface, so it can later be published as a UiPath coded agent unchanged. Every external call goes through one cached fetch helper with a replay mode.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, sse-starlette, LangGraph, Pydantic v2, httpx, shapely, Pillow, imagehash, pytest + pytest-asyncio. LLMs through OpenRouter. Hosting: Railway (backend), Vercel (frontend).

**Spec:** [`docs/backend-design.md`](backend-design.md) and [`docs/contracts.md`](contracts.md). Read both before any task.

## Global Constraints

- Evidence and trace events use the exact field names in `docs/contracts.md`.
- The score is computed by code: `logit(P) = logit(P0) + Σ w·s·q·d`. No LLM produces a score.
- Nothing is rejected automatically. Outcomes are only `fast_track`, `standard_review`, `antifraud_referral`.
- A missing or failed source yields `verdict: "inconclusive"` with the gap in `gaps`. Never `contradicts`.
- Max 6 tool calls per agent per round; 60 s per agent; max 3 rounds; 3 minutes per investigation.
- `backend/engine/` and `backend/agents/` import nothing from `backend/app/` and nothing from FastAPI.
- Every external HTTP and LLM call goes through `AgentContext` / `engine/http.py` so it is cached, traced and replayable.
- Every outgoing HTTP request sends `User-Agent: ClaimLens-hackathon/0.1`.
- Secrets only in `.env` and Railway variables: `OPENROUTER_API_KEY`, `GOOGLE_API_KEY`, `MAPILLARY_TOKEN`, `MODEL_FAST`, `MODEL_STRONG`, `REPLAY`, `REPLAY_AGENTS`, `DATA_DIR`.
- Text shown to the adjuster (summaries, hypotheses, reasons) is in Romanian; code and field names in English.
- Commit after every task; `main` always runs.

## Review Focus

Inputs the design implies but does not spell out. Each is pinned by a test in the task named.

1. A claim with no photos → photo_forensics returns `inconclusive` with a gap, and the run completes (Task 12).
2. An event date and place with no CEMS activation and no stored footprint → satellite returns `inconclusive`, not "outside the flood area" (Task 10).
3. The LLM returns malformed JSON twice → the caller gets `inconclusive` evidence, or for the Judge a `stop` with reason "judge unavailable"; the run still finishes (Tasks 4, 7).
4. The browser opens the stream after the investigation has finished, or reconnects mid-run → it receives all past steps first, then live ones (Task 8).
5. `rerun` or `question` is called while an investigation is already running → HTTP 409, nothing is started twice (Task 8).

## Roles and timeline

**BE** = backend developer · **FE** = frontend developer · **DP** = demo cases and pitch.
`∥` = can run in parallel with the tasks listed.

| Slot | BE | FE | DP |
| --- | --- | --- | --- |
| Fri 22:00–22:30 | T1 scaffold, keys | F1 scaffold ∥ | D1 accounts and stories ∥ |
| 22:30–23:15 | T2 models, DB, mock data | F1 | D1 |
| 23:15–23:30 | T3 site-check script | F2 queue + case page on mock ∥ | D1 |
| 23:30–00:15 | T4 fetch/cache, LLM, context | F2 | D2 build the two cases ∥ |
| Sat 00:15–01:00 | T5 score + rules | F2 | D2 (due 01:00) |
| 01:00–02:00 | T6 engine loop with stub agents | F2 | D3 pitch deck ∥ |
| 02:00–02:30 | T7 Orchestrator + Judge prompts | F2 | D3 |
| 02:30–03:15 | T8 API, live stream, deploy | F3 switch to live API ∥ | sleep |
| **03:15 checkpoint** | FE sees a live stubbed run from the hosted backend | | |
| 03:15–04:00 | T9 meteo | F3 live lanes, map | sleep |
| 04:00–05:15 | T10 satellite | F3 | sleep |
| 05:15–06:00 | T11 risk zones | F4 photos, score chart, decision ∥ | sleep |
| **06:00 checkpoint** | fraud case runs live with 3 real agents; BE rests 45 min | | |
| 06:45–07:45 | T12 photo forensics | F4 | D4 eval cases ∥ |
| 07:45–08:45 | T13 street view | F5 replay slider, polish ∥ | D4 |
| 08:45–09:30 | T14 news | F5 | D3 |
| 09:30–10:30 | T15 tune both cases, cache | F5 | D3 |
| 10:30–11:00 | T16 offline run | F6 intake form (only if F5 done) | D3 |
| **11:00 gate** | any agent not passing its test falls back, in the order in T16 | | |
| 11:00–12:30 | T17 three clean runs, README | bug fixes | D5 backup video 11:30 |
| 11:30–12:15 | T18 UiPath (optional) | | |
| 12:30–14:00 | on call | on call | D6 rehearse 3×, Q&A |

## File map

```
backend/
  pyproject.toml  .env.example  Procfile
  app/main.py        routes, SSE, background runs
  app/db.py          SQLite schema + Store (implements Sink)
  app/seed.py        loads demo cases, weight profiles, footprint
  engine/models.py   Pydantic types shared by everything
  engine/http.py     cached fetch, retry, replay
  engine/llm.py      OpenRouter JSON calls (text + vision)
  engine/context.py  AgentContext: budget, trace, fetch, llm
  engine/rules.py    F1 policy rules, F5 context term
  engine/score.py    log-odds score, gates, bands, recommendation
  engine/thresholds.py  per-damage-type thresholds and default weights
  engine/prompts.py  Orchestrator and Judge prompts
  engine/graph.py    LangGraph loop, stop rule
  agents/__init__.py AGENTS registry
  agents/<name>/agent.py   meteo, satellite, risk_zones, photo_forensics, street_view, news
  scripts/check_site.py
  tests/
demo/cases/  demo/cache/  demo/mock/
```

---

### Task 1: Scaffold and keys — BE, Fri 22:00–22:30 (∥ F1, D1)

**Files:** Create `backend/pyproject.toml`, `backend/.env.example`, `backend/Procfile`, `backend/app/main.py`, `backend/tests/test_health.py`. Move root `agents/README.md` → `backend/agents/README.md`, `orchestrator/README.md` → `backend/engine/README.md`.

**Produces:** `app.main:app` (FastAPI) with `GET /health → {"ok": true}`; CORS open to any origin.

- [ ] Test `test_health`: `client.get("/health").json() == {"ok": True}`. Run, see it fail.
- [ ] Create the project with the Tech Stack dependencies and the health route. Run `cd backend && pytest -q` → 1 passed.
- [ ] `.env.example` lists the variable names from Global Constraints, no values. `Procfile`: `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- [ ] In Google Cloud: enable "Street View Static API" and "Cloud Vision API", create one key restricted to those two. Create a Mapillary token. Put all keys in `backend/.env`.
- [ ] Commit.

### Task 2: Models, database, mock data — BE, 22:30–23:15

**Files:** Create `backend/engine/models.py`, `backend/app/db.py`, `backend/app/seed.py`, `demo/mock/claim_fraud.json`, `demo/mock/trace_fraud.json`, `backend/tests/test_db.py`.

**Produces** (in `engine/models.py`, Pydantic):

```python
Verdict = Literal["supports", "contradicts", "inconclusive"]
class Finding: metric: str; value: Any; unit: str | None; source: str; url: str | None; spatial_res_km: float | None; retrieved_at: str
class Evidence: agent: str; round: int; hypothesis: str; verdict: Verdict; strength: float; data_quality: float; findings: list[Finding]; reasoning_steps: list[str]; gaps: list[str]; suggested_followup: str | None
class TraceStep: case_id: str; step_id: str; parent: str | None; actor: str; type: Literal["tool_call","observation","decision","escalation"]; summary: str; inputs: dict; outputs: dict; sources: list[str]; status: str; started_at: str; ended_at: str | None
class Hypothesis: id: str; text: str; critical: bool; agents: list[str]
class RuleFlag: rule: str; passed: bool; reason: str
class WeightConfig: damage_type: str; p0: float; weights: dict[str, float]; context_weight: float
class Gate: kind: Literal["coverage", "clear_fake"]; reason: str
class Contribution: agent: str; round: int; delta_logit: float
class ScoreResult: score: float; band: str; recommendation: str; contributions: list[Contribution]; gates: list[Gate]
class Sink(Protocol):
    def trace(self, step: TraceStep) -> None: ...
    def evidence(self, e: Evidence) -> int: ...          # returns evidence id
    def score(self, s: ScoreResult, round: int) -> None: ...
    def hypotheses(self, h: list[Hypothesis]) -> None: ...
    def flags(self, f: list[RuleFlag]) -> None: ...
```

`app/db.py`: `class Store` with `__init__(path)`, `create_schema()`, the six tables from design §7, `for_claim(claim_id) -> Sink`, `get_claim(id) -> dict`, `list_claims()`, `get_policy(id)`, `evidence_for(claim_id, include_rejected=False) -> list[Evidence]`, `trace_for(claim_id) -> list[TraceStep]`, `reset_claim(id)`, `set_status(id, status)`, `save_decision(id, decision, outcome, reason)`, `reject_evidence(eid)`, `weight_config(damage_type)`, `footprints_near(lat, lon, date) -> list[dict]`, `save_footprint(dict)`.

- [ ] Tests: evidence written through `for_claim("C-1").evidence(e)` comes back equal from `evidence_for("C-1")`; `reject_evidence` hides it; `reset_claim` clears evidence, trace, score and sets status `received`.
- [ ] Implement models, Store and `seed.py` (`seed(store)`: loads every `demo/cases/*.json`, both weight profiles from `engine/thresholds.py`; idempotent).
- [ ] Write `demo/mock/claim_fraud.json` (exact shape `GET /claims/{id}` will return: `claim`, `policy`, `rule_flags`, `hypotheses`, `evidence[]`, `score`) and `demo/mock/trace_fraud.json` (about 25 trace steps over 2 rounds, following the fraud story in design §5). **Send both to FE now.**
- [ ] Run tests, commit.

### Task 3: Site-check script for DP — BE, 23:15–23:30

**Files:** Create `backend/scripts/check_site.py`.

- [ ] `python scripts/check_site.py <lat> <lon> <YYYY-MM-DD>` prints: daily rain and max gust for date −2..+2 (Open-Meteo archive), elevation at the point and at 8 points 150 m around it (Open-Meteo elevation). No key needed.
- [ ] Run for `45.63 27.80 2024-09-14`; expect 45.7 mm on the 14th. Hand to DP with one line of instructions. Commit.

### Task 4: Fetch/cache, LLM client, agent context — BE, 23:30–00:15

**Files:** Create `backend/engine/http.py`, `backend/engine/llm.py`, `backend/engine/context.py`, `backend/tests/test_http.py`, `backend/tests/test_context.py`.

**Produces:**

```python
# http.py
async def fetch(url, *, params=None, method="GET", json_body=None, headers=None, timeout=20, as_bytes=False) -> Any
#   key = sha256(method, url, sorted params, body); file demo/cache/http/<key>.json
#   REPLAY=1: return cached or raise CacheMiss. Otherwise: request, on failure retry once, save, return.
class SourceError(Exception)   # raised after the retry fails
class CacheMiss(SourceError)

# llm.py
async def llm_json(system: str, user: str, *, model: Literal["fast","strong"]="fast", images: list[bytes] | None = None) -> dict
#   OpenRouter chat completions, JSON response format, cached like fetch under demo/cache/llm/.
#   Invalid JSON → one retry → raise LLMError.

# context.py
class BudgetExceeded(Exception)
class AgentContext:
    def __init__(self, case_id, agent, round, sink: Sink, max_calls=6)
    async def fetch(self, source_name: str, url, **kw) -> Any       # counts 1 call, writes tool_call + observation trace steps
    async def fetch_first(self, attempts: list[tuple[str, str, dict]]) -> tuple[str, Any]   # main then backup; raises SourceError if all fail
    async def llm(self, system, user, **kw) -> dict                 # not counted against the budget
    def note(self, type, summary, outputs=None, sources=None)       # extra trace step
    def inconclusive(self, hypothesis: str, gap: str) -> Evidence   # strength 0, data_quality 0
```

Step ids: `r{round}.{agent}.{n}`, parent `r{round}.dispatch`.

- [ ] Tests (monkeypatched transport): second identical `fetch` reads the cache without a network call; a failing request is tried exactly twice then raises `SourceError`; with `REPLAY=1` and no cache file → `CacheMiss`; the 7th `ctx.fetch` raises `BudgetExceeded`; each `ctx.fetch` produces two trace steps on the sink; `llm_json` given invalid JSON twice raises `LLMError` (Review Focus 3).
- [ ] Implement. Pick `MODEL_FAST` and `MODEL_STRONG` by sending one real JSON prompt and one image prompt through OpenRouter; write the chosen ids into `.env.example` as comments.
- [ ] Run tests, commit.

### Task 5: Score and rules — BE, 00:15–01:00

**Files:** Create `backend/engine/score.py`, `backend/engine/rules.py`, `backend/engine/thresholds.py`, `backend/tests/test_score.py`, `backend/tests/test_rules.py`.

**Produces:**

```python
def compute_score(evidence: list[Evidence], cfg: WeightConfig, flags: list[RuleFlag], context_term: float = 0.0) -> ScoreResult
def check_policy(claim: dict, policy: dict) -> list[RuleFlag]   # rules: policy_active, waiting_period, risk_covered, address_match, notified_in_time
def context_term(claim: dict, policy: dict) -> float            # in [-1, 0]: late notification, amount_claimed > sum_insured
```

Fixed values (`thresholds.py`):
- Flood: `p0=0.5`, weights meteo 1.5, satellite 2.5, risk_zones 2.5, photo_forensics 2.0, street_view 1.0, news 1.0, `context_weight=0.5`; rain threshold 30 mm / 24 h.
- Storm: `p0=0.5`, weights meteo 3.0, news 1.5, street_view 2.0, photo_forensics 2.0, satellite 0, risk_zones 0, `context_weight=0.5`; gust threshold 70 km/h.
- `AGENTS_FOR = {"flood": all six, "storm": ["meteo","news","street_view","photo_forensics"]}`.
- `notified_in_time`: within 60 days of the event. Bands: ≥85 `very_likely`, 65–85 `likely`, 35–65 `uncertain`, <35 `unlikely`.
- Clear fake = any finding with `metric == "exact_copy_before_event"` and `value is True`.

- [ ] Score tests:
  - one evidence `supports, s=0.8, q=0.6`, weight 2.0, p0 0.5 → `score == pytest.approx(72.3, abs=0.1)`, band `likely`;
  - same with `contradicts` → `27.7`; `inconclusive` → `50.0`;
  - two rounds from the same agent → only the latest round counts;
  - a failed `risk_covered` flag → score unchanged, gate `coverage`, recommendation `standard_review` even at score 95;
  - a clear-fake finding → gate `clear_fake`, recommendation `antifraud_referral`;
  - score 90, no gates → `fast_track`; score 30 → `antifraud_referral`; score 60 → `standard_review`;
  - `contributions` sum to `logit(P) − logit(P0)`.
- [ ] Rules tests: event before `valid_from + waiting_days` fails `waiting_period`; damage type not in `covered_risks` fails `risk_covered`; notification 61 days after the event fails `notified_in_time`; all rules always return a flag (5 flags), never raise.
- [ ] Implement, run, commit.

### Task 6: Engine loop with stub agents — BE, 01:00–02:00

**Files:** Create `backend/engine/graph.py`, `backend/agents/__init__.py`, `backend/agents/stub.py`, `backend/tests/test_graph.py`.

**Consumes:** Tasks 2, 4, 5.

**Produces:**

```python
class AgentTask(BaseModel): claim: dict; policy: dict; hypotheses: list[Hypothesis]; question: str | None; round: int; prior: list[Evidence]
AgentFn = Callable[[AgentTask, AgentContext], Awaitable[Evidence]]
AGENTS: dict[str, AgentFn]                         # agents/__init__.py; starts with six stubs
class JudgeOut(BaseModel): marks: dict[str, Literal["confirmed","refuted","inconclusive","conflicting"]]; tensions: list[str]; action: Literal["stop","redispatch"]; redispatch: list[dict]  # {agent, question}, max 2
def should_stop(round: int, prev_score: float | None, score: float, judge: JudgeOut, hypotheses: list[Hypothesis], elapsed_s: float) -> tuple[bool, str]
async def run_investigation(claim: dict, policy: dict, cfg: WeightConfig, sink: Sink, *, agents=AGENTS, planner=None, judge=None, extra_question: str | None = None) -> ScoreResult
```

Graph nodes: `rules → plan → dispatch → score → judge → (dispatch | finish)`. Round 1 dispatches `AGENTS_FOR[damage_type]` in parallel with `Send`; later rounds only the Judge's `redispatch`. Each agent call is wrapped in `asyncio.wait_for(…, 60)`; any exception or timeout becomes `ctx.inconclusive(...)`. `planner` and `judge` are injectable callables so tests need no LLM. With `extra_question`, skip rules/plan, run one round where the Judge callable picks the agent.

- [ ] Tests with fake planner/judge and stub agents:
  - round 1 calls all six agents for flood, four for storm;
  - judge says `redispatch risk_zones` → round 2 calls only risk_zones with that question;
  - `should_stop` returns true with reason for: round 3; score moved 3 points; all critical marked and none conflicting; elapsed 181 s. Returns false for score moved 12 points in round 2 with a conflict;
  - an agent that raises yields inconclusive evidence and the run finishes;
  - an agent that sleeps past the limit (limit patched to 0.1 s) yields inconclusive;
  - sink receives trace steps for rules, plan, each dispatch, each score, each judge decision, and a final `decision` step with the recommendation.
- [ ] Implement, run, commit.

### Task 7: Orchestrator and Judge — BE, 02:00–02:30

**Files:** Create `backend/engine/prompts.py`; modify `backend/engine/graph.py` (default `planner`, `judge`); create `backend/tests/test_judge.py`.

**Produces:** `async def plan_hypotheses(claim, policy, flags) -> list[Hypothesis]` (strong model; 3–5 hypotheses, thresholds from `thresholds.py` written into the text, agents limited to `AGENTS_FOR`); `async def judge_round(hypotheses, evidence, score, round) -> JudgeOut` (strong model; sees hypotheses and evidence only, never the planner's reasoning; told which deeper checks each agent can run, from design §5).

- [ ] Tests: `judge_round` with `llm_json` patched to raise `LLMError` returns `action="stop"`, tensions `["judge unavailable"]` (Review Focus 3); a redispatch naming an agent outside `AGENTS_FOR` is dropped; more than two redispatches are cut to two.
- [ ] Implement prompts. Run one real planning call on the mock fraud claim and read the hypotheses for sense. Commit.

### Task 8: API, live stream, deploy — BE, 02:30–03:15 (∥ F3)

**Files:** Modify `backend/app/main.py`; create `backend/tests/test_api.py`.

**Consumes:** `Store`, `run_investigation`, `seed`.

**Produces:** the routes in design §8, plus:
- Startup: `create_schema()`, `seed()`.
- `POST /claims`: multipart (`data` JSON + `photos[]`); saves photos under `DATA_DIR/photos`; if `lat/lon` missing, geocodes the address with Nominatim through `fetch`; starts the run as a background task.
- `GET /claims/{id}/stream`: server-sent events; first sends every stored trace step, then live ones; event names `trace`, `score`, `status`.
- `rerun`, `question`: return 409 if `status == "investigating"`.
- `decision`: `approve` needs no reason; `modify` needs `outcome` and a non-empty `reason` (422 otherwise). Sets `decided`.
- `reject`: marks the evidence, recomputes with `compute_score`, returns the new `ScoreResult`.

- [ ] Tests (stub agents, fake planner/judge): `POST /claims` then polling reaches `awaiting_decision` with a score; stream opened after completion yields all steps (Review Focus 4); `rerun` during a run → 409 (Review Focus 5); `modify` without reason → 422; rejecting the only contradicting evidence raises the score; `GET /claims/{id}` matches the keys of `demo/mock/claim_fraud.json`.
- [ ] Implement, run tests.
- [ ] Deploy: Railway project from the GitHub repo, root `backend/`, add a volume mounted at `/data`, set `DATA_DIR=/data` and the keys. Open `/health` on the Railway address.
- [ ] Send FE the address. **Checkpoint 03:15:** FE runs `rerun` on the fraud case and sees stub steps arrive live. Commit.

### Agent template (applies to Tasks 9–14)

Each agent is `backend/agents/<name>/agent.py` exporting `async def run(task: AgentTask, ctx: AgentContext) -> Evidence`, registered in `AGENTS` in place of its stub. Shape:

1. Choose checks: quick ones when `task.question is None`, the deeper one when the Judge asked (design §5 table).
2. Call sources through `ctx.fetch` / `ctx.fetch_first` (main, then backup).
3. Build `findings` in code from the raw numbers, with `source`, `url`, `retrieved_at`.
4. One `ctx.llm` call (fast model) gets the hypotheses and findings and returns `verdict`, `strength`, `data_quality`, `reasoning_steps`, `gaps`, `suggested_followup` in Romanian.
5. `SourceError` on every source → `ctx.inconclusive(hypothesis, gap)`.

Each agent task has the same four steps: write the tests, run them red, implement, then run the agent once for real against the fraud or storm case so its responses land in `demo/cache/`, and commit code and cache together. Tests run with `REPLAY=1` against saved fixtures in `backend/tests/fixtures/<agent>/`.

### Task 9: Meteo — BE, 03:15–04:00

**Sources:** `https://archive-api.open-meteo.com/v1/archive` with `daily=precipitation_sum,wind_gusts_10m_max,snowfall_sum`, `start_date = event − 2`, `end_date = event + 7`, `timezone=Europe/Bucharest`. Backup: same URL with `models=era5`. Deeper check: `hourly=precipitation,wind_gusts_10m` for the event day ±1.

**Findings:** `precipitation_24h_max` (mm), `precipitation_72h_max` (mm), `wind_gusts_10m_max` (km/h), each with `spatial_res_km`.

- [ ] Tests: for (45.63, 27.80, 2024-09-14) finding `precipitation_24h_max == 45.7` and `precipitation_72h_max == pytest.approx(75.2)`; flood claim → the LLM prompt contains "30 mm"; both sources failing → `inconclusive`, gap mentions Open-Meteo; a Judge question triggers the hourly call.
- [ ] Implement, live run, commit.

### Task 10: Satellite — BE, 04:00–05:15

**Sources:**
1. `store`-independent lookup first: `task.claim["footprints"]` (the API layer attaches `Store.footprints_near` results to the claim dict before the run).
2. CEMS: `https://mapping.emergency.copernicus.eu/activations/api/activations/?…` to find activations by date and country, then the activation's product list for flood delineation vectors.
3. Backup: `demo/cache/emsr758/*.geojson`.

**First 20 minutes are a spike:** find how to download the EMSR758 delineation polygons through the API. If it is not found by 04:20, download the vector package by hand from the activation page, convert to GeoJSON (EPSG:4326) under `demo/cache/emsr758/`, seed it as an `event_footprint`, and keep the activation lookup call as the agent's first real tool call.

**Findings:** `inside_flood_extent` (bool), `distance_to_flood_edge_m`, `nearest_edge_point` (`{lat, lon}`), `map_date`, `activation` ("EMSR758"). Distances computed after projecting to UTM 35N (EPSG:32635) with `shapely` + `pyproj`.

- [ ] Tests: a point inside a fixture polygon → `inside_flood_extent True`, distance 0; a point 150 m outside → distance `pytest.approx(150, abs=5)` and `nearest_edge_point` present; no activation and no footprint for the date → `inconclusive` with a gap, never `contradicts` (Review Focus 2).
- [ ] Implement, live run on the fraud case, commit code + polygons.

### Task 11: Risk zones — BE, 05:15–06:00

**Sources:** Overpass `https://overpass-api.de/api/interpreter` (backup `https://overpass.kumi.systems/api/interpreter`), query waterways and water bodies within 2000 m with `out geom`; Open-Meteo elevation `https://api.open-meteo.com/v1/elevation`.

**Quick check:** `distance_to_water_m`, `water_name`. **Deeper check (Judge asks):** read `nearest_edge_point` from the satellite evidence in `task.prior`; `elevation_house_m`, `elevation_flood_edge_m`, `elevation_diff_m` (house − edge), `spatial_res_km: 0.09`. If there is no satellite edge point, compare with the nearest water point instead and say so in `gaps`.

- [ ] Tests: fixture waterway 400 m away → `distance_to_water_m == pytest.approx(400, abs=10)`; deeper check with a prior satellite finding → `elevation_diff_m` equals fixture difference; Overpass main failing → backup used, evidence `source` names the backup; no water within 2 km → finding `distance_to_water_m: null` and verdict left to the LLM, not an error.
- [ ] Implement, live run, commit. **Checkpoint 06:00:** `rerun` the fraud case on Railway with three real agents; round 2 must be triggered by the Judge. If the Judge does not re-dispatch, fix the Judge prompt before resting.

### Task 12: Photo forensics — BE, 06:45–07:45

**Quick checks (local, per photo):** EXIF `DateTimeOriginal` and GPS with Pillow → `exif_date`, `exif_distance_to_address_km` or `exif_missing: true`; `imagehash.phash` compared with every photo of other claims (Hamming ≤ 6 = copy) → `copy_in_other_claim`; vision LLM (fast model, the image) → `shows_declared_damage`, `looks_generated`.
**Deeper check (Judge asks):** Google Vision `POST https://vision.googleapis.com/v1/images:annotate?key=…` with `WEB_DETECTION`; for each full or partial match page, an LLM call reads the page title and URL for a publication date. A match dated before `event_date` → finding `exact_copy_before_event: true` with the URL.

One Evidence for all photos; `findings` carry a `photo` name in `metric` as `"<photo>:<check>"`, plus the plain `exact_copy_before_event` finding when it applies.

- [ ] Tests: claim with no photos → `inconclusive`, gap "nu există fotografii" (Review Focus 1); EXIF date in March for a September event → finding present and verdict prompt includes it; identical image in another claim → `copy_in_other_claim True`; Vision fixture with a full match → `exact_copy_before_event True`; Vision failing → other checks still returned, gap names Vision; at most 6 `ctx.fetch` calls with 5 photos.
- [ ] Implement, live run on the fraud case photos, commit.

### Task 13: Street view — BE, 07:45–08:45

**Sources:** Mapillary `https://graph.mapillary.com/images?fields=id,captured_at,thumb_1024_url,geometry&bbox=…` (±60 m), filtered to `captured_at < event_date`, nearest first; Google `https://maps.googleapis.com/maps/api/streetview/metadata?location=…` then `/streetview?size=640x640&location=…`.

**Quick check:** `pre_event_image_date`, `pre_event_image_source`, `pre_event_image_url`, `distance_m`. **Deeper check:** vision LLM gets the pre-event image and up to two client photos → `prior_condition`, `preexisting_damage` (bool or null).

- [ ] Tests: Mapillary fixture with images before and after the event → picks the latest one before; Mapillary empty → Google used; both empty → `inconclusive`, gap "nicio imagine stradală înainte de eveniment"; Google metadata `status != "OK"` treated as empty.
- [ ] Implement, live run on both cases, commit.

### Task 14: News — BE, 08:45–09:30

**Sources:** GDELT `https://api.gdeltproject.org/api/v2/doc/doc?mode=artlist&format=json&maxrecords=25&startdatetime=…&enddatetime=…` with two queries (Romanian and English: locality + damage word), `await asyncio.sleep(5)` between them. Backup: `ctx.llm` on a web-search-enabled OpenRouter model asked for up to 5 reports with URLs. The fast model filters results to reports that name the locality or county and the event.

**Findings:** one per confirmed report: `metric: "news_report"`, `value: title`, `source: outlet`, `url`, plus `reports_confirmed` (count).

- [ ] Tests: GDELT fixture with 3 relevant and 5 irrelevant articles → `reports_confirmed == 3` (filter LLM patched); GDELT returning the rate-limit text → backup used; both failing → `inconclusive`; reports found by the backup have `data_quality ≤ 0.5` passed in the prompt.
- [ ] Implement, live run, commit.

### Task 15: Tune both cases — BE, 09:30–10:30

- [ ] Run the fraud case live 3 times. Required: round 1 band `likely` or `uncertain`; Judge re-dispatches risk_zones and photo_forensics; final recommendation `antifraud_referral`; under 90 s. Adjust weights in `thresholds.py` and prompts only; record the final numbers in `demo/README.md`.
- [ ] Run the storm case: four agents, satellite and risk zones shown as not relevant, recommendation `fast_track`. Seed it already investigated.
- [ ] On close of the fraud case, `save_footprint` stores the polygon reference, meteo maxima and confirmed news; a second flood claim nearby gets it in `claim["footprints"]`.
- [ ] Commit `demo/cache/` in full.

### Task 16: Offline run and the 11:00 gate — BE, 10:30–11:00

- [ ] `REPLAY=1` with Wi-Fi off: `rerun` the fraud case → same recommendation, under 20 s, zero `CacheMiss`.
- [ ] `pytest -q` → all green.
- [ ] **Gate:** an agent whose tests fail or whose live run errors is switched to its cached responses for the demo (set `REPLAY_AGENTS=<names>`, read by `AgentContext.fetch`), in this order of sacrifice: news → street_view → photo_forensics web search → satellite GFM. Tell DP which ones, for the pitch.
- [ ] Commit.

### Task 17: Clean runs and docs — BE + all, 11:00–12:30

- [ ] Three consecutive clean end-to-end runs through the hosted app, then one on the laptop fallback.
- [ ] Update root `README.md`: replace the UiPath workflow table and team table with the real architecture (diagram from design §3), how to run locally, data-source attributions.
- [ ] Commit, tag `demo`.

### Task 18 (optional): UiPath coded agent — BE, 11:30–12:15, only after Task 17's three runs

- [ ] In `backend/`: add `uipath-langchain`, `uipath init` pointing at the compiled graph in `engine/graph.py`, `uipath run` locally with the fraud claim as input and a sink that prints.
- [ ] `uipath pack` and `uipath publish`; start one run from the UiPath dashboard and screenshot it for the pitch. Stop at 12:15 regardless.

---

## Frontend tasks (FE)

| # | Slot | Task | Needs |
| --- | --- | --- | --- |
| F1 | 22:00–23:15 | Vite + React + TS scaffold, router, API client with a mock/live switch, deploy to Vercel | — |
| F2 | 23:15–02:30 | Queue screen; case screen: stage timeline, one lane per agent per round, Judge decisions in plain words, all from `demo/mock/*.json` | T2 mock files |
| F3 | 02:30–05:15 | Switch to the live API; consume the stream (past steps first, then live); map with house, flood polygon and distance line (Leaflet + `GET /footprints/{id}`) | T8 |
| F4 | 05:15–07:45 | Photos with per-photo verdicts; score with contribution bars and gate banner; Approve / Modify / Investigate more; reject-evidence control | T8 |
| F5 | 07:45–10:30 | Replay slider over stored trace steps; "not relevant for this damage type" state; loading, empty and error states; visual polish | — |
| F6 | 10:30–11:00 | Intake form with photo upload (only if F5 is finished) | T8 |

## Demo and pitch tasks (DP)

| # | Slot | Task | Needs |
| --- | --- | --- | --- |
| D1 | 22:00–23:30 | Mapillary and Railway/Vercel accounts; draft both claim stories; shortlist flood addresses in the EMSR758 area and storms with press coverage | — |
| D2 | 23:30–01:00 | Using `check_site.py`: pick the flood house (outside the flood area, on a real slope, near water) and a storm with gusts ≥ 70 km/h in Open-Meteo. Write `demo/cases/fraud.json`, `demo/cases/honest.json` (claim + policy, with lat/lon) and photos: fraud photos with metadata stripped, at least one a real flood picture already published online; honest photos with matching EXIF | T3 |
| D3 | 01:00–02:30, 08:45–11:00 | Pitch deck (5 min) using the measured numbers, not "140 mm" | — |
| D4 | 06:45–08:45 | Eight more synthetic claims as JSON for the queue screen | T2 shapes |
| D5 | 11:30–12:00 | Screen-record both cases as the backup video into `demo/` | T17 |
| D6 | 12:30–14:00 | Rehearse three times, Q&A prep, name any agent running on saved data | T16 |
