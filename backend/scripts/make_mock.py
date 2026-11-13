"""Writes demo/mock/*.json: the exact shapes GET /claims/{id} and GET /claims/{id}/trace return.
Numbers are placeholders for the frontend; the real run replaces them."""
import json
from pathlib import Path

from engine.models import Evidence, Finding, TraceStep

OUT = Path(__file__).resolve().parents[2] / "demo" / "mock"
OUT.mkdir(parents=True, exist_ok=True)
T = "2026-11-14T03:{:02d}:{:02d}Z"
CID = "C-1042"


def f(metric, value, unit, source, url=None, res=None):
    return Finding(metric=metric, value=value, unit=unit, source=source, url=url, spatial_res_km=res,
                   retrieved_at="2026-11-14T03:00:10Z")


H = [
    {"id": "H1", "text": "Precipitații ≥ 30 mm în 24 h la adresă, pe 14.09.2024", "critical": True, "agents": ["meteo", "news"]},
    {"id": "H2", "text": "Adresa a fost în zona inundată cartografiată de Copernicus", "critical": True, "agents": ["satellite", "risk_zones"]},
    {"id": "H3", "text": "Fotografiile sunt autentice și arată dauna declarată (apă 60 cm în casă)", "critical": True, "agents": ["photo_forensics"]},
    {"id": "H4", "text": "Dauna nu era preexistentă", "critical": False, "agents": ["street_view"]},
]

EV = [
    (1, Evidence(agent="meteo", round=1, hypothesis=H[0]["text"], verdict="supports", strength=0.7, data_quality=0.6,
        findings=[f("precipitation_24h_max", 45.7, "mm", "Open-Meteo ERA5-Land", "https://open-meteo.com", 9),
                  f("precipitation_72h_max", 75.2, "mm", "Open-Meteo ERA5-Land", "https://open-meteo.com", 9)],
        reasoning_steps=["45.7 mm în 24 h depășește pragul de 30 mm."], gaps=["Rezoluție 9 km"], suggested_followup=None)),
    (2, Evidence(agent="satellite", round=1, hypothesis=H[1]["text"], verdict="inconclusive", strength=0.3, data_quality=0.8,
        findings=[f("inside_flood_extent", False, None, "Copernicus CEMS EMSR758", "https://mapping.emergency.copernicus.eu/activations/EMSR758/"),
                  f("distance_to_flood_edge_m", 150, "m", "Copernicus CEMS EMSR758"),
                  f("nearest_edge_point", {"lat": 45.6291, "lon": 27.8012}, None, "Copernicus CEMS EMSR758")],
        reasoning_steps=["Casa e în afara poligonului, la 150 m de margine."], gaps=["Incertitudine SAR ±20–30 m"],
        suggested_followup="Verifică diferența de nivel față de marginea apei")),
    (3, Evidence(agent="risk_zones", round=1, hypothesis=H[1]["text"], verdict="supports", strength=0.4, data_quality=0.7,
        findings=[f("distance_to_water_m", 310, "m", "OpenStreetMap")],
        reasoning_steps=["Curs de apă la 310 m."], gaps=["Altitudinea nu a fost verificată"], suggested_followup=None)),
    (4, Evidence(agent="photo_forensics", round=1, hypothesis=H[2]["text"], verdict="inconclusive", strength=0.2, data_quality=0.4,
        findings=[f("foto1.jpg:exif_missing", True, None, "EXIF"), f("foto2.jpg:exif_missing", True, None, "EXIF"),
                  f("foto1.jpg:shows_declared_damage", True, None, "Vision LLM")],
        reasoning_steps=["Fără metadate; imaginile arată apă în interior."], gaps=["Fără EXIF nu putem data pozele"],
        suggested_followup="Caută copii ale pozelor pe web")),
    (5, Evidence(agent="street_view", round=1, hypothesis=H[3]["text"], verdict="inconclusive", strength=0.1, data_quality=0.5,
        findings=[f("pre_event_image_date", "2023-06-11", None, "Mapillary")],
        reasoning_steps=["Imagine din iunie 2023, fără daune vizibile."], gaps=[], suggested_followup=None)),
    (6, Evidence(agent="news", round=1, hypothesis=H[0]["text"], verdict="supports", strength=0.6, data_quality=0.7,
        findings=[f("news_report", "Inundații în județul Galați: sute de case afectate", None, "Digi24", "https://www.digi24.ro/"),
                  f("reports_confirmed", 3, None, "GDELT")],
        reasoning_steps=["3 relatări independente confirmă inundația în localitate."], gaps=[], suggested_followup=None)),
    (7, Evidence(agent="risk_zones", round=2, hypothesis=H[1]["text"], verdict="contradicts", strength=0.9, data_quality=0.7,
        findings=[f("elevation_house_m", 47.0, "m", "Copernicus DEM (Open-Meteo)", None, 0.09),
                  f("elevation_flood_edge_m", 41.0, "m", "Copernicus DEM (Open-Meteo)", None, 0.09),
                  f("elevation_diff_m", 6.0, "m", "Copernicus DEM (Open-Meteo)", None, 0.09)],
        reasoning_steps=["Casa e cu 6 m deasupra marginii apei; 60 cm de apă în casă nu sunt plauzibili."], gaps=["Grilă DEM 90 m"],
        suggested_followup=None)),
    (8, Evidence(agent="photo_forensics", round=2, hypothesis=H[2]["text"], verdict="contradicts", strength=0.95, data_quality=0.9,
        findings=[f("exact_copy_before_event", True, None, "Google Vision Web Detection", "https://example.org/articol-martie-2024"),
                  f("foto2.jpg:first_seen", "2024-03-18", None, "Google Vision Web Detection", "https://example.org/articol-martie-2024")],
        reasoning_steps=["foto2.jpg apare într-un articol publicat în martie 2024, înainte de eveniment."], gaps=[], suggested_followup=None)),
]

