"""Demo samples: the labeled eval cases, rendered as XML (+ PDF for some)."""

from __future__ import annotations

from dataclasses import dataclass

from app.parsing.ubl import parse_invoice_xml
from app.pdfgen import invoice_pdf
from app.synthetic import build_invoice_xml


@dataclass
class Sample:
    name: str
    description: str
    xml: bytes | None
    pdf: bytes | None
    expected_decision: str


# PDF variants: name -> (base case, values printed differently on the PDF)
_PDF_VARIANTS = {
    "pdf_matches_xml": ("valid_office_supplies", {}, "XML + PDF coherentes"),
    "pdf_total_altered": (
        "valid_office_supplies",
        {"payable_amount": "903.250,00"},
        "El PDF muestra un total mayor que el XML (posible fraude)",
    ),
}


def load_samples() -> dict[str, Sample]:
    from evals.cases import CASES  # local import: evals is a sibling package

    by_name = {c.name: c for c in CASES}
    samples = {
        c.name: Sample(
            c.name, c.description, build_invoice_xml(c.spec).encode(), None, c.expected_decision
        )
        for c in CASES
    }
    for name, (base, overrides, description) in _PDF_VARIANTS.items():
        xml = build_invoice_xml(by_name[base].spec).encode()
        pdf = invoice_pdf(parse_invoice_xml(xml), overrides)
        decision = "approved" if not overrides else "needs_review"
        samples[name] = Sample(name, description, xml, pdf, decision)
    samples["pdf_only"] = Sample(
        "pdf_only",
        "Solo llega el PDF, sin el XML",
        None,
        samples["pdf_matches_xml"].pdf,
        "needs_review",
    )
    return samples
