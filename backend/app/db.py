"""SQLite storage. One file, six tables (design §7). Store.for_claim() gives the engine its Sink."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

from engine.models import Evidence, Hypothesis, RuleFlag, ScoreResult, TraceStep, WeightConfig, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS policy (
  id TEXT PRIMARY KEY, holder_name TEXT, address TEXT, lat REAL, lon REAL, valid_from TEXT, valid_to TEXT,
  waiting_days INTEGER, covered_risks TEXT, sum_insured REAL, product TEXT);
CREATE TABLE IF NOT EXISTS claim (
  id TEXT PRIMARY KEY, policy_id TEXT, damage_type TEXT, event_date TEXT, notified_at TEXT, address TEXT,
  lat REAL, lon REAL, description TEXT, amount_claimed REAL, photos TEXT, status TEXT, rule_flags TEXT,
  hypotheses TEXT, score REAL, band TEXT, recommendation TEXT, score_detail TEXT, decision TEXT,
  outcome TEXT, decision_reason TEXT, decided_at TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id TEXT, agent TEXT, round INTEGER, body TEXT,
  rejected_by_adjuster INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS trace_step (
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, step_id TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS event_footprint (
  id TEXT PRIMARY KEY, name TEXT, damage_type TEXT, date_from TEXT, date_to TEXT, center_lat REAL,
  center_lon REAL, radius_km REAL, polygon TEXT, meteo_maxima TEXT, news TEXT, sources TEXT, version INTEGER);
CREATE TABLE IF NOT EXISTS weight_config (
  damage_type TEXT PRIMARY KEY, p0 REAL, weights TEXT, context_weight REAL, updated_at TEXT);
"""

CLAIM_JSON = ("photos", "rule_flags", "hypotheses", "score_detail")
POLICY_JSON = ("covered_risks",)
FOOTPRINT_JSON = ("polygon", "meteo_maxima", "news", "sources")

Listener = Callable[[str, str, dict], None]  # (claim_id, kind, payload)


def _load(row: sqlite3.Row | None, json_cols: tuple[str, ...]) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for c in json_cols:
        if d.get(c) is not None:
            d[c] = json.loads(d[c])
    return d


class ClaimSink:
    def __init__(self, store: "Store", claim_id: str):
        self.store, self.claim_id = store, claim_id

    def trace(self, step: TraceStep) -> None:
        self.store._exec("INSERT INTO trace_step (case_id, step_id, body) VALUES (?,?,?)",
                         (self.claim_id, step.step_id, step.model_dump_json()))
        self.store._notify(self.claim_id, "trace", step.model_dump())

    def evidence(self, e: Evidence) -> int:
        eid = self.store._exec(
            "INSERT INTO evidence (claim_id, agent, round, body, created_at) VALUES (?,?,?,?,?)",
            (self.claim_id, e.agent, e.round, e.model_dump_json(), now_iso()))
        self.store._notify(self.claim_id, "evidence", {"id": eid, **e.model_dump()})
        return eid

    def score(self, s: ScoreResult, round: int) -> None:
        self.store._exec("UPDATE claim SET score=?, band=?, recommendation=?, score_detail=? WHERE id=?",
                         (s.score, s.band, s.recommendation, s.model_dump_json(), self.claim_id))
        self.store._notify(self.claim_id, "score", {"round": round, **s.model_dump()})

    def hypotheses(self, h: list[Hypothesis]) -> None:
        self.store._exec("UPDATE claim SET hypotheses=? WHERE id=?",
                         (json.dumps([x.model_dump() for x in h]), self.claim_id))

    def flags(self, f: list[RuleFlag]) -> None:
        self.store._exec("UPDATE claim SET rule_flags=? WHERE id=?",
                         (json.dumps([x.model_dump() for x in f]), self.claim_id))


