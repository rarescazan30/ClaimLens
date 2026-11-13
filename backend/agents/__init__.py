"""Registry of specialist agents. Each real agent replaces its stub here."""
from agents.stub import make_stub
from engine.thresholds import ALL_AGENTS

AGENTS = {name: make_stub(name) for name in ALL_AGENTS}

from agents.meteo.agent import run as _meteo  # noqa: E402

AGENTS["meteo"] = _meteo
