# ADR 0004: Expose the validator as an MCP server

- Status: Accepted
- Date: 2026-11-21

## Context

Invoice validation rarely lives alone. It is a step inside larger flows: an AP agent reading a mailbox, an ERP integration, an n8n workflow, or an analyst asking Claude Code "why was this invoice rejected?". Those consumers are increasingly agents.

## Decision

Ship `backend/mcp_server.py`, built on the official MCP Python SDK, with four tools:

| Tool | Deterministic | Purpose |
|---|---|---|
| `validate_invoice(xml, use_ai)` | Optional AI | Full report with decision and explanation |
| `run_dian_rules(xml)` | Yes | Only the rule engine |
| `check_nit(nit, check_digit)` | Yes | DV computation and verification |
| `recompute_cufe(xml, technical_key)` | Yes | Hash recomputation |

Small, exact tools let an agent get facts it should not guess (hashes, check digits) and keep its own reasoning for the rest. The REST API serves the UI and classic integrations, and both share the same pipeline.

## Consequences

- Any MCP client (Claude Code, Claude Desktop, agent frameworks) can use the validator without custom glue.
- The tool surface is part of the public contract. Tool names and descriptions are written for a model reader and must be kept stable.
