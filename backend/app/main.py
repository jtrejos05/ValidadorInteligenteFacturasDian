"""HTTP API (FastAPI)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from app.ai.llm import LLMClient, get_llm
from app.config import Settings, get_settings
from app.models import Decision, ValidationReport
from app.pipeline import validate
from app.samples import Sample, load_samples
from app.store import ReportStore, make_store

app = FastAPI(
    title="Validador Inteligente de Facturas DIAN",
    version="0.1.0",
    description="Valida facturas electrónicas UBL 2.1 con reglas deterministas y IA donde aporta.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_ATTACHMENTS = {"application/pdf", "image/png", "image/jpeg", "image/webp"}


@lru_cache
def get_store() -> ReportStore:
    settings = get_settings()
    return make_store(settings.database_url, settings.db_path)


@lru_cache
def _llm() -> LLMClient:
    return get_llm()


def get_llm_dep() -> LLMClient:
    return _llm()


@lru_cache
def _samples() -> dict[str, Sample]:
    return load_samples()


async def _read_limited(file: UploadFile, settings: Settings) -> bytes:
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Archivo mayor a {settings.max_upload_mb} MB")
    return data


@app.get("/api/health")
def health(llm: LLMClient = Depends(get_llm_dep)) -> dict:
    return {"status": "ok", "llm_provider": llm.name, "llm_model": llm.model}


@app.post("/api/validate", response_model=ValidationReport)
async def validate_invoice(
    xml: UploadFile | None = File(None, description="Factura electrónica UBL 2.1 (XML)"),
    attachment: UploadFile | None = File(None, description="Representación gráfica (PDF/imagen)"),
    llm: LLMClient = Depends(get_llm_dep),
    store: ReportStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> ValidationReport:
    if xml is None and attachment is None:
        raise HTTPException(400, "Envíe el XML de la factura, su PDF, o ambos")
    xml_bytes = await _read_limited(xml, settings) if xml else None
    att_bytes = await _read_limited(attachment, settings) if attachment else None
    att_type = attachment.content_type if attachment else None
    if attachment and att_type not in ALLOWED_ATTACHMENTS:
        raise HTTPException(415, f"Tipo de archivo no soportado: {att_type}")
    filename = (xml.filename if xml else None) or (attachment.filename if attachment else None)
    report = validate(
        xml=xml_bytes, attachment=att_bytes, attachment_type=att_type, filename=filename, llm=llm
    )
    store.save(report)
    return report


@app.get("/api/samples")
def list_samples() -> list[dict]:
    return [
        {
            "name": s.name,
            "description": s.description,
            "has_xml": s.xml is not None,
            "has_pdf": s.pdf is not None,
            "expected_decision": s.expected_decision,
        }
        for s in _samples().values()
    ]


@app.get("/api/samples/{name}/{kind}")
def download_sample(name: str, kind: Literal["xml", "pdf"]) -> Response:
    sample = _samples().get(name)
    data = getattr(sample, kind, None) if sample else None
    if data is None:
        raise HTTPException(404, "Muestra no encontrada")
    media = "application/xml" if kind == "xml" else "application/pdf"
    return Response(
        data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}.{kind}"'},
    )


@app.post("/api/samples/{name}/validate", response_model=ValidationReport)
def validate_sample(
    name: str,
    llm: LLMClient = Depends(get_llm_dep),
    store: ReportStore = Depends(get_store),
) -> ValidationReport:
    sample = _samples().get(name)
    if not sample:
        raise HTTPException(404, "Muestra no encontrada")
    report = validate(
        xml=sample.xml,
        attachment=sample.pdf,
        attachment_type="application/pdf" if sample.pdf else None,
        filename=f"{name}.xml" if sample.xml else f"{name}.pdf",
        llm=llm,
    )
    store.save(report)
    return report


@app.get("/api/reports", response_model=list[ValidationReport])
def list_reports(
    review_status: str | None = None, store: ReportStore = Depends(get_store)
) -> list[ValidationReport]:
    return store.list(review_status=review_status)


@app.get("/api/reports/{report_id}", response_model=ValidationReport)
def get_report(report_id: str, store: ReportStore = Depends(get_store)) -> ValidationReport:
    report = store.get(report_id)
    if not report:
        raise HTTPException(404, "Reporte no encontrado")
    return report


class ReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = None


@app.post("/api/reports/{report_id}/review", response_model=ValidationReport)
def review_report(
    report_id: str, body: ReviewRequest, store: ReportStore = Depends(get_store)
) -> ValidationReport:
    report = store.get(report_id)
    if not report:
        raise HTTPException(404, "Reporte no encontrado")
    if report.decision != Decision.NEEDS_REVIEW:
        raise HTTPException(409, "Solo las facturas en revisión manual aceptan decisión humana")
    report.review_status = body.decision
    report.reviewer_note = body.note
    store.save(report)
    return report


@app.get("/api/metrics")
def metrics(
    store: ReportStore = Depends(get_store), settings: Settings = Depends(get_settings)
) -> dict:
    reports = store.all()
    total = len(reports)
    by_decision = {d.value: sum(1 for r in reports if r.decision == d) for d in Decision}
    calls = [c for r in reports for c in r.llm_calls]
    auto = by_decision["approved"] + by_decision["rejected"]
    cost = sum(c.cost_usd for c in calls)
    minutes_saved = auto * settings.manual_minutes_per_invoice
    finding_counts: dict[str, int] = {}
    for r in reports:
        for f in r.findings:
            finding_counts[f.code] = finding_counts.get(f.code, 0) + 1
    return {
        "invoices": total,
        "by_decision": by_decision,
        "auto_resolution_rate": round(auto / total, 3) if total else 0,
        "pending_reviews": sum(1 for r in reports if r.review_status == "pending"),
        "avg_duration_ms": round(sum(r.duration_ms for r in reports) / total) if total else 0,
        "llm": {
            "calls": len(calls),
            "errors": sum(1 for c in calls if c.error),
            "input_tokens": sum(c.input_tokens for c in calls),
            "output_tokens": sum(c.output_tokens for c in calls),
            "cost_usd": round(cost, 4),
            "cost_per_invoice_usd": round(cost / total, 5) if total else 0,
            "avg_latency_ms": round(sum(c.latency_ms for c in calls) / len(calls)) if calls else 0,
        },
        "top_findings": sorted(finding_counts.items(), key=lambda kv: -kv[1])[:8],
        "business_case": {
            "assumption_manual_minutes_per_invoice": settings.manual_minutes_per_invoice,
            "assumption_analyst_cost_cop_per_hour": settings.analyst_cost_cop_per_hour,
            "estimated_hours_saved": round(minutes_saved / 60, 2),
            "estimated_cop_saved": round(minutes_saved / 60 * settings.analyst_cost_cop_per_hour),
        },
    }
