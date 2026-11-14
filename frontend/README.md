# AsigIT frontend

Evidence desk for property-claims adjusters. An orchestrator dispatches specialist agents, a judge weighs
what they find and can send them back, and the adjuster decides with the whole trace in view.

It runs on the ClaimLens backend in `../backend`. Nothing on screen is mock data.
What changed when the mock was connected, what was removed and every assumption made:
[`../docs/frontend-integration.md`](../docs/frontend-integration.md).

React 19, Vite, TypeScript, no UI framework.

## Run it

Start the backend first (see `../backend/README.md`), for example from saved responses:

```bash
cd ../backend && REPLAY=1 .venv/bin/uvicorn app.main:app --port 8000
```

Then:

```bash
npm install
npm run dev            # http://localhost:5173
npm run build          # production build in dist/
npm test               # tests for the layer that reads backend responses
```

The backend address comes from `VITE_API_URL` (default `http://localhost:8000`). To change it, copy
`.env.example` to `.env`. It is read at build time, so set it before `npm run build` when deploying.

Deep links: `#/case/C-1042` opens a case; `#/case/C-1042?t=18500` opens it 18.5 s into the replay; add
`&tab=report` for the report.

## Screens

| Route | What it shows |
| --- | --- |
| `#/` | Claims queue: claims not investigated yet, claims with a verdict sorted strongest first, quick-peek drawer |
| `#/case/:id` | Pipeline rail with 7 checkpoints, agent lanes and the judge loop; replay bar. Everything else opens from the dock: step details, score, map, claim, photos, full report |
| `#/case/:id?tab=report` | Same screen with the full report open: verdict, what moved the score, hard gates, photos, map, decision controls |

Adjuster controls, each one a backend call: start the investigation, run it again, approve the recommendation,
choose another outcome with a reason, ask the agents one more question, set a finding aside.
Play, pause, scrub and speed replay a finished run and call nothing.

## Where things live

```
src/api/client.ts      every backend call (the only file that uses fetch)
src/api/build.ts       backend responses -> what the screens draw (CaseFile); the timeline is laid out here
src/api/hooks.ts       the queue and one case, kept in step with the backend, including the live stream
src/api/build.test.ts  tests, on real recorded backend responses (src/api/fixtures/)
src/lib/types.ts       backend response types and the screens' own types
src/lib/meta.ts        labels: stages, agents, bands, outcomes, policy rules, product name (APP_NAME)
src/lib/score.ts       "points" for the charts, from the backend's own numbers
src/lib/derive.ts      timeline -> stage / lane / loop state at a given moment
src/lib/hooks.ts       the clock (replay and live), theme, hash routing
src/components/        Pipeline (rail), Aurora (WebGL light), StageDetail, Report, Queue, ...
src/styles.css         design tokens (light and dark) and all styles
```

Identifiers (agents, bands, outcomes, damage types) are spelled as the backend spells them.

## How a run reaches the screen

- A finished run: `GET /claims/{id}` and `GET /claims/{id}/trace` are turned into one `CaseFile`. The screen is a
  function of that file and a clock in ms, so the run can be replayed, paused and scrubbed.
- A live run: after `POST /rerun` or `POST /question` the app opens `GET /claims/{id}/stream`. Each event makes it
  read the claim again; the clock follows wall time. When the backend says the run is over, the stream is closed.
- A run served from saved responses ends in under a second, so its replay uses even pacing instead of the
  backend's timestamps. The steps and their order are the real ones.
- The score, band and recommendation are always the backend's. The browser never computes them.

## Look

Deep ink-violet ground with soft indigo light (a WebGL shader, with a CSS gradient fallback). Lavender marks anything
you operate or follow, mint marks what supports the claim, rose what contradicts it, amber what is uncertain. Everything
is set in Geist at medium weight with tight tracking.

Dark is the default and light is one click away. Tokens live in the "Violet pass" block of `src/styles.css`, which
overrides the earlier ones; the few styles added for the backend connection are in the last block.
Shader: `src/components/Aurora.tsx` (pauses off screen, honours reduced motion).
