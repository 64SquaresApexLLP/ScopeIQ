"""Redlined CD drawing: the redlines drawn ON the CD drawing that stage 3 compared, at the place each one is about.

  * DXF used in the comparison: the DXF is copied, every redline gets a revision cloud around the entity it is about (the
    pipe at Beta position 3, the rad-center label, the cable-schedule cell ...), a leader and a numbered callout with the
    markup text, all on a red layer; the marked-up DXF is saved and rendered to PDF.
  * PDF used in the comparison (no CAD source): the same markup is laid over the PDF pages. The PDF is a drawing of the same
    sheet coordinates, so the same positions apply; which page is which sheet is read from each page's title block.

A summary page listing every redline goes in front. Nothing here decides whether a redline is needed (that is stage 4's
decision in engine/redlines.py) and the original drawing is never modified.
"""
from __future__ import annotations

import io
import math
import re
import textwrap
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas

from scopeiq.common.logging import get_logger, log_call
from scopeiq.config import get_settings
from scopeiq.domain import SECTOR_NAMES, Discrepancy, Redline, SiteFacts, sector_code
from scopeiq.outputs.cd_revision import GAP, H, SHEETS, W, _DxfRevision
from scopeiq.outputs.redline_pdf import _summary_page
from scopeiq.reference.loader import ReferenceData

log = get_logger(__name__)
RED = Color(0.85, 0.05, 0.05)

# How the A-3 antenna layout plan is drawn (same constants as the drawings: sector centre, spacing between positions, label radius)
CENTER, LABEL_R, SPACING, R_TOWER, R_ROOF = (130.0, 110.0), 82.0, 15.0, 52.0, 68.0
BOX_W, FONT, LINE_H = 100.0, 1.7, 2.5          # callout box width, text height and line pitch, in sheet units
FREE_RIGHT = 272.0                             # the title block starts to the right of this


# =========================================================================== where things are
def _frame(az: float):
    a = math.radians(az)
    return (math.sin(a), math.cos(a)), (math.cos(a), -math.sin(a))


def position_point(az: float, pos: int, rooftop: bool) -> tuple[float, float]:
    """Where position `pos` of the sector facing `az` sits on sheet A-3 (local sheet units)."""
    u, v = _frame(az)
    r = R_ROOF if rooftop else R_TOWER
    return CENTER[0] + u[0] * r + v[0] * (pos - 2) * SPACING, CENTER[1] + u[1] * r + v[1] * (pos - 2) * SPACING


def label_point(az: float) -> tuple[float, float]:
    u, _ = _frame(az)
    return CENTER[0] + u[0] * LABEL_R, CENTER[1] + u[1] * LABEL_R


@dataclass
class Spot:
    sheet: str
    x: float
    y: float
    w: float
    h: float


class Locator:
    """Finds the place on a sheet a redline is about: from the DXF entities when there is a DXF, else from the sheet layout."""

    def __init__(self, facts: SiteFacts, dxf: _DxfRevision | None, pdf: tuple[Path, dict[str, int]] | None = None):
        self.f, self.dxf, self.pdf = facts, dxf, pdf          # pdf = (file, sheet -> page index) when there is no CAD source
        self._ocr: dict[str, list[tuple[float, float, str, float]]] = {}
        self.discs: dict[str, Discrepancy] = {}
        self.rooftop = dxf.rooftop if dxf else facts.is_rooftop

    def _az(self, sec: str | None) -> float | None:
        si = self.f.sectors.get(sec or "")
        return next((si.azimuth[k] for k in ("CD", "RFDS", "FIELD") if si and si.azimuth.get(k) is not None), None)

    def _read_page(self, sheet: str) -> list[tuple[float, float, str, float]]:
        """Text lines of one PDF sheet with their places, read with OCR (the PDF has no text layer)."""
        if sheet in self._ocr or not self.pdf or sheet not in self.pdf[1]:
            return self._ocr.get(sheet, [])
        lines: list[tuple[float, float, str, float]] = []
        try:
            import pymupdf
            from PIL import Image

            tess = _tesseract()
            with pymupdf.open(str(self.pdf[0])) as doc:
                pg = doc[self.pdf[1][sheet]]
                pix = pg.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY)
                ppu = pix.width / W                                           # pixels per sheet unit
                data = tess.image_to_data(Image.frombytes("L", (pix.width, pix.height), pix.samples), config="--psm 11", output_type=tess.Output.DICT)
            groups: dict[tuple, list[int]] = {}
            for i, word in enumerate(data["text"]):
                if word.strip() and float(data["conf"][i]) > 30:
                    groups.setdefault((data["block_num"][i], data["par_num"][i], data["line_num"][i]), []).append(i)
            for idx in groups.values():
                idx.sort(key=lambda i: data["left"][i])
                left = min(data["left"][i] for i in idx)
                top = min(data["top"][i] for i in idx)
                height = max(data["height"][i] for i in idx)
                lines.append((left / ppu, H - (top + height) / ppu, " ".join(data["text"][i] for i in idx), height / ppu))
        except Exception:  # noqa: BLE001 - without OCR the redline still gets its callout, just no cloud on the label
            log.warning("could not read the text of sheet %s for placing the markup", sheet)
        self._ocr[sheet] = lines
        return lines

    def texts(self, sheet: str) -> list[tuple[float, float, str, float]]:
        if not self.dxf:
            return self._read_page(sheet)
        ox, out = self.dxf.ox(sheet), []
        for t in self.dxf._texts(sheet):
            d = t.dxf
            p = d.align_point if d.hasattr("align_point") and (d.get("halign", 0) or d.get("valign", 0)) else d.insert
            out.append((p.x - ox, p.y, d.text, float(d.height)))
        return out

    def position_point(self, sec: str, pos: int) -> tuple[float, float] | None:
        if self.dxf:
            ox = self.dxf.ox("A-3")
            for name in ("PIPE", "ANT_PANEL", "AAU", "RRU"):
                for ins in self.dxf._inserts("A-3", name):
                    if sector_code(self.dxf._attr(ins, "SECTOR")) == sec and self.dxf._attr(ins, "POSITION") == str(pos):
                        return ins.dxf.insert.x - ox, ins.dxf.insert.y
        az = self._az(sec)
        return position_point(az, pos, self.rooftop) if az is not None else None

    def label_point(self, sec: str) -> tuple[float, float] | None:
        name = SECTOR_NAMES.get(sec, "").upper()
        for x, y, text, _ in self.texts("A-3"):
            if re.fullmatch(rf"{name}\s+\d+(\.\d+)?\s+DEG", text):
                return x, y
        az = self._az(sec)
        return label_point(az) if az is not None else None

    def _around(self, sheet: str, hits: list[tuple[float, float, str, float]]) -> Spot | None:
        if not hits:
            return None
        x0 = min(h[0] for h in hits) - 2
        x1 = max(h[0] + len(h[2]) * h[3] * 0.62 for h in hits) + 2
        y0 = min(h[1] for h in hits) - 2
        y1 = max(h[1] + h[3] for h in hits) + 2
        return Spot(sheet, x0, y0, x1 - x0, y1 - y0)

    def spot(self, d: Discrepancy, rl: Redline) -> Spot | None:
        sec, pos, sheet = d.sector, d.position, rl.sheet
        if sheet == "A-3":
            if sec and pos is not None:
                p = self.position_point(sec, int(pos))
                if p:
                    return Spot("A-3", p[0] - 9, p[1] - 9, 18, 18)
            if sec:
                p = self.label_point(sec)
                if p:
                    return Spot("A-3", p[0] - 24, p[1] - 6, 48, 12)
        texts = self.texts(sheet)
        if d.rule_id == "FLD-06":                       # the horizontal-run cell of the cable schedule
            head = next((t for t in texts if t[2].upper().startswith("HORIZ")), None)
            if head:
                want = f"{float(d.expected):g}"
                cell = [t for t in texts if abs(t[0] - head[0]) < 6 and t[1] < head[1] and re.sub(r"[^\d.]", "", t[2]) == want]
                return self._around(sheet, cell[:1])
        if d.rule_id == "FLD-03":                        # the rad-center labels on the elevation
            old = {f"{float(x):g}" for x in (d.expected or [])}
            return self._around(sheet, [t for t in texts if (m := re.search(r"RAD CENTER\s+(\d+)", t[2].upper())) and m.group(1) in old])
        if d.rule_id == "REV-02":                        # the 'RF CONFIGURATION PER RFDS' note
            return self._around(sheet, [t for t in texts if "RFDS" in t[2].upper()][:1])
        return None


