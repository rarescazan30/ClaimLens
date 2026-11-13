"""Per-damage-type numbers: what counts as 'enough' weather, which agents apply, default score weights."""
from engine.models import WeightConfig

ALL_AGENTS = ["meteo", "satellite", "risk_zones", "photo_forensics", "street_view", "news"]

AGENTS_FOR = {
    "flood": ALL_AGENTS,
    "storm": ["meteo", "news", "street_view", "photo_forensics"],
}

RAIN_24H_MM = 30      # flood
GUST_KMH = 70         # storm
NOTIFY_DAYS = 60      # PAD notification deadline

THRESHOLD_TEXT = {
    "flood": f"precipitații ≥ {RAIN_24H_MM} mm în 24 h",
    "storm": f"rafale ≥ {GUST_KMH} km/h",
}

DEFAULT_WEIGHTS = [
    WeightConfig(damage_type="flood", p0=0.5, context_weight=0.5,
                 weights={"meteo": 1.5, "satellite": 2.5, "risk_zones": 2.5,
                          "photo_forensics": 2.0, "street_view": 1.0, "news": 1.0}),
    WeightConfig(damage_type="storm", p0=0.5, context_weight=0.5,
                 weights={"meteo": 3.0, "news": 1.5, "street_view": 2.0,
                          "photo_forensics": 2.0, "satellite": 0, "risk_zones": 0}),
]
