"""Run one agent for real against a claim and print what it found. Saves responses to demo/cache.

    python -m scripts.try_agent satellite 45.5553 27.7203 2024-09-14 "Str. X 1, Pechea, jud. Galați" [flood|storm] ["judge question"]
"""
import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from agents import AGENTS  # noqa: E402
from engine.context import AgentContext  # noqa: E402
from engine.graph import AgentTask  # noqa: E402
from engine.models import Hypothesis  # noqa: E402


class PrintSink:
    def trace(self, s): print(f"  [{s.step_id}] {s.type:<11} {s.status:<6} {s.summary}")
    def evidence(self, e): return 1
    def score(self, s, r): pass
    def hypotheses(self, h): pass
    def flags(self, f): pass


async def main(agent, lat, lon, day, address, kind="flood", question=None, *photos):
    claim = {"id": "TRY", "damage_type": kind, "event_date": day, "address": address, "lat": float(lat),
             "lon": float(lon), "description": "apă în casă, 60 cm", "photos": [], "photo_paths": list(photos),
             "other_photo_paths": [], "footprints": []}
    task = AgentTask(claim=claim, policy={}, round=2 if question else 1, question=question or None,
                     hypotheses=[Hypothesis(id="H1", text="Dauna declarată este plauzibilă", agents=[agent])])
    e = await AGENTS[agent](task, AgentContext("TRY", agent, task.round, PrintSink()))
    print(f"\n{e.verdict}  strength={e.strength} quality={e.data_quality}")
    for f in e.findings:
        print(f"  {f.metric:<28} {str(f.value)[:90]} {f.unit or ''}   [{f.source}]")
    for g in e.gaps:
        print("  gap:", g)

if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:]))
