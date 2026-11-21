"""AnthropicLLM response handling, tested with a fake SDK client (no network)."""

from types import SimpleNamespace

import pytest

from app.ai.llm import AnthropicLLM, LLMError
from app.config import Settings


def _response(stop_reason="end_turn", text='{"ok": true}'):
    return SimpleNamespace(
        stop_reason=stop_reason,
        model="claude-opus-5-5",
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=1000,
            output_tokens=200,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )


@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    g = AnthropicLLM(Settings(llm_provider="anthropic"))
    g.captured = {}

    def fake_create(**kwargs):
        g.captured = kwargs
        return g.next_response

    g.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=fake_create)))
    return g


def _call(g):
    return g.complete_json(
        purpose="t",
        system="sys",
        content=[{"type": "text", "text": "x"}],
        schema={"type": "object"},
        payload={},
    )


def test_parses_json_and_tracks_cost(gateway):
    gateway.next_response = _response()
    data, call = _call(gateway)
    assert data == {"ok": True}
    assert call.input_tokens == 1000 and call.output_tokens == 200
    assert call.cost_usd == pytest.approx(1000 / 1e6 * 4 + 200 / 1e6 * 20)


def test_request_uses_structured_output_caching_and_fallbacks(gateway):
    gateway.next_response = _response()
    _call(gateway)
    req = gateway.captured
    assert req["model"] == "claude-opus-5-5"
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert req["fallbacks"] == "default"


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_bad_stop_reasons_raise(gateway, stop):
    gateway.next_response = _response(stop_reason=stop)
    with pytest.raises(LLMError):
        _call(gateway)


def test_invalid_json_raises(gateway):
    gateway.next_response = _response(text="not json")
    with pytest.raises(LLMError):
        _call(gateway)
