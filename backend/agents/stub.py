"""Placeholder agent used until the real one exists. Says plainly that it knows nothing."""
import asyncio

from engine.context import AgentContext
from engine.graph import AgentTask
from engine.models import Evidence


def make_stub(name: str):
    async def run(task: AgentTask, ctx: AgentContext) -> Evidence:
        await asyncio.sleep(0.4)
        ctx.note("observation", f"Agentul {name} nu este încă implementat")
        return ctx.inconclusive(task.hypotheses[0].text, f"Agentul {name} nu este încă implementat")
    return run
