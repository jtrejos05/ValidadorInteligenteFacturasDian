# Intelligent DIAN Invoice Validator

This tool validates Colombian electronic invoices (*factura electrónica de venta*, DIAN, UBL 2.1) before an accounts-payable team pays them. Deterministic code handles everything that can be computed, and an LLM handles the few things only reading and judgment can do. A human decides whenever the system is unsure.

> **Python · FastAPI · Claude API · MCP · React + TypeScript · SQLite · GitHub Actions**

---

## 1. The problem

In Colombian AP teams, an analyst checks each supplier invoice before payment. Typical problems:

- **Tampered or miscalculated invoices.** The CUFE (the invoice's SHA-384 fingerprint) does not match the data.
- **Wrong NIT or check digit.** The IVA cannot be deducted, so the invoice has to be reissued.
- **Arithmetic and tax errors.** Line totals, IVA rates (19 / 5 / 0 %), or a payable amount that does not add up.
- **Numbering resolution issues.** An expired resolution, a number outside the authorized range, a wrong prefix, or another issuer's resolution.
- **Semantic errors.** Medicines or basic foods charged 19% IVA, or consulting billed at 0%. These are valid arithmetic but wrong tax treatment, and no simple rule catches them.
- **PDF vs XML mismatch.** People pay from the PDF, but the XML is the legal document.

A manual check takes several minutes per invoice and is error-prone. The goal is to auto-resolve the clear cases, approving the clean ones and rejecting the broken ones, and to send only the ambiguous ones to a person with a plain-language explanation.

## 2. Approach: choose the right intervention per check

The request "an agent that validates invoices" was treated as a hypothesis. Breaking the process down showed that most checks are exact computations. → [ADR 0001](docs/adr/0001-deterministic-core-llm-at-the-edges.md)

```
            ┌──────────────────────── deterministic ────────────────────────┐
 XML ──► parse (XXE-safe) ──► rules: structure · NIT DV · CUFE · totals ·    │
            │                 tax rates · dates · numbering resolution       │
            │                                   │                            │
 PDF/img ─► LLM extraction ──► cross-check vs XML (warning) ──┐              │
            │                                   │             ├─► decision ──┼─► LLM explanation
 lines ───► LLM semantic tax review (warning) ──┘             │   policy     │   (Spanish, for AP)
            └──────────────────────────────────────────────────┴──────────────┘
                                                                  │
                                    needs_review ──► human review queue (UI / API)
```

| Layer | What it does | Why this tool |
|---|---|---|
| **Rules** (`app/rules/`) | CUFE recomputation per Anexo Técnico 1.9, NIT check digit, totals, allowed rates, resolution range and validity, mandatory fields | Exact, free, instant, auditable |
| **LLM: semantic review** (`app/ai/tax_review.py`) | Does the IVA rate fit the product described? | Needs reading comprehension plus tax knowledge |
| **LLM: extraction** (`app/ai/extractor.py`) | Reads the PDF or image the supplier sent | Perception; layouts vary per supplier |
| **LLM: explanation** (`app/ai/explainer.py`) | Turns findings into next steps for an accountant | Language generation |
| **Policy** (`pipeline.decide`) | Rule error → reject · any warning → review · else approve | Must be predictable and auditable |
| **Human in the loop** | Review queue with approve/reject plus audit note | Final say on anything uncertain |

**Guardrails** ([ADR 0002](docs/adr/0002-ai-findings-are-warnings-human-in-the-loop.md))

- AI findings are capped at *warning*, so the model can escalate an invoice but can never reject or approve one.
- All model output is schema-constrained JSON.
- Invoice content is treated as untrusted data in every prompt, as a prompt-injection defense.
- The XML parser has external entities and network access disabled (XXE).
- Upload size and type limits are enforced.
- Validation degrades gracefully if the model is down.

## 3. Quickstart

Requirements: Python 3.11+ with [uv](https://docs.astral.sh/uv/), and Node 20+.

```bash
# Backend (http://127.0.0.1:8000, docs at /docs)
cd backend
uv sync
uv run uvicorn app.main:app --reload

# Frontend (http://localhost:5173), in another terminal
cd frontend
npm install
npm run dev
```

**No API key is needed.** Without one, the app uses a deterministic mock LLM, so the full demo works offline. To use Claude:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # or create backend/.env from .env.example
```

The UI ships **28 sample invoices**: valid ones, ones with each defect sown in, semantic cases, and PDF+XML cases. Pick one from the dropdown or download its XML/PDF.

### Live demo (Vercel)

**https://dian-validator.vercel.app** runs with the mock LLM, so anyone can try it at no cost.

It is deployed as two Vercel projects from this repo:

| Project | Root | What it is |
|---|---|---|
| `dian-validator` | `frontend/` | Vite static build. `vercel.json` rewrites `/api/*` to the API, so the app is same-origin and needs no CORS |
| `dian-validator-api` | `backend/` | FastAPI, auto-detected by Vercel (`app/main.py`), Python 3.12 |

Serverless functions have no persistent disk, so the API stores reports in Postgres when `DATABASE_URL` (or `POSTGRES_URL`) is set, for example Neon from the Vercel Marketplace. Without it, it falls back to SQLite (locally in `data/`, on Vercel in an ephemeral `/tmp`).

## 4. API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/validate` | Multipart: `xml` and/or `attachment` (PDF/PNG/JPG). Returns the report |
| `GET` | `/api/reports?review_status=pending` | History and review queue |
| `POST` | `/api/reports/{id}/review` | Human decision `{decision, note}` |
| `GET` | `/api/metrics` | Auto-resolution rate, AI cost and latency, top findings, business case |
| `GET` | `/api/samples` · `POST /api/samples/{name}/validate` | Demo data |

## 5. MCP server (agent integration)

The validator is also an MCP server, so agents (Claude Code, AP bots, n8n) can call it as tools. → [ADR 0004](docs/adr/0004-mcp-server-for-agent-integration.md)

```bash
claude mcp add dian-validator -- uv --directory /path/to/repo/backend run python mcp_server.py
```

Tools:

- `validate_invoice(xml, use_ai)`
- `run_dian_rules(xml)`
- `check_nit(nit, check_digit)`
- `recompute_cufe(xml, technical_key)`

## 6. Quality: tests and evals

```bash
cd backend
uv run pytest -q                      # 85 unit / integration tests
uv run python -m evals.run_evals      # offline evals with quality gates
uv run python -m evals.run_evals --live   # same evals against Claude
```

The eval set (`evals/cases.py`) is **28 labeled synthetic invoices**, each with known defects. The harness reports:

| Metric | Gate | What it protects |
|---|---|---|
| Rule precision / recall | 1.0 | Every sown defect is caught, with no false alarms |
| AI recall (semantic + PDF cases) | ≥ 0.66 | The model catches what rules cannot |
| AI false-positive rate | ≤ 0.10 | The model does not flood reviewers |
| Decision accuracy | ≥ 0.90 | End-to-end behavior |
| Cost and latency per invoice | Tracked | Unit economics |

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs lint, tests, offline evals and the frontend build on every push and PR. Live evals run on `main` when an `ANTHROPIC_API_KEY` secret is configured.

Note: the mock passes the AI evals by construction. Offline AI scores prove the plumbing; the live run measures the model ([ADR 0003](docs/adr/0003-llm-gateway-structured-outputs-and-mock.md)).

## 7. Observability and business case

Every LLM call is traced: purpose, model, input/output tokens, latency, estimated USD cost and errors. Traces are stored with each report and aggregated on the **Metrics** page:

- Share of invoices resolved without a human. This is the efficiency lever.
- AI cost per invoice. Typically one or two low-effort calls; zero when rules reject or nothing is found.
- Estimated analyst hours and COP saved. The assumptions are editable and shown on screen: `DIAN_MANUAL_MINUTES_PER_INVOICE` (default 6) and `DIAN_ANALYST_COST_COP_PER_HOUR` (default 35,000).

## 8. Repository layout

```
backend/
  app/
    rules/        deterministic DIAN checks (cufe, nit, totals, dates, structure)
    ai/           llm gateway + tax_review, extractor, explainer
    parsing/      hardened UBL 2.1 parser
    pipeline.py   orchestration + decision policy
    main.py       FastAPI
    synthetic.py  invoice generator with defect injection
  mcp_server.py   MCP tools
  evals/          labeled cases + harness
  tests/
frontend/         React + TypeScript (Vite)
docs/adr/         architecture decision records
```

## 9. Limitations and next steps

- **No XAdES signature check.** The XML digital signature is not verified yet; that would be the next deterministic rule. The CUFE check already detects data tampering when the technical key is known.
- **No live DIAN lookup.** Technical keys come from a local catalog (`app/data/resolutions.json`). In production they would come from the DIAN enablement service, and the CUFE status from the DIAN web service.
- **Partial document coverage.** Credit and debit notes (CUDE), INC/ICA edge cases, withholdings (*retenciones*), and foreign currency are partially covered.
- **Semantic tax review is advisory.** Colombian IVA rules have many exceptions; the review flags cases for a tax specialist and is not tax advice.
- **Synthetic eval data.** The next step is a sample of real, anonymized supplier invoices with labels from the AP team.
- **Integrations.** Possible next steps: an email inbox listener, an ERP push (SAP / Siigo) on approval, and webhooks on review decisions.
