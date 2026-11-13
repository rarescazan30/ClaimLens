"""Registry of specialist agents. Each real agent replaces its stub here."""
from agents.stub import make_stub
from engine.thresholds import ALL_AGENTS

AGENTS = {name: make_stub(name) for name in ALL_AGENTS}

from agents.meteo.agent import run as _meteo  # noqa: E402

from agents.satellite.agent import run as _satellite  # noqa: E402

from agents.risk_zones.agent import run as _risk  # noqa: E402

AGENTS["meteo"] = _meteo
AGENTS["risk_zones"] = _risk
AGENTS["satellite"] = _satellite
