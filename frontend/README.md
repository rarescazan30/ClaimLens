# AsigIT frontend

Evidence desk for property-claims adjusters. An orchestrator dispatches specialist agents, a judge weighs
what they find and can send them back, and the adjuster decides with the whole trace in view.

Everything runs on mock data for now. React 19, Vite, TypeScript, no UI framework.

## Run it

```bash
npm install
npm run dev            # http://localhost:5173
npm run build          # production build in dist/
npm run build:single   # one self-contained dist-single/index.html, handy for sharing
```

Deep links for demos: `#/case/C-1047?t=18500` opens a case at 18.5 s into the run; add `&tab=report` for the report.

## Screens

| Route | What it shows |
| --- | --- |
| `#/` | Claims queue: new claims, verdict-ready claims sorted strongest first, event footprint, quick-peek drawer |
| `#/case/:id` | Pipeline rail with 10 checkpoints, agent lanes and the judge loop; replay bar. Everything else opens from the dock below it, one panel at a time: step details, score, map, claim, photos, full report |
| `#/case/:id?tab=report` | Same screen with the full report open: verdict, score bands, what moved the score, hard gates, photos, decision controls |

Reviewer controls: start / pause / scrub / replay the run, pin any checkpoint or agent lane, correct an extracted
field and re-run from that step, set a finding aside (the score recomputes), approve the recommendation, override it
with a reason, or send a follow-up question to the orchestrator.

## Where things live

```
src/mock/types.ts     data contracts (CaseFile, AgentRun, Evidence, JudgeDecision, TraceEvent)
src/mock/data.ts      two full demo cases (C-1042 wind, C-1047 flood) and the queue
src/mock/api.ts       the only file the UI calls for data
src/lib/derive.ts     timeline -> stage / lane / loop state
src/lib/score.ts      logit(P) = logit(P0) + sum(weight * strength * quality * direction), bands, routing
src/lib/hooks.ts      replay clock, theme, hash routing, per-case reviewer session
src/components/       Pipeline (rail), Aurora (WebGL light), StageDetail, Report, Queue, ...
src/styles.css        design tokens (light and dark) and all styles
```

## Connecting the backend

Replace the three functions in `src/mock/api.ts` and keep their return types:

- `listQueue(): Promise<QueueCase[]>`
- `getCase(id): Promise<CaseFile>`
- `getTrace(id): Promise<TraceEvent[]>` (the flat event format from the workflow doc: `case_id, step_id, parent,
  actor, type, summary, outputs, sources, status, started_at, ended_at`)

The UI is driven by time offsets (`at`, `dur` in ms). For a live run, feed events as they arrive and advance the clock
in `useRun` from the latest event timestamp instead of `requestAnimationFrame`; recorded runs replay as they do now.

Reviewer actions are local state today (`getSession` / `saveSession` in `src/lib/hooks.ts`). Each maps to one call:
approve or override -> human task completion; "ask for more" -> new orchestrator task; set a finding aside -> re-score;
field correction -> re-run from the affected stage.

The product name is one constant: `APP_NAME` in `src/mock/meta.ts`.

## Look

Deep ink-violet ground with soft indigo light (a WebGL shader, with a CSS gradient fallback). Lavender marks anything
you operate or follow, mint marks what supports the claim, rose what contradicts it, amber what is uncertain. Everything
is set in Geist at medium weight with tight tracking.

Each screen follows the same pattern: a numbered kicker (`01 —— Claims queue`), a headline whose second half is
lavender, one big figure that counts up, and content that rises in one piece at a time. On a case, the score builds in
a card beside the headline with the findings that moved it listed underneath, and a thin line along the bottom of the
window shows how far the run has got.

Dark is the default and light is one click away. Tokens and all of the above live in the last block of
`src/styles.css` ("Violet pass"), which overrides the earlier ones. Shader: `src/components/Aurora.tsx` (pauses off
screen, honours reduced motion).

## Checks

```bash
node tools/shoot.mjs      # screenshots of every main state, both themes, 1440 / 1024 / 390
node tools/interact.mjs   # click-through of the reviewer flows
```

Both need Chrome at `/usr/bin/google-chrome` (edit the path in the scripts if yours differs).

Demo data: people, policies and claims are synthetic.
