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