claim = {
    "claim": {"id": CID, "policy_id": "P-7731", "damage_type": "flood", "event_date": "2024-09-14", "notified_at": "2024-09-19",
              "address": "Str. Exemplu 12, Pechea, jud. Galați", "lat": 45.6305, "lon": 27.8031,
              "description": "Apă în casă, aproximativ 60 cm, mobilier și pardoseală distruse.", "amount_claimed": 48000,
              "photos": ["foto1.jpg", "foto2.jpg"], "status": "awaiting_decision", "decision": None, "outcome": None,
              "decision_reason": None, "decided_at": None, "created_at": "2026-11-14T03:00:00Z"},
    "policy": {"id": "P-7731", "holder_name": "Persoană Sintetică", "address": "Str. Exemplu 12, Pechea, jud. Galați",
               "lat": 45.6305, "lon": 27.8031, "valid_from": "2024-02-01", "valid_to": "2025-01-31", "waiting_days": 0,
               "covered_risks": ["flood", "earthquake", "landslide"], "sum_insured": 100000, "product": "PAD"},
    "rule_flags": [{"rule": r, "passed": True, "reason": t} for r, t in [
        ("policy_active", "Poliță activă la data evenimentului"), ("waiting_period", "Perioada de așteptare a trecut"),
        ("risk_covered", "Inundația este risc acoperit"), ("address_match", "Adresa coincide cu polița"),
        ("notified_in_time", "Notificat la 5 zile de la eveniment")]],
    "hypotheses": H,
    "not_relevant_agents": [],
    "evidence": [{"id": i, "rejected_by_adjuster": False, **e.model_dump()} for i, e in EV],
    "score": {"score": 12.4, "band": "unlikely", "recommendation": "antifraud_referral",
              "contributions": [{"agent": "meteo", "round": 1, "delta_logit": 0.63}, {"agent": "satellite", "round": 1, "delta_logit": 0.0},
                                {"agent": "risk_zones", "round": 2, "delta_logit": -1.58}, {"agent": "photo_forensics", "round": 2, "delta_logit": -1.71},
                                {"agent": "street_view", "round": 1, "delta_logit": 0.0}, {"agent": "news", "round": 1, "delta_logit": 0.42},
                                {"agent": "context", "round": 0, "delta_logit": 0.0}],
              "gates": [{"kind": "clear_fake", "reason": "foto2.jpg: copie exactă publicată înainte de eveniment"}]},
    "score_history": [{"round": 1, "score": 74.1, "band": "likely"}, {"round": 2, "score": 12.4, "band": "unlikely"}],
}

