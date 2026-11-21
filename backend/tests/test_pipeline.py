import pytest

from app.ai.llm import LLMError
from app.models import Decision, FindingSource, Severity
from app.pipeline import decide, validate
from app.samples import load_samples
from app.synthetic import build_invoice_xml
from evals.cases import CASES


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_decisions_on_labeled_cases(case, llm, today):
    report = validate(xml=build_invoice_xml(case.spec).encode(), llm=llm, today=today)
    assert report.decision.value == case.expected_decision
    ai_codes = {f.code for f in report.findings if f.source == FindingSource.AI}
    assert case.ai_codes <= ai_codes
    assert report.explanation is not None


def test_ai_findings_never_reject_on_their_own():
    from app.models import Finding

    ai_only = [
        Finding(
            code="TAX_RATE_SUSPICIOUS",
            severity=Severity.WARNING,
            source=FindingSource.AI,
            message="x",
            confidence=0.99,
        )
    ]
    assert decide(ai_only)[0] == Decision.NEEDS_REVIEW


def test_semantic_review_skipped_when_rules_already_reject(llm, today):
    case = next(c for c in CASES if c.name == "cufe_tampered")
    report = validate(xml=build_invoice_xml(case.spec).encode(), llm=llm, today=today)
    assert "tax_review" not in {c.purpose for c in report.llm_calls}


def test_invalid_xml_is_rejected_gracefully(llm):
    report = validate(xml=b"not xml", llm=llm)
    assert report.decision == Decision.REJECTED
    assert report.findings[0].code == "INVALID_XML"


@pytest.mark.parametrize(
    ("name", "expected_code"),
    [
        ("pdf_matches_xml", None),
        ("pdf_total_altered", "PDF_XML_MISMATCH"),
        ("pdf_only", "XML_MISSING"),
    ],
)
def test_pdf_flows(name, expected_code, llm, today):
    sample = load_samples()[name]
    report = validate(
        xml=sample.xml,
        attachment=sample.pdf,
        attachment_type="application/pdf",
        llm=llm,
        today=today,
    )
    assert report.decision.value == sample.expected_decision
    codes = {f.code for f in report.findings}
    if expected_code:
        assert expected_code in codes


class FailingLLM:
    name = "failing"
    model = "none"

    def complete_json(self, **kwargs):
        raise LLMError("service unavailable")


def test_llm_outage_degrades_gracefully(today):
    """If the model is down, deterministic validation still works and nothing crashes."""
    case = next(c for c in CASES if c.name == "valid_office_supplies")
    report = validate(xml=build_invoice_xml(case.spec).encode(), llm=FailingLLM(), today=today)
    assert report.decision == Decision.APPROVED
    assert "AI_REVIEW_SKIPPED" in {f.code for f in report.findings}
    assert report.explanation is not None
