"""Deterministic DIAN rule engine."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.config import get_settings
from app.models import Finding, Invoice
from app.rules import cufe, dates, nit, structure, totals  # noqa: F401  (registers rules)
from app.rules.base import RuleContext, load_resolutions, registered_rules
from app.rules.cufe import compute_cufe
from app.rules.nit import nit_check_digit

__all__ = ["run_rules", "compute_cufe", "nit_check_digit"]


def run_rules(
    invoice: Invoice, today: date | None = None, skip: set[str] | None = None
) -> list[Finding]:
    settings = get_settings()
    ctx = RuleContext(
        invoice=invoice,
        today=today or date.today(),
        resolutions=load_resolutions(settings.resolutions_path),
        tolerance=Decimal(str(settings.amount_tolerance)),
    )
    findings: list[Finding] = []
    for name, fn in registered_rules():
        if skip and name in skip:
            continue
        findings.extend(fn(ctx))
    return findings
