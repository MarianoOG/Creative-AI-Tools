"""The LLM used for keyword generation, relevance and comment rewriting.

Pick the provider with ``SCOUT_LLM_PROVIDER`` (``anthropic`` by default, or
``openai``) and optionally the model with ``SCOUT_LLM_MODEL``. Each provider
needs its own key in the environment; a missing key is an error, never a
silent fallback to another provider or to no LLM.

Every call asks for one JSON object that matches a JSON schema.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

from .config import require_env
from .errors import ScoutError

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"
# Models that accept the server-side refusal fallback parameter.
_FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-fable-5-2", "claude-sonnet-5-5")


class LLM(Protocol):
    def json(self, system: str, prompt: str, schema: dict) -> dict: ...


def _parse_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    raise ScoutError("The LLM did not return valid JSON.")


class AnthropicLLM:
    def __init__(self, model: str):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=require_env(
            "ANTHROPIC_API_KEY", "Add it to youtube-scout/.env or the environment (or set SCOUT_LLM_PROVIDER)."
        ))
        self.model = model

    def json(self, system: str, prompt: str, schema: dict) -> dict:
        kwargs = dict(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        )
        try:
            if self.model in _FALLBACK_MODELS:
                response = self.client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
                )
            else:
                response = self.client.messages.create(**kwargs)
        except self._anthropic.AuthenticationError as exc:
            raise ScoutError("ANTHROPIC_API_KEY was rejected.") from exc
        except self._anthropic.RateLimitError as exc:
            raise ScoutError("The Anthropic API rate limit was hit; try again later.") from exc
        except self._anthropic.APIStatusError as exc:
            raise ScoutError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except self._anthropic.APIConnectionError as exc:
            raise ScoutError("Could not reach the Anthropic API.") from exc
        if response.stop_reason == "refusal":
            raise ScoutError("The LLM declined this request.")
        if response.stop_reason == "max_tokens":
            raise ScoutError("The LLM response was cut off (max_tokens).")
        text = "".join(block.text for block in response.content if block.type == "text")
        return _parse_json(text)


class OpenAILLM:
    def __init__(self, model: str):
        try:
            import openai
        except ImportError as exc:
            raise ScoutError("SCOUT_LLM_PROVIDER=openai needs the openai package: pip install openai") from exc
        self.client = openai.OpenAI(api_key=require_env(
            "OPENAI_API_KEY", "Add it to youtube-scout/.env or the environment."
        ))
        self.model = model

    def json(self, system: str, prompt: str, schema: dict) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": schema, "strict": True},
            },
        )
        return _parse_json(response.choices[0].message.content or "")


def get_llm() -> LLM:
    provider = os.getenv("SCOUT_LLM_PROVIDER", "anthropic").strip().lower()
    model = os.getenv("SCOUT_LLM_MODEL", "").strip()
    if provider == "anthropic":
        return AnthropicLLM(model or DEFAULT_ANTHROPIC_MODEL)
    if provider == "openai":
        if not model:
            raise ScoutError("SCOUT_LLM_MODEL is not set. Name the OpenAI model to use.")
        return OpenAILLM(model)
    raise ScoutError(f"Unknown SCOUT_LLM_PROVIDER {provider!r}: use 'anthropic' or 'openai'.")


def object_schema(properties: dict) -> dict:
    """A strict JSON schema object: every property required, nothing extra."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }
