"""Construction drawing (CD) extraction.

Two paths, same output:
  * DXF (preferred): equipment, pipes and sleds come from block attributes (ANT_PANEL, AAU, RRU, PIPE, SLED);
    schedules and notes from TEXT entities grouped into table rows. Confidence 0.99.
  * PDF (vector outlines, no text layer): sheets are rendered (PyMuPDF), table lines removed (OpenCV) and read
    with Tesseract OCR; model text is matched to the catalog. Confidence = OCR word confidence x match score,
    and anything under the threshold goes to the review queue. In Snowflake the same step can use
    AI_PARSE_DOCUMENT (see snowflake/11_pipeline_procedures.sql).

Sheets: T-1 title/SoW/notes, A-2 elevation, A-3 antenna layout plan, A-4 antenna & cable schedule, E-1 grounding.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from scopeiq.common.errors import ExtractionError
from scopeiq.common.logging import get_logger, log_call
from scopeiq.domain import ConfigItem, ExtractedField, SectorInfo, SourceRef, TrunkInfo, sector_code
from scopeiq.reference.catalog import Catalog

log = get_logger(__name__)

SHEETS = ["T-1", "A-2", "A-3", "A-4", "E-1"]
SHEET_GAP = 400            # DXF model-space offset between sheets
STATUS_MAP = {"EXISTING": "Existing", "NEW": "New", "PROPOSED": "New", "REMOVE": "Remove"}
TYPE_KIND = {"ANTENNA": "passive", "AAU": "air", "RRU": "radio"}


@dataclass
class CdResult:
    method: str = ""
    revision: str = ""
    rfds_reference: str | None = None
    items: list[ConfigItem] = field(default_factory=list)
    sectors: dict[str, SectorInfo] = field(default_factory=dict)
    trunk: TrunkInfo | None = None
    jumpers: list[dict] = field(default_factory=list)
    scope_lines: list[str] = field(default_factory=list)
    fields: list[ExtractedField] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _num(t) -> float | None:
    try:
        return float(str(t).replace("'", "").replace('"', "").strip())
    except (TypeError, ValueError):
        return None


# =========================================================================== DXF
@log_call()
def extract_cd_dxf(path: Path, *, site_id: str, doc_id: str, revision: str, catalog: Catalog) -> CdResult:
    import ezdxf

    try:
        doc = ezdxf.readfile(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"DXF {Path(path).name} could not be read: {exc}", cause=exc) from exc
    res = CdResult(method="DXF", revision=revision)
    msp = doc.modelspace()

    def sheet_of(x: float) -> str:
        i = int(x // SHEET_GAP)
        return SHEETS[i] if 0 <= i < len(SHEETS) else "?"

    ant_rc: dict[tuple[str, int], float] = {}
    radios = []
    for e in msp.query("INSERT"):
        name = e.dxf.name
        attrs = {a.dxf.tag: a.dxf.text for a in e.attribs}
        sheet = sheet_of(e.dxf.insert.x)
        sec = sector_code(attrs.get("SECTOR"))
        pos = int(attrs["POSITION"]) if str(attrs.get("POSITION", "")).isdigit() else None
        ref = SourceRef(doc_id, "CD", revision, sheet, f"block {name}")
        if name in ("ANT_PANEL", "AAU"):
            cat, score = catalog.resolve(attrs.get("MODEL", ""), kinds=("air",) if name == "AAU" else ("passive",))
            it = ConfigItem(site_id, "CD", sec, pos, cat.kind if cat else ("air" if name == "AAU" else "passive"), cat.key if cat else None,
                            attrs.get("MODEL", ""), STATUS_MAP.get(attrs.get("STATUS", "").upper(), attrs.get("STATUS", "")),
                            rad_center_ft=_num(attrs.get("RAD_CENTER_FT")), azimuth_deg=_num(attrs.get("AZIMUTH")),
                            mech_tilt=_num(attrs.get("MECH_TILT")), ref=ref, confidence=round(0.99 * score, 3))
            res.items.append(it)
            if it.rad_center_ft is not None and pos is not None:
                ant_rc[(sec, pos)] = max(ant_rc.get((sec, pos), 0), it.rad_center_ft)
            if it.azimuth_deg is not None:
                res.sectors.setdefault(sec, SectorInfo(sec)).azimuth.setdefault("CD", it.azimuth_deg)
        elif name == "RRU":
            cat, score = catalog.resolve(attrs.get("MODEL", ""), kinds=("radio",))
            radios.append(ConfigItem(site_id, "CD", sec, pos, "radio", cat.key if cat else None, attrs.get("MODEL", ""),
                                     STATUS_MAP.get(attrs.get("STATUS", "").upper(), attrs.get("STATUS", "")), bands=attrs.get("BANDS", ""),
                                     ref=ref, confidence=round(0.99 * score, 3), feeds_position=pos))
        elif name == "PIPE":
            st = attrs.get("STATUS", "").upper()
            res.items.append(ConfigItem(site_id, "CD", sec, pos, "pipe", "PIPE", "Mount pipe",
                                        "New" if st.startswith("PROPOSED") else "Existing", ref=ref, confidence=0.99,
                                        attrs={"cd_status": st, "spare": "SPARE" in st, "new_frame": "NEW FRAME" in st}))
            if "NEW FRAME" in st:
                res.sectors.setdefault(sec, SectorInfo(sec)).new_frame = True
        elif name == "SLED":
            st = attrs.get("STATUS", "").upper()
            res.items.append(ConfigItem(site_id, "CD", sec, None, "sled", "SLED", "Roof sled", "Existing" if st == "EXISTING" else "New",
                                        ref=ref, confidence=0.99, attrs={"cd_status": st}))
            res.sectors.setdefault(sec, SectorInfo(sec)).sled["CD"] = st == "EXISTING"
    for r in radios:
        r.rad_center_ft = ant_rc.get((r.sector, r.position))
        res.items.append(r)

    # TEXT entities -> rows per sheet
    texts: dict[str, list[tuple[float, float, str]]] = {}
    for t in msp.query("TEXT"):
        if t.dxf.layer == "A-REV":          # revision markup (delta tags, change list) is not drawing data
            continue
        texts.setdefault(sheet_of(t.dxf.insert.x), []).append((round(t.dxf.insert.y, 1), t.dxf.insert.x, t.dxf.text))
    _parse_text_sheets(res, texts, doc_id, revision, site_id)
    _finish(res, site_id, doc_id)
    return res


def _rows(entries: list[tuple[float, float, str]], tol: float = 0.6) -> list[list[str]]:
    rows: list[tuple[float, list[tuple[float, str]]]] = []
    for y, x, t in sorted(entries, key=lambda e: (-e[0], e[1])):
        if rows and abs(rows[-1][0] - y) <= tol:
            rows[-1][1].append((x, t))
        else:
            rows.append((y, [(x, t)]))
    return [[t for _, t in sorted(cells)] for _, cells in rows]


def _parse_text_sheets(res: CdResult, texts: dict, doc_id: str, revision: str, site_id: str) -> None:
    for row in _rows(texts.get("T-1", [])):
        line = " ".join(row)
        m = re.search(r"RF CONFIGURATION PER RFDS (R\d+)", line)
        if m:
            res.rfds_reference = m.group(1)
        for i, cell in enumerate(row):
            if re.fullmatch(r"\d+\.", cell.strip()) and i + 1 < len(row):
                cell = f"{cell} {row[i + 1]}"
            m = re.match(r"\d+\.\s+(.*)", cell.strip())
            if m and any(v in m.group(1) for v in ("INSTALL", "REMOVE", "REPLACE", "FIELD VERIFY")):
                res.scope_lines.append(m.group(1))
    for row in _rows(texts.get("A-3", [])):
        line = " ".join(row)
        m = re.match(r"(ALPHA|BETA|GAMMA|DELTA)\s+(\d+)\s+DEG", line)
        if m:
            res.sectors.setdefault(sector_code(m.group(1)), SectorInfo(sector_code(m.group(1)))).azimuth.setdefault("CD", float(m.group(2)))
    for row in _rows(texts.get("A-4", [])):
        if row and re.fullmatch(r"T\d+", row[0]) and len(row) >= 8:
            spec = int(re.sub(r"\D", "", row[7]) or 0)
            cnt = (res.trunk.count + 1) if res.trunk else 1
            res.trunk = TrunkInfo("CD", cnt, _num(row[4]), _num(row[5]), _num(row[6]), spec, SourceRef(doc_id, "CD", revision, "A-4", "Cable schedule"))
        elif row and row[0].startswith(("DC JUMPER", "FIBER JUMPER")) and len(row) >= 4:
            res.jumpers.append({"jumper": row[0], "route": row[1], "length": row[2], "qty": int(_num(row[3]) or 0)})


# =========================================================================== PDF (OCR)
EQUIP_RE = re.compile(r"^(ALPHA|BETA|GAMMA|DELTA)\s+(\S{1,3})\s+(\d)\s+(EXISTING|PROPOSED|REMOVE)\s+(ANTENNA|AAU|RRU)\s+(\S+)\s+(.+?)\s+(\d{2,3})\s+(\S+)\s+(\S+)\s*$")
TRUNK_RE = re.compile(r"^T[\dlI|]+\s+HYBRID.*?(\d{2,3})\s+(\d{1,3})\s+([\d.]+)\s+(\d{3})\s*FT", re.I)
SECTOR_LABEL_RE = re.compile(r"^(ALPHA|BETA|GAMMA|DELTA)$")


def _ocr_page(pdf_path: Path, page_index: int, dpi: int, crop: tuple[float, float, float, float] | None = None):
    """Render one page, remove ruled lines, return (cleaned image, tesseract data dict)."""
    import cv2
    import numpy as np
    import pymupdf
    import pytesseract

    with pymupdf.open(str(pdf_path)) as pdf:
        pix = pdf[page_index].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    if crop:
        h, w = img.shape
        img = img[int(crop[1] * h):int(crop[3] * h), int(crop[0] * w):int(crop[2] * w)]
    th = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    k = max(40, dpi // 8)
    hor = cv2.morphologyEx(th, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k, 1)))
    ver = cv2.morphologyEx(th, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, k)))
    th[(hor > 0) | (ver > 0)] = 0
    clean = 255 - th
    data = pytesseract.image_to_data(clean, config="--psm 6", output_type=pytesseract.Output.DICT)
    return clean, data


def _ocr_lines(data: dict) -> list[tuple[str, float, tuple[int, int]]]:
    """Group tesseract words into lines -> (text, mean confidence 0..1, (x, y) of first word)."""
    lines: dict[tuple, list[int]] = {}
    for i, w in enumerate(data["text"]):
        if w.strip():
            lines.setdefault((data["block_num"][i], data["par_num"][i], data["line_num"][i]), []).append(i)
    out = []
    for idx in lines.values():
        idx.sort(key=lambda i: data["left"][i])
        confs = [float(data["conf"][i]) for i in idx if float(data["conf"][i]) >= 0]
        out.append((" ".join(data["text"][i] for i in idx), (sum(confs) / len(confs) / 100) if confs else 0.0,
                    (data["left"][idx[0]], data["top"][idx[0]])))
    return out


@log_call()
def extract_cd_pdf_ocr(path: Path, *, site_id: str, doc_id: str, revision: str, catalog: Catalog, dpi: int = 600) -> CdResult:
    try:
        import pytesseract
        from scopeiq.config import get_settings
        cmd = get_settings().get("engine.tesseract_cmd")
        if cmd:                                   # e.g. C:\Program Files\Tesseract-OCR\tesseract.exe on Windows
            pytesseract.pytesseract.tesseract_cmd = str(cmd)
        pytesseract.get_tesseract_version()
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError("Tesseract OCR is not installed - CD PDF needs OCR (or AI_PARSE_DOCUMENT in Snowflake)",
                              cause=exc, details={"file": Path(path).name}) from exc
    res = CdResult(method="PDF_OCR", revision=revision)
    # A-4 schedules: equipment + cable schedule (left 82% of the sheet, top 75%)
    _, data = _ocr_page(path, 3, dpi, crop=(0, 0, 0.82, 0.78))
    for text, conf, _ in _ocr_lines(data):
        t = re.sub(r"\s+", " ", text.replace("|", " ")).strip().upper()
        m = EQUIP_RE.match(t)
        if m:
            sec, az, pos, st, typ, mfr, model, rc, tilt, bands = m.groups()
            kind = TYPE_KIND[typ]
            az_val = float(az) if az.isdigit() else None
            if az_val is None:          # OCR misread (e.g. '2/0'): repaired below from the sector's other rows
                conf *= 0.8
            cat, score = catalog.resolve(model, kinds=(kind,), cutoff=0.6)
            item = ConfigItem(site_id, "CD", sector_code(sec), int(pos), kind, cat.key if cat else None, model.title(),
                              STATUS_MAP[st], rad_center_ft=float(rc), azimuth_deg=az_val,
                              mech_tilt=_num(tilt) if kind != "radio" else None, bands=bands,
                              ref=SourceRef(doc_id, "CD", revision, "A-4", "OCR schedule row"),
                              confidence=round(min(conf, 0.99) * (score or 0.3), 3), feeds_position=int(pos) if kind == "radio" else None)
            res.items.append(item)
            if az_val is not None:
                res.sectors.setdefault(item.sector, SectorInfo(item.sector)).azimuth.setdefault("CD", az_val)
            continue
        m = TRUNK_RE.match(t)
        if m:
            v, h, req, spec = m.groups()
            cnt = (res.trunk.count + 1) if res.trunk else 1
            res.trunk = TrunkInfo("CD", cnt, float(v), float(h), float(req), int(spec), SourceRef(doc_id, "CD", revision, "A-4", "OCR cable schedule"))
    for it in res.items:
        if it.azimuth_deg is None and it.sector in res.sectors and "CD" in res.sectors[it.sector].azimuth:
            it.azimuth_deg = res.sectors[it.sector].azimuth["CD"]
            it.attrs["azimuth_repaired"] = True
    # T-1: scope of work, structure type and the RFDS revision the CD was drawn from
    _, data = _ocr_page(path, 0, max(300, dpi * 2 // 3))
    rooftop = False
    for text, _, _ in _ocr_lines(data):
        u = text.upper()
        m = re.search(r"RFDS\s+(R\s*\d+)", u)
        if m:
            res.rfds_reference = m.group(1).replace(" ", "")
        rooftop = rooftop or "STRUCTURE: ROOFTOP" in u or "STRUCTURE TYPE: ROOFTOP" in u
        m = re.match(r"^\s*\d+\.\s+((?:INSTALL|REMOVE|REPLACE|FIELD VERIFY).*)$", u)
        if m:
            res.scope_lines.append(re.split(r"\s+(?:SITE ID|SITE NAME|SITE|MARKET|CUSTOMER|ADDRESS|CITY|STATE|ZIP|HEIGHT|STRUCTURE)\b", m.group(1))[0].strip())
    scope = " | ".join(res.scope_lines)
    if "SECTOR FRAME" in scope:
        for sec in {i.sector for i in res.items}:
            res.sectors.setdefault(sec, SectorInfo(sec)).new_frame = True
    if rooftop:
        # A-3 sled labels are crossed by azimuth lines and do not OCR reliably, so the scope of work decides:
        # no "INSTALL ... ROOF SLED" on T-1 means the CD treats every sector's sled as existing.
        installs_sled = "ROOF SLED" in scope and "INSTALL" in scope
        for sec in sorted({i.sector for i in res.items}):
            res.sectors.setdefault(sec, SectorInfo(sec)).sled["CD"] = not installs_sled
            res.items.append(ConfigItem(site_id, "CD", sec, None, "sled", "SLED", "Roof sled", "New" if installs_sled else "Existing",
                                        ref=SourceRef(doc_id, "CD", revision, "T-1", "scope of work (OCR)"), confidence=0.8,
                                        attrs={"inferred": True}))
        if installs_sled:
            res.warnings.append("CD scope installs roof sled(s) but the A-3 labels are not legible by OCR; confirm which sectors")
    # pipes are not printed as text on the PDF: one per scheduled antenna position is inferred and flagged, so
    # the field survey (not this inference) decides pipe kits, and no "pipe missing" finding is raised from it
    for (sec, pos) in sorted({(i.sector, i.position) for i in res.items if i.kind in ("passive", "air")}):
        res.items.append(ConfigItem(site_id, "CD", sec, pos, "pipe", "PIPE", "Mount pipe", "Existing",
                                    ref=SourceRef(doc_id, "CD", revision, "A-3", "inferred from occupied position"), confidence=0.7,
                                    attrs={"inferred": True}))
    res.warnings.append("CD read by OCR: spare pipes and sector-frame status are not printed on the PDF; verify on A-3")
    _finish(res, site_id, doc_id)
    return res


def _finish(res: CdResult, site_id: str, doc_id: str) -> None:
    for it in res.items:
        res.fields.append(ExtractedField(doc_id, site_id, it.ref.page if it.ref else "", f"CD:{it.sector}{it.position or ''}:{it.kind}",
                                         it.model_text, it.confidence, res.method, needs_review=it.confidence < 0.8 or it.catalog_key is None))
    if res.trunk:
        t = res.trunk
        res.fields.append(ExtractedField(doc_id, site_id, "A-4", "CD:trunk", {"count": t.count, "vertical_ft": t.vertical_ft,
                                         "horizontal_ft": t.horizontal_ft, "specified_ft": t.specified_ft}, 0.99 if res.method == "DXF" else 0.85, res.method))
    log.info("CD read via %s: %d items, trunk=%s, rfds_ref=%s", res.method, len(res.items),
             res.trunk.specified_ft if res.trunk else None, res.rfds_reference, extra={"site_id": site_id})


def extract_cd(dxf: Path | None, pdf: Path | None, *, site_id: str, doc_ids: dict, revision: str, catalog: Catalog,
               ocr_enabled: bool = True, dpi: int = 600) -> CdResult:
    """Prefer DXF; fall back to OCR on the PDF."""
    if dxf:
        return extract_cd_dxf(dxf, site_id=site_id, doc_id=doc_ids["dxf"], revision=revision, catalog=catalog)
    if pdf and ocr_enabled:
        return extract_cd_pdf_ocr(pdf, site_id=site_id, doc_id=doc_ids["pdf"], revision=revision, catalog=catalog, dpi=dpi)
    raise ExtractionError("No machine-readable CD (DXF missing and OCR disabled)", details={"site_id": site_id})
