"""ClaimLens API: what the React app talks to. Routes, the live stream and background investigations.

The engine (engine/, agents/) knows nothing about this file. It gets a claim and a Sink.
"""
from __future__ import annotations

import asyncio
import json
import os
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
from engine import http
from engine.graph import run_investigation
from engine.models import TraceStep
from engine.rules import context_term
from engine.score import compute_score
from engine.thresholds import AGENTS_FOR, ALL_AGENTS

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

OUTCOMES = ("fast_track", "standard_review", "antifraud_referral")
RUN_KEYS = ("rule_flags", "hypotheses", "score_detail", "score", "band", "recommendation")


class DecisionIn(BaseModel):
    decision: Literal["approve", "modify"]
    outcome: str | None = None
    reason: str | None = None


class QuestionIn(BaseModel):
    question: str


def create_app(cases_dir: Path | None = None) -> FastAPI:
    data_dir = Path(os.environ.get("DATA_DIR") or Path(__file__).resolve().parents[1] / "data")
    photo_roots = [data_dir / "photos", DEMO / "cases" / "photos"]

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

    def photo_file(name: str) -> Path | None:
        for root in photo_roots:
            p = (root / name).resolve()
            if p.is_file() and root.resolve() in p.parents:
                return p
        return None

    # ---- running investigations
    async def investigate(claim_id: str, question: str | None = None) -> None:
        s = store()
        try:
            claim = s.get_claim(claim_id)
            policy = s.get_policy(claim["policy_id"]) or {}
            cfg = s.weight_config(claim["damage_type"]) or s.weight_config("flood")
            engine_claim = {k: v for k, v in claim.items() if k not in RUN_KEYS}
            engine_claim["photo_paths"] = [str(p) for p in map(photo_file, claim.get("photos") or []) if p]
            engine_claim["other_photo_paths"] = [
                str(p) for c in s.list_claims() if c["id"] != claim_id
                for p in map(photo_file, c.get("photos") or []) if p]
            if claim.get("lat") is not None:
                engine_claim["footprints"] = s.footprints_near(claim["lat"], claim["lon"], claim["event_date"])
            kwargs = dict(app.state.engine_kwargs)
            if question:
                kwargs |= {"extra_question": question, "prior": s.evidence_for(claim_id),
                           "hypotheses": [h for h in _hyps(claim)] or None}
            await run_investigation(engine_claim, policy, cfg, s.for_claim(claim_id), **kwargs)
        except Exception as e:  # never leave a case stuck in 'investigating'
            s.for_claim(claim_id).trace(TraceStep(
                case_id=claim_id, step_id=f"error.{uuid.uuid4().hex[:6]}", actor="engine", type="escalation",
                summary=f"Investigația s-a oprit cu o eroare: {type(e).__name__}: {e}. Dosarul merge la evaluator.",
                status="failed"))
        finally:
            s.set_status(claim_id, "awaiting_decision")

    def _hyps(claim: dict):
        from engine.models import Hypothesis
        return [Hypothesis(**h) for h in claim.get("hypotheses") or []]

    def start(claim_id: str, question: str | None = None) -> None:
        store().set_status(claim_id, "investigating")  # before the task starts, so a second start is refused
        task = asyncio.get_running_loop().create_task(investigate(claim_id, question))
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
        if claim.get("lat") is None or claim.get("lon") is None:
            try:
                hits = await http.fetch("https://nominatim.openstreetmap.org/search",
                                        params={"q": claim["address"], "format": "json", "limit": 1})
                claim["lat"], claim["lon"] = float(hits[0]["lat"]), float(hits[0]["lon"])
            except (http.SourceError, IndexError, KeyError, ValueError):
                raise HTTPException(422, "Adresa nu a putut fi localizată. Trimiteți lat/lon.")
        claim["id"] = claim.get("id") or f"C-{uuid.uuid4().hex[:6].upper()}"
        if s.get_claim(claim["id"]) is not None:
            raise HTTPException(409, "Există deja un dosar cu acest ID")
        names = []
        for i, up in enumerate(photos):
            ext = Path(up.filename or "").suffix.lower() or ".jpg"
            target = data_dir / "photos" / claim["id"] / f"foto{i + 1}{ext}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(await up.read())
            names.append(f"{claim['id']}/{target.name}")
        claim["photos"] = names or claim.get("photos") or []
        allowed = {"id", "policy_id", "damage_type", "event_date", "notified_at", "address", "lat", "lon",
                   "description", "amount_claimed", "photos"}
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
        }

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

    @app.post("/claims/{claim_id}/question")
    async def question(claim_id: str, body: QuestionIn):
        refuse_if_running(claim_or_404(claim_id))
        if not body.question.strip():
            raise HTTPException(422, "Întrebarea este goală")
        start(claim_id, body.question.strip())
        return {"id": claim_id, "status": "investigating"}

    @app.post("/claims/{claim_id}/decision")
    async def decide(claim_id: str, body: DecisionIn):
        c = claim_or_404(claim_id)
        refuse_if_running(c)
        if c["recommendation"] is None:
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
        await save_footprint(c)
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
        from engine.models import RuleFlag
        cfg = s.weight_config(c["damage_type"]) or s.weight_config("flood")
        result = compute_score(s.evidence_for(claim_id), cfg, [RuleFlag(**f) for f in c["rule_flags"] or []],
                               context_term(c, s.get_policy(c["policy_id"]) or {}))
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

    @app.get("/photos/{name:path}")
    def photo(name: str):
        p = photo_file(name)
        if p is None:
            raise HTTPException(404, "Fotografie inexistentă")
        return FileResponse(p)

    return app


app = create_app()
