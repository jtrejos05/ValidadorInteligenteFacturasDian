# ADR 0002: AI findings are warnings; humans decide

- Status: Accepted
- Date: 2026-11-21

## Context

Accounts payable is a regulated, money-moving process. Two error types have different costs:

- **False reject.** A good supplier invoice is blocked. This damages the relationship and adds late-payment friction.
- **False approve.** A wrong or fraudulent invoice is paid. This causes direct financial loss and tax exposure, because a wrongly charged IVA cannot be taken as a deductible.

LLM judgments are probabilistic and can be manipulated: line descriptions and PDFs are third-party content, so they are a prompt-injection surface.

## Decision

- Findings carry a `source` (`rule` or `ai`). AI findings are capped at `WARNING`.
- Decision policy:
  - Any rule `ERROR` leads to `REJECTED`.
  - Any `WARNING` leads to `NEEDS_REVIEW`.
  - Otherwise the invoice is `APPROVED`.
- The model can escalate an invoice to a human, but it can never reject or approve one on its own.
- `NEEDS_REVIEW` invoices go to a review queue (UI + API) where a person approves or rejects them with a note. The note is stored with the report for audit.
- Extraction from PDF is AI. A PDF/XML mismatch is therefore a warning, even though the comparison itself is deterministic, because the extracted value might be the thing that is wrong.
- Prompts mark invoice content as untrusted data and tell the model to ignore instructions inside it. Outputs are schema-constrained JSON, so injected text cannot change the response shape.
- AI findings below a confidence threshold (0.6) are dropped to limit reviewer noise. The eval tracks the false-positive rate.

## Consequences

- The worst a bad model output can do is send an invoice to a human.
- The share of invoices auto-resolved (approved or rejected without a human) becomes the key efficiency metric, and AI false positives directly reduce it. That is why both are tracked in evals and on the metrics page.
- If the model is down, validation still runs. The semantic review is skipped (`AI_REVIEW_SKIPPED`) and the deterministic decision stands.
