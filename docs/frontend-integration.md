# Frontend connected to the backend: what was done

Written on the night of 14 November 2026, for reading the next morning.

The frontend mock (`asigit-frontend.zip`) is now in `frontend/` and talks to the real backend. Nothing on screen
comes from fake data any more. The work is on the branch `rc/frontend`. It is **not merged into `main` and not
pushed**. The backend was not changed.

Contents:

1. [Where things stand](#1-where-things-stand)
2. [How to run it](#2-how-to-run-it)
3. [What was removed](#3-what-was-removed)
4. [What was added](#4-what-was-added)
5. [Buttons that stayed, and what each one calls](#5-buttons-that-stayed-and-what-each-one-calls)
6. [Names that were changed](#6-names-that-were-changed)
7. [Assumptions I made](#7-assumptions-i-made)
8. [Decisions waiting for you](#8-decisions-waiting-for-you)
9. [Known problems and what was not tested](#9-known-problems-and-what-was-not-tested)
10. [Where the code is](#10-where-the-code-is)

---

## 1. Where things stand

| | |
| --- | --- |
| Branch | `rc/frontend`, two commits on top of `main` |
| First commit | the mock exactly as received, so you can always see or recover the original |
| Second commit | the connection to the backend and everything in this document |
| Build | `npm run build` passes with no type errors |
| Tests | 19 frontend tests pass (`npm test`); the 138 backend tests are untouched |
| Checked by hand | queue, case screen, replay, live run, map, set aside, decision, ask for more, run again; all against a backend running on saved responses |
| Not done | merge, push, deploy; see [section 8](#8-decisions-waiting-for-you) |

---

## 2. How to run it

Two terminals.

Backend (from saved responses, no keys needed):

```bash
cd backend && REPLAY=1 .venv/bin/uvicorn app.main:app --port 8000
```

Frontend:

```bash
cd frontend && npm install && npm run dev
```

Then open http://localhost:5173.

- The frontend reads the backend address from `VITE_API_URL`. The default is `http://localhost:8000`. To change it,
  copy `frontend/.env.example` to `frontend/.env`.
- Your backend on port 8000 was started before the merge. **Restart it** so it runs the current code.
- Leave out `REPLAY=1` to run with real keys. See [problem 2](#9-known-problems-and-what-was-not-tested) first.

---

## 3. What was removed

Your rule: anything on screen that the backend cannot serve disappears. This is the full list. Every item can be
seen in the first commit (`git show 5b79a00 --stat`, or `git diff 5b79a00 rc/frontend -- frontend/`).

### Buttons

| Removed | Where it was | Why |
| --- | --- | --- |
| **Correct a field** (pencil icon) and the "Edited by you" label | Step details, document step | The backend has no way to change a claim's fields. |
| **Re-run from here** | Step details, after correcting a field | The backend can only re-run the whole investigation. That is now the "Run again" button ([section 4](#4-what-was-added)). |
| **Undo** (a decision) | Decision panel | The backend has no undo for a decision. "Run again" erases the decision together with the run. |
| **Restore finding** (the reverse of "set aside") | Full report, "What moved the score" | The backend can set a finding aside but cannot bring it back. |
| **Event footprint** button and its card | Queue, left menu | The card showed invented numbers (37 linked claims, 81%). The backend has no list of footprints and no such counts. |

### Steps on the pipeline rail (10 became 7)

| Removed step | Why |
| --- | --- |
| Client data validation | The backend does not do this step. |
| Document parsing (with confidence bars per field) | The backend receives a claim as data; it does not read documents. |
| Photo pre-screen | The backend checks photos inside the Photo forensics agent, not as a separate step. |

The seven that stayed: Claim, Policy check, Plan, Agents, Judge, Verdict, Review.

### Things shown that were not real

| Removed | Why |
| --- | --- |
| The two hand-written demo cases and the eight queue rows in `src/mock/data.ts` | Replaced by the claims the backend holds. |
| The drawn map (invented roads, river and flood shape) | Replaced by the real flood polygons from Copernicus, to scale. |
| The map for wind claims (a drawn gust area with "stations") | The backend has no map data for storms. Storm claims have no Map button. |
| Coloured placeholder tiles for photos | Replaced by the real photo files from the backend. |
| "by Ana M." on a logged decision | The backend has no user accounts. |
| The "Wind profile v2" label and "weights from ..." | The backend does not give the weight profile a name. |
| Hand-written reasons why an agent was skipped | The backend only says "not relevant for this type of claim". |
| The hand-written sentence under the plan | Replaced by a count taken from the real plan. |
| Claim types "landslide" and "snow" | The backend handles flood and storm. |
| Score calculated in the browser | The score, band and recommendation now always come from the backend. |
| "Queued for the orchestrator" list | A question now really runs. The list shows the questions asked and the round that answered them. |

### Files

| Removed | Why |
| --- | --- |
| `src/mock/data.ts`, `src/mock/api.ts` | The fake data and the fake data source. |
| `src/components/Guide.tsx` | Not used by any screen in the mock. |
| `tools/shoot.mjs`, `tools/interact.mjs`, and the `puppeteer-core` package | Scripts that clicked through the mock's flows. Those flows changed, and the scripts needed Chrome at a Linux path. |

---

## 4. What was added

Kept to the minimum needed for the app to work for real.

| Added | Why |
| --- | --- |
| **Run again** button (replay bar, when a run is over). It asks once before it acts. | Calls the backend's re-run. Without it, a claim that was investigated or decided once could never be shown again in a demo. It erases the previous run and decision. This is the one new button; see [decision 3](#8-decisions-waiting-for-you). |
| **Confirm** step on "set aside" | Setting a finding aside cannot be undone in the backend, so one extra click protects against a slip. |
| **Replay investigation** button | Shown when the replay of a finished run sits at 0:00. In the mock this spot said "Start investigation", which would now be wrong: the investigation already happened. |
| A live bar instead of the replay bar while a run is in progress | There is nothing to scrub while the run is live. |
| Real map, real photos | See [section 3](#3-what-was-removed). |
| Messages when the backend is off, a claim does not exist, or the backend refuses an action | In the mock nothing could fail. |
| `frontend/.env.example`, 19 tests, this document | |

---

## 5. Buttons that stayed, and what each one calls

| Button | Backend call |
| --- | --- |
| Start investigation (claim never investigated) | `POST /claims/{id}/rerun`, then the live stream |
| Run again | `POST /claims/{id}/rerun`, then the live stream |
| Approve / Approve recommendation | `POST /claims/{id}/decision` with `approve` |
| Choose another route, Confirm override | `POST /claims/{id}/decision` with `modify`, the chosen outcome and the reason |
| Ask for more, Send to orchestrator | `POST /claims/{id}/question`, then the live stream |
| Set aside (a finding) | `POST /claims/{id}/evidence/{id}/reject` |
| Map | `GET /claims/{id}/flood-extent` |
| Photos | `GET /photos/{name}` |

These work only on what is already loaded, so they need no backend call: play, pause, scrub, speed, skip to
verdict, the pipeline steps and agent lanes, the panels on the left, the queue filters, the claim switcher,
light and dark theme, "Jump to this moment".

Backend features that have **no button** (I did not add any; see [decision 4](#8-decisions-waiting-for-you)):
creating a claim with photos (`POST /claims`), and reading a saved event footprint (`GET /footprints/{id}`).

---

## 6. Names that were changed

The frontend now uses the backend's names everywhere, in code and in style classes. There is no translation layer.

| What | Mock | Now (backend's name) |
| --- | --- | --- |
| Agents | `weather`, `streetview`, `risk`, `forensics` | `meteo`, `street_view`, `risk_zones`, `photo_forensics` (`satellite`, `news` unchanged) |
| Outcomes | type `Route`: `fast-track`, `standard`, `investigate` | type `Outcome`: `fast_track`, `standard_review`, `antifraud_referral` |
| Bands | `very-likely` | `very_likely` (`likely`, `uncertain`, `unlikely` unchanged) |
| Claim type | `wind` | `storm` |
| Hypothesis marks | `open`, `conflict` | `inconclusive`, `conflicting` (`confirmed`, `refuted` unchanged) |
| Decision | `approved`, `overridden` | `approve`, `modify` |
| Claim status | `new`, `verdict` | `received`, `investigating`, `awaiting_decision`, `decided` |
| Folder | `src/mock/` | `src/lib/` (shared types and labels), `src/api/` (backend calls) |

What the user reads on screen changed in one place: the third outcome is labelled "Antifraud referral" and
"Refer to the antifraud team" (the mock said "Investigate" and "Refer to special investigations"), to match the
backend's outcome.

---

## 7. Assumptions I made

Each one says what I assumed, why, and where to change it.

**A1. The UI is in English, the backend's text is in Romanian, and I left both as they are.**
Labels, buttons and headings are English (from the mock). Findings, hypotheses, the Judge's reasoning and rule
explanations are Romanian (from the backend). The screen mixes the two. This is the most visible issue; see
[decision 1](#8-decisions-waiting-for-you).

**A2. The product name stays "AsigIT".**
The mock calls the product AsigIT; the repository and backend say ClaimLens. I did not know which is current.
It is one line: `APP_NAME` in `frontend/src/lib/meta.ts` (the page title in `frontend/index.html` also says it).

**A3. The folder is `frontend/`.**
As agreed. `ui/README.md` (a placeholder from the first plan) now points to it.

**A4. A run that finished too fast to watch is replayed at an even pace.**
With saved responses the backend finishes in under a second. So for any run shorter than 15 seconds, the replay
gives each step a fixed length (about 35 seconds for three rounds). The order of steps and all content are
real; only the clock is not. A run that took real time (live keys) is shown on the backend's own timestamps.
Where: `PACE` and `PACED_BELOW_MS` at the top of `frontend/src/api/build.ts`.

**A5. A finished claim opens on its result, not at the start.**
You see the score and recommendation at once; the replay bar goes back through the run.

**A6. "New claims" are claims not investigated yet or running now. "Verdict ready" are finished ones, decided or not.**
Decided claims stay in the list, marked "decided".

**A7. The queue asks the backend for each claim's details.**
The claim list from the backend has no claimant name or description. So the queue makes one extra request per
claim. Fine for a demo with a few claims; for many claims the backend list should carry those two fields.

**A8. Amounts are in RON.**
The backend stores a number with no currency.

**A9. Points per finding are worked out from the backend's numbers.**
The backend gives each agent's push on the score in its own unit. The "+14" and "−31" on screen are "the score
with this finding, minus the score without it", computed from those. The final score itself is never recomputed.
"Starts at 50" is worked out the same way. Where: `frontend/src/lib/score.ts`.

**A10. Only each agent's latest answer is counted.**
This is the backend's rule: when an agent is sent back, its new answer replaces the old one. The report lists the
ones that count, plus any set aside.

**A11. A finding cannot be set aside after the decision is made.**
The backend would allow it. I hid it because changing the score under a recorded decision would be confusing.

**A12. The authenticity gate says "Not checked" when the claim has no photos.**
The mock always said "Passed". With no photos nothing was checked, and "Passed" would be a false claim.

**A13. The first step, "Claim", shows the stored claim.**
The backend has no intake step. This step shows the claim's facts as the backend holds them (number, policyholder,
address, event, notification date, amount, photo count). I kept it so the rail starts with what was claimed.

**A14. Short labels are built from measured values, in English.**
"150 m outside the flood", "47.9 mm in 24 h", "90.4 km/h gusts". They are put together from the numbers the
agents measured, never from the model's text. Where: `headline()` in `frontend/src/api/build.ts`.

**A15. Policy rule names are English labels for the backend's five rules.**
The explanation next to each is the backend's own text. Where: `RULE_LABEL` in `frontend/src/lib/meta.ts`.

**A16. The sentence under the verdict is the Judge's first two points.**
The mock had a hand-written sentence. I use the first two "tensions" from the Judge's last round.

**A17. The map shows only what the backend has.**
The house, the Copernicus flood polygons, the measured distance to the flood edge, the nearest water and the
height difference. No roads or background tiles. It appears only for claims with a mapped flood.

**A18. After you ask a question, the replay starts from your question, not from the beginning.**

**A19. If the live stream drops, the screen asks the backend every two seconds until the run is over.**

**A20. The backend was not changed.**
Everything was done on the frontend side, so `rc/frontend` touches only `frontend/`, `docs/`, `ui/README.md`,
`README.md`, `demo/mock/README.md` and `.gitignore`.

---

## 8. Decisions waiting for you

1. **Language.** Mixed English and Romanian on one screen will be noticed in the demo. Two ways out:
   translate the frontend's labels to Romanian (frontend-only, no keys needed, a few hours), or make the backend
   answer in English (needs the saved responses recorded again with real keys). I recommend the first.
2. **Product name**: AsigIT or ClaimLens. One line to change (A2).
3. **Keep "Run again"?** It is the one button I added that was not in the mock. I recommend keeping it: without
   it a decided claim cannot be demonstrated twice. To remove it, delete the last block in
   `frontend/src/components/ReplayBar.tsx`.
4. **A form to file a new claim?** The backend supports it (`POST /claims` with photos); the mock has no screen
   for it, so there is none. Say if you want one.
5. **Merge and push.** Nothing is merged or pushed. When you are happy: merge `rc/frontend` into `main` and push.
6. **"Ask for more" in the demo**: see problem 1 below, then decide whether to show it.

---

## 9. Known problems and what was not tested

1. **"Ask for more" gives a poor result when the backend runs on saved responses (`REPLAY=1`).**
   A new question has no saved answer. The agent reports "interpretation unavailable", the Judge is "unavailable",
   and the score moves for no good reason (in my test from 79.5 to 54.6). The frontend shows exactly what the
   backend returned. With real keys this does not happen. For a demo on saved responses, do not press it, or
   record an answer for the exact question you plan to ask.
2. **Not tested with real keys.** I did not spend your API credit. Everything was tested on saved responses, where
   a run ends in under a second. A real run (about a minute, steps arriving live) uses the same code and has a
   test for its layout, but nobody has watched one in this UI yet. Do one before the demo.
3. **Photos were not tested with real files.** Neither demo case has photos yet. The photo grid and the per-photo
   notes are built and type-checked, but I have only seen the "No photos on this claim" state.
4. **After a finding is set aside, two places still mention it**: the agent's lane on the rail, and the Judge's
   sentence under the verdict. The score, the report list and the recommendation are correct.
5. **Light theme and phone layout were only spot-checked** (one phone screenshot of the case screen; light theme
   not re-checked after the changes).
6. **Deploying.** `VITE_API_URL` is read when the frontend is built, so on Vercel it must be set to the Railway
   address before building.
7. **The backend allows any website to call it** (it was built that way for the hackathon). Fine for the demo,
   not for real use.

---

## 10. Where the code is

```
frontend/src/api/client.ts     every backend call the app makes (the only place that uses fetch)
frontend/src/api/build.ts      turns backend responses into what the screens draw; the timeline lives here
frontend/src/api/hooks.ts      keeps the queue and one case in step with the backend, including the live stream
frontend/src/api/build.test.ts 19 tests, run on real recorded backend responses (src/api/fixtures/)
frontend/src/lib/types.ts      backend response types, and the screen's own types
frontend/src/lib/meta.ts       labels: stages, agents, bands, outcomes, policy rules, product name
frontend/src/lib/score.ts      "points" for the charts, from the backend's numbers
frontend/src/lib/derive.ts     what each stage and agent lane is doing at a given moment
frontend/src/lib/hooks.ts      the clock (replay and live), theme, routing
frontend/src/components/       the screens (same files as the mock)
frontend/src/styles.css        the mock's styles; the few additions are in the last block, "Backend wiring"
```

To see exactly what changed from the mock:

```bash
git diff 5b79a00 rc/frontend --stat -- frontend/
```
