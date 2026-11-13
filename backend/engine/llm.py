"""LLM calls through OpenRouter. Always JSON out; cached and replayable like every other external call."""
from __future__ import annotations

import base64
import json
import os
import re

import httpx

from engine.http import CacheMiss, SourceError, cache_get, cache_put, make_key, replay_on

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
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
    out = json.loads(text)
    if not isinstance(out, dict):
        raise ValueError("not a JSON object")
    return out


async def llm_json(system: str, user: str, *, model: str = "fast", images: list[bytes] | None = None) -> dict:
    mid = model_id(model)
    key = make_key(mid, system, user, [make_key(base64.b64encode(i).decode()) for i in images or []])
    saved = cache_get("llm", key)
    if saved is not None:
        return saved
    if replay_on():
        raise CacheMiss(f"no saved LLM answer for model {mid}")

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
            cache_put("llm", key, out)
            return out
        except ValueError as e:  # includes JSONDecodeError
            last = e
    raise LLMError(f"model {mid} returned invalid JSON twice: {last}")
