# Intake Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every claim starts from two PDFs (claim form, policy) and its photos; the backend reads and checks them in five visible steps (Claim, Documents, Client data, Policy check, Photo check), raises flags the Judge and the score take into account, pauses on a failed policy rule until the adjuster continues, and every live run really runs.

**Architecture:** New pure check functions in `backend/engine/` (documents, client data, photos, geocoding) run as new LangGraph nodes before the plan. Results are stored on the claim (`checks`, `early_flags`) and reach the frontend through `GET /claims/{id}`. A failed policy rule ends the run in status `paused`; `POST /claims/{id}/continue` resumes it at the plan. The fetch/LLM cache stops reading saved answers outside replay mode.

**Tech Stack:** Python 3.13, FastAPI, LangGraph, Pydantic v2, `pypdf` (read PDFs), `reportlab` (write stand-in PDFs until the demo team's template exists), OpenStreetMap Nominatim, pytest. React 19 + Vite + TypeScript, vitest.

**Spec:** [`docs/intake-design.md`](intake-design.md) (approved 14 Nov 2026). Also read [`docs/contracts.md`](contracts.md) and [`docs/frontend-integration.md`](frontend-integration.md).

**Branch:** `rc/intake`, from `main`.

## Global Constraints

- The AI never rejects or blocks a claim. A pause hands the claim to a person, who can always continue.
- Outcomes stay `fast_track`, `standard_review`, `antifraud_referral`.
- Every flag is `{step, code, field, severity: "warn" | "fail", reason}`; `reason` is Romanian, like all text the backend writes.
- Each client-data or document flag subtracts **0.25** from the log-odds, **capped at −1.0** in total, one contribution per flag with `agent: "client"`.
- A failed policy rule never changes the score; it pauses the claim and still forces `standard_review` at the end (existing coverage gate).
- Every flag reaches the Orchestrator and the Judge, every round.
- Documents are read by code, never by an AI.
- Run modes: **live** (default) never reads saved answers; **replay** (`REPLAY=1`) only reads them; **record** (`RECORD=1`) never reads and overwrites `demo/cache/`.
- Live mode writes nothing to `demo/cache/` (the run itself is kept in the database and replays in the app). *(Ruling, see the design note in Task 1.)*
- `backend/engine/` imports nothing from `backend/app/` or FastAPI.
- All personal data in demo files is synthetic (CNP and IBAN pass their checksums but belong to no one).
- Existing behaviour keeps working: the investigation loop, the stream rules in `demo/mock/README.md`, all 138 backend and 19 frontend tests (updated where a task says so).
- The frontend uses the backend's identifiers verbatim (see `docs/frontend-integration.md` section 6).

## Review Focus

1. **A database created before this change** (`backend/data/claimlens.db` on the developers' machines) lacks the new columns → startup adds them; nothing crashes, old claims still open (Task 2).
2. **A claim form with missing key fields** (no event date, address or damage type) → the documents step flags them, the policy rules fail on them, the claim pauses; nothing raises (Task 9).
3. **An address the map cannot find, or Nominatim down** → client flag "address not found", the claim falls back to the policy address's point; if neither is found the address rule fails and the claim pauses; continuing runs agents that return `inconclusive` instead of crashing on missing coordinates (Tasks 4, 9).
4. **`continue` pressed twice, or on a claim that is not paused** → HTTP 409, nothing starts twice; `rerun` on a paused claim starts over from the documents (Task 10).
5. **Live mode in the test suite** → no test reaches the real network; live mode calls the transport every time even for an identical request (Task 1).

---

## File structure

```
backend/engine/modes.py        run mode (live | replay | record), shared by http.py and llm.py
backend/engine/models.py       + CheckItem, Flag, StepResult, ReadDocument; Contribution.reason; Sink.checks / Sink.claim_read
backend/engine/documents.py    read_document, write_document, CLAIM_FIELDS, POLICY_FIELDS, check_intake, check_documents
backend/engine/validators.py   cnp_valid, iban_valid, phone_valid, email_valid
backend/engine/geocode.py      geocode(address) -> GeoHit | None  (Nominatim, through http.fetch)
backend/engine/client.py       check_client
backend/engine/photos.py       read_exif, image_hash, check_photos (moved out of the photo agent)
backend/engine/rules.py        + amount rule, address rule by distance; context_term without the amount part
backend/engine/score.py        + data-flag contributions
backend/engine/graph.py        + intake, documents, client, photos, paused nodes; resume at plan
backend/engine/prompts.py      planner and Judge receive the flags
backend/app/db.py              new claim columns + migration; checks, early flags, documents, run mode
backend/app/main.py            status paused, /continue, /documents, decision while paused, POST /claims makes PDFs
backend/app/seed.py            demo claims built from their PDFs
backend/scripts/make_documents.py   demo JSON source → two PDFs per case
demo/cases/                    sources/*.json, documents/<id>/*.pdf, photos/<id>/*
frontend/src/...               types, build, screens (Tasks 12–13)
```

---

### Task 0: "Ask for more" gets its own Judge rounds (colleague's feedback)

**Problem.** A question run continues the round count (round 4 after a 3-round investigation), so `should_stop` stops at
once with "Limita de 3 runde a fost atinsă" (`engine/graph.py`, `round >= MAX_ROUNDS`). The Judge is called, but it can
never send an agent back, and the app shows only the stop reason, not what the Judge concluded about the answer.

**Files:**
- Modify: `backend/engine/graph.py` (`should_stop`, `question_node`, `judge_node`), `frontend/src/api/build.ts` (Judge summary)
- Test: `backend/tests/test_graph.py`, `frontend/src/api/build.test.ts`

**Interfaces:**
- `should_stop(round, prev_score, score, judge, hypotheses, elapsed_s, first_round: int = 1)`: the round limit counts rounds
  of the current run only, `round - first_round + 1 >= MAX_ROUNDS`. The time budget also restarts with the run.
- `question_node` sets `first_round` in the state to the question's own round (`round_ + 1`).
- Frontend: a stopped Judge's `summary` is its first tension followed by the stop reason, so the adjuster sees what the
  Judge made of the new answer.

- [ ] **Step 1: Failing tests**

```python
async def test_question_after_three_rounds_lets_the_judge_send_an_agent_back(sink):
    # prior evidence from rounds 1-3; stub Judge answers "redispatch" once, then "stop"
    await run_investigation(CLAIM, POLICY, CFG, sink, extra_question="De ce?", prior=PRIOR_R3, **STUBS)
    judges = [s for s in sink.steps if s.step_id.endswith(".judge")]
    assert judges[0].outputs["action"] == "redispatch"            # round 4 may send an agent back
    assert "Limita" not in judges[0].summary

async def test_question_run_still_stops_after_three_rounds_of_its_own(sink): ...  # stub always redispatches → rounds 4, 5, 6, then stop
```

```ts
it('a stopped Judge shows what it concluded, not only why it stopped', () => {
  expect(c.judge[2].summary).toContain('Clientul declară');
});
```

- [ ] **Step 2: Run, expect FAIL.** `cd backend && .venv/bin/pytest tests/test_graph.py -q`, `cd frontend && npm test`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Both suites PASS.**
- [ ] **Step 5: Commit** `"Ask for more gets its own Judge rounds; the Judge's conclusion is shown"`.

Related: in the colleague's screenshot rounds 1 and 2 show the same time. That is the cache answering round 2 from
disk in no time (identical requests to an earlier run); Task 1 removes it.

---

### Task 1: Run modes: live runs really run

**Files:**
- Create: `backend/engine/modes.py`
- Modify: `backend/engine/http.py:30-90`, `backend/engine/llm.py:56-80`, `backend/engine/context.py:36-56`
- Test: `backend/tests/test_http.py`

**Interfaces:**
- Produces: `modes.run_mode() -> Literal["live", "replay", "record"]` (`REPLAY` set and not `0` → replay; else `RECORD` set and not `0` → record; else live). `http.served_from_cache() -> bool`: True if the most recent `fetch`/`llm_json` in the current task was answered from disk (a `ContextVar`).
- `fetch(..., replay=None)` keeps its signature; `replay=True` (from `REPLAY_AGENTS`) forces reading.

Design note (ruling): the design's mode table says live mode saves answers. The run is already kept in the database and replays in the app, and writing would dirty the committed `demo/cache/` on every run, so live mode writes nothing. Update `docs/intake-design.md` section 11 to say so in this task.

- [ ] **Step 1: Write the failing tests** (replace `test_second_identical_fetch_reads_cache`)

```python
async def test_live_mode_calls_the_source_every_time(route):
    calls = route({"example.org": {"ok": 1}})
    await http.fetch("https://example.org/a")
    await http.fetch("https://example.org/a")
    assert len(calls) == 2
    assert http.served_from_cache() is False

async def test_live_mode_does_not_write_the_cache(route, tmp_path):
    route({"example.org": {"ok": 1}})
    await http.fetch("https://example.org/a")
    assert not any((tmp_path / "cache").rglob("*.json"))

async def test_record_mode_overwrites_and_replay_reads_it(route, monkeypatch):
    monkeypatch.setenv("RECORD", "1")
    route({"example.org": {"v": 2}})
    await http.fetch("https://example.org/a")
    monkeypatch.delenv("RECORD"); monkeypatch.setenv("REPLAY", "1")
    calls = route({"example.org": {"v": 3}})
    assert await http.fetch("https://example.org/a") == {"v": 2}
    assert calls == [] and http.served_from_cache() is True

async def test_llm_live_mode_asks_the_provider_every_time(monkeypatch):
    # provider mocked exactly as in test_llm_parses_fenced_json_and_caches
    await llm.llm_json("s", "u"); await llm.llm_json("s", "u")
    assert provider_calls == 2 and not any((tmp_cache).rglob("*.json"))
```

Rename `test_llm_parses_fenced_json_and_caches` to `test_llm_parses_fenced_json_and_record_mode_caches` and set `RECORD=1` in it.

- [ ] **Step 2: Run, expect FAIL**: `cd backend && .venv/bin/pytest tests/test_http.py -q` → the four new tests fail.
- [ ] **Step 3: Implement** `modes.run_mode`; in `fetch` and `llm_json` read the cache only when replaying (global or forced), write only in record mode, set the `ContextVar`.
- [ ] **Step 4: Run the whole suite**: `.venv/bin/pytest -q` → all pass. `test_end_to_end.py::test_fraud_story_live_then_offline` now records with `RECORD=1` before its offline half: change it accordingly.
- [ ] **Step 5: Mark tool calls**: in `AgentContext` add `"replayed": http.served_from_cache()` to the outputs of the answer step after each fetch. Test in `tests/test_context.py`: `test_answer_step_says_whether_it_was_replayed` (live → False, replay → True). Run, pass.
- [ ] **Step 6: Commit** `git commit -m "Live runs never read saved answers; RECORD=1 refreshes them"` (with the attribution line).

---

### Task 2: Check results, flags and their storage

**Files:**
- Modify: `backend/engine/models.py`, `backend/app/db.py`, `backend/tests/conftest.py` (FakeSink)
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Produces in `engine/models.py`:
  - `CheckItem(id: str, label: str, value: str | None = None, status: Literal["ok","flag","fail","info"], reason: str | None = None)`
  - `Flag(step: Literal["intake","documents","client","policy","photos"], code: str, field: str | None = None, severity: Literal["warn","fail"], reason: str)`
  - `StepResult(step: str, items: list[CheckItem] = [], flags: list[Flag] = [])`
  - `Contribution` gains `reason: str | None = None`
  - `Sink` gains `checks(self, result: StepResult) -> None` and `claim_read(self, fields: dict) -> None`
- Produces in `app/db.py`: claim columns `documents TEXT` (JSON `{"claim_form": path, "policy": path}`), `checks TEXT` (JSON `{step: StepResult}`), `early_flags TEXT` (JSON list of Flag), `run_mode TEXT`. `Store.migrate()` adds missing columns with `ALTER TABLE`; `create_schema()` calls it. `ClaimSink.checks` merges one step into `checks`, appends its flags to `early_flags` (replacing that step's earlier flags) and notifies `("checks", result)`. `ClaimSink.claim_read(fields)` updates the claim's read fields (`address, lat, lon, event_date, notified_at, damage_type, description, amount_claimed, policy_id`). `reset_claim` also clears `checks`, `early_flags`, `run_mode`.

- [ ] **Step 1: Failing tests**

```python
def test_old_database_gets_the_new_columns(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db); con.execute("CREATE TABLE claim (id TEXT PRIMARY KEY, status TEXT)")
    con.execute("INSERT INTO claim VALUES ('C-1', 'received')"); con.commit(); con.close()
    s = Store(db); s.create_schema()
    assert s.get_claim("C-1")["checks"] is None

def test_checks_replace_a_step_and_its_flags(store):
    sink = store.for_claim("C-1042")
    f = Flag(step="client", code="phone_invalid", field="telefon", severity="warn", reason="x")
    sink.checks(StepResult(step="client", flags=[f, f]))
    sink.checks(StepResult(step="client", flags=[f]))
    c = store.get_claim("C-1042")
    assert list(c["checks"]) == ["client"] and len(c["early_flags"]) == 1

def test_rerun_clears_checks(store): ...  # after reset_claim: checks, early_flags, run_mode are None
```

- [ ] **Step 2: Run, expect FAIL.** `.venv/bin/pytest tests/test_db.py -q`
- [ ] **Step 3: Implement** models, columns (add to `CLAIM_JSON`), `migrate`, sink methods; add no-op-recording `checks`/`claim_read` to `FakeSink`.
- [ ] **Step 4: Run the whole suite, expect PASS.**
- [ ] **Step 5: Commit** `"Store check results and early flags on the claim"`.

---

### Task 3: Reading and writing the documents; Claim and Documents steps

**Files:**
- Create: `backend/engine/documents.py`
- Modify: `backend/pyproject.toml` (add `pypdf>=5`, `reportlab>=4`)
- Test: `backend/tests/test_documents.py`

**Interfaces:**
- Produces:
  - `CLAIM_FIELDS: dict[str, str]` and `POLICY_FIELDS: dict[str, str]`: field name → Romanian label, exactly the names in design section 4 (`numar_dosar, numar_polita, nume_asigurat, cnp, telefon, email, iban, adresa_daunei, tip_dauna, data_evenimentului, data_notificarii, descriere, suma_solicitata, numar_fotografii`; `numar_polita, produs, nume_asigurat, cnp, adresa_asigurata, valabila_de_la, valabila_pana_la, zile_asteptare, riscuri_acoperite, suma_asigurata`). These two dicts are the only place to change when the demo team's template arrives.
  - `ReadDocument(kind: Literal["claim_form","policy"], fields: dict[str, str], missing: list[str], readable: bool)` (in `models.py`)
  - `read_document(path: Path, kind) -> ReadDocument`: if the PDF has form fields, read them by name; else read lines `"<label>: <value>"` from the page text using the labels above. Unreadable or absent file → `readable=False`, every field missing.
  - `write_document(fields: dict[str, str], kind, path: Path) -> None`: a stand-in PDF with fillable form fields named as above, drawn with reportlab (`acroForm.textfield`).
  - `to_claim(claim_doc: ReadDocument, policy_doc: ReadDocument) -> tuple[dict, dict]`: the engine's `claim` and `policy` dicts. Mapping: `tip_dauna` `inundație`→`flood`, `furtună`→`storm`; `riscuri_acoperite` comma list mapped the same way (`cutremur`→`earthquake`, `alunecare de teren`→`landslide`, `incendiu`→`fire`); dates `YYYY-MM-DD` or `DD.MM.YYYY` → ISO; amounts `48.000`, `48000`, `48 000 RON` → `48000.0`. Unparseable value → key left out.
  - `check_intake(docs: dict[str, Path | None], photos: list[Path], declared_photos: int | None) -> StepResult`: items for claim form, policy, photos; flags `claim_form_missing`, `policy_missing` (severity `fail`), `photo_count_mismatch` (`warn`).
  - `check_documents(claim_doc, policy_doc) -> StepResult`: one item per field (value shown, status ok / flag); flags `field_missing` and `field_malformed` (`warn`), `field` = the field name. Required: all fields except `email`, `iban`, `numar_fotografii`.

- [ ] **Step 1: Failing tests** (`write_document` makes the fixtures, so the reader is tested on real PDFs)

```python
def test_round_trip_reads_every_field(tmp_path):
    write_document(CLAIM, "claim_form", tmp_path / "c.pdf")
    d = read_document(tmp_path / "c.pdf", "claim_form")
    assert d.readable and d.missing == [] and d.fields["suma_solicitata"] == "48000"

def test_flat_text_pdf_is_read_by_labels(tmp_path): ...  # PDF drawn with canvas.drawString("Număr poliță: P-7731")

def test_not_a_pdf_is_unreadable_not_an_error(tmp_path):
    (tmp_path / "x.pdf").write_text("hello")
    assert read_document(tmp_path / "x.pdf", "policy").readable is False

def test_to_claim_maps_romanian_values():
    claim, policy = to_claim(doc(tip_dauna="inundație", data_evenimentului="14.09.2024", suma_solicitata="48.000 RON"), pol(riscuri_acoperite="inundație, cutremur"))
    assert claim["damage_type"] == "flood" and claim["event_date"] == "2024-09-14" and claim["amount_claimed"] == 48000.0
    assert policy["covered_risks"] == ["flood", "earthquake"]

def test_missing_and_malformed_fields_are_flagged():
    r = check_documents(doc(data_evenimentului="ieri", telefon=""), pol())
    assert {(f.code, f.field) for f in r.flags} == {("field_malformed", "data_evenimentului"), ("field_missing", "telefon")}

def test_missing_policy_document_is_a_fail_flag():
    r = check_intake({"claim_form": Path("c.pdf"), "policy": None}, [], 0)
    assert [f.code for f in r.flags] == ["policy_missing"] and r.flags[0].severity == "fail"
```

`CLAIM`/`doc()`/`pol()` are helpers in the test file built from the C-1042 values in design section 4.

- [ ] **Step 2: Run, expect FAIL.** `.venv/bin/pip install -e ".[dev]" && .venv/bin/pytest tests/test_documents.py -q`
- [ ] **Step 3: Implement** `documents.py`.
- [ ] **Step 4: Run, expect PASS**; whole suite green.
- [ ] **Step 5: Commit** `"Read and write the claim form and policy PDFs; Claim and Documents checks"`.

---

### Task 4: Client data step

**Files:**
- Create: `backend/engine/validators.py`, `backend/engine/geocode.py`, `backend/engine/client.py`
- Test: `backend/tests/test_client.py`

**Interfaces:**
- Produces:
  - `cnp_valid(s: str) -> bool`: 13 digits; checksum = Σ digit_i × `279146358279`[i] mod 11, 10 → 1, equals the 13th digit.
  - `iban_valid(s: str) -> bool`: spaces removed, move first 4 characters to the end, letters → numbers (A=10…Z=35), value mod 97 == 1.
  - `phone_valid(s)`: Romanian: `07` + 8 digits, or `+407` + 8 digits, spaces and dashes ignored. `email_valid(s)`: `^[^@\s]+@[^@\s]+\.[^@\s]+$`.
  - `GeoHit(lat: float, lon: float, precision: Literal["house","street","town"])`; `async geocode(address: str) -> GeoHit | None` through `http.fetch("https://nominatim.openstreetmap.org/search", params={"q": address, "format": "json", "limit": 1, "addressdetails": 1})`; precision from `addresstype`: `house`/`building` → house, `road` → street, anything else → town. Not found or source error → None.
  - `async check_client(claim_doc: ReadDocument, policy_doc: ReadDocument) -> tuple[StepResult, GeoHit | None, GeoHit | None]` (claim point, policy point). Flags, all `warn`: `name_mismatch`, `cnp_mismatch`, `cnp_invalid`, `phone_invalid`, `email_invalid` (only if present), `iban_invalid` (only if present), `address_not_found` (claim address), `address_imprecise` (found only to town level). Names compared case- and diacritic-insensitively.

- [ ] **Step 1: Failing tests**

```python
def test_cnp_and_iban_checksums():
    assert cnp_valid("1960101170000") and not cnp_valid("1960101170001")
    assert iban_valid("RO49 AAAA 1B31 0075 9384 0000") and not iban_valid("RO49AAAA1B31007593840001")

def test_phone_formats():
    assert phone_valid("0722 123 456") and phone_valid("+40722123456") and not phone_valid("072212345")

async def test_geocode_precision(route):
    route({"nominatim": [{"lat": "45.6", "lon": "27.7", "addresstype": "road"}]})
    assert await geocode("Str. X, Pechea") == GeoHit(lat=45.6, lon=27.7, precision="street")

async def test_address_not_found_is_a_flag_not_an_error(route):
    route({"nominatim": []})
    result, point, _ = await check_client(doc(), pol())
    assert point is None and "address_not_found" in [f.code for f in result.flags]

async def test_mismatched_cnp_and_bad_phone(route):
    route({"nominatim": [{"lat": "45.6", "lon": "27.7", "addresstype": "house"}]})
    result, _, _ = await check_client(doc(cnp="1960101170000", telefon="123"), pol(cnp="2960101170000"))
    assert {f.code for f in result.flags} >= {"cnp_mismatch", "phone_invalid"}

async def test_names_match_without_diacritics(route): ...  # "Persoană Sintetică" vs "PERSOANA SINTETICA" → no name_mismatch
```

- [ ] **Step 2: Run, expect FAIL.** `.venv/bin/pytest tests/test_client.py -q`
- [ ] **Step 3: Implement** the three modules.
- [ ] **Step 4: Run, expect PASS**; whole suite green.
- [ ] **Step 5: Commit** `"Client data step: identity, contact, bank account and address checks"`.

---

### Task 5: Policy rules on read data

**Files:**
- Modify: `backend/engine/rules.py`
- Test: `backend/tests/test_rules.py`

**Interfaces:**
- Consumes: `GeoHit` (Task 4).
- Produces: `check_policy(claim: dict, policy: dict, claim_point: GeoHit | None = None, policy_point: GeoHit | None = None) -> list[RuleFlag]`. Rules in this order: `policy_active, waiting_period, risk_covered, address_match, notified_in_time, amount_within_sum_insured`. `address_match` passes if both points exist and are within **100 m**, or (no points) the normalised texts are equal, where normalising also drops `str.`/`strada`, `nr.`, `jud.`/`judetul` and diacritics. `amount_within_sum_insured` passes if `amount_claimed <= sum_insured`; fails if either is missing.
- `policy_flags(rules: list[RuleFlag]) -> StepResult` (step `policy`): one item per rule, one `fail` flag per failed rule with `code = rule`.
- `context_term` drops the amount part (now a rule) and keeps only late notification.

- [ ] **Step 1: Failing tests**

```python
def test_amount_above_sum_insured_fails_the_new_rule():
    f = {r.rule: r for r in check_policy(claim(amount_claimed=120000), policy(sum_insured=100000))}
    assert f["amount_within_sum_insured"].passed is False

def test_address_match_by_points_within_100_m():
    a, b = GeoHit(lat=45.6059, lon=27.78329, precision="house"), GeoHit(lat=45.6065, lon=27.78329, precision="house")
    assert rule(check_policy(claim(), policy(address="altă scriere"), a, b), "address_match") is True   # ~67 m

def test_address_match_by_text_ignores_street_prefix_and_diacritics():
    assert rule(check_policy(claim(address="Strada Exemplu 12, Pechea"), policy(address="Str. Exemplu 12, Pechea")), "address_match")

def test_context_term_no_longer_counts_the_amount():
    assert context_term(claim(amount_claimed=1e9), policy(sum_insured=1)) == 0.0
```

Update the existing rules tests that expect five rules to expect six.

- [ ] **Step 2: Run, expect FAIL.** `.venv/bin/pytest tests/test_rules.py -q`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Whole suite PASS.**
- [ ] **Step 5: Commit** `"Policy check: amount rule, address compared by map position"`.

---

### Task 6: Photo check step

**Files:**
- Create: `backend/engine/photos.py`
- Modify: `backend/agents/photo_forensics/agent.py` (import helpers from `engine.photos`; reuse precomputed results)
- Test: `backend/tests/test_photos.py`, existing `backend/tests/test_photo_forensics.py` must stay green

**Interfaces:**
- Produces: `read_exif`, `image_hash` (moved, same behaviour as `read_exif`/`_hash` today). `check_photos(paths: list[Path], event_date: str, house: tuple[float, float] | None, earlier: list[Path]) -> tuple[StepResult, list[Finding]]`. The findings are exactly the ones the agent produces today for its local checks (`<name>:exif_missing`, `:exif_date`, `:exif_days_before_event`/`after`, `:exif_distance_to_address_km`, `:copy_in_other_claim`, `:unreadable`), so the agent's evidence and the demo scores do not change. Flags (`warn`): `photo_unreadable`, `photo_no_date`, `photo_before_event`, `photo_far_from_address` (more than **1 km**), `photo_copy_in_earlier_claim`.
- The agent reads precomputed findings from `task.claim.get("photo_findings")` when present, else computes them with `check_photos` (so the agent still works alone).

- [ ] **Step 1: Failing tests** (photos made in the test with Pillow and an EXIF block)

```python
def test_photo_taken_before_the_event_is_flagged(tmp_path):
    p = jpeg_with_exif(tmp_path / "a.jpg", date="2024:09:01 10:00:00")
    result, findings = check_photos([p], "2024-09-14", None, [])
    assert [f.code for f in result.flags] == ["photo_before_event"]
    assert "a.jpg:exif_days_before_event" in [f.metric for f in findings]

def test_photo_far_from_the_house_is_flagged(tmp_path): ...   # GPS 3 km away → photo_far_from_address
def test_unreadable_photo_is_a_flag_not_an_error(tmp_path): ... # text file named .jpg → photo_unreadable
def test_no_photos_gives_one_info_item_and_no_flags(): ...
```

- [ ] **Step 2: Run, expect FAIL.** `.venv/bin/pytest tests/test_photos.py -q`
- [ ] **Step 3: Implement** `photos.py`; change the agent to use it.
- [ ] **Step 4: Whole suite PASS** (including `test_photo_forensics.py` unchanged).
- [ ] **Step 5: Commit** `"Photo check step, shared with the photo forensics agent"`.

---

### Task 7: Score lines for client-data and document flags

**Files:**
- Modify: `backend/engine/score.py`
- Test: `backend/tests/test_score.py`

**Interfaces:**
- Produces: `compute_score(evidence, cfg, flags, context_term=0.0, data_flags: list[Flag] | None = None) -> ScoreResult`. Each flag with `step in ("documents", "client")` adds `Contribution(agent="client", round=0, delta_logit=-0.25, reason=flag.reason)`; when the running total would pass −1.0 the remaining flags add `0.0` (still listed). Intake, policy and photo flags add nothing.

- [ ] **Step 1: Failing tests**

```python
def test_each_client_flag_costs_a_quarter_logit_capped_at_one():
    flags = [Flag(step="client", code=f"c{i}", severity="warn", reason=f"r{i}") for i in range(6)]
    r = compute_score([], CFG, [], 0.0, flags)
    lines = [c for c in r.contributions if c.agent == "client"]
    assert [c.delta_logit for c in lines] == [-0.25] * 4 + [0.0, 0.0]
    assert r.score == round(100 / (1 + math.exp(1.0)), 1)

def test_photo_and_policy_flags_do_not_move_the_score(): ...
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Whole suite PASS.**
- [ ] **Step 5: Commit** `"Client-data and document flags lower the score, one visible line each"`.

---

### Task 8: Flags reach the Orchestrator and the Judge

**Files:**
- Modify: `backend/engine/prompts.py`
- Test: `backend/tests/test_judge.py`

**Interfaces:**
- Produces: `plan_hypotheses(claim, policy, flags, early_flags: list[Flag] | None = None)` and `judge_round(..., early_flags: list[Flag] | None = None)`. Both add a block `Semnale din verificările inițiale:` listing `[step] reason` for every flag, or `niciunul`. The Judge block adds: `Constatările agentului Foto-forensic provin din aceleași verificări ale fotografiilor.` when any `photos` flag is present.

- [ ] **Step 1: Failing test**: with `fake_llm` capturing the user text, `judge_round(..., early_flags=[Flag(step="client", code="cnp_mismatch", severity="warn", reason="CNP diferit")])` → the captured prompt contains `Semnale din verificările inițiale` and `CNP diferit`. Same for `plan_hypotheses`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Whole suite PASS.**
- [ ] **Step 5: Commit** `"Orchestrator and Judge see every flag from the early checks"`.

---

### Task 9: The graph: five steps, the pause, resuming

**Files:**
- Modify: `backend/engine/graph.py`
- Test: `backend/tests/test_graph.py`

**Interfaces:**
- Consumes: Tasks 2–8.
- Produces: `run_investigation(claim, policy, cfg, sink, *, documents: dict[str, Path | None] | None = None, photos: list[Path] | None = None, earlier_photos: list[Path] | None = None, resume: dict | None = None, ...existing kwargs) -> ScoreResult | None`.
  - With `documents`: nodes `intake → documents → client → rules → photos`, then `plan` if every policy rule passed, else `paused` → END and the function returns **None**. `claim`/`policy` passed in are replaced by `to_claim(...)`; coordinates come from the claim point, else the policy point. Each node calls `sink.checks(...)` and writes one trace step with ids `intake`, `documents`, `client`, `rules`, `photos`, `paused` (outputs: `{"failed_rules": [...]}`), all with `parent=None` chained in order. `sink.claim_read(...)` after `client`.
  - With `resume={"early_flags": [...], "rule_flags": [...], "photo_findings": [...]}`: starts at a `continue` trace step (actor `adjuster`), then `plan`, and runs as today.
  - Without `documents` and `resume`: today's behaviour (`rules → plan …`), so old tests and the question path keep working.
  - `early_flags` go to the planner, the Judge (every round) and `compute_score`.
  - Agents that need coordinates (`meteo, satellite, risk_zones, street_view`) get `inconclusive` evidence with gap `Adresa nu a putut fi localizată` when the claim has no `lat`/`lon`, without being called.

- [ ] **Step 1: Failing tests** (stub agents, planner and Judge as in the existing graph tests; documents from `write_document`)

```python
async def test_all_rules_pass_runs_through_to_the_verdict(sink, docs_ok):
    out = await run_investigation({}, {}, CFG, sink, documents=docs_ok, photos=[], **STUBS)
    assert out is not None
    assert [s.step_id for s in sink.steps][:6] == ["intake", "documents", "client", "rules", "photos", "plan"]

async def test_expired_policy_pauses_before_the_agents(sink, docs_expired):
    out = await run_investigation({}, {}, CFG, sink, documents=docs_expired, photos=[], **STUBS)
    assert out is None and sink.steps[-1].step_id == "paused"
    assert not any(s.actor.startswith("agent:") for s in sink.steps)

async def test_resume_starts_at_the_plan_and_the_judge_gets_the_flags(sink): ...
async def test_claim_form_without_event_date_pauses_without_raising(sink, docs_no_date): ...
async def test_no_coordinates_makes_location_agents_inconclusive(sink): ...
```

- [ ] **Step 2: Run, expect FAIL.** `.venv/bin/pytest tests/test_graph.py -q`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Whole suite PASS.**
- [ ] **Step 5: Commit** `"Five intake steps before the plan; pause on a failed policy rule; resume at the plan"`.

---

### Task 10: API: paused claims, continue, documents

**Files:**
- Modify: `backend/app/main.py`, `backend/app/seed.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: Task 9.
- Produces (document every item in `docs/contracts.md` and `demo/mock/README.md` in this task):
  - `investigate()` passes `documents` (paths from the claim's `documents` column, resolved under `DATA_DIR/documents` and `demo/cases/documents`), photos and earlier photos; sets status **`paused`** when the engine returns None, else `awaiting_decision`. Stores `run_mode` (`modes.run_mode()`) when a run starts. The stream's closing rule treats `paused` like `awaiting_decision`.
  - `POST /claims/{id}/continue`: 409 unless status is `paused`; starts the run with `resume=` built from the stored `early_flags`, `rule_flags` and the photo findings; returns `{"id", "status": "investigating"}`.
  - `POST /claims/{id}/decision`: when `paused`, only `decision: "modify"` with an outcome and a reason (approve → 409 "Nu există încă o recomandare").
  - `GET /claims/{id}`: new keys `checks`, `flags` (= early flags), `documents` (`{"claim_form": {field: value}, "policy": {...}}`, from reading the PDFs), `run_mode`.
  - `GET /documents/{claim_id}/{name}`: serves `claim_form.pdf` or `policy.pdf` of that claim; same folder-escape protection as `/photos`.
  - `POST /claims`: JSON as today; the backend calls `write_document` for both PDFs into `DATA_DIR/documents/<id>/` and records them, then investigates from the documents.
  - `seed`: a case file may give `"documents": {"claim_form": "...", "policy": "..."}` (paths under `demo/cases/documents/`); the seed reads them with `read_document` + `to_claim` and stores the claim and policy fields (no checks, no geocoding), so the queue shows the policyholder before any run. Old-format case files still load.

- [ ] **Step 1: Failing tests**

```python
def test_claim_with_expired_policy_pauses_and_can_continue(client): ...
    # POST a claim whose policy expired → status "paused", checks has the five steps, flags include policy_active
    # POST /continue → 200; after the run status "awaiting_decision"; second POST /continue → 409

def test_paused_claim_can_be_decided_only_with_an_outcome_and_reason(client): ...
def test_documents_are_served_and_cannot_escape_their_folder(client): ...
def test_case_response_has_checks_flags_documents_and_run_mode(client): ...
def test_rerun_of_a_paused_claim_starts_from_the_documents(client): ...
```

- [ ] **Step 2: Run, expect FAIL.** `.venv/bin/pytest tests/test_api.py -q`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Whole suite PASS.**
- [ ] **Step 5: Commit** `"API: paused claims, continue, decide while paused, original documents"`.

---

### Task 11: Demo documents and the third case

**Files:**
- Create: `backend/scripts/make_documents.py`, `demo/cases/sources/C-1042.json`, `C-1038.json`, `C-1050.json`
- Modify: `demo/cases/fraud.json`, `honest.json` (point to documents), create `demo/cases/paused.json`, `demo/README.md`, `backend/README.md` (run modes, documents)
- Test: `backend/tests/test_seed.py`

**Interfaces:**
- `make_documents.py [case ...]` reads `demo/cases/sources/<id>.json` (`{"claim_form": {field: value}, "policy": {field: value}}`) and writes `demo/cases/documents/<id>/claim_form.pdf` and `policy.pdf` with `write_document`.
- Sources use the values in design section 4. C-1042 and C-1038 keep today's data until the demo team supplies real addresses (Task 15). **C-1050**: flood, Pechea, same event; policy valid `2023-02-01` to `2024-01-31`, so `policy_active` fails and the claim pauses; one client-data flag (phone `0722 12 345`, one digit short).

- [ ] **Step 1: Failing test** `test_demo_cases_load_from_their_documents`: seed into an empty store → three claims; C-1042 holder name read from its PDF; C-1050 status `received`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Write the sources, run** `cd backend && .venv/bin/python scripts/make_documents.py` and commit the PDFs.
- [ ] **Step 4: PASS**; whole suite green.
- [ ] **Step 5: Commit** `"Demo claims as PDFs; third claim that pauses on an expired policy"`.

---

### Task 12: Frontend: types, calls and the case builder

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/api/client.ts`, `frontend/src/api/build.ts`, `frontend/src/lib/meta.ts`, `frontend/src/lib/derive.ts`
- Test: `frontend/src/api/build.test.ts`, new fixture `frontend/src/api/fixtures/paused.json`

**Interfaces:**
- Consumes: Task 10's API.
- Produces:
  - types: `ClaimStatus` adds `'paused'`; `ApiCheckItem`, `ApiFlag`, `ApiStepResult` mirroring Task 2; `ApiClaimDetail` adds `checks: Partial<Record<CheckStep, ApiStepResult>>`, `flags: ApiFlag[]`, `documents: { claim_form?: Record<string,string>; policy?: Record<string,string> }`, `run_mode: 'live' | 'replay' | 'record' | null`. `StageId` adds `'documents' | 'client' | 'photos'`. `CaseFile` adds `flags: ApiFlag[]`, `documents`, `runMode`, `paused: { rules: string[] } | undefined`.
  - client: `continueRun(id)` → `POST /claims/{id}/continue`; `documentUrl(id, 'claim_form' | 'policy')`.
  - `STAGES` back to 10, order `intake, documents, client, policy, photos, plan, agents, judge, verdict, review`; `photos` title "Photo check".
  - `buildCase`: trace ids `intake`, `documents`, `client`, `rules`(→ policy), `photos` each close their window; `paused` closes nothing and sets `paused`; `continue` starts the next run segment like a question does. `details` for the five steps come from `checks` (no more synthesised intake facts). Contributions with `agent: "client"` keep their `reason`.
  - `useCase.actions` adds `continueRun()`.

- [ ] **Step 1: Failing tests**

```ts
it('lays the five early steps before the plan', () => {
  expect(c.windows.map((w) => w.stage).slice(0, 6)).toEqual(['intake', 'documents', 'client', 'policy', 'photos', 'plan']);
});
it('a paused claim stops after the photo check and names the failed rule', () => {
  expect(paused.paused).toEqual({ rules: ['policy_active'] });
  expect(paused.windows[paused.windows.length - 1].stage).toBe('photos');
});
it('shows each step\'s check items from the backend', () => {
  expect(c.details.client!.map((i) => i.status)).toContain('flag');
});
it('continuing lays the investigation right after the pause', () => { ... });
```

Build `paused.json` by hand from the shapes in `docs/contracts.md` (Task 10); update `flood.json`/`storm.json` fixtures with `checks: {}`, `flags: []`, `documents: {}`, `run_mode: null` so old runs still build.

- [ ] **Step 2: Run, expect FAIL.** `cd frontend && npm test`
- [ ] **Step 3: Implement.**
- [ ] **Step 4: PASS**; `npm run build` passes.
- [ ] **Step 5: Commit** `"Frontend reads the five early steps, flags and the pause"`.

---

### Task 13: Frontend screens

**Files:**
- Modify: `frontend/src/components/Pipeline.tsx` (10 nodes; restore the mock's x positions from commit `5b79a00`), `StageDetail.tsx`, `CaseView.tsx`, `DecisionPanel.tsx`, `Report.tsx`, `Queue.tsx`, `ClaimMenu.tsx`, `icons.ts`, `src/styles.css` (last block only)

**What each screen shows** (all data from Task 12; no new numbers computed in the browser):
- Step details for the five early steps: the check items with status icons and the flag reason under each problem. Documents step: the read fields of each PDF and an **Open PDF** link per document (new tab).
- Paused claim: headline "Paused: a policy rule failed", the failed rules and reasons, buttons **Continue investigation** (calls `continueRun`) and **Choose an outcome** (opens the decision panel with only "Choose another route"; no Approve). The rail after the photo check waits.
- Queue: paused claims under "New claims" with a "Paused" chip; claim switcher shows "Paused".
- Report: a "Flags from the early checks" card (step, reason); `client` contributions as lines "Client data: <reason>" in "What moved the score".
- Judge step: a collapsed "Flags the Judge was given" list.
- Case header chip: "Live run" or "Replayed from saved answers" from `runMode`.

- [ ] **Step 1: Run the backend and the frontend; open C-1050.** It pauses before any AI call, so the pause screens work without keys. Continuing it, and every other claim, needs live keys until Task 16 records the new saved answers.
- [ ] **Step 2: Check by hand**: paused headline and both buttons; Continue starts a run; Choose an outcome records a decision; Open PDF opens the document; the five steps show their items; 375 px width has no horizontal scroll; light theme readable.
- [ ] **Step 3:** `npm run build` and `npm test` pass.
- [ ] **Step 4: Commit** `"Screens for the early checks, the pause and the documents"`.

---

### Task 14: Documentation

**Files:**
- Modify: `README.md` (rail of 10 steps, run modes, "What is real today", "Not built yet"), `docs/frontend-integration.md` (sections 3, 4, 5: the three steps are back), `frontend/README.md`, `docs/intake-design.md` (any rulings made during the build)

- [ ] **Step 1:** Update the files; every command in the README run once to check it.
- [ ] **Step 2: Commit** `"Docs: intake steps, pause, run modes"`.

---

### Task 15 (demo team + BE): real addresses, photos, the team's templates

Inputs the code cannot make up. Each arrives independently.

- [ ] **Templates.** When the demo team's claim form and policy PDFs arrive: put one sample of each in `backend/tests/fixtures/`, change only `CLAIM_FIELDS`/`POLICY_FIELDS` (and `write_document` to fill the team's template), add `test_team_template_is_read` reading the sample. Suite green, commit.
- [ ] **Real street addresses** for C-1042, C-1038, C-1050: a real house at or next to today's point (C-1042: about 150 m outside the EMSR758 flood and higher than its edge). Check each with `backend/scripts/check_site.py` and with `geocode()` (precision `house` or `street`). Update the sources, regenerate the PDFs, commit.
- [ ] **Photos** for every case under `demo/cases/photos/<id>/`, listed in the case file, with capture date and GPS in the files: C-1038 dated 26–27.11.2023 at the house; C-1042 per the fraud story the team chooses. Commit.

---

### Task 16 (BE, needs the keys): record the saved answers, check both modes

- [ ] **Step 1:** `cd backend && RECORD=1 .venv/bin/uvicorn app.main:app --port 8000`, then run every demo claim once from the app (C-1050: continue it once too). Check scores and outcomes are the story the pitch tells.
- [ ] **Step 2:** Check `git diff --stat demo/cache` contains no key or token (`grep -rE "key=|token=|Bearer" demo/cache` → nothing).
- [ ] **Step 3:** Restart with `REPLAY=1`; each claim replays with no network; "Replayed from saved answers" shows.
- [ ] **Step 4:** Restart in live mode; run C-1038 twice; both runs make real calls (trace answers say `replayed: false`) and may score differently.
- [ ] **Step 5:** Whole backend and frontend suites green. Commit `"Saved answers recorded for the three demo claims"`.
