"""CUFE (Código Único de Factura Electrónica) recomputation.

Per the DIAN technical annex (Anexo Técnico Factura Electrónica de Venta v1.9):

    CUFE = SHA-384(NumFac + FecFac + HorFac + ValFac
                   + CodImp1 + ValImp1 + CodImp2 + ValImp2 + CodImp3 + ValImp3
                   + ValTot + NitFE + NumAdq + ClTec + TipoAmbiente)

where CodImp1/2/3 are "01" (IVA), "04" (INC) and "03" (ICA), and every amount
uses two decimals with a dot separator.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal

from app.models import Finding, Invoice, Severity
from app.rules.base import RuleContext, finding, money, rule

_CUFE_RE = re.compile(r"^[0-9a-f]{96}$")
_TAX_ORDER = ("01", "04", "03")


def _tax_total(invoice: Invoice, code: str) -> Decimal:
    return sum((t.tax_amount for t in invoice.tax_totals if t.tax_code == code), Decimal("0"))


def cufe_input_string(invoice: Invoice, technical_key: str) -> str:
    parts = [
        invoice.number or "",
        invoice.issue_date.isoformat() if invoice.issue_date else "",
        invoice.issue_time or "",
        money(invoice.line_extension_amount),
    ]
    for code in _TAX_ORDER:
        parts += [code, money(_tax_total(invoice, code))]
    parts += [
        money(invoice.payable_amount),
        invoice.supplier.nit or "",
        invoice.customer.nit or "",
        technical_key,
        invoice.profile_execution_id or "",
    ]
    return "".join(parts)


def compute_cufe(invoice: Invoice, technical_key: str) -> str:
    return hashlib.sha384(cufe_input_string(invoice, technical_key).encode("utf-8")).hexdigest()


@rule("cufe")
def check_cufe(ctx: RuleContext) -> list[Finding]:
    inv = ctx.invoice
    if not inv.cufe:
        return []  # reported by the structure rule
    if not _CUFE_RE.match(inv.cufe):
        return [
            finding(
                "CUFE_FORMAT",
                Severity.ERROR,
                "El CUFE debe ser un hash SHA-384 de 96 caracteres hexadecimales en minúscula.",
                field="cufe",
                actual=inv.cufe,
            )
        ]
    resolution = ctx.resolutions.get(inv.numbering.authorization or "")
    if not resolution or not resolution.get("technical_key"):
        return [
            finding(
                "CUFE_NOT_VERIFIABLE",
                Severity.WARNING,
                "No se encontró la clave técnica de la resolución de numeración; "
                "el CUFE no se pudo recalcular.",
                field="numbering.authorization",
                actual=inv.numbering.authorization,
            )
        ]
    expected = compute_cufe(inv, resolution["technical_key"])
    if expected != inv.cufe:
        return [
            finding(
                "CUFE_MISMATCH",
                Severity.ERROR,
                "El CUFE no coincide con el recalculado a partir de los datos de la factura. "
                "La factura pudo ser alterada después de firmada o se calculó mal.",
                field="cufe",
                expected=expected,
                actual=inv.cufe,
            )
        ]
    return []
