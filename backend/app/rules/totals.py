"""Arithmetic consistency: lines, taxes and monetary totals."""

from __future__ import annotations

from decimal import Decimal

from app.models import Finding, Severity
from app.rules.base import RuleContext, finding, money, rule

# Allowed rates (%) per tax scheme. 01 = IVA, 04 = INC (impuesto nacional al consumo).
ALLOWED_RATES = {
    "01": {Decimal("0"), Decimal("5"), Decimal("19")},
    "04": {Decimal("2"), Decimal("4"), Decimal("8"), Decimal("16")},
}
TAX_NAMES = {"01": "IVA", "04": "INC", "03": "ICA"}


def _off(a: Decimal, b: Decimal, tol: Decimal) -> bool:
    return abs(a - b) > tol


@rule("line_amounts")
def check_lines(ctx: RuleContext) -> list[Finding]:
    out = []
    for line in ctx.invoice.lines:
        expected = line.quantity * line.unit_price
        if _off(expected, line.line_extension_amount, ctx.tolerance):
            out.append(
                finding(
                    "LINE_AMOUNT_MISMATCH",
                    Severity.ERROR,
                    f"Línea {line.id}: cantidad × precio unitario no coincide con el valor de la línea.",
                    field=f"lines[{line.id}].line_extension_amount",
                    expected=money(expected),
                    actual=money(line.line_extension_amount),
                )
            )
    return out


@rule("tax_rates")
def check_tax_rates(ctx: RuleContext) -> list[Finding]:
    out = []
    subtotals = [(f"lines[{ln.id}]", t) for ln in ctx.invoice.lines for t in ln.taxes]
    subtotals += [("tax_totals", t) for t in ctx.invoice.tax_totals]
    for where, tax in subtotals:
        name = TAX_NAMES.get(tax.tax_code, tax.tax_code)
        allowed = ALLOWED_RATES.get(tax.tax_code)
        if allowed is not None and tax.percent not in allowed:
            out.append(
                finding(
                    "INVALID_TAX_RATE",
                    Severity.ERROR,
                    f"Tarifa de {name} no permitida ({tax.percent}%).",
                    field=f"{where}.percent",
                    expected=", ".join(f"{r}%" for r in sorted(allowed)),
                    actual=f"{tax.percent}%",
                )
            )
        expected = (tax.taxable_amount * tax.percent / Decimal("100")).quantize(Decimal("0.01"))
        if _off(expected, tax.tax_amount, ctx.tolerance):
            out.append(
                finding(
                    "TAX_CALC_MISMATCH",
                    Severity.ERROR,
                    f"El {name} no corresponde a base × tarifa.",
                    field=f"{where}.tax_amount",
                    expected=money(expected),
                    actual=money(tax.tax_amount),
                )
            )
    return out


@rule("monetary_totals")
def check_totals(ctx: RuleContext) -> list[Finding]:
    inv = ctx.invoice
    out: list[Finding] = []
    tol = ctx.tolerance
    if inv.line_extension_amount is None or inv.payable_amount is None:
        return out  # reported by the structure rule

    lines_sum = sum((ln.line_extension_amount for ln in inv.lines), Decimal("0"))
    if inv.lines and _off(lines_sum, inv.line_extension_amount, tol):
        out.append(
            finding(
                "LINES_SUM_MISMATCH",
                Severity.ERROR,
                "La suma de las líneas no coincide con el subtotal de la factura.",
                field="line_extension_amount",
                expected=money(lines_sum),
                actual=money(inv.line_extension_amount),
            )
        )

    # Header tax totals must match the sum of line-level taxes, per tax scheme.
    for code in {t.tax_code for ln in inv.lines for t in ln.taxes} | {
        t.tax_code for t in inv.tax_totals
    }:
        line_tax = sum(
            (t.tax_amount for ln in inv.lines for t in ln.taxes if t.tax_code == code), Decimal("0")
        )
        header_tax = sum((t.tax_amount for t in inv.tax_totals if t.tax_code == code), Decimal("0"))
        if _off(line_tax, header_tax, tol):
            out.append(
                finding(
                    "TAX_TOTAL_MISMATCH",
                    Severity.ERROR,
                    f"El total de {TAX_NAMES.get(code, code)} del encabezado no coincide con la suma de las líneas.",
                    field="tax_totals",
                    expected=money(line_tax),
                    actual=money(header_tax),
                )
            )

    total_tax = sum((t.tax_amount for t in inv.tax_totals), Decimal("0"))
    expected_inclusive = inv.line_extension_amount + total_tax
    if inv.tax_inclusive_amount is not None and _off(
        expected_inclusive, inv.tax_inclusive_amount, tol
    ):
        out.append(
            finding(
                "TAX_INCLUSIVE_MISMATCH",
                Severity.ERROR,
                "El total con impuestos no es igual a subtotal + impuestos.",
                field="tax_inclusive_amount",
                expected=money(expected_inclusive),
                actual=money(inv.tax_inclusive_amount),
            )
        )

    base = inv.tax_inclusive_amount if inv.tax_inclusive_amount is not None else expected_inclusive
    expected_payable = base - inv.allowance_total + inv.charge_total - inv.prepaid_amount
    if _off(expected_payable, inv.payable_amount, tol):
        out.append(
            finding(
                "PAYABLE_MISMATCH",
                Severity.ERROR,
                "El valor a pagar no cuadra con total + cargos − descuentos − anticipos.",
                field="payable_amount",
                expected=money(expected_payable),
                actual=money(inv.payable_amount),
            )
        )
    return out
