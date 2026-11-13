# backend/

FastAPI + SQLite + a LangGraph investigation engine. Design: [`docs/backend-design.md`](../docs/backend-design.md).

```
app/       API routes, live stream, SQLite store, seeding        (knows about the web)
engine/    rules → plan → dispatch → score → judge loop          (knows nothing about the web)
agents/    meteo, satellite, risk_zones, photo_forensics, street_view, news
scripts/   check_site.py (pick demo addresses), try_agent.py (run one agent for real)
tests/     pytest; every external service is faked at the network edge
```

## Run locally

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

```bash
cp .env.example .env
```

Fill in `.env`, then:

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```

```bash
.venv/bin/pytest -q
```

Start an investigation of the seeded fraud case:

```bash
curl -X POST localhost:8000/claims/C-1042/rerun
```

## Keys (`.env`, never committed)

| Variable | Needed for | Without it |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | Orchestrator, Judge, every agent's verdict, vision, news backup | Agents still fetch real data, but every verdict is "inconclusive" |
| `GOOGLE_API_KEY` | Street View metadata and image, Vision web detection (enable both APIs) | Street view falls back to Mapillary only; web copy search is a stated gap |
| `MAPILLARY_TOKEN` | Mapillary street imagery | Street view uses Google only |
| `MODEL_FAST`, `MODEL_STRONG`, `MODEL_SEARCH` | Override the default OpenRouter models | Defaults are used |

Meteo, satellite, risk zones and GDELT need no key.

## Replay mode (offline demo)

Every external response and every model answer is saved under `demo/cache/`. With `REPLAY=1` nothing touches
the network; a request that was never saved fails loudly as a cache miss. `REPLAY_AGENTS=news,street_view`
forces only those agents to saved responses.

Before the demo: run each case once with the network on, commit `demo/cache/`, then run again with `REPLAY=1`.

## Deploy (Railway)

1. New project → Deploy from GitHub repo → root directory `backend`.
2. Add a volume mounted at `/data`; set `DATA_DIR=/data`.
3. Add the keys from `.env` as variables.
4. Open `/health` on the generated address and give that address to the frontend.

## API

See design §8. Extra routes added while building: `GET /claims/{id}/flood-extent` (GeoJSON for the map).
Sample responses: [`demo/mock/`](../demo/mock/).
