# ADR 0001: Deterministic core, LLM at the edges

- Status: Accepted
- Date: 2026-11-21

## Context

The request was for an "intelligent invoice validator." Read literally, that becomes "send the XML to an LLM and ask if it is valid." Most of what makes a DIAN invoice valid, though, is computable:

| Check | Nature | Right tool |
|---|---|---|
| CUFE = SHA-384 of 15 concatenated fields | Exact hash | Code |
| NIT check digit (modulo 11) | Exact arithmetic | Code |
| Line, tax and payable totals | Exact arithmetic | Code |
| Allowed IVA/INC rates | Catalog lookup | Code |
| Numbering resolution: prefix, range, validity period | Lookup + comparison | Code |
| Does a 19% rate make sense for "Acetaminofén 500 mg"? | Reading + domain knowledge | LLM |
| What does the PDF the supplier sent actually say? | Perception (document/vision) | LLM |
| Explain the result to an accountant | Language generation | LLM |

An LLM is slower, costs money per call, cannot be audited line by line, and can be wrong about a SHA-384 or a modulo-11 sum. Code is free, instant, exact and testable for those checks.

## Decision

- All computable checks are deterministic rules (`backend/app/rules/`), each a pure function with unit tests. They are the source of truth.
- The LLM is used only where no rule can do the job: semantic tax review, PDF/image extraction, and explanations.
- The final decision (approve / reject / review) comes from a deterministic policy (`pipeline.decide`), not from the model.

## Consequences

- The deterministic layer can be validated to 100% precision and recall on the labeled set. CI enforces it.
- With rules only, the system works fully offline and costs nothing (`use_ai=False` in the MCP tool, or no API key).
- LLM cost stays small: one or two calls per invoice. The semantic review is skipped when rules already reject, and the explanation call is skipped when there is nothing to explain.
- Adding a new DIAN rule is ordinary software work: a function, a test and an eval case.
