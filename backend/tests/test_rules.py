import pytest

from app.parsing.ubl import InvoiceParseError, parse_invoice_xml
from app.rules import run_rules
from app.synthetic import build_invoice_xml
from evals.cases import CASES


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_rules_report_exactly_the_sown_defects(case, today):
    invoice = parse_invoice_xml(build_invoice_xml(case.spec))
    codes = {f.code for f in run_rules(invoice, today=today)}
    assert codes == case.rule_codes


def test_parser_rejects_non_invoice():
    with pytest.raises(InvoiceParseError):
        parse_invoice_xml("<CreditNote/>")


def test_parser_rejects_malformed_xml():
    with pytest.raises(InvoiceParseError):
        parse_invoice_xml("<Invoice><unclosed></Invoice>")


def test_parser_does_not_expand_external_entities(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET")
    xxe = f"""<?xml version="1.0"?>
<!DOCTYPE Invoice [<!ENTITY xxe SYSTEM "file:///{secret.as_posix()}">]>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>&xxe;</cbc:ID>
</Invoice>"""
    invoice = parse_invoice_xml(xxe)
    assert "TOP-SECRET" not in (invoice.number or "")


def test_missing_fields_are_reported_not_crashed(today):
    minimal = """<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"/>"""
    findings = run_rules(parse_invoice_xml(minimal), today=today)
    codes = {f.code for f in findings}
    assert {"MISSING_FIELD", "NO_LINES", "MISSING_RESOLUTION"} <= codes
