"""A thin, provider-agnostic LLM client that returns parsed JSON.

The judge only ever needs one capability: "given a system + user prompt,
return a JSON object". This module hides the provider differences behind a
single `complete_json()` function, configured via environment variables:

    JUDGE_LLM_PROVIDER  -> "openai" (default) | "anthropic"
    JUDGE_MODEL         -> model name (provider-specific default if unset)
    OPENAI_API_KEY      -> required for openai
    ANTHROPIC_API_KEY   -> required for anthropic

Weave auto-traces OpenAI/Anthropic SDK calls once `weave.init` has run, so the
raw LLM calls show up nested under the judge ops automatically.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any, Dict

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
}


class LLMError(RuntimeError):
    """Raised when the LLM call or JSON parsing fails."""


def get_provider() -> str:
    return os.getenv("JUDGE_LLM_PROVIDER", "openai").strip().lower() or "openai"


def get_model() -> str:
    explicit = os.getenv("JUDGE_MODEL", "").strip()
    if explicit:
        return explicit
    return DEFAULT_MODELS.get(get_provider(), DEFAULT_MODELS["openai"])


@lru_cache(maxsize=2)
def _openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise LLMError("openai package not installed") from exc
    if not os.getenv("OPENAI_API_KEY"):
        raise LLMError("OPENAI_API_KEY is not set")
    return OpenAI()


@lru_cache(maxsize=2)
def _anthropic_client():
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover
        raise LLMError("anthropic package not installed") from exc
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise LLMError("ANTHROPIC_API_KEY is not set")
    return Anthropic()


def _extract_json(text: str) -> Dict[str, Any]:
    """Parse a JSON object out of an LLM response, tolerating code fences."""
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the first {...} block.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise LLMError(f"Could not parse JSON from model output: {text[:500]!r}")


def _complete_openai(system: str, user: str, temperature: float) -> str:
    client = _openai_client()
    resp = client.chat.completions.create(
        model=get_model(),
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


def _complete_anthropic(system: str, user: str, temperature: float) -> str:
    client = _anthropic_client()
    resp = client.messages.create(
        model=get_model(),
        max_tokens=4096,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
    return "".join(parts)


def complete_json(
    system: str,
    user: str,
    temperature: float = 0.0,
) -> Dict[str, Any]:
    """Call the configured LLM and return a parsed JSON object.

    Raises LLMError on provider/parse failure.
    """
    provider = get_provider()
    try:
        if provider == "anthropic":
            raw = _complete_anthropic(system, user, temperature)
        elif provider == "openai":
            raw = _complete_openai(system, user, temperature)
        else:
            raise LLMError(f"Unknown JUDGE_LLM_PROVIDER: {provider!r}")
    except LLMError:
        raise
    except Exception as exc:  # provider/network errors
        raise LLMError(f"LLM call failed ({provider}): {exc}") from exc

    return _extract_json(raw)
