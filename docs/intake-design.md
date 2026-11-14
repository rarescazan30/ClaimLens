# Intake checks: design

The five steps a claim goes through **before** the Orchestrator plans: receiving the claim, reading the documents,
checking the client's data, checking the policy, and a quick photo check. Backend and frontend.

Status: **draft for approval**. Decisions marked *(your call)* came from the conversation on 14 November 2026;
decisions marked *(my call)* are proposals you can correct. Nothing here is built yet.

---

## 1. Why

Today a claim enters the backend as clean, typed data, so the first part of the pipeline checks almost nothing:
the "Claim" step only displays the claim, and only the policy rules are real. Three steps from the original mock
(client data validation, document parsing, photo pre-screen) were removed because the backend did not do them.

An adjuster's real work starts with paperwork: is the file complete, is this the policyholder, does the claim fit
the policy, are the photos usable. These steps make that part real, so that every investigation starts from data
the system has itself read and checked, and every problem found early reaches the Judge and the adjuster.

## 2. Goals, non-goals, anti-goals

**Goals**
- A claim is two PDFs (claim form, policy) plus photos. The backend reads them itself.
- Five visible steps, each with its own checks, shown on the rail and in Step details.
- Every problem found is a **flag** with a plain reason. All flags reach the Judge; client-data flags also lower
  the score.
- A failed policy rule **pauses** the claim before the agents. The adjuster sees why and either continues the
  investigation or decides straight away.
- The adjuster can open the original PDFs from the app.

**Non-goals** *(your call)*
- Reading arbitrary, scanned or handwritten documents. Our PDFs come from one template we design.
- An upload screen. Demo claims are built by us.
- Correcting a field in the app or re-running from a middle step.

**Anti-goals**
- The AI rejecting or blocking a claim. A pause only hands the claim to a person, who can always continue.
- A flag that changes the score with no visible reason. Every score change has its own line in the report.
- Breaking the existing investigation loop. Agents, Judge, score and the live stream keep working as today.

## 3. Approaches considered

**A. Documents in a fixed template, read by code** *(chosen)*. We design a PDF form with named fields; the backend
reads the fields by name. Exact, fast, free, no AI. Fits "standard PDFs, not the impressive part".

**B. Any PDF, read by an AI.** Works on documents we did not design, but can misread a figure, needs confidence
scores and a correction flow. Rejected: you decided the documents are standard and this is not where the effort goes.

**C. Keep typed JSON, generate a PDF only for show.** Least work, but the "documents" step would be fake.
Rejected: it breaks the rule that nothing on screen is mock.

## 4. The documents

*(your call)* The two templates (claim form, policy) come from the demo team. They are standard (every claim uses the
same layout), but their exact layout and field names are not fixed yet. The reader is built against the first
sample of each; until then the field list below is the working assumption. *(my call)* If the template is a
fillable PDF form, the backend reads the named fields; if it is a flat typed PDF, it reads the labelled lines
("Număr poliță: P-7731"). Either way it is read by code, not by an AI.

**Claim form (`cerere_despagubire.pdf`)**

| Field | Example |
| --- | --- |
| `numar_dosar` | C-1042 |
| `numar_polita` | P-7731 |
| `nume_asigurat` | Persoană Sintetică Unu |
| `cnp` | synthetic, valid checksum |
| `telefon`, `email` | +40 7xx xxx xxx, nume@example.ro |
| `iban` | synthetic, valid checksum |
| `adresa_daunei` | Str. Exemplu 12, Pechea, jud. Galați |
| `tip_dauna` | inundație / furtună |
| `data_evenimentului`, `data_notificarii` | 2024-09-14, 2024-09-19 |
| `descriere` | free text |
| `suma_solicitata` | 48000 |
| `numar_fotografii` | 3 |

**Policy (`polita.pdf`)**

| Field | Example |
| --- | --- |
| `numar_polita`, `produs` | P-7731, PAD |
| `nume_asigurat`, `cnp` | must match the claim form |
| `adresa_asigurata` | Str. Exemplu 12, Pechea, jud. Galați |
| `valabila_de_la`, `valabila_pana_la` | 2024-02-01, 2025-01-31 |
| `zile_asteptare` | 0 |
| `riscuri_acoperite` | inundație, cutremur, alunecare de teren |
| `suma_asigurata` | 100000 |

