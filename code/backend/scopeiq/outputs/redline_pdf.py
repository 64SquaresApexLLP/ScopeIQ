"""Red-marked copy of the CD PDF: each sheet that has redlines gets numbered red markup boxes, a REDLINE
stamp and a delta revision tag; a summary sheet listing every redline (with its discrepancy and the
governing source) is added at the front. The original drawing is never modified."""
from __future__ import annotations

import io
import textwrap
from datetime import date
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color, red
from reportlab.pdfgen import canvas

from scopeiq.common.logging import get_logger, log_call
from scopeiq.domain import Redline

log = get_logger(__name__)
SHEET_PAGE = {"T-1": 0, "A-2": 1, "A-3": 2, "A-4": 3, "E-1": 4}
RED = Color(0.85, 0.05, 0.05)


def _overlay(w: float, h: float, items: list[tuple[int, Redline]], stamp: str) -> PdfReader:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.setStrokeColor(RED)
    c.setFillColor(RED)
    # stamp
    c.setLineWidth(2)
    c.rect(w * 0.56, h * 0.90, w * 0.24, h * 0.07)
    c.setFont("Helvetica-Bold", max(10, h * 0.025))
    c.drawString(w * 0.57, h * 0.935, "REDLINE")
    c.setFont("Helvetica", max(6, h * 0.011))
    c.drawString(w * 0.57, h * 0.91, stamp)
    # numbered markup boxes, white-backed so they stay legible over linework, stacked in the lower middle
    fs = max(6.0, h * 0.0125)
    x0, box_w = w * 0.40, w * 0.40
    y = h * 0.47

    def wrap(text: str, font: str, size: float, width: float) -> list[str]:
        out, cur = [], ""
        for word in text.split():
            trial = f"{cur} {word}".strip()
            if c.stringWidth(trial, font, size) <= width:
                cur = trial
            else:
                out.append(cur)
                cur = word
        return out + ([cur] if cur else [])

    for n, r in items:
        lines = wrap(r.markup, "Helvetica", fs, box_w - 30)
        ref_line = f"ref {r.disc_id} | was: {r.change_from[:36]} -> now: {r.change_to[:36]}"
        bh = (len(lines) + 1) * fs * 1.3 + 8
        c.setFillColor(Color(1, 1, 1))
        c.setLineWidth(1.4)
        c.rect(x0, y - bh, box_w, bh, stroke=1, fill=1)
        c.setFillColor(RED)
        c.circle(x0 + 11, y - 11, 8, stroke=1, fill=0)
        c.setFont("Helvetica-Bold", fs)
        c.drawCentredString(x0 + 11, y - 11 - fs / 3, str(n))
        c.setFont("Helvetica", fs)
        ty = y - fs * 1.5
        for ln in lines:
            c.drawString(x0 + 24, ty, ln)
            ty -= fs * 1.3
        c.setFont("Helvetica-Oblique", fs * 0.8)
        c.drawString(x0 + 24, ty, ref_line if c.stringWidth(ref_line, "Helvetica-Oblique", fs * 0.8) < box_w - 30 else ref_line[:90])
        y -= bh + 6
        if y < h * 0.06:
            break
    c.save()
    buf.seek(0)
    return PdfReader(buf)


def _summary_page(w: float, h: float, site_id: str, doc_rev: str, redlines: list[tuple[int, Redline]], stamp: str) -> PdfReader:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.setFillColor(RED)
    c.setStrokeColor(RED)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(40, h - 60, f"REDLINE SUMMARY - {site_id} CD {doc_rev}")
    c.setFont("Helvetica", 10)
    c.drawString(40, h - 80, stamp)
    c.setFillColor(Color(0, 0, 0))
    y = h - 115
    c.setFont("Helvetica-Bold", 9)
    for x, t in ((40, "#"), (65, "SHEET"), (110, "MARKUP"), (w - 330, "FROM"), (w - 200, "TO"), (w - 90, "STATUS")):
        c.drawString(x, y, t)
    c.setFont("Helvetica", 8.5)
    for n, r in redlines:
        lines = textwrap.wrap(r.markup, width=int((w - 330 - 120) / 4.4)) or [""]
        if y - 14 * len(lines) < 40:
            break
        y -= 16
        c.drawString(40, y, str(n))
        c.drawString(65, y, r.sheet)
        for i, ln in enumerate(lines):
            c.drawString(110, y - i * 11, ln)
        c.drawString(w - 330, y, r.change_from[:24])
        c.drawString(w - 200, y, r.change_to[:22])
        c.drawString(w - 90, y, r.status)
        y -= 11 * (len(lines) - 1)
    c.save()
    buf.seek(0)
    return PdfReader(buf)


@log_call()
def write_redlined_pdf(cd_pdf: Path, out_path: Path, redlines: list[Redline], *, site_id: str, prepared_by: str = "ScopeIQ") -> Path | None:
    cd_redlines = [r for r in redlines if r.doc_type == "CD"]
    if not cd_redlines:
        return None
    reader = PdfReader(str(cd_pdf))
    writer = PdfWriter()
    stamp = f"{prepared_by} - {date.today().isoformat()} - {len(cd_redlines)} markup(s) - status per ScopeIQ workflow"
    numbered = list(enumerate(cd_redlines, start=1))
    p0 = reader.pages[0]
    w, h = float(p0.mediabox.width), float(p0.mediabox.height)
    writer.add_page(_summary_page(w, h, site_id, cd_redlines[0].doc_revision, numbered, stamp).pages[0])
    for i, page in enumerate(reader.pages):
        sheet = next((s for s, idx in SHEET_PAGE.items() if idx == i), None)
        items = [(n, r) for n, r in numbered if r.sheet == sheet]
        if items:
            pw, ph = float(page.mediabox.width), float(page.mediabox.height)
            page.merge_page(_overlay(pw, ph, items, stamp).pages[0])
        writer.add_page(page)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        writer.write(f)
    log.info("redlined CD written: %s (%d markups)", out_path.name, len(cd_redlines), extra={"site_id": site_id})
    return out_path
