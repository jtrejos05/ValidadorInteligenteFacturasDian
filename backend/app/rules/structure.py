"""Mandatory fields and catalog values."""

from __future__ import annotations

from app.models import Finding, Severity
from app.rules.base import RuleContext, finding, rule

REQUIRED_FIELDS = {
    "ubl_version": "Versión UBL (cbc:UBLVersionID)",
    "customization_id": "Tipo de operación (cbc:CustomizationID)",
    "profile_execution_id": "Ambiente (cbc:ProfileExecutionID)",
    "number": "Número de factura (cbc:ID)",
    "cufe": "CUFE (cbc:UUID)",
    "issue_date": "Fecha de emisión (cbc:IssueDate)",
    "issue_time": "Hora de emisión (cbc:IssueTime)",
    "invoice_type_code": "Tipo de factura (cbc:InvoiceTypeCode)",
    "currency": "Moneda (cbc:DocumentCurrencyCode)",
    "payable_amount": "Valor a pagar (cbc:PayableAmount)",
    "line_extension_amount": "Subtotal (cbc:LineExtensionAmount)",
}

# Anexo técnico, tabla 13.1.3: 01 venta, 02 exportación, 03 contingencia facturador,
# 04 contingencia DIAN.
INVOICE_TYPES = {"01", "02", "03", "04"}


@rule("structure")
def check_structure(ctx: RuleContext) -> list[Finding]:
    inv = ctx.invoice
    out: list[Finding] = []

    for attr, label in REQUIRED_FIELDS.items():
        if getattr(inv, attr) in (None, ""):
            out.append(
                finding(
                    "MISSING_FIELD",
                    Severity.ERROR,
                    f"Falta el campo obligatorio: {label}.",
                    field=attr,
                )
            )
    if not inv.supplier.nit:
        out.append(
            finding(
                "MISSING_FIELD", Severity.ERROR, "Falta el NIT del emisor.", field="supplier.nit"
            )
        )
    if not inv.customer.nit:
        out.append(
            finding(
                "MISSING_FIELD",
                Severity.ERROR,
                "Falta la identificación del adquiriente.",
                field="customer.nit",
            )
        )
    if not inv.lines:
        out.append(
            finding(
                "NO_LINES", Severity.ERROR, "La factura no tiene líneas de detalle.", field="lines"
            )
        )

    if inv.ubl_version and inv.ubl_version != "UBL 2.1":
        out.append(
            finding(
                "UBL_VERSION",
                Severity.ERROR,
                "La DIAN exige UBL 2.1.",
                field="ubl_version",
                expected="UBL 2.1",
                actual=inv.ubl_version,
            )
        )
    if inv.invoice_type_code and inv.invoice_type_code not in INVOICE_TYPES:
        out.append(
            finding(
                "INVALID_INVOICE_TYPE",
                Severity.ERROR,
                "Tipo de factura no válido según la tabla 13.1.3 del anexo técnico.",
                field="invoice_type_code",
                expected=", ".join(sorted(INVOICE_TYPES)),
                actual=inv.invoice_type_code,
            )
        )
    if inv.profile_execution_id and inv.profile_execution_id not in {"1", "2"}:
        out.append(
            finding(
                "INVALID_ENVIRONMENT",
                Severity.ERROR,
                "El ambiente debe ser 1 (producción) o 2 (pruebas).",
                field="profile_execution_id",
                actual=inv.profile_execution_id,
            )
        )
    elif inv.profile_execution_id == "2":
        out.append(
            finding(
                "TEST_ENVIRONMENT",
                Severity.WARNING,
                "La factura fue emitida en ambiente de pruebas; no tiene validez fiscal.",
                field="profile_execution_id",
                actual="2",
            )
        )
    if inv.currency and inv.currency != "COP":
        out.append(
            finding(
                "FOREIGN_CURRENCY",
                Severity.WARNING,
                "La factura no está en COP; verifique la tasa de cambio reportada.",
                field="currency",
                actual=inv.currency,
            )
        )
    return out
