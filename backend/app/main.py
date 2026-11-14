"""ClaimLens API: what the React app talks to. Routes, the live stream and background investigations.

The engine (engine/, agents/) knows nothing about this file. It gets a claim and a Sink.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.db import Store
from app.seed import DEMO, seed
from engine import http, modes
from engine.documents import from_claim, read_document, write_document
from engine.graph import run_investigation
from engine.models import TraceStep
from engine.rules import context_term
from engine.score import compute_score
from engine.thresholds import AGENTS_FOR, ALL_AGENTS

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

OUTCOMES = ("fast_track", "standard_review", "antifraud_referral")
CLAIM_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
RUN_KEYS = ("rule_flags", "hypotheses", "score_detail", "score", "band", "recommendation",
            "documents", "checks", "early_flags", "run_mode")   # not part of the claim the engine or the UI reads
DOCUMENT_KINDS = ("claim_form", "policy")


class DecisionIn(BaseModel):
    decision: Literal["approve", "modify"]
    outcome: str | None = None
    reason: str | None = None


class QuestionIn(BaseModel):
    question: str


def create_app(cases_dir: Path | None = None) -> FastAPI:
    data_dir = Path(os.environ.get("DATA_DIR") or Path(__file__).resolve().parents[1] / "data")
    photo_roots = [data_dir / "photos", DEMO / "cases" / "photos"]
    document_roots = [data_dir / "documents", (cases_dir or DEMO / "cases") / "documents"]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        data_dir.mkdir(parents=True, exist_ok=True)
        store = Store(data_dir / "claimlens.db")
        store.create_schema()
        seed(store, cases_dir)
        for c in store.list_claims():  # a restart mid-run must not leave a case stuck
            if c["status"] == "investigating":
                store.set_status(c["id"], "awaiting_decision" if c["score"] is not None else "received")
        store.listeners.append(publish)
        app.state.store = store
        yield

    app = FastAPI(title="ClaimLens", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.engine_kwargs = {}   # tests inject agents / planner / judge here
    app.state.tasks = set()
    subscribers: dict[str, list[asyncio.Queue]] = {}

    def publish(claim_id: str, kind: str, payload: dict) -> None:
        for q in subscribers.get(claim_id, []):
            q.put_nowait((kind, payload))

    def store() -> Store:
        return app.state.store

    def claim_or_404(claim_id: str) -> dict:
        c = store().get_claim(claim_id)
        if c is None:
            raise HTTPException(404, "Dosar inexistent")
        return c

    def inside(roots: list[Path], name: str) -> Path | None:
        """The file `name` under the first root that has it; None if absent or if the name leaves the folder."""
        for root in roots:
            p = (root / name).resolve()
            if p.is_file() and root.resolve() in p.parents:
                return p
        return None

    def photo_file(name: str) -> Path | None:
        return inside(photo_roots, name)

    def document_files(claim: dict) -> dict[str, Path | None]:
        names = claim.get("documents") or {}
        return {k: inside(document_roots, names[k]) if isinstance(names.get(k), str) else None
                for k in DOCUMENT_KINDS}

    # ---- running investigations
    async def investigate(claim_id: str, question: str | None = None, resume: bool = False) -> None:
        """One run. A claim with documents is read from its PDFs (or resumed after a pause); a claim stored
        without documents (old demo data) runs exactly as before, from its stored fields."""
        s = store()
        status = "awaiting_decision"
        try:
            claim = s.get_claim(claim_id)
            policy = s.get_policy(claim["policy_id"]) or {}
            cfg = s.weight_config(claim["damage_type"]) or s.weight_config("flood")
            engine_claim = {k: v for k, v in claim.items() if k not in RUN_KEYS}
            photos = [p for p in map(photo_file, claim.get("photos") or []) if p]
            # only claims filed before this one: the earlier claimant is never penalised for a later copy
            earlier = [p for c in s.claims_before(claim_id) for p in map(photo_file, c.get("photos") or []) if p]
            engine_claim["photo_paths"] = [str(p) for p in photos]
            engine_claim["other_photo_paths"] = [str(p) for p in earlier]
            if claim.get("lat") is not None and claim.get("event_date"):
                engine_claim["footprints"] = s.footprints_near(claim["lat"], claim["lon"], claim["event_date"])
            kwargs = dict(app.state.engine_kwargs)
            stored = {"early_flags": claim.get("early_flags") or [], "rule_flags": claim.get("rule_flags") or []}
            if question:
                kwargs |= {"extra_question": question, "prior": s.evidence_for(claim_id),
                           "hypotheses": [h for h in _hyps(claim)] or None}
                if claim.get("early_flags") is not None:   # read from documents: keep the flags of the early steps
                    kwargs["resume"] = stored
            elif resume:
                kwargs |= {"resume": stored, "photos": photos, "earlier_photos": earlier,
                           "footprints_for": s.footprints_near}
            elif claim.get("documents"):
                kwargs |= {"documents": document_files(claim), "photos": photos, "earlier_photos": earlier,
                           "footprints_for": s.footprints_near}
            result = await run_investigation(engine_claim, policy, cfg, s.for_claim(claim_id), **kwargs)
            if result is None:
                status = "paused"
        except Exception as e:  # never leave a case stuck in 'investigating'
            s.for_claim(claim_id).trace(TraceStep(
                case_id=claim_id, step_id=f"error.{uuid.uuid4().hex[:6]}", actor="engine", type="escalation",
                summary=f"Investigația s-a oprit cu o eroare: {type(e).__name__}: {e}. Dosarul merge la evaluator.",
                status="failed"))
        finally:
            s.set_status(claim_id, status)

    def _hyps(claim: dict):
        from engine.models import Hypothesis
        return [Hypothesis(**h) for h in claim.get("hypotheses") or []]

    def start(claim_id: str, question: str | None = None, resume: bool = False) -> None:
        store().set_status(claim_id, "investigating")  # before the task starts, so a second start is refused
        store().set_run_mode(claim_id, modes.run_mode())
        task = asyncio.get_running_loop().create_task(investigate(claim_id, question, resume))
        app.state.tasks.add(task)
        task.add_done_callback(app.state.tasks.discard)

    def refuse_if_running(claim: dict) -> None:
        if claim["status"] == "investigating":
            raise HTTPException(409, "Investigația este deja în curs")

    # ---- routes
    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/claims")
    def list_claims():
        keys = ("id", "address", "damage_type", "event_date", "status", "score", "band", "recommendation",
                "decision", "outcome", "created_at")
        return [{k: c.get(k) for k in keys} for c in store().list_claims()]

    @app.post("/claims")
    async def create_claim(data: str = Form(...), photos: list[UploadFile] = File(default=[])):
        try:
            body = json.loads(data)
            claim = dict(body["claim"])
        except (ValueError, KeyError, TypeError):
            raise HTTPException(422, "Câmpul 'data' trebuie să fie JSON cu cheia 'claim'")
        s = store()
        if isinstance(body.get("policy"), dict):
            s.upsert_policy(body["policy"])
            claim.setdefault("policy_id", body["policy"]["id"])
        if not claim.get("policy_id") or s.get_policy(claim["policy_id"]) is None:
            raise HTTPException(422, "Poliță inexistentă")
        for field in ("damage_type", "event_date", "address"):
            if not claim.get(field):
                raise HTTPException(422, f"Lipsește câmpul '{field}'")
        if claim["damage_type"] not in AGENTS_FOR:
            raise HTTPException(422, f"Tip de daună necunoscut. Acceptate: {', '.join(AGENTS_FOR)}")
        claim["id"] = claim.get("id") or f"C-{uuid.uuid4().hex[:6].upper()}"
        if not isinstance(claim["id"], str) or not CLAIM_ID.match(claim["id"]):   # the id becomes a folder name
            raise HTTPException(422, "ID de dosar invalid: doar litere, cifre, '-' și '_' (maximum 40)")
        for up in photos:
            if Path(up.filename or "").suffix.lower() not in PHOTO_TYPES:
                raise HTTPException(422, f"Tip de fișier neacceptat. Acceptate: {', '.join(sorted(PHOTO_TYPES))}")
        if s.get_claim(claim["id"]) is not None:
            raise HTTPException(409, "Există deja un dosar cu acest ID")
        names = []
        for i, up in enumerate(photos):
            ext = Path(up.filename or "").suffix.lower()
            target = data_dir / "photos" / claim["id"] / f"foto{i + 1}{ext}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(await up.read())
            names.append(f"{claim['id']}/{target.name}")
        claim["photos"] = names or claim.get("photos") or []
        # The two PDFs are the claim's source of truth: the run reads them back and locates the address itself
        # (lat/lon sent in the JSON are not used).
        folder = data_dir / "documents" / claim["id"]
        folder.mkdir(parents=True, exist_ok=True)
        for kind, fields in zip(DOCUMENT_KINDS, from_claim(claim, s.get_policy(claim["policy_id"]) or {})):
            write_document(fields, kind, folder / f"{kind}.pdf")
        claim["documents"] = {kind: f"{claim['id']}/{kind}.pdf" for kind in DOCUMENT_KINDS}
        allowed = {"id", "policy_id", "damage_type", "event_date", "notified_at", "address",
                   "description", "amount_claimed", "photos", "documents"}
        s.upsert_claim({k: v for k, v in claim.items() if k in allowed})
        start(claim["id"])
        return {"id": claim["id"]}

    @app.get("/claims/{claim_id}")
    def get_claim(claim_id: str):
        c = claim_or_404(claim_id)
        s = store()
        history = [{"round": int(t.step_id.split(".")[0][1:]), "score": t.outputs.get("score"),
                    "band": t.outputs.get("band")}
                   for t in s.trace_for(claim_id) if t.step_id.endswith(".score")]
        return {
            "claim": {k: v for k, v in c.items() if k not in RUN_KEYS},
            "policy": s.get_policy(c["policy_id"]),
            "rule_flags": c["rule_flags"] or [],
            "hypotheses": c["hypotheses"] or [],
            "not_relevant_agents": [a for a in ALL_AGENTS if a not in AGENTS_FOR.get(c["damage_type"], ALL_AGENTS)],
            "evidence": s.evidence_rows(claim_id),
            "score": c["score_detail"],
            "score_history": history,
            "checks": c.get("checks") or {},
            "flags": c.get("early_flags") or [],
            "documents": read_documents(c),
            "run_mode": c.get("run_mode"),
        }

    def read_documents(claim: dict) -> dict:
        """Each PDF's read fields ({} for one that is missing or unreadable); {} for a claim without documents."""
        if not claim.get("documents"):
            return {}
        return {kind: (read_document(path, kind).fields if path else {})
                for kind, path in document_files(claim).items()}

    @app.get("/claims/{claim_id}/trace")
    def get_trace(claim_id: str):
        claim_or_404(claim_id)
        return [t.model_dump() for t in store().trace_for(claim_id)]

    @app.get("/claims/{claim_id}/stream")
    async def stream(claim_id: str):
        claim_or_404(claim_id)

        async def gen():
            q: asyncio.Queue = asyncio.Queue()
            subscribers.setdefault(claim_id, []).append(q)  # subscribe first, so nothing is missed
            try:
                seen = set()
                for t in store().trace_for(claim_id):
                    seen.add(t.step_id)
                    yield {"event": "trace", "data": t.model_dump_json()}
                status = store().get_claim(claim_id)["status"]
                if status != "investigating":
                    for t in store().trace_for(claim_id):   # steps written while history was being sent
                        if t.step_id not in seen:
                            seen.add(t.step_id)
                            yield {"event": "trace", "data": t.model_dump_json()}
                    yield {"event": "status", "data": json.dumps({"status": status})}
                    return
                while True:
                    kind, payload = await q.get()
                    if kind == "trace":
                        if payload["step_id"] in seen:
                            continue
                        seen.add(payload["step_id"])
                    yield {"event": kind, "data": json.dumps(payload, ensure_ascii=False, default=str)}
                    if kind == "status" and payload["status"] != "investigating":
                        return
            finally:
                subscribers[claim_id].remove(q)
        return EventSourceResponse(gen())

    @app.post("/claims/{claim_id}/rerun")
    async def rerun(claim_id: str):
        refuse_if_running(claim_or_404(claim_id))
        store().reset_claim(claim_id)
        start(claim_id)
        return {"id": claim_id, "status": "investigating"}

    @app.post("/claims/{claim_id}/continue")
    async def continue_run(claim_id: str):
        if claim_or_404(claim_id)["status"] != "paused":
            raise HTTPException(409, "Investigația nu este oprită; nu are ce continua")
        start(claim_id, resume=True)
        return {"id": claim_id, "status": "investigating"}

    @app.post("/claims/{claim_id}/question")
    async def question(claim_id: str, body: QuestionIn):
        c = claim_or_404(claim_id)
        refuse_if_running(c)
        if c["status"] == "paused":
            raise HTTPException(409, "Investigația este oprită: continuați investigația sau decideți")
        if not body.question.strip():
            raise HTTPException(422, "Întrebarea este goală")
        start(claim_id, body.question.strip())
        return {"id": claim_id, "status": "investigating"}

    @app.post("/claims/{claim_id}/decision")
    async def decide(claim_id: str, body: DecisionIn):
        c = claim_or_404(claim_id)
        refuse_if_running(c)
        paused = c["status"] == "paused"   # no recommendation yet: only another outcome, with a reason
        if paused and body.decision == "approve":
            raise HTTPException(409, "Nu există încă o recomandare")
        if c["recommendation"] is None and not paused:
            raise HTTPException(409, "Dosarul nu a fost încă investigat")
        if body.decision == "approve":
            outcome, reason = c["recommendation"], body.reason
        else:
            if body.outcome not in OUTCOMES:
                raise HTTPException(422, f"Rezultat necunoscut. Acceptate: {', '.join(OUTCOMES)}")
            if not (body.reason or "").strip():
                raise HTTPException(422, "Modificarea recomandării cere un motiv")
            outcome, reason = body.outcome, body.reason.strip()
        store().save_decision(claim_id, body.decision, outcome, reason)
        try:
            await save_footprint(c)
        except Exception:   # learning is best-effort; the adjuster's decision is already saved
            pass
        return {"id": claim_id, "status": "decided", "outcome": outcome}

    @app.post("/claims/{claim_id}/evidence/{evidence_id}/reject")
    def reject(claim_id: str, evidence_id: int):
        c = claim_or_404(claim_id)
        refuse_if_running(c)
        s = store()
        rows = s.evidence_rows(claim_id)
        if evidence_id not in [r["id"] for r in rows]:
            raise HTTPException(404, "Dovadă inexistentă în acest dosar")
        s.reject_evidence(evidence_id)
        from engine.models import Flag, RuleFlag
        cfg = s.weight_config(c["damage_type"]) or s.weight_config("flood")
        early = [Flag(**f) for f in c["early_flags"]] if c.get("early_flags") is not None else None
        result = compute_score(s.evidence_for(claim_id), cfg, [RuleFlag(**f) for f in c["rule_flags"] or []],
                               context_term(c, s.get_policy(c["policy_id"]) or {}), data_flags=early)
        s.for_claim(claim_id).score(result, max((r["round"] for r in rows), default=1))
        return result.model_dump()

    def satellite_findings(claim_id: str) -> dict:
        for e in reversed(store().evidence_for(claim_id, include_rejected=True)):
            if e.agent == "satellite":
                return {f.metric: f.value for f in e.findings}
        return {}

    @app.get("/claims/{claim_id}/flood-extent")
    async def flood_extent(claim_id: str):
        """GeoJSON of the mapped flood for this claim, for the map. Served from the saved Copernicus response."""
        claim_or_404(claim_id)
        url = satellite_findings(claim_id).get("flood_extent_geojson_url")
        if not url:
            raise HTTPException(404, "Nu există o hartă a zonei inundate pentru acest dosar")
        try:
            return await http.fetch(url, timeout=60)
        except http.SourceError:
            raise HTTPException(502, "Harta zonei inundate nu a putut fi încărcată")

    async def save_footprint(claim: dict) -> None:
        """Learning step: keep the event's flood area, weather maxima and news for the next claims nearby."""
        found = satellite_findings(claim["id"])
        url, code = found.get("flood_extent_geojson_url"), found.get("activation")
        if not (url and code):
            return
        try:
            polygon = await http.fetch(url, timeout=60)
        except http.SourceError:
            return
        from datetime import date, timedelta
        from shapely.geometry import shape
        from shapely.ops import unary_union
        bounds = unary_union([shape(f["geometry"]).buffer(0) for f in polygon["features"]]).bounds
        day = date.fromisoformat(claim["event_date"][:10])
        ev = store().evidence_for(claim["id"])
        meteo = {f.metric: f.value for e in ev if e.agent == "meteo" for f in e.findings}
        news = [{"title": f.value, "outlet": f.source, "url": f.url}
                for e in ev if e.agent == "news" for f in e.findings if f.metric == "news_report"]
        store().save_footprint({
            "id": f"{code}-{found.get('mapped_area') or 'zona'}", "name": f"{code} – {found.get('mapped_area') or ''}".strip(" –"),
            "damage_type": claim["damage_type"], "date_from": (day - timedelta(days=3)).isoformat(),
            "date_to": (day + timedelta(days=10)).isoformat(),
            "center_lat": (bounds[1] + bounds[3]) / 2, "center_lon": (bounds[0] + bounds[2]) / 2,
            "radius_km": max(bounds[3] - bounds[1], bounds[2] - bounds[0]) * 111 / 2 + 2,
            "polygon": polygon, "meteo_maxima": {**meteo, "map_date": found.get("map_date"), "geojson_url": url},
            "news": news, "sources": [f"Copernicus CEMS Rapid Mapping {code}"], "version": 1})

    @app.get("/footprints/{footprint_id}")
    def footprint(footprint_id: str):
        f = store().get_footprint(footprint_id)
        if f is None:
            raise HTTPException(404, "Amprentă inexistentă")
        return f

    @app.get("/documents/{claim_id}/{name}")
    def document(claim_id: str, name: str):
        kind = name.removesuffix(".pdf")
        c = store().get_claim(claim_id)
        p = document_files(c).get(kind) if c and kind in DOCUMENT_KINDS and name == f"{kind}.pdf" else None
        if p is None:
            raise HTTPException(404, "Document inexistent")
        return FileResponse(p, media_type="application/pdf")

    @app.get("/photos/{name:path}")
    def photo(name: str):
        p = photo_file(name)
        if p is None:
            raise HTTPException(404, "Fotografie inexistentă")
        return FileResponse(p)

    return app


app = create_app()