All personal data in demo PDFs is **synthetic**. The CNP and IBAN are generated to pass their checksums but belong
to no one. Real personal data never goes into the repository.

Libraries: `pypdf` to read the PDFs, `reportlab` to write stand-in PDFs (demo script and `POST /claims` with typed JSON) until the team's template exists; then the backend fills the team's template.

## 5. The five steps

Order on the rail: **Claim → Documents → Client data → Policy check → Photo check → Plan → Agents → Judge →
Verdict → Review** (10 steps, as in the original mock, with Documents moved before Client data because the client
check needs the read fields).

Each step writes one trace step and a list of **check items** (label, value, status ok/flag/fail/info, reason).
Every item that is not ok also produces a **flag**.

| # | Step | Backend does | Flags *(your call: all are flags, nothing stops except a failed policy rule)* |
| --- | --- | --- | --- |
| 1 | **Claim** (intake) | Finds the claim form, the policy and the photos on file; counts them | Missing claim form or policy; photo count differs from `numar_fotografii` |
| 2 | **Documents** | Reads every field of both PDFs; checks each required field is present and well formed (dates, amounts, damage type) | Missing or malformed field (named) |
| 3 | **Client data** | Name and CNP match between claim and policy; CNP checksum; phone and email format; IBAN checksum; finds both addresses on the map (OpenStreetMap) and reports how precise the match is. *(your call)* Demo cases use **real street addresses**, so the house coordinates the agents use come from this lookup | Each mismatch or invalid value; address not found on the map |
| 4 | **Policy check** | The five existing rules, run on the read fields, plus **claimed amount within the sum insured** *(my call: promoted from a hidden score nudge to a visible rule)*. Address rule compares the two geocoded points (same place if within 100 m) instead of the spelling *(my call)* | Each failed rule → **pause** |
| 5 | **Photo check** | The quick photo checks, moved forward from the Photo forensics agent: readable file, capture date present, date after the event, taken near the address, copy of a photo in an earlier claim | No capture date; date before the event; far from the address; copy found. The Judge decides whether to dig deeper |

After step 5 the claim fields used by the agents (address, coordinates, dates, damage type, description, amount,
photos) are the ones read from the documents. The investigation then continues exactly as today.

The Photo forensics agent keeps all its findings, including the quick checks, so its verdict and the demo scores do
not move *(my call)*. The photo step runs the same functions earlier and shows the results as flags; the agent
reuses them instead of reading the files twice. The Judge is told the flags and the agent's findings come from the
same checks. A copy found in an earlier claim stays a flag and a finding; only a copy published online before the
event forces antifraud referral, as today *(my call)*.

## 6. Flags, the score and the Judge

- **Flag** = `{step, code, field?, severity: "warn" | "fail", reason}`. Reasons in Romanian, like the rest of the
  backend's text. Stored on the claim, returned by the API, shown in each step and in the report.
- **Score** *(your call: client-data problems lower it; my call on the numbers)*: each client-data or document flag
  subtracts 0.25 from the log-odds, capped at −1.0 in total, shown in "What moved the score" as one line per flag
  ("CNP does not match the policy −6"). Policy-rule failures do not change the number (they pause the claim and
  force standard review, as today). Photo flags do not change the number directly; the Photo forensics agent and
  the Judge weigh them.
- **Judge and Orchestrator** *(your call: all flags reach the Judge)*: both receive the full flag list, every round.
  Today only the Orchestrator sees failed policy rules and the Judge sees no flags at all; this changes.

## 7. The pause

*(your call: a failed policy rule pauses before the agents; the adjuster can still continue)*

```
intake → documents → client → policy ──(all rules pass)──► photos → plan → agents …
                                   └──(a rule fails)──► photos → PAUSED
                                                                  │
                         adjuster presses "Continue investigation" │  POST /claims/{id}/continue
                                                                  ▼
                                                                plan → agents → judge … (as today)
                         or decides at once                        POST /claims/{id}/decision (outcome + reason)
```

- The photo check still runs before the pause, so the adjuster sees everything the early steps found.
- New claim status **`paused`**. The live stream sends `status: paused` and closes, like the end of a run.
- Continuing starts the investigation from the plan, reusing the checks already done. The failed rule stays as a
  flag, still forces standard review at the end, and reaches the Judge.
- Deciding while paused: only "another outcome, with a reason" (`decision: "modify"`), since there is no
  recommendation yet. The decision is stored as today.
