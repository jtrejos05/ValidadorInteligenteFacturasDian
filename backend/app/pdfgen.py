"""Tiny dependency-free PDF writer for the invoice's graphic representation.

Only used to produce demo/eval PDFs from synthetic invoices. It writes a single
page of text with a standard Helvetica font, so it has a real text layer.
"""

from __future__ import annotations

from decimal import Decimal

from app.models import Invoice


def _co(amount: Decimal | None) -> str:
    """Colombian format: 1.234.567,50"""
    s = f"{(amount or Decimal('0')):,.2f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def invoice_lines(inv: Invoice, overrides: dict[str, str] | None = None) -> list[tuple[int, str]]:
    """(font size, text) rows. `overrides` lets evals print a different value than the XML."""
    o = overrides or {}
    iva = sum((t.tax_amount for t in inv.tax_totals if t.tax_code == "01"), Decimal("0"))
    rows = [
        (16, f"Factura electrónica de venta No. {o.get('number', inv.number)}"),
        (10, f"Emisor: {inv.supplier.name}"),
        (10, f"Emisor NIT: {o.get('supplier_nit', inv.supplier.nit)}-{inv.supplier.check_digit}"),
        (10, f"Adquiriente: {inv.customer.name}"),
        (10, f"Adquiriente NIT: {inv.customer.nit}"),
        (10, f"Fecha de emisión: {inv.issue_date}"),
        (10, f"Resolución DIAN No. {inv.numbering.authorization}"),
        (10, ""),
        (11, "Detalle"),
    ]
    for ln in inv.lines:
        rows.append(
            (9, f"{ln.id}. {ln.description}  x{ln.quantity}  ${_co(ln.line_extension_amount)}")
        )
    rows += [
        (10, ""),
        (10, f"Subtotal: ${o.get('subtotal', _co(inv.line_extension_amount))}"),
        (10, f"IVA: ${o.get('iva_total', _co(iva))}"),
        (12, f"Total a pagar: ${o.get('payable_amount', _co(inv.payable_amount))}"),
        (10, ""),
        (7, f"CUFE: {o.get('cufe', inv.cufe)}"),
    ]
    return rows


def render_pdf(rows: list[tuple[int, str]]) -> bytes:
    y = 800
    ops = ["BT"]
    for size, text in rows:
        ops.append(f"/F1 {size} Tf 1 0 0 1 40 {y} Tm ({_escape(text)}) Tj")
        y -= size + 8
    ops.append("ET")
    stream = "\n".join(ops).encode("cp1252", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


def invoice_pdf(inv: Invoice, overrides: dict[str, str] | None = None) -> bytes:
    return render_pdf(invoice_lines(inv, overrides))
