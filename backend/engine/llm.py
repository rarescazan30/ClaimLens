"""LLM calls through OpenRouter. Always JSON out; replayed from saved answers in replay mode, saved in record mode."""
from __future__ import annotations

import base64
import json
import os
import re

import httpx

from engine.http import CacheMiss, SourceError, _from_cache, cache_get, cache_put, make_key
from engine.modes import run_mode

URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMError(SourceError):
    """The model did not return valid JSON after one retry, or the provider failed."""


def model_id(model: str) -> str:
    if model == "fast":
        return os.environ.get("MODEL_FAST") or "anthropic/claude-haiku-5.5"
    if model == "strong":
        return os.environ.get("MODEL_STRONG") or "anthropic/claude-sonnet-5.5"
    return model  # a literal OpenRouter id


async def _complete(payload: dict) -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise LLMError("OPENROUTER_API_KEY is not set")
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(URL, json=payload, headers={"Authorization": f"Bearer {key}"})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"] or ""
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        raise LLMError(f"OpenRouter failed: {type(e).__name__}: {e}") from e


def _parse(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in the answer")
    # first complete object only: models sometimes add a second object or a closing remark
    out, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(out, dict):
        raise ValueError("not a JSON object")
    return out


async def llm_json(system: str, user: str, *, model: str = "fast", images: list[bytes] | None = None) -> dict:
    mid = model_id(model)
    key = make_key(mid, system, user, [make_key(base64.b64encode(i).decode()) for i in images or []])
    _from_cache.set(False)
    if run_mode() == "replay":
        saved = cache_get("llm", key)
        if saved is None:
            raise CacheMiss(f"no saved LLM answer for model {mid}")
        _from_cache.set(True)
        return saved

    content: list | str = user
    if images:
        content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(i).decode()}}
            for i in images]
    payload = {"model": mid, "temperature": 0,
               "messages": [{"role": "system", "content": system + "\nRăspunde DOAR cu un obiect JSON valid."},
                            {"role": "user", "content": content}]}
    last: Exception | None = None
    for _ in range(2):
        try:
            out = _parse(await _complete(payload))
            if run_mode() == "record":
                cache_put("llm", key, out)
            return out
        except (ValueError, LLMError) as e:  # invalid JSON, or a provider hiccup (timeout, 429, 5xx)
            last = e
    raise LLMError(f"model {mid} failed twice: {type(last).__name__}: {last}")