- "Run again" on a paused claim reads the documents again from the start.

## 8. API changes (for the frontend)

Everything existing keeps working. Additions:

| Change | Detail |
| --- | --- |
| `POST /claims` | keeps accepting JSON; it now generates the two PDFs from that JSON with the same code as the demo script, so every claim has documents and the PDFs are the one source of truth *(my call)* |
| Claim status | new value `paused` (between `investigating` and `awaiting_decision`) |
| `GET /claims/{id}` | new keys: `checks` (one list of check items per step: `intake`, `documents`, `client`, `policy`, `photos`), `flags` (all flags), `documents` (each read field with its value and which PDF it came from) |
| Trace step ids | new: `intake`, `documents`, `client`, `photos`, `paused`, `continue`. `rules` stays the policy check |
| `POST /claims/{id}/continue` | only when `paused`; starts the investigation from the plan; 409 otherwise |
| `POST /claims/{id}/decision` | also allowed when `paused`, with `decision: "modify"`, an outcome and a reason |
| `GET /documents/{claim_id}/{name}` | serves the original PDF, for an "Open PDF" link |
| Score contributions | new entries with `agent: "client"` (one per client/document flag) besides `"context"` |

The exact shapes go into `docs/contracts.md` and `demo/mock/README.md` as part of the plan.

## 9. Frontend

- The rail goes back to 10 steps. Claim, Documents, Client data, Policy check and Photo check show their real check
  items from `checks`, with the flag reason under each problem.
- Documents step: the read fields of each PDF, and an "Open PDF" link per document.
- Paused claim: the headline says which rule failed and why; two buttons, **Continue investigation** and
  **Choose an outcome**; the rest of the rail waits. The queue shows paused claims under "New claims" with a
  "Paused" label.
- Report: a "Flags from the early checks" list; client-data lines in "What moved the score".
- Judge step: the flags it was given, so the adjuster sees the Judge was told.

## 10. Demo cases

- C-1042 (flood) and C-1038 (storm) get their two PDFs and **real street addresses** *(your call)*. The address must
  sit at or next to today's chosen point (for C-1042: about 150 m outside the mapped flood), or the story changes.
  `backend/scripts/check_site.py` shows what is at a point.
- *(your call)* The demo team adds photos to every case, with capture date and location in the files.
- A **third case** shows the pause: a valid claim whose policy had expired before the event *(my call; the demo
  team may prefer another failed rule)*.
- At least one case should carry a client-data flag (for example a phone number with a digit missing) to show the
  score line.

## 11. Live runs must really run

Today the backend answers **any request it has made before from disk, even with real keys and without `REPLAY=1`**
(`engine/http.py` and `engine/llm.py` read the saved answer first). On a demo claim that was run before, pressing
"Run again" with keys therefore repeats the saved run instead of investigating again.

*(your call: every run is genuine)* Three clear modes:

| Mode | Set by | Reads saved answers | Calls the outside world | Saves answers |
| --- | --- | --- | --- | --- |
| **Live** (default) | nothing | never | always | no — the run itself is kept in the database and replays in the app |
| **Replay** | `REPLAY=1` | always | never | no |
| **Record** | `RECORD=1` | never | always | yes, overwriting `demo/cache/`, to refresh the saved demo answers |

In live mode each agent fetches its data again and every AI step (plan, agent verdicts, Judge) is asked again, so
the result can differ from run to run. The trace marks each step as live or replayed, and the app shows which mode
the run used.

## 12. Costs and risks

- **Saved answers must be recorded again.** The Judge and Orchestrator prompts change (they now include flags),
  so every saved AI answer for both demo cases stops matching. Both cases, plus the third, must be run once with
  real keys and the cache committed. Until then, replay mode shows "judge unavailable".
- **Geocoding** uses OpenStreetMap's Nominatim, already used when creating a claim: one request per address,
  cached and replayable. Their usage rules ask for at most one request per second.
- Two new Python dependencies (`pypdf`, `reportlab`).
- The engine stays free of web-server code, so it can still become a UiPath coded agent.

## 13. Left to the builder

- Exact Romanian wording of check items and flag reasons.
- How the template looks (layout, logo), as long as the field names above are used.
- Where the new check code lives inside `backend/engine/`, and how the graph resumes from the plan.
- Frontend layout of the new step details, within the existing visual style.
