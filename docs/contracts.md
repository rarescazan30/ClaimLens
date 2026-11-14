# Shared contracts

Agreed formats every part of the system uses. Change them only after telling the whole team —
agents, Judge, Data Fabric and UI all depend on them.

## Evidence (output of every specialist agent)

Same format for all agents, so the Judge and the UI never depend on a specific agent.

```json
{
  "agent": "meteo",
  "round": 1,
  "hypothesis": "Rafale >= 70 km/h la adresa, 12.11.2026 18:00-23:00",
  "verdict": "supports | contradicts | inconclusive",
  "strength": 0.8,
  "data_quality": 0.6,
  "findings": [
    {"metric": "wind_gusts_10m_max", "value": 87, "unit": "km/h",
     "source": "Open-Meteo ERA5-Land", "url": "...", "spatial_res_km": 9,
     "retrieved_at": "2026-11-13T21:40Z"}
  ],
  "reasoning_steps": ["..."],
  "gaps": ["Rezolutie 9 km, nu prinde rafale locale"],
  "suggested_followup": "Cauta statia meteo cea mai apropiata sau stiri din cartier"
}
```

- `strength` — how much the evidence moves the verdict.
- `data_quality` — how much we can trust the source (resolution, time distance, official or not).
- Kept separate because the Judge uses them differently.

## Trace event (one per step, drives the UI timeline and replay)

```json
{"case_id": "C-1042", "step_id": "r2.risk.3", "parent": "r2.judge",
 "actor": "agent:risk_zones", "type": "tool_call | observation | decision | escalation",
 "summary": "Diferenta de nivel casa vs. marginea poligonului: +6.2 m",
 "inputs": {}, "outputs": {}, "sources": ["Copernicus DEM"],
 "status": "done", "started_at": "...", "ended_at": "..."}
```

## Score

```
logit(P) = logit(P0) + Σ_i  w[t,i] · s_i · q_i · d_i
```

- `P0` base probability per damage type; `w` insurer weight per damage type × agent;
  `s` strength; `q` data_quality; `d` = +1 supports / −1 contradicts / 0 inconclusive.
- F1 (coverage) and clear fakes in F2 are **gates**, not terms in the sum.
- Bands: very likely ≥ 85 · likely 65–85 · uncertain 35–65 · unlikely < 35.
- Called the **claim plausibility score** — never "probability the company pays".
- Weights change prioritisation and the recommendation only. **Nothing is ever rejected automatically.**

## Intake: documents, early checks, the pause (API)

Every claim filed through `POST /claims` has two PDFs, the claim form and the policy. The run reads them back
(code, never an AI), runs five early steps, and pauses before the agents when a policy rule fails.

```
intake → documents → client → rules (policy) → photos ──(all rules pass)──► plan → agents → judge … → final
                                                      └──(a rule fails)──► paused
paused ── POST /claims/{id}/continue ──► continue → plan → agents … (as above)
       └─ POST /claims/{id}/decision with decision "modify", an outcome and a reason
```

### Claim status

`received` → `investigating` → `paused` | `awaiting_decision` → `decided`.
`paused`: the early steps found a failed policy rule; no agent ran, there is no score and no recommendation yet.

### Routes

| Route | Detail |
| --- | --- |
| `POST /claims` | multipart: `data` (JSON `{"claim": {...}, "policy"?: {...}}`) and `photos`. Same JSON as before; the claim may also carry the policyholder's `holder_name`, `cnp`, `telefon` (alias `phone`), `email`, `iban` (written into the claim form), and `policy` may carry `cnp` (stored, written into the policy PDF). Policy keys that are not policy columns are ignored. The backend writes `claim_form.pdf` and `policy.pdf` and investigates from them. `lat`/`lon` in the JSON are not used: the address read from the PDF is located during the run (a failed lookup is a flag, not an error). Returns `{"id"}`. |
| `POST /claims/{id}/continue` | only when `paused` (else 409): starts again at the plan, reusing the checks already done; the failed rule stays a flag, keeps forcing standard review and reaches the Judge. Returns `{"id", "status": "investigating"}`. |
| `POST /claims/{id}/decision` | also when `paused`, only with `{"decision": "modify", "outcome", "reason"}`. `approve` while paused → 409 `Nu există încă o recomandare`. |
| `POST /claims/{id}/question` | 409 while `paused` (continue or decide first). On a claim read from documents, the question run keeps the stored rule flags and early flags. |
| `POST /claims/{id}/rerun` | also on a paused claim: reads the PDFs again from the start. |
| `GET /documents/{claim_id}/{name}` | `name` is `claim_form.pdf` or `policy.pdf`: the original PDF (`application/pdf`), for an "Open PDF" link. 404 for any other name, a claim without documents, or a path outside the documents folders. |

**Client data and flags.** Client data comes from the documents, as on a paper form: whatever the caller leaves
out is missing from the PDF and is flagged, and each client/document flag lowers the score by one `client` line.
To file a claim with no such flags, send: on the claim `cnp` (valid), `telefon` (Romanian format), plus everything
already required (`policy_id`, `damage_type`, `event_date`, `notified_at`, `address`, `description`,
`amount_claimed`); `email` and `iban` are optional but flagged when malformed; on the policy `cnp` (same as the
claim's), `holder_name`, `address`, `valid_from`, `valid_to`, `waiting_days`, `covered_risks`, `sum_insured`,
`product`. The address must be found by the map lookup at house or street level.

### `GET /claims/{id}`: new keys

```json
{
  "checks": {
    "intake":    {"step": "intake", "items": [CheckItem], "flags": [Flag]},
    "documents": {"step": "documents", "items": [...], "flags": [...]},
    "client":    {"step": "client", "items": [...], "flags": [...]},
    "policy":    {"step": "policy", "items": [...], "flags": [...]},
    "photos":    {"step": "photos", "items": [...], "flags": [...]}
  },
  "flags": [Flag],
  "documents": {"claim_form": {"numar_dosar": "C-1042", "...": "..."}, "policy": {"numar_polita": "P-7731"}},
  "run_mode": "live | replay | record | null"
}
```

- `CheckItem`: `{"id", "label", "value": str | null, "status": "ok | flag | fail | info", "reason": str | null}`.
- `Flag`: `{"step": "intake | documents | client | policy | photos", "code", "field": str | null,
  "severity": "warn | fail", "reason"}`. `flags` is every flag of the five steps, in step order.
- `checks` is `{}` and `flags` `[]` for a claim not yet run, or stored without documents (old demo data).
- `documents`: the fields read from each PDF, by form-field name (`CLAIM_FIELDS` / `POLICY_FIELDS` in
  `backend/engine/documents.py`), read again on every request; `{}` for one PDF that is missing or unreadable;
  `{}` overall for a claim without documents.
- `run_mode`: the mode of the latest run (`null` before any run).
- `claim` no longer carries `documents`, `checks`, `early_flags` or `run_mode`.

### Trace step ids (new)

`intake`, `documents`, `client`, `photos` (one per early step, `outputs.items` and `outputs.flags`; `client` also
`outputs.coordinates`), `paused` (`outputs.failed_rules`, the last step of a paused run), `continue` (actor
`adjuster`, `outputs.failed_rules`, the first step after `POST /continue`). `rules` stays the policy check (on the
documents path it also has `outputs.items`).

### Score contributions

Besides the agents and `"context"`, one entry per client or document flag:
`{"agent": "client", "round": 0, "delta_logit": -0.25, "reason": "CNP-ul din cerere nu are un format valid …"}`.
`reason` is shown as is; it is `null` for the other entries.
