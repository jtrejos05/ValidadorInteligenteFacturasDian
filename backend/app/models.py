"""Domain models: the normalized invoice, findings and the validation report."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class Party(BaseModel):
    name: str | None = None
    nit: str | None = None  # identification number without check digit
    check_digit: str | None = None  # DV as declared in the document
    id_scheme: str | None = None  # "31" = NIT, "13" = cédula, ...


class TaxSubtotal(BaseModel):
    tax_code: str  # "01" IVA, "04" INC, "03" ICA
    taxable_amount: Decimal
    tax_amount: Decimal
    percent: Decimal


class InvoiceLine(BaseModel):
    id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_extension_amount: Decimal
    taxes: list[TaxSubtotal] = Field(default_factory=list)


class NumberingRange(BaseModel):
    authorization: str | None = None
    prefix: str | None = None
    range_from: int | None = None
    range_to: int | None = None
    start_date: date | None = None
    end_date: date | None = None


class Invoice(BaseModel):
    """Normalized view of a DIAN invoice, independent of the source (XML or PDF)."""

    source: str = "xml"  # "xml" | "pdf" | "image"
    ubl_version: str | None = None
    customization_id: str | None = None
    profile_execution_id: str | None = None  # 1 = production, 2 = test
    number: str | None = None
    cufe: str | None = None
    issue_date: date | None = None
    issue_time: str | None = None
    due_date: date | None = None
    invoice_type_code: str | None = None
    currency: str | None = None
    supplier: Party = Field(default_factory=Party)
    customer: Party = Field(default_factory=Party)
    lines: list[InvoiceLine] = Field(default_factory=list)
    tax_totals: list[TaxSubtotal] = Field(default_factory=list)
    line_extension_amount: Decimal | None = None
    tax_exclusive_amount: Decimal | None = None
    tax_inclusive_amount: Decimal | None = None
    allowance_total: Decimal = Decimal("0")
    charge_total: Decimal = Decimal("0")
    prepaid_amount: Decimal = Decimal("0")
    payable_amount: Decimal | None = None
    numbering: NumberingRange = Field(default_factory=NumberingRange)


class Severity(StrEnum):
    ERROR = "error"  # the invoice would be rejected by DIAN / must not be paid
    WARNING = "warning"  # suspicious, needs a human to look at it
    INFO = "info"


class FindingSource(StrEnum):
    RULE = "rule"  # deterministic check
    AI = "ai"  # LLM judgment, never auto-rejects on its own


class Finding(BaseModel):
    code: str  # stable identifier, e.g. "CUFE_MISMATCH"
    severity: Severity
    source: FindingSource = FindingSource.RULE
    message: str
    field: str | None = None
    expected: str | None = None
    actual: str | None = None
    confidence: float | None = None  # only for AI findings


class Decision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class LLMCall(BaseModel):
    purpose: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    error: str | None = None


class Explanation(BaseModel):
    summary: str
    actions: list[str] = Field(default_factory=list)
    risk_level: str = "low"  # low | medium | high


class ValidationReport(BaseModel):
    id: str
    created_at: datetime
    filename: str | None = None
    invoice: Invoice
    findings: list[Finding]
    decision: Decision
    decision_reason: str
    explanation: Explanation | None = None
    llm_calls: list[LLMCall] = Field(default_factory=list)
    duration_ms: int = 0
    review_status: str | None = None  # pending | approved | rejected (human decision)
    reviewer_note: str | None = None
