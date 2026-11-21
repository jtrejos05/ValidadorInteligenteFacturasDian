"""Labeled eval cases.

Each case is a synthetic invoice with exactly the defects we sowed, plus the
finding codes a correct validator must report. `rule_codes` are checked against
the deterministic engine; `ai_codes` are what the LLM review is expected to flag
(semantic issues no rule can see, e.g. a tax rate that does not fit the product).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal as D

from app.synthetic import InvoiceSpec, Line

# Fixed "today" so date rules are reproducible.
EVAL_TODAY = date(2026, 11, 21)


@dataclass
class Case:
    name: str
    description: str
    spec: InvoiceSpec
    rule_codes: set[str] = field(default_factory=set)
    ai_codes: set[str] = field(default_factory=set)
    expected_decision: str = "approved"


def _spec(**kw) -> InvoiceSpec:
    return InvoiceSpec(**kw)


CASES: list[Case] = [
    # --- valid invoices -------------------------------------------------------------
    Case("valid_office_supplies", "Factura válida de papelería", _spec()),
    Case(
        "valid_mixed_rates",
        "Factura válida con IVA 19% y 5%",
        _spec(
            number="SETP990000102",
            lines=[
                Line("Servicio de mantenimiento preventivo", D("1"), D("450000")),
                Line("Medicina prepagada plan básico", D("1"), D("120000"), D("5")),
            ],
        ),
    ),
    Case(
        "valid_other_supplier",
        "Factura válida de otro emisor y resolución",
        _spec(
            number="FEV1500",
            authorization="18764000002",
            prefix="FEV",
            range_from=1,
            range_to=50000,
            supplier_name="Alimentos La Sabana S.A.",
            supplier_nit="860001022",
            customer_name="Juan Pérez",
            customer_nit="1020304050",
            customer_scheme="13",
            lines=[Line("Caja de galletas surtidas x 24", D("5"), D("32000"))],
        ),
    ),
    # --- integrity --------------------------------------------------------------------
    Case(
        "cufe_tampered",
        "CUFE que no corresponde a los datos (factura alterada)",
        _spec(number="SETP990000103", cufe_override="a" * 96),
        {"CUFE_MISMATCH"},
        expected_decision="rejected",
    ),
    Case(
        "cufe_bad_format",
        "CUFE con formato inválido",
        _spec(number="SETP990000104", cufe_override="ABC-123"),
        {"CUFE_FORMAT"},
        expected_decision="rejected",
    ),
    Case(
        "missing_cufe",
        "Factura sin CUFE",
        _spec(number="SETP990000105", omit_cufe=True),
        {"MISSING_FIELD"},
        expected_decision="rejected",
    ),
    Case(
        "unknown_resolution",
        "Resolución sin clave técnica conocida: CUFE no verificable",
        _spec(number="SETP990000106", authorization="18769999999"),
        {"CUFE_NOT_VERIFIABLE"},
        expected_decision="needs_review",
    ),
    # --- identity ---------------------------------------------------------------------
    Case(
        "supplier_dv_wrong",
        "Dígito de verificación del emisor incorrecto",
        _spec(number="SETP990000107", supplier_dv="9"),
        {"SUPPLIER_DV_INVALID"},
        expected_decision="rejected",
    ),
    Case(
        "customer_dv_wrong",
        "Dígito de verificación del adquiriente incorrecto",
        _spec(number="SETP990000108", customer_dv="1"),
        {"CUSTOMER_DV_INVALID"},
        expected_decision="rejected",
    ),
    Case(
        "resolution_other_supplier",
        "Usa la resolución de numeración de otro emisor",
        _spec(
            number="FEV1501",
            authorization="18764000002",
            prefix="FEV",
            range_from=1,
            range_to=50000,
        ),
        {"RESOLUTION_SUPPLIER_MISMATCH"},
        expected_decision="rejected",
    ),
    # --- arithmetic -------------------------------------------------------------------
    Case(
        "iva_rate_16",
        "Tarifa de IVA derogada (16%)",
        _spec(
            number="SETP990000109",
            lines=[Line("Silla ergonómica de oficina", D("3"), D("380000"), D("16"))],
        ),
        {"INVALID_TAX_RATE"},
        expected_decision="rejected",
    ),
    Case(
        "line_tax_wrong",
        "IVA de una línea mal calculado",
        _spec(
            number="SETP990000110",
            lines=[Line("Monitor 27 pulgadas", D("2"), D("890000"), tax_override=D("300000"))],
        ),
        {"TAX_CALC_MISMATCH"},
        expected_decision="rejected",
    ),
    Case(
        "line_amount_wrong",
        "Cantidad × precio no coincide con el valor de la línea",
        _spec(
            number="SETP990000111",
            lines=[Line("Teclado inalámbrico", D("4"), D("95000"), amount_override=D("400000"))],
        ),
        {"LINE_AMOUNT_MISMATCH"},
        expected_decision="rejected",
    ),
    Case(
        "payable_wrong",
        "Valor a pagar inflado",
        _spec(number="SETP990000112", payable_delta=D("150000")),
        {"PAYABLE_MISMATCH"},
        expected_decision="rejected",
    ),
    Case(
        "subtotal_wrong",
        "Subtotal del encabezado no cuadra con las líneas",
        _spec(number="SETP990000113", subtotal_delta=D("50000")),
        {"LINES_SUM_MISMATCH", "TAX_INCLUSIVE_MISMATCH"},
        expected_decision="rejected",
    ),
    # --- dates & numbering ------------------------------------------------------------
    Case(
        "number_out_of_range",
        "Consecutivo fuera del rango autorizado",
        _spec(number="SETP995000001"),
        {"NUMBER_OUT_OF_RANGE"},
        expected_decision="rejected",
    ),
    Case(
        "wrong_prefix",
        "Prefijo distinto al autorizado",
        _spec(number="FACT990000114"),
        {"PREFIX_MISMATCH"},
        expected_decision="rejected",
    ),
    Case(
        "expired_resolution",
        "Emitida con la resolución vencida",
        _spec(number="SETP990000115", period_start=date(2024, 1, 1), period_end=date(2025, 12, 31)),
        {"OUTSIDE_RESOLUTION_PERIOD"},
        expected_decision="rejected",
    ),
    Case(
        "future_date",
        "Fecha de emisión en el futuro",
        _spec(number="SETP990000116", issue_date=date(2027, 3, 1), due_date=date(2027, 3, 31)),
        {"FUTURE_ISSUE_DATE"},
        expected_decision="rejected",
    ),
    Case(
        "due_before_issue",
        "Vencimiento anterior a la emisión",
        _spec(number="SETP990000117", due_date=date(2026, 9, 1)),
        {"DUE_BEFORE_ISSUE"},
        expected_decision="rejected",
    ),
    # --- structure --------------------------------------------------------------------
    Case(
        "ubl_20",
        "Versión UBL antigua",
        _spec(number="SETP990000118", ubl_version="UBL 2.0"),
        {"UBL_VERSION"},
        expected_decision="rejected",
    ),
    Case(
        "test_environment",
        "Emitida en ambiente de pruebas",
        _spec(number="SETP990000119", profile="2"),
        {"TEST_ENVIRONMENT"},
        expected_decision="needs_review",
    ),
    # --- semantic (AI) — all rules pass, but something does not make sense ------------
    Case(
        "ai_medicine_full_iva",
        "Medicamento facturado con IVA 19% (normalmente excluido)",
        _spec(
            number="SETP990000120",
            lines=[Line("Acetaminofén 500 mg caja x 100 tabletas", D("20"), D("12000"))],
        ),
        ai_codes={"TAX_RATE_SUSPICIOUS"},
        expected_decision="needs_review",
    ),
    Case(
        "ai_basic_food_full_iva",
        "Alimento de la canasta básica con IVA 19%",
        _spec(
            number="SETP990000121",
            lines=[
                Line("Arroz blanco bolsa 5 kg", D("30"), D("21000")),
                Line("Huevos AA cubeta x 30", D("15"), D("16500")),
            ],
        ),
        ai_codes={"TAX_RATE_SUSPICIOUS"},
        expected_decision="needs_review",
    ),
    Case(
        "ai_consulting_zero_iva",
        "Servicio de consultoría con IVA 0%",
        _spec(
            number="SETP990000122",
            lines=[Line("Honorarios consultoría tributaria octubre", D("1"), D("6500000"), D("0"))],
        ),
        ai_codes={"TAX_RATE_SUSPICIOUS"},
        expected_decision="needs_review",
    ),
]
