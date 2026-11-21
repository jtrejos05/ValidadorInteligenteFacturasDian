"""Validation pipeline: deterministic core, LLM at the edges, human in the loop.

    XML ──► parse ──► rules (source of truth) ──┐
                                                ├─► decision policy ─► explanation
    PDF ──► LLM extraction ──► cross-check ─────┤      (deterministic)     (LLM)
    lines ─► LLM semantic tax review ───────────┘

Decision policy:
    any rule ERROR            -> REJECTED      (deterministic evidence)
    any WARNING (rule or AI)  -> NEEDS_REVIEW  (a human decides)
    otherwise                 -> APPROVED

AI findings are capped at WARNING, so the model can send an invoice to a human
but can never reject (or approve) one on its own.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.ai import explainer, extractor, tax_review
from app.ai.llm import LLMClient, LLMError
from app.config import get_settings
from app.models import (
    Decision,
    Finding,
    FindingSource,
    Invoice,
    LLMCall,
    Party,
    Severity,
    ValidationReport,
)
from app.parsing.ubl import InvoiceParseError, parse_invoice_xml
from app.rules import run_rules

MIN_EXTRACTION_CONFIDENCE = 0.7


def decide(findings: list[Finding]) -> tuple[Decision, str]:
    errors = [
        f for f in findings if f.severity == Severity.ERROR and f.source == FindingSource.RULE
    ]
    warnings = [f for f in findings if f.severity in (Severity.WARNING, Severity.ERROR)]
    if errors:
        return Decision.REJECTED, f"{len(errors)} error(es) de validación DIAN"
    if warnings:
        return Decision.NEEDS_REVIEW, f"{len(warnings)} alerta(s) requieren revisión humana"
    return Decision.APPROVED, "Sin hallazgos"


def _info(code: str, message: str) -> Finding:
    return Finding(code=code, severity=Severity.INFO, source=FindingSource.AI, message=message)


def validate(
    *,
    xml: bytes | None = None,
    attachment: bytes | None = None,
    attachment_type: str | None = None,
    filename: str | None = None,
    llm: LLMClient,
    today: date | None = None,
    run_ai: bool = True,
) -> ValidationReport:
    if xml is None and attachment is None:
        raise ValueError("Se requiere el XML o la representación gráfica (PDF/imagen)")

    settings = get_settings()
    started = time.perf_counter()
    findings: list[Finding] = []
    calls: list[LLMCall] = []
    invoice = Invoice()

    # 1. Deterministic core ------------------------------------------------------------
    if xml is not None:
        try:
            invoice = parse_invoice_xml(xml)
            findings += run_rules(invoice, today=today)
        except InvoiceParseError as exc:
            findings.append(
                Finding(code="INVALID_XML", severity=Severity.ERROR, message=str(exc), field="xml")
            )

    # 2. Graphic representation (PDF / image) -------------------------------------------
    if attachment is not None and run_ai:
        try:
            extracted, call = extractor.extract_fields(attachment, attachment_type or "", llm)
            calls.append(call)
            if xml is not None:
                findings += extractor.compare_with_xml(
                    extracted, invoice, Decimal(str(settings.amount_tolerance))
                )
            else:
                invoice = _invoice_from_extraction(extracted, attachment_type)
                findings.append(
                    Finding(
                        code="XML_MISSING",
                        severity=Severity.WARNING,
                        message="Solo se recibió la representación gráfica. El documento legal es el "
                        "XML; solicítelo al proveedor para validar CUFE, totales y resolución.",
                        field="xml",
                    )
                )
            if float(extracted.get("confidence") or 0) < MIN_EXTRACTION_CONFIDENCE:
                findings.append(
                    Finding(
                        code="EXTRACTION_LOW_CONFIDENCE",
                        severity=Severity.WARNING,
                        source=FindingSource.AI,
                        message="La lectura del PDF/imagen tuvo baja confianza.",
                        confidence=float(extracted.get("confidence") or 0),
                    )
                )
        except LLMError as exc:
            findings.append(
                Finding(
                    code="EXTRACTION_FAILED",
                    severity=Severity.WARNING,
                    source=FindingSource.AI,
                    message=f"No se pudo leer la representación gráfica: {exc}",
                )
            )

    # 3. Semantic review — skipped when rules already reject (no value, only cost) ----
    already_rejected = decide(findings)[0] == Decision.REJECTED
    if run_ai and invoice.lines and not already_rejected:
        try:
            ai_findings, call = tax_review.review_tax_rates(invoice, llm)
            findings += ai_findings
            if call:
                calls.append(call)
        except LLMError as exc:
            findings.append(_info("AI_REVIEW_SKIPPED", f"Revisión semántica no disponible: {exc}"))

    # 4. Decision (deterministic) + explanation (LLM) ----------------------------------
    decision, reason = decide(findings)
    explanation = None
    if run_ai:
        try:
            explanation, call = explainer.explain(invoice, findings, decision, llm)
            if call:
                calls.append(call)
        except LLMError:
            from app.ai.llm import MockLLM

            explanation, _ = explainer.explain(invoice, findings, decision, MockLLM())

    return ValidationReport(
        id=uuid.uuid4().hex[:12],
        created_at=datetime.now(UTC),
        filename=filename,
        invoice=invoice,
        findings=findings,
        decision=decision,
        decision_reason=reason,
        explanation=explanation,
        llm_calls=calls,
        duration_ms=int((time.perf_counter() - started) * 1000),
        review_status="pending" if decision == Decision.NEEDS_REVIEW else None,
    )


def _invoice_from_extraction(data: dict, media_type: str | None) -> Invoice:
    def dec(key: str) -> Decimal | None:
        return extractor._dec(data.get(key))

    issue = data.get("issue_date")
    try:
        issue_date = date.fromisoformat(issue) if issue else None
    except ValueError:
        issue_date = None
    return Invoice(
        source="pdf" if media_type == "application/pdf" else "image",
        number=data.get("number"),
        cufe=data.get("cufe"),
        issue_date=issue_date,
        supplier=Party(name=data.get("supplier_name"), nit=data.get("supplier_nit")),
        customer=Party(nit=data.get("customer_nit")),
        line_extension_amount=dec("subtotal"),
        payable_amount=dec("payable_amount"),
    )
