"""Registry of specialist agents. Each real agent replaces its stub here."""
from agents.stub import make_stub
from engine.thresholds import ALL_AGENTS

AGENTS = {name: make_stub(name) for name in ALL_AGENTS}

from agents.meteo.agent import run as _meteo  # noqa: E402

from agents.satellite.agent import run as _satellite  # noqa: E402

from agents.risk_zones.agent import run as _risk  # noqa: E402

from agents.photo_forensics.agent import run as _photo  # noqa: E402

from agents.street_view.agent import run as _street  # noqa: E402
from agents.news.agent import run as _news  # noqa: E402

AGENTS["meteo"] = _meteo
AGENTS["street_view"] = _street
AGENTS["news"] = _news
AGENTS["photo_forensics"] = _photo
AGENTS["risk_zones"] = _risk
AGENTS["satellite"] = _satellite
