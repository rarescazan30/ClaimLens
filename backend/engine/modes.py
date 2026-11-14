"""The three run modes. Live (default) really runs; replay reads saved answers only; record runs and overwrites them."""
from __future__ import annotations

import os
from typing import Literal

Mode = Literal["live", "replay", "record"]


def _on(name: str) -> bool:
    return os.environ.get(name, "") not in ("", "0")


def run_mode() -> Mode:
    if _on("REPLAY"):
        return "replay"
    if _on("RECORD"):
        return "record"
    return "live"