# =========================================================================== layout (shared by the DXF and PDF renderers)
@dataclass
class Placed:
    n: int
    r: Redline
    spot: Spot | None
    box: tuple[float, float, float, float]       # x, y (bottom), w, h
    lines: list[str]
    ref: str


def _cloud(s: Spot, step: float = 4.0, depth: float = 0.22) -> list[tuple[float, float]]:
    """Scalloped outline of a revision cloud around a rectangle."""
    corners = [(s.x, s.y), (s.x + s.w, s.y), (s.x + s.w, s.y + s.h), (s.x, s.y + s.h)]
    pts: list[tuple[float, float]] = []
    for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1]):
        length = math.hypot(x1 - x0, y1 - y0)
        n = max(2, round(length / step))
        nx, ny = (y1 - y0) / length, -(x1 - x0) / length         # outward normal for a counter-clockwise outline
        for i in range(n):
            for k in range(6):
                t = (i + k / 6) / n
                bulge = math.sin(math.pi * ((i + k / 6) % 1)) * depth * (length / n)
                pts.append((x0 + (x1 - x0) * t + nx * bulge, y0 + (y1 - y0) * t + ny * bulge))
    return pts


def _overlap(a, b) -> bool:
    return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])


class Ink:
    """Where a sheet already has linework or text, so a callout can go where the drawing is empty."""
    PX = 2.0                                          # pixels per sheet unit

    def __init__(self, page):
        import numpy as np
        import pymupdf

        zoom = W * self.PX / float(page.rect.width)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY)
        mask = (np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width) < 200).astype(np.int64)
        self.rows, self.cols = mask.shape
        self.ii = np.pad(mask.cumsum(0).cumsum(1), ((1, 0), (1, 0)))

    def frac(self, x: float, y: float, w: float, h: float) -> float:
        c0, c1 = max(0, int(x * self.PX)), min(self.cols, int((x + w) * self.PX))
        r0, r1 = max(0, int((H - y - h) * self.PX)), min(self.rows, int((H - y) * self.PX))      # sheet y is up, image rows run down
        if c1 <= c0 or r1 <= r0:
            return 1.0
        ii = self.ii
        return float(ii[r1, c1] - ii[r0, c1] - ii[r1, c0] + ii[r0, c0]) / ((c1 - c0) * (r1 - r0))


def _best_box(spot: Spot | None, bh: float, taken: list, ink: Ink | None) -> tuple[float, float]:
    """Bottom-left of the callout: empty paper, close to the thing it is about, clear of other callouts and of the cloud."""
    tx, ty = (spot.x + spot.w / 2, spot.y + spot.h / 2) if spot else (W * 0.4, 38.0)
    best, best_cost = (8.0, 8.0), float("inf")
    y = 4.0
    while y + bh <= H - 4:
        x = 4.0
        while x + BOX_W <= FREE_RIGHT:
            box = (x, y, BOX_W, bh)
            if not any(_overlap(box, t) for t in taken) and not (spot and _overlap(box, (spot.x - 3, spot.y - 3, spot.w + 6, spot.h + 6))):
                cost = (ink.frac(*box) * 400 if ink else 0.0) + 0.05 * math.hypot(x + BOX_W / 2 - tx, y + bh / 2 - ty)
                if cost < best_cost:
                    best, best_cost = (x, y), cost
            x += 4.0
        y += 3.0
    return best