class Store:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.listeners: list[Listener] = []

    # -- plumbing
    def _exec(self, sql: str, args: tuple = ()) -> int:
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.lastrowid

    def _all(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def _notify(self, claim_id: str, kind: str, payload: dict) -> None:
        for listener in list(self.listeners):
            listener(claim_id, kind, payload)

    def _upsert(self, table: str, row: dict, json_cols: tuple[str, ...]) -> None:
        row = {k: (json.dumps(v) if k in json_cols and v is not None else v) for k, v in row.items()}
        cols = ",".join(row)
        marks = ",".join("?" for _ in row)
        self._exec(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})", tuple(row.values()))

    def create_schema(self) -> None:
        with self.lock:
            self.db.executescript(SCHEMA)

    def for_claim(self, claim_id: str) -> ClaimSink:
        return ClaimSink(self, claim_id)

    # -- policies and claims
    def upsert_policy(self, p: dict) -> None:
        self._upsert("policy", p, POLICY_JSON)

    def get_policy(self, policy_id: str) -> dict | None:
        rows = self._all("SELECT * FROM policy WHERE id=?", (policy_id,))
        return _load(rows[0] if rows else None, POLICY_JSON)

    def upsert_claim(self, c: dict) -> None:
        c = {"status": "received", "created_at": now_iso(), **c}
        self._upsert("claim", c, CLAIM_JSON)

    def get_claim(self, claim_id: str) -> dict | None:
        rows = self._all("SELECT * FROM claim WHERE id=?", (claim_id,))
        return _load(rows[0] if rows else None, CLAIM_JSON)

    def list_claims(self) -> list[dict]:
        return [_load(r, CLAIM_JSON) for r in self._all("SELECT * FROM claim ORDER BY created_at DESC")]

    def claims_before(self, claim_id: str) -> list[dict]:
        """Claims filed earlier than this one (by insertion order)."""
        return [_load(r, CLAIM_JSON) for r in self._all(
            "SELECT * FROM claim WHERE rowid < (SELECT rowid FROM claim WHERE id=?) ORDER BY rowid", (claim_id,))]

    def set_status(self, claim_id: str, status: str) -> None:
        self._exec("UPDATE claim SET status=? WHERE id=?", (status, claim_id))
        self._notify(claim_id, "status", {"status": status})

    def reset_claim(self, claim_id: str) -> None:
        self._exec("DELETE FROM evidence WHERE claim_id=?", (claim_id,))
        self._exec("DELETE FROM trace_step WHERE case_id=?", (claim_id,))
        self._exec("UPDATE claim SET status='received', score=NULL, band=NULL, recommendation=NULL, "
                   "score_detail=NULL, rule_flags=NULL, hypotheses=NULL, decision=NULL, outcome=NULL, "
                   "decision_reason=NULL, decided_at=NULL WHERE id=?", (claim_id,))

    def save_decision(self, claim_id: str, decision: str, outcome: str, reason: str | None) -> None:
        self._exec("UPDATE claim SET decision=?, outcome=?, decision_reason=?, decided_at=?, status='decided' "
                   "WHERE id=?", (decision, outcome, reason, now_iso(), claim_id))
        self._notify(claim_id, "status", {"status": "decided"})

    # -- evidence and trace
    def evidence_rows(self, claim_id: str) -> list[dict]:
        """Evidence with database id and rejected flag, for the API."""
        return [{"id": r["id"], "rejected_by_adjuster": bool(r["rejected_by_adjuster"]), **json.loads(r["body"])}
                for r in self._all("SELECT * FROM evidence WHERE claim_id=? ORDER BY id", (claim_id,))]

    def evidence_for(self, claim_id: str, include_rejected: bool = False) -> list[Evidence]:
        return [Evidence(**{k: v for k, v in r.items() if k not in ("id", "rejected_by_adjuster")})
                for r in self.evidence_rows(claim_id) if include_rejected or not r["rejected_by_adjuster"]]

    def reject_evidence(self, evidence_id: int) -> None:
        self._exec("UPDATE evidence SET rejected_by_adjuster=1 WHERE id=?", (evidence_id,))

    def trace_for(self, claim_id: str) -> list[TraceStep]:
        return [TraceStep(**json.loads(r["body"]))
                for r in self._all("SELECT body FROM trace_step WHERE case_id=? ORDER BY id", (claim_id,))]

    # -- weights and footprints
    def save_weight_config(self, w: WeightConfig) -> None:
        self._upsert("weight_config", {"damage_type": w.damage_type, "p0": w.p0, "weights": w.weights,
                                       "context_weight": w.context_weight, "updated_at": now_iso()}, ("weights",))

    def weight_config(self, damage_type: str) -> WeightConfig | None:
        rows = self._all("SELECT * FROM weight_config WHERE damage_type=?", (damage_type,))
        d = _load(rows[0] if rows else None, ("weights",))
        return WeightConfig(**{k: d[k] for k in ("damage_type", "p0", "weights", "context_weight")}) if d else None

    def save_footprint(self, f: dict) -> None:
        self._upsert("event_footprint", f, FOOTPRINT_JSON)

    def get_footprint(self, footprint_id: str) -> dict | None:
        rows = self._all("SELECT * FROM event_footprint WHERE id=?", (footprint_id,))
        return _load(rows[0] if rows else None, FOOTPRINT_JSON)

    def footprints_near(self, lat: float, lon: float, date: str) -> list[dict]:
        """Footprints whose dates cover `date` and whose circle contains the point."""
        from math import cos, radians
        out = []
        for r in self._all("SELECT * FROM event_footprint WHERE date_from<=? AND date_to>=?", (date, date)):
            f = _load(r, FOOTPRINT_JSON)
            dy = (lat - f["center_lat"]) * 111.0
            dx = (lon - f["center_lon"]) * 111.0 * cos(radians(lat))
            if (dx * dx + dy * dy) ** 0.5 <= (f["radius_km"] or 0):
                out.append(f)
        return out
