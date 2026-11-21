"""Parse a DIAN UBL 2.1 invoice XML into the normalized `Invoice` model.

Parsing is deliberately tolerant: missing fields become `None` so the rule engine
can report them as findings instead of crashing on the first problem.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from lxml import etree

from app.models import Invoice, InvoiceLine, NumberingRange, Party, TaxSubtotal

NS = {
    "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "sts": "dian:gov:co:facturaelectronica:Structures-2-1",
}

# Hardened parser: no external entities, no network access (XXE protection).
_PARSER = etree.XMLParser(
    resolve_entities=False, no_network=True, remove_blank_text=True, huge_tree=False
)


class InvoiceParseError(ValueError):
    """The document is not well-formed XML or not a UBL Invoice."""


def _text(node: etree._Element | None, path: str) -> str | None:
    if node is None:
        return None
    found = node.find(path, NS)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def _attr(node: etree._Element | None, path: str, attr: str) -> str | None:
    if node is None:
        return None
    found = node.find(path, NS)
    return None if found is None else found.get(attr)


def _dec(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _party(root: etree._Element, role: str) -> Party:
    party = root.find(f"cac:{role}/cac:Party", NS)
    if party is None:
        return Party()
    company_id = "cac:PartyTaxScheme/cbc:CompanyID"
    return Party(
        name=_text(party, "cac:PartyTaxScheme/cbc:RegistrationName")
        or _text(party, "cac:PartyName/cbc:Name"),
        nit=_text(party, company_id),
        check_digit=_attr(party, company_id, "schemeID"),
        id_scheme=_attr(party, company_id, "schemeName"),
    )


def _subtotals(parent: etree._Element) -> list[TaxSubtotal]:
    result = []
    for sub in parent.findall("cac:TaxTotal/cac:TaxSubtotal", NS):
        result.append(
            TaxSubtotal(
                tax_code=_text(sub, "cac:TaxCategory/cac:TaxScheme/cbc:ID") or "",
                taxable_amount=_dec(_text(sub, "cbc:TaxableAmount")) or Decimal("0"),
                tax_amount=_dec(_text(sub, "cbc:TaxAmount")) or Decimal("0"),
                percent=_dec(_text(sub, "cac:TaxCategory/cbc:Percent")) or Decimal("0"),
            )
        )
    return result


def parse_invoice_xml(content: bytes | str) -> Invoice:
    raw = content.encode("utf-8") if isinstance(content, str) else content
    try:
        root = etree.fromstring(raw, _PARSER)
    except etree.XMLSyntaxError as exc:
        raise InvoiceParseError(f"XML mal formado: {exc}") from exc

    if etree.QName(root).localname != "Invoice":
        raise InvoiceParseError(
            f"Se esperaba un documento UBL 'Invoice', se recibió '{etree.QName(root).localname}'"
        )

    control = root.find(
        "ext:UBLExtensions/ext:UBLExtension/ext:ExtensionContent/sts:DianExtensions/sts:InvoiceControl",
        NS,
    )
    numbering = NumberingRange(
        authorization=_text(control, "sts:InvoiceAuthorization"),
        prefix=_text(control, "sts:AuthorizedInvoices/sts:Prefix"),
        range_from=_int(_text(control, "sts:AuthorizedInvoices/sts:From")),
        range_to=_int(_text(control, "sts:AuthorizedInvoices/sts:To")),
        start_date=_date(_text(control, "sts:AuthorizationPeriod/cbc:StartDate")),
        end_date=_date(_text(control, "sts:AuthorizationPeriod/cbc:EndDate")),
    )

    lines = []
    for line in root.findall("cac:InvoiceLine", NS):
        lines.append(
            InvoiceLine(
                id=_text(line, "cbc:ID") or "",
                description=_text(line, "cac:Item/cbc:Description") or "",
                quantity=_dec(_text(line, "cbc:InvoicedQuantity")) or Decimal("0"),
                unit_price=_dec(_text(line, "cac:Price/cbc:PriceAmount")) or Decimal("0"),
                line_extension_amount=_dec(_text(line, "cbc:LineExtensionAmount")) or Decimal("0"),
                taxes=_subtotals(line),
            )
        )

    totals = root.find("cac:LegalMonetaryTotal", NS)
    return Invoice(
        source="xml",
        ubl_version=_text(root, "cbc:UBLVersionID"),
        customization_id=_text(root, "cbc:CustomizationID"),
        profile_execution_id=_text(root, "cbc:ProfileExecutionID"),
        number=_text(root, "cbc:ID"),
        cufe=_text(root, "cbc:UUID"),
        issue_date=_date(_text(root, "cbc:IssueDate")),
        issue_time=_text(root, "cbc:IssueTime"),
        due_date=_date(_text(root, "cbc:DueDate")),
        invoice_type_code=_text(root, "cbc:InvoiceTypeCode"),
        currency=_text(root, "cbc:DocumentCurrencyCode"),
        supplier=_party(root, "AccountingSupplierParty"),
        customer=_party(root, "AccountingCustomerParty"),
        lines=lines,
        tax_totals=_subtotals(root),
        line_extension_amount=_dec(_text(totals, "cbc:LineExtensionAmount")),
        tax_exclusive_amount=_dec(_text(totals, "cbc:TaxExclusiveAmount")),
        tax_inclusive_amount=_dec(_text(totals, "cbc:TaxInclusiveAmount")),
        allowance_total=_dec(_text(totals, "cbc:AllowanceTotalAmount")) or Decimal("0"),
        charge_total=_dec(_text(totals, "cbc:ChargeTotalAmount")) or Decimal("0"),
        prepaid_amount=_dec(_text(totals, "cbc:PrepaidAmount")) or Decimal("0"),
        payable_amount=_dec(_text(totals, "cbc:PayableAmount")),
        numbering=numbering,
    )
