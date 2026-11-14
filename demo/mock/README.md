# Mock API responses for the frontend

Placeholder numbers, real shapes. They were used to build the UI before the backend was live.
The app in `frontend/` now talks to the real backend and does not read these files (see `docs/frontend-integration.md`).

| File | Same shape as |
| --- | --- |
| `claims_list.json` | `GET /claims` |
| `claim_fraud.json` | `GET /claims/{id}` (with the intake keys `checks`, `flags`, `documents`, `run_mode`) |
| `trace_fraud.json` | `GET /claims/{id}/trace`; each item is also one `trace` event on `GET /claims/{id}/stream` |

Stream events (server-sent events): `trace` (one step), `evidence` (one evidence row), `score`
(`{round, score, band, recommendation, contributions, gates}`), `status` (`{status}`).
Step ids: `intake`, `documents`, `client`, `rules` (policy check), `photos`, `paused`, `continue`, `plan`, `r<round>.dispatch`, `r<round>.<agent>.<n>`, `r<round>.score`, `r<round>.judge`, `final`.
Outcomes: `fast_track`, `standard_review`, `antifraud_referral`. Bands: `very_likely`, `likely`, `uncertain`, `unlikely`.
Claim statuses: `received`, `investigating`, `paused`, `awaiting_decision`, `decided`.
Score contributions: one per agent and round, `"context"`, and one `"client"` entry per client or document flag,
with its `reason` (the other entries have `reason: null`).

## Live stream rules (read before wiring `EventSource`)

- On connect the server first sends every stored `trace` step, then live events.
- The server **closes the stream** after the `status` event that ends a run (`paused`, `awaiting_decision` or `decided`).
  Call `es.close()` when you receive it; otherwise the browser reconnects every few seconds and replays everything.
- After `POST /claims/{id}/rerun`, `/question` or `/continue`, open a new stream.
- Past `evidence` and `score` events are not replayed on connect. Load `GET /claims/{id}` first, then apply live events.
- Step ids are unique per claim. A question run closes with `r<round>.final` and starts with `r<round>.question`.
- Map layer: `GET /claims/{id}/flood-extent` returns the flood polygons as GeoJSON (404 if the claim has none).
- Claim ids: letters, digits, `-`, `_`. Photo uploads: jpg, jpeg, png, webp, heic.

## Paused claims, continue, documents

- A claim whose policy check fails stops after the photo check with step `paused` and status `paused` (no score yet).
- `POST /claims/{id}/continue` (only when `paused`, else 409) → `{"id", "status": "investigating"}`; the run starts
  with step `continue`, then `plan`, as usual.
- `POST /claims/{id}/decision` while paused: only `{"decision": "modify", "outcome", "reason"}`;
  `approve` → 409 `Nu există încă o recomandare`. `/question` while paused → 409.
- `POST /claims/{id}/rerun` on a paused claim reads the PDFs again from the start.
- `GET /documents/{id}/claim_form.pdf` and `GET /documents/{id}/policy.pdf` serve the original PDFs.
- Full shapes of `checks`, `flags`, `documents`, `run_mode`: `docs/contracts.md`, section "Intake".
