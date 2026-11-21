"""Synthetic DIAN invoice generator.

Builds realistic UBL 2.1 invoices (with a correct CUFE) and lets callers sow
specific defects. Used for unit tests, the eval dataset and the demo samples —
no real taxpayer data is ever needed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from app.parsing.ubl import parse_invoice_xml
from app.rules.base import money
from app.rules.cufe import compute_cufe
from app.rules.nit import nit_check_digit

_CATALOG = json.loads(
    (Path(__file__).parent / "data" / "resolutions.json").read_text(encoding="utf-8")
)
_CUFE_PLACEHOLDER = "__CUFE__"


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class Line:
    description: str
    quantity: Decimal
    unit_price: Decimal
    iva_percent: Decimal = Decimal("19")
    amount_override: Decimal | None = None  # sow LINE_AMOUNT_MISMATCH
    tax_override: Decimal | None = None  # sow TAX_CALC_MISMATCH


@dataclass
class InvoiceSpec:
    number: str = "SETP990000101"
    issue_date: date = date(2026, 10, 15)
    issue_time: str = "10:30:00-05:00"
    due_date: date | None = date(2026, 11, 14)
    profile: str = "1"
    ubl_version: str = "UBL 2.1"
    invoice_type: str = "01"
    currency: str = "COP"
    authorization: str = "18760000001"
    prefix: str = "SETP"
    range_from: int = 990000000
    range_to: int = 995000000
    period_start: date = date(2025, 1, 1)
    period_end: date = date(2027, 12, 31)
    supplier_name: str = "Distribuciones Andinas S.A.S."
    supplier_nit: str = "900373115"
    supplier_dv: str | None = None  # None = correct DV
    customer_name: str = "Comercializadora del Caribe Ltda."
    customer_nit: str = "800197268"
    customer_dv: str | None = None
    customer_scheme: str = "31"
    lines: list[Line] = field(
        default_factory=lambda: [
            Line("Resma papel carta 75g", Decimal("10"), Decimal("18500")),
            Line("Tóner impresora láser", Decimal("2"), Decimal("245000")),
        ]
    )
    subtotal_delta: Decimal = Decimal("0")  # sow LINES_SUM_MISMATCH
    payable_delta: Decimal = Decimal("0")  # sow PAYABLE_MISMATCH
    cufe_override: str | None = None  # sow CUFE_MISMATCH / CUFE_FORMAT
    omit_cufe: bool = False
    technical_key: str | None = None  # None = take it from the catalog


def build_invoice_xml(spec: InvoiceSpec) -> str:
    line_rows = []
    groups: dict[Decimal, list[Decimal]] = {}  # rate -> [taxable, tax]
    lines_sum = Decimal("0")
    for i, ln in enumerate(spec.lines, start=1):
        amount = _q(
            ln.amount_override if ln.amount_override is not None else ln.quantity * ln.unit_price
        )
        tax = _q(ln.tax_override if ln.tax_override is not None else amount * ln.iva_percent / 100)
        lines_sum += amount
        g = groups.setdefault(ln.iva_percent, [Decimal("0"), Decimal("0")])
        g[0] += amount
        g[1] += tax
        line_rows.append(
            f"""  <cac:InvoiceLine>
    <cbc:ID>{i}</cbc:ID>
    <cbc:InvoicedQuantity unitCode="94">{ln.quantity}</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="{spec.currency}">{money(amount)}</cbc:LineExtensionAmount>
    <cac:TaxTotal>
      <cbc:TaxAmount currencyID="{spec.currency}">{money(tax)}</cbc:TaxAmount>
      <cac:TaxSubtotal>
        <cbc:TaxableAmount currencyID="{spec.currency}">{money(amount)}</cbc:TaxableAmount>
        <cbc:TaxAmount currencyID="{spec.currency}">{money(tax)}</cbc:TaxAmount>
        <cac:TaxCategory>
          <cbc:Percent>{ln.iva_percent:.2f}</cbc:Percent>
          <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
        </cac:TaxCategory>
      </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:Item><cbc:Description>{escape(ln.description)}</cbc:Description></cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="{spec.currency}">{money(ln.unit_price)}</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>"""
        )

    total_tax = sum((g[1] for g in groups.values()), Decimal("0"))
    subtotals = "\n".join(
        f"""    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="{spec.currency}">{money(g[0])}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="{spec.currency}">{money(g[1])}</cbc:TaxAmount>
      <cac:TaxCategory>
        <cbc:Percent>{rate:.2f}</cbc:Percent>
        <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>"""
        for rate, g in sorted(groups.items())
    )
    tax_inclusive = lines_sum + total_tax
    payable = tax_inclusive + spec.payable_delta

    supplier_dv = spec.supplier_dv or nit_check_digit(spec.supplier_nit)
    customer_dv = spec.customer_dv or (
        nit_check_digit(spec.customer_nit) if spec.customer_scheme == "31" else ""
    )
    due = f"\n  <cbc:DueDate>{spec.due_date.isoformat()}</cbc:DueDate>" if spec.due_date else ""
    uuid = (
        ""
        if spec.omit_cufe
        else f'\n  <cbc:UUID schemeID="{spec.profile}" schemeName="CUFE-SHA384">{_CUFE_PLACEHOLDER}</cbc:UUID>'
    )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
         xmlns:sts="dian:gov:co:facturaelectronica:Structures-2-1">
  <ext:UBLExtensions>
    <ext:UBLExtension>
      <ext:ExtensionContent>
        <sts:DianExtensions>
          <sts:InvoiceControl>
            <sts:InvoiceAuthorization>{spec.authorization}</sts:InvoiceAuthorization>
            <sts:AuthorizationPeriod>
              <cbc:StartDate>{spec.period_start.isoformat()}</cbc:StartDate>
              <cbc:EndDate>{spec.period_end.isoformat()}</cbc:EndDate>
            </sts:AuthorizationPeriod>
            <sts:AuthorizedInvoices>
              <sts:Prefix>{spec.prefix}</sts:Prefix>
              <sts:From>{spec.range_from}</sts:From>
              <sts:To>{spec.range_to}</sts:To>
            </sts:AuthorizedInvoices>
          </sts:InvoiceControl>
        </sts:DianExtensions>
      </ext:ExtensionContent>
    </ext:UBLExtension>
  </ext:UBLExtensions>
  <cbc:UBLVersionID>{spec.ubl_version}</cbc:UBLVersionID>
  <cbc:CustomizationID>10</cbc:CustomizationID>
  <cbc:ProfileID>DIAN 2.1: Factura Electrónica de Venta</cbc:ProfileID>
  <cbc:ProfileExecutionID>{spec.profile}</cbc:ProfileExecutionID>
  <cbc:ID>{spec.number}</cbc:ID>{uuid}
  <cbc:IssueDate>{spec.issue_date.isoformat()}</cbc:IssueDate>
  <cbc:IssueTime>{spec.issue_time}</cbc:IssueTime>{due}
  <cbc:InvoiceTypeCode>{spec.invoice_type}</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>{spec.currency}</cbc:DocumentCurrencyCode>
  <cbc:LineCountNumeric>{len(spec.lines)}</cbc:LineCountNumeric>
  <cac:AccountingSupplierParty>
    <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
    <cac:Party>
      <cac:PartyName><cbc:Name>{escape(spec.supplier_name)}</cbc:Name></cac:PartyName>
      <cac:PartyTaxScheme>
        <cbc:RegistrationName>{escape(spec.supplier_name)}</cbc:RegistrationName>
        <cbc:CompanyID schemeAgencyID="195" schemeID="{supplier_dv}" schemeName="31">{spec.supplier_nit}</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
      </cac:PartyTaxScheme>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
    <cac:Party>
      <cac:PartyName><cbc:Name>{escape(spec.customer_name)}</cbc:Name></cac:PartyName>
      <cac:PartyTaxScheme>
        <cbc:RegistrationName>{escape(spec.customer_name)}</cbc:RegistrationName>
        <cbc:CompanyID schemeAgencyID="195" schemeID="{customer_dv}" schemeName="{spec.customer_scheme}">{spec.customer_nit}</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
      </cac:PartyTaxScheme>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="{spec.currency}">{money(total_tax)}</cbc:TaxAmount>
{subtotals}
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="{spec.currency}">{money(lines_sum + spec.subtotal_delta)}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="{spec.currency}">{money(lines_sum)}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="{spec.currency}">{money(tax_inclusive)}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="{spec.currency}">{money(payable)}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
{chr(10).join(line_rows)}
</Invoice>
"""
    if spec.omit_cufe:
        return xml
    if spec.cufe_override is not None:
        return xml.replace(_CUFE_PLACEHOLDER, spec.cufe_override)
    key = spec.technical_key or _CATALOG.get(spec.authorization, {}).get(
        "technical_key", "sin-clave-tecnica"
    )
    # The issuer's software computes the CUFE over whatever data it emitted, so
    # arithmetic defects do not, by themselves, break the CUFE.
    invoice = parse_invoice_xml(xml.replace(_CUFE_PLACEHOLDER, "0" * 96))
    return xml.replace(_CUFE_PLACEHOLDER, compute_cufe(invoice, key))
