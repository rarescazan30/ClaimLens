# Mock API responses for the frontend

Placeholder numbers, real shapes. Build the UI against these until the backend is live.

| File | Same shape as |
| --- | --- |
| `claims_list.json` | `GET /claims` |
| `claim_fraud.json` | `GET /claims/{id}` |
| `trace_fraud.json` | `GET /claims/{id}/trace`; each item is also one `trace` event on `GET /claims/{id}/stream` |

Stream events (server-sent events): `trace` (one step), `evidence` (one evidence row), `score`
(`{round, score, band, recommendation, contributions, gates}`), `status` (`{status}`).
Step ids: `rules`, `plan`, `r<round>.dispatch`, `r<round>.<agent>.<n>`, `r<round>.score`, `r<round>.judge`, `final`.
Outcomes: `fast_track`, `standard_review`, `antifraud_referral`. Bands: `very_likely`, `likely`, `uncertain`, `unlikely`.

## Live stream rules (read before wiring `EventSource`)

- On connect the server first sends every stored `trace` step, then live events.
- The server **closes the stream** after the `status` event that ends a run (`awaiting_decision` or `decided`).
  Call `es.close()` when you receive it; otherwise the browser reconnects every few seconds and replays everything.
- After `POST /claims/{id}/rerun` or `/question`, open a new stream.
- Past `evidence` and `score` events are not replayed on connect. Load `GET /claims/{id}` first, then apply live events.
- Step ids are unique per claim. A question run closes with `r<round>.final` and starts with `r<round>.question`.
- Map layer: `GET /claims/{id}/flood-extent` returns the flood polygons as GeoJSON (404 if the claim has none).
- Claim ids: letters, digits, `-`, `_`. Photo uploads: jpg, jpeg, png, webp, heic.
