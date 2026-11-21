"""Dates and numbering resolution (rango de numeración autorizado)."""

from __future__ import annotations

import re

from app.models import Finding, Severity
from app.rules.base import RuleContext, finding, rule


@rule("dates")
def check_dates(ctx: RuleContext) -> list[Finding]:
    inv = ctx.invoice
    out: list[Finding] = []
    if inv.issue_date and inv.issue_date > ctx.today:
        out.append(
            finding(
                "FUTURE_ISSUE_DATE",
                Severity.ERROR,
                "La fecha de emisión está en el futuro.",
                field="issue_date",
                actual=inv.issue_date.isoformat(),
            )
        )
    if inv.issue_date and inv.due_date and inv.due_date < inv.issue_date:
        out.append(
            finding(
                "DUE_BEFORE_ISSUE",
                Severity.ERROR,
                "La fecha de vencimiento es anterior a la fecha de emisión.",
                field="due_date",
                actual=inv.due_date.isoformat(),
            )
        )
    return out


@rule("numbering_resolution")
def check_numbering(ctx: RuleContext) -> list[Finding]:
    inv = ctx.invoice
    num = inv.numbering
    out: list[Finding] = []
    if not num.authorization:
        return [
            finding(
                "MISSING_RESOLUTION",
                Severity.ERROR,
                "La factura no informa la resolución de numeración (sts:InvoiceControl).",
                field="numbering.authorization",
            )
        ]

    if inv.issue_date and num.start_date and num.end_date:
        if not (num.start_date <= inv.issue_date <= num.end_date):
            out.append(
                finding(
                    "OUTSIDE_RESOLUTION_PERIOD",
                    Severity.ERROR,
                    "La factura se emitió fuera de la vigencia de la resolución de numeración.",
                    field="issue_date",
                    expected=f"{num.start_date} a {num.end_date}",
                    actual=inv.issue_date.isoformat(),
                )
            )

    if inv.number:
        prefix = num.prefix or ""
        if prefix and not inv.number.startswith(prefix):
            out.append(
                finding(
                    "PREFIX_MISMATCH",
                    Severity.ERROR,
                    "El número de la factura no usa el prefijo autorizado.",
                    field="number",
                    expected=prefix,
                    actual=inv.number,
                )
            )
        match = re.search(r"(\d+)$", inv.number)
        if match and num.range_from is not None and num.range_to is not None:
            consecutive = int(match.group(1))
            if not (num.range_from <= consecutive <= num.range_to):
                out.append(
                    finding(
                        "NUMBER_OUT_OF_RANGE",
                        Severity.ERROR,
                        "El consecutivo está fuera del rango autorizado por la DIAN.",
                        field="number",
                        expected=f"{num.range_from}-{num.range_to}",
                        actual=str(consecutive),
                    )
                )

    known = ctx.resolutions.get(num.authorization)
    if known and inv.supplier.nit and known.get("supplier_nit") not in (None, inv.supplier.nit):
        out.append(
            finding(
                "RESOLUTION_SUPPLIER_MISMATCH",
                Severity.ERROR,
                "La resolución de numeración pertenece a otro emisor.",
                field="numbering.authorization",
                expected=known.get("supplier_nit"),
                actual=inv.supplier.nit,
            )
        )
    return out