def layout(items: list[tuple[int, Redline]], locator: Locator, ink: Ink | None = None) -> list[Placed]:
    """Callout boxes in the emptiest paper next to the thing they are about, never on top of each other."""
    placed: list[Placed] = []
    taken: list[tuple[float, float, float, float]] = []
    for n, r in items:
        lines = textwrap.wrap(r.markup, 62) or [""]
        bh = (len(lines) + 1) * LINE_H + 4
        spot = locator.spot(locator.discs[r.disc_id], r) if r.disc_id in locator.discs else None
        x, y = _best_box(spot, bh, taken, ink)
        taken.append((x, y, BOX_W, bh))
        placed.append(Placed(n, r, spot, (x, y, BOX_W, bh), lines, f"ref {r.disc_id} | was: {r.change_from[:34]} -> now: {r.change_to[:34]}"))
    return placed


def _connect(box, spot: Spot) -> list[tuple[float, float]]:
    """Leader from the nearest edge of the callout to the nearest edge of the cloud."""
    bx, by, bw, bh = box
    if bx + bw <= spot.x:
        return [(bx + bw, by + bh / 2), (spot.x, spot.y + spot.h / 2)]
    if spot.x + spot.w <= bx:
        return [(bx, by + bh / 2), (spot.x + spot.w, spot.y + spot.h / 2)]
    if by >= spot.y + spot.h:
        return [(bx + bw / 2, by), (spot.x + spot.w / 2, spot.y + spot.h)]
    return [(bx + bw / 2, by + bh), (spot.x + spot.w / 2, spot.y)]


def ops_for(placed: list[Placed]) -> list[tuple]:
    """Drawing operations in sheet units: ('poly', pts, closed) ('fillrect', x, y, w, h) ('circle', x, y, r) ('text', x, y, s, height, style)."""
    ops: list[tuple] = []
    for p in placed:
        x, y, w, h = p.box
        if p.spot:
            s = p.spot
            ops.append(("poly", _cloud(s), True))
            ops.append(("poly", _connect(p.box, s), False))
            ops += [("circle", s.x, s.y + s.h, 3.0), ("text", s.x, s.y + s.h, str(p.n), 2.6, "center")]
        ops.append(("fillrect", x, y, w, h))
        ops += [("circle", x + 5, y + h - 5, 3.0), ("text", x + 5, y + h - 5, str(p.n), 2.6, "center")]
        ty = y + h - 4.2
        for ln in p.lines:
            ops.append(("text", x + 10, ty, ln, FONT, "left"))
            ty -= LINE_H
        ops.append(("text", x + 10, ty, p.ref[:92], FONT * 0.78, "left"))
    return ops


# =========================================================================== renderers
def _draw_dxf(rv: _DxfRevision, sheet: str, ops: list[tuple]) -> None:
    from ezdxf.enums import TextEntityAlignment as TA

    ox, msp = rv.ox(sheet), rv.msp
    if "A-REDLINE-BG" not in rv.doc.layers:
        rv.doc.layers.add("A-REDLINE-BG", color=7)
    style = "OpenSans" if "OpenSans" in rv.doc.styles else "Standard"
    for op in ops:
        kind = op[0]
        if kind == "poly":
            msp.add_lwpolyline([(ox + x, y) for x, y in op[1]], close=op[2], dxfattribs={"layer": "A-REV"})
        elif kind == "circle":
            msp.add_circle((ox + op[1], op[2]), op[3], dxfattribs={"layer": "A-REV"})
        elif kind == "fillrect":
            _, x, y, w, h = op
            pts = [(ox + x, y), (ox + x + w, y), (ox + x + w, y + h), (ox + x, y + h)]
            hatch = msp.add_hatch(dxfattribs={"layer": "A-REDLINE-BG"})
            hatch.paths.add_polyline_path(pts, is_closed=True)
            hatch.set_solid_fill(rgb=(255, 255, 255))
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "A-REV"})
        elif kind == "text":
            _, x, y, s, height, align = op
            e = msp.add_text(s, height=height, dxfattribs={"layer": "A-REV", "style": style})
            e.set_placement((ox + x, y - (height / 3 if align == "center" else 0)), align=TA.MIDDLE_CENTER if align == "center" else TA.LEFT)


