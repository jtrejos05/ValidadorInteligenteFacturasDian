# ADR 0003: One LLM gateway, structured outputs, and an offline mock

- Status: Accepted
- Date: 2026-11-21

## Context

We need LLM calls that are reliable to parse, observable (tokens, latency, cost), testable in CI without an API key, and swappable if the client mandates another provider.

## Decision

- **One seam.** Every model call goes through `LLMClient.complete_json(purpose, system, content, schema, payload)` in `backend/app/ai/llm.py`. No other module imports the SDK.
- **Structured outputs.** Each task defines a strict JSON schema (`additionalProperties: false`) passed via `output_config.format`, so responses always parse.
- **Model.** The default is `claude-opus-5-5` at `effort: low`, because these are classification and extraction tasks. Both are configurable through env vars, and the effort level is something to tune against the live eval.
- **Caching.** System prompts are static per task and marked with `cache_control` so repeated calls reuse the cached prefix.
- **Refusals.** Server-side fallbacks (`fallbacks: "default"`) are enabled. `refusal` and `max_tokens` stop reasons raise `LLMError`, and the pipeline degrades gracefully.
- **Trace.** Each call returns an `LLMCall` with tokens, latency, estimated cost and errors. Traces are stored with the report and aggregated on `/api/metrics`.
- **MockLLM.** A deterministic implementation registers one handler per task (keyword heuristics, a regex extractor over the PDF text layer, template explanations). Provider selection is `auto` (Claude if credentials exist, otherwise the mock), `anthropic` or `mock`.

## Consequences

- CI runs the full pipeline and evals with no secrets and no flakiness.
- **The mock passes the AI evals by construction.** Offline AI scores prove the plumbing, not the model. Real AI quality comes from `run_evals --live`, which CI runs on `main` when a key is configured.
- Swapping providers means writing one class.