steps, n = [], [0]


def step(step_id, parent, actor, type_, summary, outputs=None, sources=None, inputs=None):
    n[0] += 3
    steps.append(TraceStep(case_id=CID, step_id=step_id, parent=parent, actor=actor, type=type_, summary=summary,
                           inputs=inputs or {}, outputs=outputs or {}, sources=sources or [], status="done",
                           started_at=T.format(n[0] // 60, n[0] % 60), ended_at=T.format((n[0] + 2) // 60, (n[0] + 2) % 60)).model_dump())


step("rules", None, "rules", "decision", "Verificare poliță: 5 din 5 reguli trecute", {"flags": claim["rule_flags"]})
step("plan", None, "orchestrator", "decision", "Plan: 4 ipoteze, 6 agenți", {"hypotheses": H})
step("r1.dispatch", "plan", "orchestrator", "decision", "Runda 1: 6 agenți în paralel")
for i, e in EV[:6]:
    step(f"r1.{e.agent}.1", "r1.dispatch", f"agent:{e.agent}", "tool_call", f"Interogare {e.findings[0].source}", sources=[e.findings[0].source])
    step(f"r1.{e.agent}.2", "r1.dispatch", f"agent:{e.agent}", "observation", e.reasoning_steps[0], {"verdict": e.verdict}, [e.findings[0].source])
step("r1.score", "r1.dispatch", "score", "observation", "Scor după runda 1: 74.1 (probabil)", {"score": 74.1, "band": "likely"})
step("r1.judge", "r1.dispatch", "judge", "decision",
     "Tensiune: casa e în afara zonei inundate, dar dosarul declară 60 cm de apă în casă. Pozele nu au metadate. Retrimit 2 agenți.",
     {"action": "redispatch", "redispatch": [
         {"agent": "risk_zones", "question": "Care e diferența de nivel dintre casă și marginea zonei inundate?"},
         {"agent": "photo_forensics", "question": "Au mai fost publicate aceste poze înainte de 14.09.2024?"}]})
step("r2.dispatch", "r1.judge", "orchestrator", "decision", "Runda 2: zone de risc, foto-forensic")
for i, e in EV[6:]:
    step(f"r2.{e.agent}.1", "r2.dispatch", f"agent:{e.agent}", "tool_call", f"Interogare {e.findings[0].source}", sources=[e.findings[0].source])
    step(f"r2.{e.agent}.2", "r2.dispatch", f"agent:{e.agent}", "observation", e.reasoning_steps[0], {"verdict": e.verdict}, [e.findings[0].source])
step("r2.score", "r2.dispatch", "score", "observation", "Scor după runda 2: 12.4 (improbabil)", {"score": 12.4, "band": "unlikely"})
step("r2.judge", "r2.dispatch", "judge", "decision", "Toate ipotezele critice au verdict. Opresc investigația.", {"action": "stop"})
step("final", "r2.judge", "engine", "escalation", "Recomandare: trimitere la antifraudă. Decizia aparține evaluatorului.",
     {"recommendation": "antifraud_referral"})

(OUT / "claim_fraud.json").write_text(json.dumps(claim, ensure_ascii=False, indent=1))
(OUT / "trace_fraud.json").write_text(json.dumps(steps, ensure_ascii=False, indent=1))
queue = [{k: claim["claim"][k] for k in ("id", "address", "damage_type", "event_date", "status")} |
         {"score": 12.4, "band": "unlikely", "recommendation": "antifraud_referral"}]
(OUT / "claims_list.json").write_text(json.dumps(queue, ensure_ascii=False, indent=1))
print(len(steps), "steps")