def _draw_pdf(c: canvas.Canvas, pw: float, ph: float, ops: list[tuple]) -> None:
    sx, sy = pw / W, ph / H                       # sheet units -> points (y is up in both)
    c.setStrokeColor(RED)
    for op in ops:
        kind = op[0]
        if kind == "poly":
            c.setLineWidth(1.1)
            path = c.beginPath()
            path.moveTo(op[1][0][0] * sx, op[1][0][1] * sy)
            for x, y in op[1][1:]:
                path.lineTo(x * sx, y * sy)
            if op[2]:
                path.close()
            c.drawPath(path, stroke=1, fill=0)
        elif kind == "circle":
            c.setLineWidth(1.0)
            c.setFillColor(Color(1, 1, 1))
            c.circle(op[1] * sx, op[2] * sy, op[3] * sx, stroke=1, fill=1)
        elif kind == "fillrect":
            c.setLineWidth(1.2)
            c.setFillColor(Color(1, 1, 1))
            c.rect(op[1] * sx, op[2] * sy, op[3] * sx, op[4] * sy, stroke=1, fill=1)
        elif kind == "text":
            _, x, y, s, height, align = op
            c.setFillColor(RED)
            c.setFont("Helvetica-Bold" if align == "center" else "Helvetica", height * sy)
            (c.drawCentredString if align == "center" else c.drawString)(x * sx, (y - (height / 3 if align == "center" else 0)) * sy, s)


# =========================================================================== PDF pages -> sheets
def _tesseract():
    import pytesseract

    cmd = get_settings().get("engine.tesseract_cmd")
    if not cmd:
        default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        cmd = str(default) if default.exists() else None
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = str(cmd)
    return pytesseract


def detect_sheet_pages(pdf_path: Path) -> dict[str, int]:
    """Which page is which sheet, read from the 'SHEET A-3' block of each page; the standard order fills any page that cannot be read."""
    pages: dict[str, int] = {}
    try:
        import pymupdf
        from PIL import Image

        tess = _tesseract()
        with pymupdf.open(str(pdf_path)) as doc:
            count = len(doc)
            for i, pg in enumerate(doc):
                r = pg.rect
                pix = pg.get_pixmap(dpi=200, clip=pymupdf.Rect(r.width * 0.80, r.height * 0.86, r.width, r.height * 0.99), colorspace=pymupdf.csGRAY)
                txt = tess.image_to_string(Image.frombytes("L", (pix.width, pix.height), pix.samples), config="--psm 6").upper()
                m = re.search(r"SHEET\s*([A-Z])\s*[-–—]\s*(\d)", txt)
                if m:
                    pages.setdefault(f"{m.group(1)}-{m.group(2)}", i)
    except Exception:  # noqa: BLE001 - without OCR the standard sheet order is used
        log.warning("sheet numbers could not be read from %s; using the standard sheet order", Path(pdf_path).name)
        count = len(PdfReader(str(pdf_path)).pages)
    used = set(pages.values())
    for i, s in enumerate(SHEETS):
        if s not in pages and i < count and i not in used:
            pages[s] = i
    return pages


# =========================================================================== the redlined drawing
def _final_name(facts: SiteFacts) -> str:
    return f"{facts.site_id}_CD_{(facts.cd_revision or 'REV').replace(' ', '')}_REDLINED"


