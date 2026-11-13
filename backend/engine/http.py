"""One door to the outside world: every external request is retried once, saved to disk, and replayable.

REPLAY=1 makes fetch() read only from the cache, so a whole investigation runs with no network.
Secrets (key/token params, Authorization headers) are left out of both the cache key and the saved file.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx

UA = "ClaimLens-hackathon/0.1"
SECRET_PARAMS = {"key", "access_token", "token", "apikey", "api_key"}
TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests swap this for a mock


class SourceError(Exception):
    """An external source failed after the retry."""


class CacheMiss(SourceError):
    """Replay mode asked for a response that was never saved."""


def cache_dir() -> Path:
    default = Path(__file__).resolve().parents[2] / "demo" / "cache"
    return Path(os.environ.get("CACHE_DIR") or default)


def replay_on() -> bool:
    return os.environ.get("REPLAY", "") not in ("", "0")


def make_key(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]


def cache_get(bucket: str, key: str) -> Any | None:
    path = cache_dir() / bucket / f"{key}.json"
    return json.loads(path.read_text()) if path.exists() else None


def cache_put(bucket: str, key: str, value: Any) -> None:
    path = cache_dir() / bucket / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))


async def fetch(url: str, *, params: dict | None = None, method: str = "GET", json_body: Any = None,
                data: dict | None = None, headers: dict | None = None, timeout: float = 20,
                as_bytes: bool = False, as_text: bool = False, replay: bool | None = None) -> Any:
    public_params = {k: v for k, v in (params or {}).items() if k.lower() not in SECRET_PARAMS}
    key = make_key(method, url, public_params, json_body, data)
    saved = cache_get("http", key)
    if saved is not None:
        body = saved["body"]
        return base64.b64decode(body) if saved.get("bytes") else body
    if replay if replay is not None else replay_on():
        raise CacheMiss(f"no saved response for {method} {url}")

    last: Exception | None = None
    async with httpx.AsyncClient(transport=TRANSPORT, timeout=timeout, follow_redirects=True) as client:
        for _ in range(2):  # one try + one retry
            try:
                r = await client.request(method, url, params=params, json=json_body, data=data,
                                         headers={"User-Agent": UA, **(headers or {})})
                r.raise_for_status()
                if as_bytes:
                    body: Any = r.content
                    cache_put("http", key, {"url": url, "bytes": True, "body": base64.b64encode(body).decode()})
                else:
                    body = r.text if as_text else r.json()
                    cache_put("http", key, {"url": url, "params": public_params, "body": body})
                return body
            except (httpx.HTTPError, ValueError) as e:
                last = e
    raise SourceError(f"{method} {url} failed: {type(last).__name__}: {last}")
