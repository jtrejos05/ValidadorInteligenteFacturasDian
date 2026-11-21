from decimal import Decimal

from app.parsing.ubl import parse_invoice_xml
from app.rules.cufe import compute_cufe, cufe_input_string
from app.synthetic import InvoiceSpec, build_invoice_xml

KEY = "fc8eac422eba16e22ffd8c6f94b3f40a6e38162c"


def _invoice():
    return parse_invoice_xml(build_invoice_xml(InvoiceSpec()))


def test_input_string_follows_annex_order():
    inv = _invoice()
    s = cufe_input_string(inv, KEY)
    assert s == (
        "SETP990000101"
        "2026-10-15"
        "10:30:00-05:00"
        "675000.00"
        "01"
        "128250.00"
        "04"
        "0.00"
        "03"
        "0.00"
        "803250.00"
        "900373115"
        "800197268" + KEY + "1"
    )


def test_cufe_is_sha384_hex():
    cufe = compute_cufe(_invoice(), KEY)
    assert len(cufe) == 96
    assert all(c in "0123456789abcdef" for c in cufe)


def test_generated_invoice_carries_matching_cufe():
    inv = _invoice()
    assert inv.cufe == compute_cufe(inv, KEY)


def test_any_change_in_signed_data_changes_cufe():
    inv = _invoice()
    original = compute_cufe(inv, KEY)
    inv.payable_amount += Decimal("1")
    assert compute_cufe(inv, KEY) != original
