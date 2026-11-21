"""LLM gateway.

A single seam (`LLMClient.complete_json`) between the app and the model. Every
call returns schema-constrained JSON plus an `LLMCall` trace record (tokens,
latency, cost), so the rest of the code never touches the SDK directly.

Two implementations:
- `AnthropicLLM`: Claude via the official SDK, structured outputs, prompt caching
  on the (static) system prompt, and server-side refusal fallbacks.
- `MockLLM`: deterministic, offline. Lets CI, evals and demos run with no API key.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from typing import Any, Protocol

from app.config import Settings, get_settings
from app.models import LLMCall


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    name: str
    model: str

    def complete_json(
        self,
        *,
        purpose: str,
        system: str,
        content: list[dict[str, Any]],
        schema: dict[str, Any],
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], LLMCall]:
        """Return JSON matching `schema`.

        `content` is the user message (Anthropic content blocks). `payload` is the
        same input as structured data, used by the mock.
        """
        ...


def _cost(settings: Settings, input_tokens: int, output_tokens: int) -> float:
    return round(
        input_tokens / 1e6 * settings.price_input_per_mtok
        + output_tokens / 1e6 * settings.price_output_per_mtok,
        6,
    )


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, settings: Settings | None = None):
        import anthropic

        self._anthropic = anthropic
        self.settings = settings or get_settings()
        self.model = self.settings.llm_model
        self.client = anthropic.Anthropic(timeout=self.settings.llm_timeout_s)

    def complete_json(self, *, purpose, system, content, schema, payload):
        started = time.perf_counter()
        call = LLMCall(purpose=purpose, provider=self.name, model=self.model)
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                # On a policy decline the API transparently retries on a fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={
                    "effort": self.settings.llm_effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
                # The system prompt is static per purpose -> cache it.
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}],
            )
        except self._anthropic.APIStatusError as exc:
            call.error = f"HTTP {exc.status_code}: {exc.message}"
            raise LLMError(call.error) from exc
        except self._anthropic.APIConnectionError as exc:
            call.error = "connection error"
            raise LLMError(call.error) from exc
        finally:
            call.latency_ms = int((time.perf_counter() - started) * 1000)

        usage = response.usage
        call.input_tokens = (
            (usage.input_tokens or 0)
            + (getattr(usage, "cache_read_input_tokens", 0) or 0)
            + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        )
        call.output_tokens = usage.output_tokens or 0
        call.cost_usd = _cost(self.settings, call.input_tokens, call.output_tokens)
        call.model = response.model

        if response.stop_reason == "refusal":
            call.error = "refusal"
            raise LLMError("El modelo declinó la solicitud")
        if response.stop_reason == "max_tokens":
            call.error = "max_tokens"
            raise LLMError("Respuesta truncada (max_tokens)")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError("Respuesta sin contenido de texto")
        try:
            return json.loads(text), call
        except json.JSONDecodeError as exc:
            call.error = "invalid json"
            raise LLMError("JSON inválido en la respuesta") from exc


MockHandler = Callable[[dict[str, Any]], dict[str, Any]]


class MockLLM:
    """Deterministic stand-in. Each purpose registers a handler over `payload`."""

    name = "mock"
    model = "mock-deterministic"
    handlers: dict[str, MockHandler] = {}

    @classmethod
    def register(cls, purpose: str) -> Callable[[MockHandler], MockHandler]:
        def deco(fn: MockHandler) -> MockHandler:
            cls.handlers[purpose] = fn
            return fn

        return deco

    def complete_json(self, *, purpose, system, content, schema, payload):
        started = time.perf_counter()
        if purpose not in self.handlers:
            raise LLMError(f"Mock sin handler para '{purpose}'")
        result = self.handlers[purpose](payload)
        # Rough token estimate so cost dashboards have something meaningful to show.
        est_in = (len(system) + len(json.dumps(payload, default=str))) // 4
        est_out = len(json.dumps(result)) // 4
        call = LLMCall(
            purpose=purpose,
            provider=self.name,
            model=self.model,
            input_tokens=est_in,
            output_tokens=est_out,
            latency_ms=int((time.perf_counter() - started) * 1000),
            cost_usd=0.0,
        )
        return result, call


def _has_anthropic_credentials() -> bool:
    return any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"))


def get_llm(settings: Settings | None = None) -> LLMClient:
    settings = settings or get_settings()
    provider = settings.llm_provider
    if provider == "auto":
        provider = "anthropic" if _has_anthropic_credentials() else "mock"
    if provider == "anthropic":
        return AnthropicLLM(settings)
    return MockLLM()