def remove_redlined_cd(out_dir: Path, facts: SiteFacts) -> None:
    """No redline is needed: a redlined drawing left over from an earlier run must not be mistaken for a current one."""
    for ext in (".pdf", ".dxf"):
        (Path(out_dir) / f"{_final_name(facts)}{ext}").unlink(missing_ok=True)


@log_call()
def write_redlined_cd(*, facts: SiteFacts, discs: list[Discrepancy], redlines: list[Redline], dxf_path: Path | None, pdf_path: Path | None,
                      out_dir: Path, ref: ReferenceData, prepared_by: str = "ScopeIQ") -> dict[str, str]:
    cd = [r for r in redlines if r.doc_type == "CD"]
    out_dir = Path(out_dir)
    if not cd or not (dxf_path or pdf_path):
        remove_redlined_cd(out_dir, facts)
        return {}
    out_dir.mkdir(parents=True, exist_ok=True)
    use_dxf = bool(dxf_path) and str(facts.cd_method).upper().startswith("DXF")
    source = Path(dxf_path if use_dxf else pdf_path)
    numbered = list(enumerate(cd, start=1))
    stamp = f"{prepared_by} - {date.today().isoformat()} - {len(cd)} markup(s) on {source.name} - status per ScopeIQ workflow"
    by_sheet = {s: [(n, r) for n, r in numbered if r.sheet == s] for s in SHEETS}
    name, files, writer = _final_name(facts), {}, PdfWriter()
    rv = None
    if use_dxf:
        rv = _DxfRevision(source, facts.site_id, 0, "ISSUED FOR REVIEW", facts, ref, {d.disc_id: d for d in discs}, None)
        locator = Locator(facts, rv)
    else:
        locator = Locator(facts, None)                              # the PDF case is completed below, once the sheets are known
    locator.discs = {d.disc_id: d for d in discs}
    if use_dxf:
        import pymupdf

        plain = out_dir / f".{name}.plain.pdf"                     # the drawing as it is, to see where the paper is empty
        rv.render_pdf(plain, title="plain")
        with pymupdf.open(str(plain)) as base:
            inks = {s: Ink(base[i]) for i, s in enumerate(SHEETS) if i < len(base)}
        plain.unlink(missing_ok=True)
        for sheet, items in by_sheet.items():
            if items:
                _draw_dxf(rv, sheet, ops_for(layout(items, locator, inks.get(sheet))))
        tmp = out_dir / f".{name}.render.pdf"
        rv.render_pdf(tmp, title=f"{facts.site_id} CD {facts.cd_revision} - redlines")
        reader = PdfReader(str(tmp))
        files["redlined_cd_dxf"] = str(rv.save(out_dir / f"{name}.dxf"))
    else:
        reader = PdfReader(str(source))
        page_of = detect_sheet_pages(source)
        locator.pdf = (source, page_of)
        import pymupdf

        base = pymupdf.open(str(source))
        for sheet, items in by_sheet.items():
            if not items or sheet not in page_of:
                continue
            page = reader.pages[page_of[sheet]]
            pw, ph = float(page.mediabox.width), float(page.mediabox.height)
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(pw, ph))
            _draw_pdf(c, pw, ph, ops_for(layout(items, locator, Ink(base[page_of[sheet]]))))
            c.save()
            buf.seek(0)
            page.merge_page(PdfReader(buf).pages[0])
        base.close()
    p0 = reader.pages[0]
    writer.add_page(_summary_page(float(p0.mediabox.width), float(p0.mediabox.height), facts.site_id, facts.cd_revision, numbered, stamp).pages[0])
    for pg in reader.pages:
        writer.add_page(pg)
    pdf_out = out_dir / f"{name}.pdf"
    with open(pdf_out, "wb") as fh:
        writer.write(fh)
    if use_dxf:
        (out_dir / f".{name}.render.pdf").unlink(missing_ok=True)
    files["redlined_cd_pdf"] = str(pdf_out)
    log.info("redlined CD written: %s (%d markups, from %s)", pdf_out.name, len(cd), source.name, extra={"site_id": facts.site_id})
    return files
