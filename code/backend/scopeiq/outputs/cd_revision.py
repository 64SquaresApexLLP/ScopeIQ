"""Next CD revision with the redlines incorporated (workflow REDLINE ... INCORPORATE: "new revision issued").

The redlined PDF (redline_pdf.py) only marks the drawing up. This module carries every CD redline into the
drawing itself and re-issues the set as the next revision (REV 1 -> REV 2):

  * DXF (editable source): block attributes, schedule cells, scope-of-work lines and A-3 geometry are edited,
    each change gets a red delta tag on layer A-REV, the title blocks get a revision history and the sheets
    are re-rendered to PDF (ezdxf PyMuPDF backend).
  * PDF only (vector outlines, no text layer): the values to change are located with OCR, redacted and
    rewritten in place. Symbols on A-3 cannot be redrawn without CAD; those changes are listed on T-1 for the A&E.

Only redlines a reviewer has approved (APPROVED and later) are applied. T-1 lists every redline with its
discrepancy id and whether it was applied; the others say why not. While any non-rejected redline is still
unapplied the set is issued FOR REVIEW, not FOR CONSTRUCTION. Source documents are never modified.
It is run on request ("Implement changes" in the app, POST /pipeline/sites/{id}/apply), not by every pipeline run.
"""
from __future__ import annotations

import json
import math
import re
import textwrap
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from scopeiq.common.logging import get_logger, log_call
from scopeiq.domain import SECTOR_NAMES, Discrepancy, Redline, SiteFacts, sector_code
from scopeiq.reference.loader import ReferenceData

log = get_logger(__name__)

SHEETS = ["T-1", "A-2", "A-3", "A-4", "E-1"]
GAP, W, H = 400, 340, 220                 # DXF sheet layout (model space offset, sheet size)
REVIEWED = {"APPROVED", "SENT_TO_AE", "ACKNOWLEDGED", "INCORPORATED"}
SKIP = {"REJECTED"}
STATUS_TAG = {"EXISTING": "(E)", "NEW": "(P)", "PROPOSED": "(P)", "REMOVE": "(R)"}
SCHED_STATUS = {"EXISTING": "EXISTING", "NEW": "PROPOSED", "REMOVE": "REMOVE"}
TYPE_BY_KIND = {"air": "AAU", "radio": "RRU", "passive": "ANTENNA"}
EQUIP_COLS = [18, 10, 9, 18, 16, 26, 40, 14, 13, 22]          # A-4 antenna & equipment schedule column widths
CABLE_COLS = [16, 34, 30, 30, 17, 18, 18, 22]                 # A-4 cable schedule column widths


@dataclass
class Change:
    redline_id: str
    disc_id: str
    rule_id: str
    sheet: str
    markup: str
    status: str               # redline workflow status
    applied: bool = False
    detail: str = ""           # what was changed on the drawing, or why it was not


def next_revision(rev: str) -> tuple[str, int]:
    m = re.search(r"(\d+)\s*$", rev or "")
    n = int(m.group(1)) + 1 if m else 1
    return f"REV {n}", n


def _ft_in(ft: float) -> str:
    inches = round(ft * 12)
    return f"{inches // 12}'-{inches % 12}\""


def _g(x) -> str:
    return f"{round(float(x), 1):g}"


def _measured_rc(facts: SiteFacts) -> dict[tuple, float]:
    """(sector, position, catalog key) -> measured rad center of each existing antenna found in the field."""
    return {(i.sector, i.position, i.catalog_key): float(i.rad_center_ft) for i in facts.field_items
            if i.rad_center_ft is not None and i.kind in ("passive", "air")}


def _model(ref: ReferenceData, key: str | None) -> str:
    return ref.catalog.get(key).model if key and key in ref.catalog else str(key or "")


def _key_of(ref: ReferenceData, model_text: str, kind: str | None = None) -> str | None:
    cat, _ = ref.catalog.resolve(model_text or "", kinds=(kind,) if kind else None) if model_text else (None, 0)
    return cat.key if cat else None


# =========================================================================== entry point
@log_call()
def write_revised_cd(*, site_id: str, dxf_path: Path | None, pdf_path: Path | None, out_dir: Path, redlines: list[Redline],
                     discrepancies: list[Discrepancy], facts: SiteFacts, ref: ReferenceData, trunk_plan: dict | None = None,
                     ocr_dpi: int = 400) -> dict[str, str]:
    """Write <site>_CD_REV<n+1>.pdf (and .dxf when the source is a DXF) plus a JSON change log. Returns the paths."""
    discs = {d.disc_id: d for d in discrepancies}
    changes = [Change(r.redline_id, r.disc_id, discs[r.disc_id].rule_id if r.disc_id in discs else "", r.sheet, r.markup, r.status)
               for r in redlines if r.doc_type == "CD"]
    todo = [c for c in changes if c.status in REVIEWED]          # only redlines a reviewer approved are implemented
    if not todo or not (dxf_path or pdf_path):
        return {}
    new_rev, n = next_revision(facts.cd_revision)
    issue = "ISSUED FOR CONSTRUCTION" if all(c.status in REVIEWED for c in changes if c.status not in SKIP) else "ISSUED FOR REVIEW"
    for c in changes:
        if c.status in SKIP:
            c.detail = f"not applied: redline {c.status.lower()}"
        elif c.status not in REVIEWED:
            c.detail = f"not applied: redline is {c.status} - approve it, then implement again"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{site_id}_CD_REV{n}"
    files: dict[str, str] = {}
    if dxf_path:
        rv = _DxfRevision(Path(dxf_path), site_id, n, issue, facts, ref, discs, trunk_plan)
        rv.apply(todo)
        rv.finish(changes)
        files["revised_cd_dxf"] = str(rv.save(out_dir / f"{stem}.dxf"))
        files["revised_cd_pdf"] = str(rv.render_pdf(out_dir / f"{stem}.pdf", title=f"{site_id} Construction Drawings {new_rev}"))
    else:
        rv = _PdfRevision(Path(pdf_path), site_id, n, issue, facts, ref, discs, ocr_dpi)
        rv.apply(todo)
        files["revised_cd_pdf"] = str(rv.save(out_dir / f"{stem}.pdf", changes, title=f"{site_id} Construction Drawings {new_rev}"))
    log_path = out_dir / f"{stem}_changes.json"
    log_path.write_text(json.dumps({"site_id": site_id, "from_revision": facts.cd_revision, "to_revision": new_rev, "issued": issue,
                                    "source": Path(dxf_path or pdf_path).name, "changes": [asdict(c) for c in changes]}, indent=2), encoding="utf-8")
    files["revised_cd_changes"] = str(log_path)
    log.info("CD %s written for %s: %d of %d redline(s) applied", new_rev, site_id, sum(c.applied for c in changes), len(changes),
             extra={"site_id": site_id})
    return files


# =========================================================================== DXF
class _DxfRevision:
    def __init__(self, path: Path, site_id: str, rev_no: int, issue: str, facts: SiteFacts, ref: ReferenceData,
                 discs: dict[str, Discrepancy], trunk_plan: dict | None):
        import ezdxf

        self.doc = ezdxf.readfile(str(path))
        self.msp = self.doc.modelspace()
        self.site_id, self.n, self.issue, self.f, self.ref, self.discs, self.tp = site_id, rev_no, issue, facts, ref, discs, trunk_plan
        if "A-REV" not in self.doc.layers:
            self.doc.layers.add("A-REV", color=1)
        self.rooftop = any(True for _ in self._inserts("A-3", "SLED"))
        self.trunk_dirty = False
        self.notes_by_sector: dict[str, int] = {}

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _ref_x(e) -> float:
        t = e.dxftype()
        if t == "LINE":
            return e.dxf.start.x
        if t in ("TEXT", "INSERT"):
            return e.dxf.insert.x
        if t == "CIRCLE":
            return e.dxf.center.x
        if t == "LWPOLYLINE":
            return e.get_points()[0][0]
        return 0.0

    def _sheet_of(self, e) -> str:
        i = int(self._ref_x(e) // GAP)
        return SHEETS[i] if 0 <= i < len(SHEETS) else "?"

    def ox(self, sheet: str) -> float:
        return SHEETS.index(sheet) * GAP

    def _texts(self, sheet: str):
        return [t for t in self.msp.query("TEXT") if self._sheet_of(t) == sheet]

    def _inserts(self, sheet: str, *names: str):
        return [e for e in self.msp.query("INSERT") if self._sheet_of(e) == sheet and (not names or e.dxf.name in names)]

    @staticmethod
    def _attrs(ins) -> dict:
        return {a.dxf.tag: a for a in ins.attribs}

    def _attr(self, ins, tag: str) -> str:
        a = self._attrs(ins).get(tag)
        return a.dxf.text if a else ""

    def _set_attr(self, ins, tag: str, value) -> None:
        a = self._attrs(ins).get(tag)
        if a:
            a.dxf.text = str(value)

    def text(self, x: float, y: float, t: str, h: float = 1.6, layer: str = "A-TEXT", align=None):
        from ezdxf.enums import TextEntityAlignment as TA

        e = self.msp.add_text(t, height=h, dxfattribs={"layer": layer, "style": "OpenSans"})
        e.set_placement((x, y), align=align or TA.LEFT)
        return e

    def delta(self, x: float, y: float, size: float = 2.6) -> None:
        """Red revision triangle with the revision number, centred on (x, y)."""
        from ezdxf.enums import TextEntityAlignment as TA

        pts = [(x - size / 2, y - size * 0.4), (x + size / 2, y - size * 0.4), (x, y + size * 0.55)]
        self.msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "A-REV"})
        self.text(x, y - size * 0.12, str(self.n), size * 0.42, "A-REV", TA.MIDDLE_CENTER)

    def _sector_geom(self, sec: str) -> tuple[float, float, tuple, tuple, float] | None:
        """(cx, cy, u, v, azimuth) of a sector on A-3, from its label 'ALPHA 45 DEG'."""
        name = SECTOR_NAMES.get(sec, "").upper()
        lab = next((t for t in self._texts("A-3") if re.fullmatch(rf"{name}\s+\d+(\.\d+)?\s+DEG", t.dxf.text)), None)
        if not lab:
            return None
        az = float(lab.dxf.text.split()[1])
        a = math.radians(az)
        return self.ox("A-3") + 130, 110.0, (math.sin(a), math.cos(a)), (math.cos(a), -math.sin(a)), az

    def _position_point(self, sec: str, pos: int) -> tuple[float, float] | None:
        pipe = next((p for p in self._inserts("A-3", "PIPE") if sector_code(self._attr(p, "SECTOR")) == sec
                     and self._attr(p, "POSITION") == str(pos)), None)
        if pipe:
            return pipe.dxf.insert.x, pipe.dxf.insert.y
        g = self._sector_geom(sec)
        if not g:
            return None
        cx, cy, u, v, _ = g
        R = 68 if self.rooftop else 52
        return cx + u[0] * R + v[0] * (pos - 2) * 15, cy + u[1] * R + v[1] * (pos - 2) * 15

    def _sector_note(self, sec: str, text: str) -> None:
        """A-3 note under the sector label (stacked when a sector gets several)."""
        from ezdxf.enums import TextEntityAlignment as TA

        name = SECTOR_NAMES.get(sec, "").upper()
        lab = next((t for t in self._texts("A-3") if re.fullmatch(rf"{name}\s+\d+(\.\d+)?\s+DEG", t.dxf.text)), None)
        if not lab:
            return
        k = self.notes_by_sector.get(sec, 0)
        self.notes_by_sector[sec] = k + 1
        x, y = lab.dxf.align_point.x, lab.dxf.align_point.y - 3.6 - k * 2.6
        self.text(x, y, text, 1.35, "A-TEXT", TA.MIDDLE_CENTER)
        self.delta(x - len(text) * 0.42 - 2.5, y)

    # ------------------------------------------------------------------ T-1 scope of work
    def _sow(self) -> list:
        x0 = self.ox("T-1") + 14
        rows = [t for t in self._texts("T-1") if abs(t.dxf.insert.x - x0) < 0.5 and re.match(r"\d+\.\s", t.dxf.text)]
        return sorted(rows, key=lambda t: -t.dxf.insert.y)

    def _sow_renumber(self) -> None:
        for i, t in enumerate(self._sow(), start=1):
            t.dxf.text = re.sub(r"^\d+\.", f"{i}.", t.dxf.text)

    def sow_add(self, line: str) -> None:
        rows = self._sow()
        if any(r.dxf.text.split(". ", 1)[-1] == line for r in rows):
            return
        anchor = next((r for r in rows if "FIELD VERIFY" in r.dxf.text), rows[-1] if rows else None)
        if anchor is None:
            return
        y = anchor.dxf.insert.y
        left = self.ox("T-1") + 140
        for e in list(self.msp):                # push the rest of the list, its revision tags and the sheet index down one line
            if self._sheet_of(e) != "T-1" or e.dxftype() not in ("TEXT", "LWPOLYLINE") or e.dxf.layer in ("A-BORDER", "A-TITLE"):
                continue
            x, ey = (e.dxf.insert.x, e.dxf.insert.y) if e.dxftype() == "TEXT" else e.get_points()[0][:2]
            if x < left and ey <= y + 1.5:
                e.translate(0, -5, 0)
        self.text(self.ox("T-1") + 14, y, f"0. {line}", 2.2)
        self.delta(self.ox("T-1") + 10, y + 0.9)
        self._sow_renumber()

    def sow_count(self, verb: str, model: str, delta_qty: int) -> None:
        """INSTALL (n) MODEL -> n + delta_qty; adds the line when the model is not on the list yet."""
        pat = re.compile(rf"^(\d+\.\s+{verb}\s+\()(\d+)(\)\s+{re.escape(model.upper())})$")
        for t in self._sow():
            m = pat.match(t.dxf.text)
            if m:
                q = int(m.group(2)) + delta_qty
                t.dxf.text = f"{m.group(1)}{q}{m.group(3)}" if q > 0 else t.dxf.text
                self.delta(self.ox("T-1") + 10, t.dxf.insert.y + 0.9)
                return
        if delta_qty > 0:
            self.sow_add(f"{verb} ({delta_qty}) {model.upper()}")

    # ------------------------------------------------------------------ A-4 tables
    def _rows(self, sheet: str = "A-4") -> list[tuple[float, list]]:
        rows: list[tuple[float, list]] = []
        cells = [t for t in self._texts(sheet) if t.dxf.layer != "A-REV"]       # revision tags are not table cells
        for t in sorted(cells, key=lambda t: (-round(t.dxf.insert.y, 1), t.dxf.insert.x)):
            if rows and abs(rows[-1][0] - t.dxf.insert.y) <= 0.6:
                rows[-1][1].append(t)
            else:
                rows.append((t.dxf.insert.y, [t]))
        return [(y, sorted(c, key=lambda t: t.dxf.insert.x)) for y, c in rows]

    def equip_rows(self) -> list[list]:
        names = {v.upper() for v in SECTOR_NAMES.values()}
        return [c for _, c in self._rows() if len(c) == len(EQUIP_COLS) and c[0].dxf.text in names]

    def cable_rows(self) -> list[list]:
        return [c for _, c in self._rows() if len(c) == len(CABLE_COLS) and re.fullmatch(r"T\d+", c[0].dxf.text)]

    def _shift_below(self, y_cut: float, dy: float) -> None:
        """Move every A-4 entity below y_cut by dy; stretch vertical table lines that cross it."""
        for e in list(self.msp):
            if self._sheet_of(e) != "A-4" or e.dxf.layer in ("A-BORDER", "A-TITLE"):
                continue
            t = e.dxftype()
            if t == "LINE":
                y0, y1 = e.dxf.start.y, e.dxf.end.y
                if max(y0, y1) < y_cut - 0.01:
                    e.translate(0, dy, 0)
                elif min(y0, y1) < y_cut - 0.01:            # vertical line crossing the cut: move its lower end
                    if y0 < y1:
                        e.dxf.start = (e.dxf.start.x, y0 + dy, 0)
                    else:
                        e.dxf.end = (e.dxf.end.x, y1 + dy, 0)
            elif t in ("TEXT", "LWPOLYLINE", "INSERT", "CIRCLE"):
                y = e.dxf.insert.y if t in ("TEXT", "INSERT") else e.dxf.center.y if t == "CIRCLE" else e.get_points()[0][1]
                if y < y_cut - 0.01:
                    e.translate(0, dy, 0)

    def _row_geom(self, row: list) -> tuple[float, float, float]:
        """(bottom line y, row height, text height) of a schedule row."""
        rows = self.equip_rows()
        rh = abs(rows[0][0].dxf.insert.y - rows[1][0].dxf.insert.y) if len(rows) > 1 else 4.2
        return row[0].dxf.insert.y - 1.2, rh, row[0].dxf.height

    def insert_equip_row(self, after: list | None, values: list) -> None:
        rows = self.equip_rows()
        ref_row = after or rows[-1]
        y_b, rh, th = self._row_geom(ref_row)
        hline = next((ln for ln in self.msp.query("LINE") if self._sheet_of(ln) == "A-4" and abs(ln.dxf.start.y - y_b) < 0.05
                      and abs(ln.dxf.end.y - y_b) < 0.05), None)
        self._shift_below(y_b, -rh)
        if hline:
            self.msp.add_line((hline.dxf.start.x, y_b - rh), (hline.dxf.end.x, y_b - rh), dxfattribs={"layer": "A-TABLE"})
        x = self.ox("A-4") + 10
        for w, val in zip(EQUIP_COLS, values):
            self.text(x + 0.8, y_b - rh + 1.2, str(val), th, "A-TABLE")
            x += w
        self.delta(self.ox("A-4") + 6.5, y_b - rh / 2)

    def delete_equip_row(self, row: list) -> None:
        y_b, rh, _ = self._row_geom(row)
        for t in row:
            self.msp.delete_entity(t)
        line = next((ln for ln in self.msp.query("LINE") if self._sheet_of(ln) == "A-4" and abs(ln.dxf.start.y - y_b) < 0.05
                     and abs(ln.dxf.end.y - y_b) < 0.05), None)
        if line:
            self.msp.delete_entity(line)
        self._shift_below(y_b, rh)
        self.delta(self.ox("A-4") + 6.5, y_b + rh / 2)

    def set_cell(self, cell, value, mark: bool = True) -> None:
        if cell.dxf.text != str(value):
            cell.dxf.text = str(value)
            if mark:
                self.delta(cell.dxf.insert.x - 2.2, cell.dxf.insert.y + 0.8, 2.0)

    # ------------------------------------------------------------------ device symbols on A-3 / schedule
    def add_device(self, sec: str, pos: int, key: str, status: str, *, rc: float | None, label_note: str = "") -> bool:
        """Draw a device block on A-3 (status NEW or REMOVE) and add its schedule row."""
        from ezdxf.enums import TextEntityAlignment as TA

        g, pp = self._sector_geom(sec), self._position_point(sec, pos)
        it = self.ref.catalog.get(key) if key in self.ref.catalog else None
        if not g or not pp or not it:
            return False
        _, _, u, v, az = g
        kind = it.kind
        layer = f"A-{'RRU' if kind == 'radio' else 'ANT'}-{'NEW' if status == 'NEW' else 'REMOVE'}"
        here = [b for b in self._inserts("A-3", "RRU", "ANT_PANEL", "AAU") if sector_code(self._attr(b, "SECTOR")) == sec
                and self._attr(b, "POSITION") == str(pos)]
        name = SECTOR_NAMES[sec].upper()
        if kind == "radio":
            k = sum(1 for b in here if b.dxf.name == "RRU")
            ip = (pp[0] - u[0] * (3 + k * 2.2), pp[1] - u[1] * (3 + k * 2.2))
            b = self.msp.add_blockref("RRU", ip, dxfattribs={"rotation": -az, "layer": layer, "xscale": 0.6, "yscale": 0.6})
            b.add_auto_attribs({"SECTOR": name.title(), "POSITION": str(pos), "MODEL": it.model, "STATUS": status, "BANDS": it.bands})
            lp = (ip[0] - u[0] * 1.5 - v[0] * 6.5, ip[1] - u[1] * 1.5 - v[1] * 6.5)
        else:
            k = sum(1 for b in here if b.dxf.name != "RRU")
            off = 3.5 + k * 5.5
            ip = (pp[0] + u[0] * off, pp[1] + u[1] * off)
            b = self.msp.add_blockref("AAU" if kind == "air" else "ANT_PANEL", ip,
                                      dxfattribs={"rotation": -az, "layer": layer, "xscale": 0.8, "yscale": 0.8})
            b.add_auto_attribs({"SECTOR": name.title(), "POSITION": str(pos), "MFR": it.manufacturer, "MODEL": it.model, "STATUS": status,
                                "AZIMUTH": f"{az:g}", "RAD_CENTER_FT": _g(rc) if rc is not None else "", "MECH_TILT": "0"})
            lp = (pp[0] + u[0] * (off + 1.2) + v[0] * 6.5, pp[1] + u[1] * (off + 1.2) + v[1] * 6.5)
        tag = STATUS_TAG[status]
        self.text(lp[0], lp[1], f"{sec}{pos} {tag} {it.model}{label_note}", 1.25, "A-REV", TA.MIDDLE_LEFT)
        self.delta(ip[0], ip[1] + 3.2)
        # schedule row: after the sector's last row
        sec_rows = [r for r in self.equip_rows() if r[0].dxf.text == name]
        rc_txt = _g(rc) if rc is not None else (sec_rows[0][7].dxf.text if sec_rows else "-")
        self.insert_equip_row(sec_rows[-1] if sec_rows else None,
                              [name, f"{az:g}", pos, SCHED_STATUS[status], TYPE_BY_KIND.get(kind, "RRU"), it.manufacturer.upper(),
                               it.model.upper(), rc_txt, "-" if kind == "radio" else 0, it.bands])
        if kind in ("radio", "air") and status == "NEW":
            for r in [c for _, c in self._rows() if len(c) == 4 and c[1].dxf.text == f"TOP OVP TO {'RRU' if kind == 'radio' else 'AAU'}"]:
                self.set_cell(r[3], int(float(r[3].dxf.text or 0)) + 1)
        return True

    def _device_blocks(self, sec: str, pos: int | None = None, key: str | None = None) -> list:
        out = []
        for b in self._inserts("A-3", "RRU", "ANT_PANEL", "AAU"):
            if sector_code(self._attr(b, "SECTOR")) != sec or (pos is not None and self._attr(b, "POSITION") != str(pos)):
                continue
            if key and _key_of(self.ref, self._attr(b, "MODEL")) != key:
                continue
            out.append(b)
        return out

    def _label_for(self, sec: str, pos: int, model: str):
        return next((t for t in self._texts("A-3") if t.dxf.text.startswith(f"{sec}{pos} ") and t.dxf.text.endswith(model)), None)

    def _rotate_sector(self, sheet: str, center: tuple[float, float], old_az: float, new_az: float, rmin: float, rmax: float) -> None:
        from ezdxf.math import Matrix44

        cx, cy = center
        m = Matrix44.chain(Matrix44.translate(-cx, -cy, 0), Matrix44.z_rotate(math.radians(old_az - new_az)), Matrix44.translate(cx, cy, 0))
        for e in list(self.msp):
            if self._sheet_of(e) != sheet or e.dxf.layer in ("A-BORDER", "A-TITLE", "A-STRUCT", "A-REV"):
                continue
            t = e.dxftype()
            p = (e.dxf.start if t == "LINE" else e.dxf.insert if t in ("TEXT", "INSERT") else e.dxf.center if t == "CIRCLE"
                 else e.get_points()[0][:2] if t == "LWPOLYLINE" else None)
            if p is None:
                continue
            dx, dy = p[0] - cx, p[1] - cy
            dist = math.hypot(dx, dy)
            bearing = math.degrees(math.atan2(dx, dy)) % 360
            if rmin < dist <= rmax and abs((bearing - old_az + 180) % 360 - 180) <= 45:
                e.transform(m)
                if t == "TEXT":
                    e.dxf.rotation = 0

    # ------------------------------------------------------------------ apply
    def apply(self, changes: list[Change]) -> None:
        for c in changes:
            d = self.discs.get(c.disc_id)
            handler = getattr(self, f"_rule_{c.rule_id.replace('-', '_')}", None)
            if not d or not handler:
                c.detail = "not applied automatically: A&E to revise per the markup"
                continue
            try:
                c.detail = handler(d) or ""
                c.applied = not c.detail.startswith("not applied")
            except Exception as exc:  # noqa: BLE001 - one bad change must not lose the rest of the revision
                log.warning("redline %s (%s) could not be applied: %s", c.redline_id, c.rule_id, exc, extra={"site_id": self.site_id})
                c.detail = f"not applied: {exc}"
        if self.trunk_dirty:
            self._sync_trunk()

    def _rule_FLD_02(self, d: Discrepancy) -> str:
        pipe = next((p for p in self._inserts("A-3", "PIPE") if sector_code(self._attr(p, "SECTOR")) == d.sector
                     and self._attr(p, "POSITION") == str(d.position)), None)
        if not pipe:
            return "not applied: pipe symbol not found on A-3"
        x, y = pipe.dxf.insert.x, pipe.dxf.insert.y
        used = any(self._attr(b, "STATUS") == "NEW" for b in self._device_blocks(d.sector, d.position))
        if used:
            self._set_attr(pipe, "STATUS", "PROPOSED")
            self.text(x + 1.5, y - 2.2, "(P) MOUNT PIPE", 1.2, "A-REV")
            out = f"A-3: {SECTOR_NAMES[d.sector]} pos {d.position} pipe revised (E) -> (P) (position is used)"
        else:
            self.msp.delete_entity(pipe)
            self.text(x + 1.5, y - 2.2, "NO PIPE (FIELD)", 1.2, "A-REV")
            out = f"A-3: (E) spare pipe at {SECTOR_NAMES[d.sector]} pos {d.position} deleted (not present per drone survey)"
        self.delta(x, y + 2.6)
        return out

    def _rule_FLD_05(self, d: Discrepancy) -> str:
        sled = next((s for s in self._inserts("A-3", "SLED") if sector_code(self._attr(s, "SECTOR")) == d.sector), None)
        if not sled:
            return "not applied: sled symbol not found on A-3"
        self._set_attr(sled, "STATUS", "PROPOSED")
        x, y = sled.dxf.insert.x, sled.dxf.insert.y
        lab = min((t for t in self._texts("A-3") if t.dxf.text == "(E) ROOF SLED"),
                  key=lambda t: math.hypot(t.dxf.insert.x - x, t.dxf.insert.y - y), default=None)
        if lab:
            lab.dxf.text = "(P) ROOF SLED"
        self.delta(x, y + 4.5)
        self.sow_add(f"INSTALL (1) NON-PENETRATING ROOF SLED ({SECTOR_NAMES[d.sector].upper()})")
        return f"A-3: {SECTOR_NAMES[d.sector]} roof sled (E) -> (P); T-1 scope adds the sled"

    def _rule_FLD_06(self, d: Discrepancy) -> str:
        self.trunk_dirty = True
        return f"A-4 cable schedule horizontal run {_g(d.expected)} -> {_g(d.found)} ft; required length and trunk recomputed"

    def _rule_FLD_04(self, d: Discrepancy) -> str:
        design = (self.f.sectors.get(d.sector).azimuth.get("RFDS") if d.sector in self.f.sectors else None)
        design = design if design is not None else d.expected
        self._sector_note(d.sector, f"(E) ANTENNAS MEASURED {float(d.found):.0f} DEG - RE-ORIENT TO {_g(design)} DEG")
        self.sow_add(f"RE-ORIENT (E) {SECTOR_NAMES[d.sector].upper()} ANTENNAS FROM {float(d.found):.0f} DEG TO {_g(design)} DEG (DESIGN AZIMUTH)")
        return f"A-3 note and T-1 scope: re-orient {SECTOR_NAMES[d.sector]} {float(d.found):.0f} -> {_g(design)} deg"

    def _rule_FLD_01(self, d: Discrepancy) -> str:
        rc = next((v for (s, p, k), v in _measured_rc(self.f).items() if (s, p, k) == (d.sector, d.position, d.found)), None)
        if not self.add_device(d.sector, d.position, d.found, "REMOVE", rc=rc, label_note=" (UNRECORDED)"):
            return "not applied: sector or catalog item not found"
        self.sow_count("REMOVE", _model(self.ref, d.found), 1)
        return f"A-3/A-4: unrecorded (E) {_model(self.ref, d.found)} added at {SECTOR_NAMES[d.sector]} pos {d.position} as (R) remove; T-1 scope"

    def _rule_FLD_03(self, d: Discrepancy) -> str:
        meas = _measured_rc(self.f)
        done = 0
        for b in self._inserts("A-3", "ANT_PANEL", "AAU"):
            if self._attr(b, "STATUS") != "EXISTING":
                continue
            sec, pos = sector_code(self._attr(b, "SECTOR")), int(self._attr(b, "POSITION") or 0)
            v = meas.get((sec, pos, _key_of(self.ref, self._attr(b, "MODEL"))))
            if v is None:
                continue
            self._set_attr(b, "RAD_CENTER_FT", _g(v))
            for r in self.equip_rows():
                if sector_code(r[0].dxf.text) == sec and r[2].dxf.text == str(pos) and r[3].dxf.text == "EXISTING" \
                        and _key_of(self.ref, r[6].dxf.text) == _key_of(self.ref, self._attr(b, "MODEL")):
                    self.set_cell(r[7], _g(v))
            for t in self._texts("A-2"):
                if t.dxf.text.startswith(f"{sec}{pos} ") and "(E)" in t.dxf.text:
                    t.dxf.text = re.sub(r"RC [\d.]+'", f"RC {_g(v)}'", t.dxf.text)
            done += 1
        old = {float(x) for x in d.expected or []}
        still_used = {float(i.rad_center_ft) for i in self.f.cd_items if i.status != "Existing" and i.rad_center_ft is not None}
        new = sorted({round(float(x), 1) for x in d.found or []})
        for t in self._texts("A-2"):
            m = re.fullmatch(r"RAD CENTER (\d+)'-(\d+)\"", t.dxf.text)
            if m and int(m.group(1)) + int(m.group(2)) / 12 in old:
                txt = f"(E) RAD CENTER {_ft_in(new[0])} (MEASURED)" if len(new) == 1 else \
                    f"(E) RAD CENTER {_ft_in(new[0])} TO {_ft_in(new[-1])} (MEASURED)"
                if int(m.group(1)) in still_used:
                    self.text(t.dxf.insert.x, t.dxf.insert.y - 2.6, txt, t.dxf.height, "A-DIM")
                else:
                    t.dxf.text = txt
                self.delta(t.dxf.insert.x - 2.5, t.dxf.insert.y + 0.9)
        return f"A-2/A-3/A-4: rad center of {done} existing antenna(s) revised to measured values ({'/'.join(map(_g, new))} ft)"

    def _rule_RFC_01(self, d: Discrepancy) -> str:
        g = self._sector_geom(d.sector)
        if not g:
            return "not applied: sector label not found on A-3"
        cx, cy, _, _, old = g
        new = float(d.expected)
        R = 68 if self.rooftop else 52
        self._rotate_sector("A-3", (cx, cy), old, new, 5, R + 40)
        self._rotate_sector("E-1", (self.ox("E-1") + 120, 115), old, new, 20, 45)
        name = SECTOR_NAMES[d.sector].upper()
        for t in self._texts("A-3"):
            if re.fullmatch(rf"{name}\s+\d+(\.\d+)?\s+DEG", t.dxf.text):
                t.dxf.text = f"{name} {_g(new)} DEG"
                self.delta(t.dxf.align_point.x - 14, t.dxf.align_point.y)
        for b in self._inserts("A-3", "ANT_PANEL", "AAU"):
            if sector_code(self._attr(b, "SECTOR")) == d.sector:
                self._set_attr(b, "AZIMUTH", _g(new))
        for r in self.equip_rows():
            if r[0].dxf.text == name:
                self.set_cell(r[1], _g(new), mark=r is next(x for x in self.equip_rows() if x[0].dxf.text == name))
        self.sow_add(f"RE-ORIENT {name} SECTOR FROM {_g(old)} DEG TO {_g(new)} DEG PER RFDS {self.f.rfds_revision}")
        return f"A-3/A-4/E-1: {SECTOR_NAMES[d.sector]} azimuth {_g(old)} -> {_g(new)} deg (sector re-drawn); T-1 scope"

    def _rule_RFC_02(self, d: Discrepancy) -> str:
        it = next((i for i in self.f.rfds_final if i.sector == d.sector and i.position == d.position and i.catalog_key == d.expected), None)
        if not self.add_device(d.sector, d.position, d.expected, "NEW", rc=it.rad_center_ft if it else None):
            return "not applied: sector or catalog item not found"
        self.sow_count("INSTALL", _model(self.ref, d.expected), 1)
        self.trunk_dirty = True
        return f"A-3/A-4: (P) {_model(self.ref, d.expected)} added at {SECTOR_NAMES[d.sector]} pos {d.position}; T-1 scope and jumper schedule"

    def _rule_RFC_03(self, d: Discrepancy) -> str:
        blocks = self._device_blocks(d.sector, d.position, d.found)
        blocks = [b for b in blocks if self._attr(b, "STATUS") == "NEW"][:1]
        if not blocks:
            return "not applied: device symbol not found on A-3"
        b = blocks[0]
        x, y = b.dxf.insert.x, b.dxf.insert.y
        model = self._attr(b, "MODEL")
        lab = self._label_for(d.sector, d.position, model)
        self.msp.delete_entity(b)
        if lab:
            self.msp.delete_entity(lab)
        self.delta(x, y)
        name = SECTOR_NAMES[d.sector].upper()
        row = next((r for r in self.equip_rows() if r[0].dxf.text == name and r[2].dxf.text == str(d.position)
                    and r[3].dxf.text == "PROPOSED" and _key_of(self.ref, r[6].dxf.text) == d.found), None)
        if row:
            self.delete_equip_row(row)
        self.sow_count("INSTALL", model, -1)
        self.trunk_dirty = True
        return f"A-3/A-4: (P) {model} deleted at {SECTOR_NAMES[d.sector]} pos {d.position}; T-1 scope"

    def _rule_RFC_04(self, d: Discrepancy) -> str:
        sec, name = d.sector, SECTOR_NAMES[d.sector].upper()
        g = self._sector_geom(sec)
        if not g:
            return "not applied: sector label not found on A-3"
        _, _, _, v, _ = g
        moves = []          # (blocks, label, rows, from, to) collected first so swaps do not chase each other
        for key, want in (d.expected or {}).items():
            have = (d.found or {}).get(key, [])
            for a, b in zip(sorted(set(have) - set(want)), sorted(set(want) - set(have))):
                blocks = self._device_blocks(sec, a, key)
                model = _model(self.ref, key)
                labels = [t for t in self._texts("A-3") if t.dxf.text.startswith(f"{sec}{a} ") and _key_of(self.ref, t.dxf.text.split(" ", 2)[-1]) == key]
                rows = [r for r in self.equip_rows() if r[0].dxf.text == name and r[2].dxf.text == str(a) and _key_of(self.ref, r[6].dxf.text) == key]
                keys2 = [t for t in self._texts("A-2") if t.dxf.text.startswith(f"{sec}{a} ") and model.upper() in t.dxf.text.upper()]
                moves.append((blocks, labels, rows, keys2, a, b, model))
        for blocks, labels, rows, keys2, a, b, _ in moves:
            dx, dy = v[0] * (b - a) * 15, v[1] * (b - a) * 15
            for e in blocks:
                e.translate(dx, dy, 0)
                self._set_attr(e, "POSITION", b)
            for t in labels:
                t.translate(dx, dy, 0)
                t.dxf.text = re.sub(rf"^{sec}{a} ", f"{sec}{b} ", t.dxf.text)
            for r in rows:
                self.set_cell(r[2], b)
            for t in keys2:
                t.dxf.text = re.sub(rf"^{sec}{a}", f"{sec}{b}", t.dxf.text)
            if blocks:
                self.delta(blocks[0].dxf.insert.x, blocks[0].dxf.insert.y + 3.2)
        return "A-3/A-4: " + "; ".join(f"{m} pos {a} -> {b}" for *_, a, b, m in moves) + f" ({SECTOR_NAMES[sec]}, per RFDS {self.f.rfds_revision})"

    def _rule_MNT_01(self, d: Discrepancy) -> str:
        mods = d.expected or []
        if not mods:
            return "not applied: no modifications listed"
        report = self.f.ma.report_id if self.f.ma else "MA"
        kit = next((m.group(1) for x in mods for m in [re.search(r"\((MRK[^)]*)\)", x.get("text") or "")] if m), mods[0].get("kit_key") or "KIT")
        for x in mods:
            self._sector_note(x["sector"], f"(P) MOUNT REINFORCEMENT {kit} x{x['qty']} PER {report}")
        secs = ", ".join(SECTOR_NAMES.get(x["sector"], x["sector"]).upper() for x in mods)
        self.sow_add(f"INSTALL ({sum(x['qty'] for x in mods)}) MOUNT REINFORCEMENT KIT {kit} ({secs}) PER {report}")
        return f"A-3 notes and T-1 scope: mount reinforcement {kit} at {secs} per {report}"

    def _rule_REV_02(self, d: Discrepancy) -> str:
        for t in self._texts("T-1"):
            if f"RFDS {d.found}" in t.dxf.text:
                t.dxf.text = t.dxf.text.replace(f"RFDS {d.found}", f"RFDS {d.expected}")
                self.delta(t.dxf.insert.x - 2.5, t.dxf.insert.y + 0.9)
                return f"T-1 general note: RFDS {d.found} -> {d.expected}"
        return "not applied: RFDS note not found on T-1"

    def _sync_trunk(self) -> None:
        """Cable schedule, A-2 route callout and T-1 trunk scope line follow the corrected trunk plan (same as BOM REV n)."""
        tp = self.tp or {}
        if not tp.get("count") or tp.get("held") or tp.get("length_ft") is None:
            return
        rows = self.cable_rows()
        for r in rows:
            self.set_cell(r[4], _g(tp["vertical_ft"]), mark=False)
            self.set_cell(r[5], _g(tp["horizontal_ft"]))
            self.set_cell(r[6], _g(tp["required_ft"]))
            self.set_cell(r[7], f"{tp['length_ft']} FT")
        if rows and len(rows) != tp["count"]:
            log.warning("trunk count on CD %d vs plan %d: cable schedule rows left for the A&E", len(rows), tp["count"], extra={"site_id": self.site_id})
        for t in self._texts("A-2"):
            if t.dxf.text.startswith("(P) HYBRID TRUNK - HORIZ RUN"):
                t.dxf.text = f"(P) HYBRID TRUNK - HORIZ RUN {_g(tp['horizontal_ft'])} FT"
                self.delta(t.dxf.insert.x - 2.5, t.dxf.insert.y + 0.8)
        for t in self._sow():
            m = re.match(r"^(\d+\.\s+INSTALL\s+\()\d+(\)\s+HYBRID TRUNK 6x12,\s+)\d+( FT.*)$", t.dxf.text)
            if m:
                new = f"{m.group(1)}{tp['count']}{m.group(2)}{tp['length_ft']}{m.group(3)}"
                if new != t.dxf.text:
                    t.dxf.text = new
                    self.delta(self.ox("T-1") + 10, t.dxf.insert.y + 0.9)

    # ------------------------------------------------------------------ title blocks, notes, output
    def finish(self, changes: list[Change]) -> None:
        today = date.today().isoformat()
        for sheet in SHEETS:
            ox = self.ox(sheet)
            for t in self._texts(sheet):
                m = re.fullmatch(r"REV (\d+)\s+(\d{4}-\d{2}-\d{2})", t.dxf.text)
                if m:
                    prev_no, prev_date = m.groups()
                    t.dxf.text = f"REV {self.n}  {today}"
                    x = ox + W - 55
                    self.text(x, 104, "REVISIONS", 1.6, "A-TITLE")
                    self.text(x, 99.5, f"{prev_no}  {prev_date}  ISSUED FOR CONSTRUCTION", 1.3, "A-TITLE")
                    self.text(x, 96, f"{self.n}  {today}  REDLINES INCORPORATED", 1.3, "A-REV")
                    self.delta(x + 47, 96.6, 2.2)
                elif t.dxf.text == "ISSUED FOR CONSTRUCTION":
                    t.dxf.text = self.issue
        ox = self.ox("T-1")
        self.text(ox + 150, 58, f"REVISION {self.n} - REDLINES INCORPORATED", 2.4, "A-REV")
        y = 53.0
        for i, c in enumerate(changes, start=1):
            state = "APPLIED" if c.applied else "OPEN"
            for j, ln in enumerate(textwrap.wrap(f"{i}. [{c.sheet}] {c.markup} ({c.disc_id}, redline {c.status}, {state})", 98)):
                self.text(ox + 152 + (0 if j == 0 else 3), y, ln, 1.45, "A-REV")
                y -= 3.0
            if y < 9:
                break

    def save(self, path: Path) -> Path:
        self.doc.saveas(str(path))
        return path

    def render_pdf(self, path: Path, *, title: str) -> Path:
        import pymupdf
        from ezdxf.addons.drawing import Frontend, RenderContext, layout
        from ezdxf.addons.drawing import pymupdf as mupdf_backend
        from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
        from ezdxf.math import BoundingBox2d

        for lyr in self.doc.layers:               # print in black like REV 1; only the revision layer stays red
            if lyr.dxf.name != "A-REV":
                lyr.color = 7
        cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.COLOR)
        groups: dict[int, list] = {}
        for e in self.msp:
            groups.setdefault(int(self._ref_x(e) // GAP), []).append(e)
        out = pymupdf.open()
        for i in range(len(SHEETS)):
            backend = mupdf_backend.PyMuPdfBackend()
            fe = Frontend(RenderContext(self.doc), backend, config=cfg)
            fe.set_background("#ffffff")           # draw_entities() does not set it: without this the page is model-space black
            fe.draw_entities(groups.get(i, []))
            page = layout.Page(17, 11, layout.Units.inch)
            data = backend.get_pdf_bytes(page, settings=layout.Settings(fit_page=True),
                                         render_box=BoundingBox2d([(i * GAP - 3, -3), (i * GAP + W + 3, H + 3)]))
            with pymupdf.open("pdf", data) as sheet:
                out.insert_pdf(sheet)
        out.set_metadata({"title": title, "creator": "ScopeIQ"})
        out.save(str(path))
        out.close()
        return path


# =========================================================================== PDF only (OCR)
class _PdfRevision:
    """Edits a CD PDF that has no DXF: values are found by OCR, redacted and rewritten. Coordinates of free areas
    (title block, T-1 notes) follow the A&E sheet template (340 x 220 drawing units, fitted to the page)."""

    RED = (0.85, 0.05, 0.05)

    def __init__(self, path: Path, site_id: str, rev_no: int, issue: str, facts: SiteFacts, ref: ReferenceData,
                 discs: dict[str, Discrepancy], dpi: int):
        import pymupdf

        self.pdf = pymupdf.open(str(path))
        self.src = path
        self.site_id, self.n, self.issue, self.f, self.ref, self.discs, self.dpi = site_id, rev_no, issue, facts, ref, discs, dpi
        self.edits: dict[int, list[tuple]] = {}         # page -> [(rect, new text, mark)]: redact and rewrite
        self.adds: list[tuple] = []                     # (page, x, y, text, font size): new text, nothing covered
        self.notes: list[str] = []                      # A-3 revision notes (changes the PDF cannot redraw)
        self._ocr: dict[tuple, list] = {}

    # ------------------------------------------------------------------ geometry and OCR
    def _map(self, page_i: int, x: float, y: float) -> tuple[float, float]:
        """Drawing units (relative to the sheet) -> PDF points."""
        r = self.pdf[page_i].rect
        s = min(r.width / (W + 6), r.height / (H + 6))
        offx, offy = (r.width - (W + 6) * s) / 2, (r.height - (H + 6) * s) / 2
        return offx + (x + 3) * s, r.height - (offy + (y + 3) * s)

    def _scale(self, page_i: int) -> float:
        r = self.pdf[page_i].rect
        return min(r.width / (W + 6), r.height / (H + 6))

    def lines(self, page_i: int, crop: tuple[float, float, float, float] = (0, 0, 1, 1)) -> list[list[tuple[str, object]]]:
        """OCR lines of a page region: [[(word, rect in points), ...], ...] (table rules removed first)."""
        import pymupdf
        from scopeiq.extract.cd import _ocr_page

        k = (page_i, crop)
        if k not in self._ocr:
            _, data = _ocr_page(self.src, page_i, self.dpi, crop=None if crop == (0, 0, 1, 1) else crop)
            r = self.pdf[page_i].rect
            sx = 72 / self.dpi
            ox, oy = int(crop[0] * round(r.width * self.dpi / 72)), int(crop[1] * round(r.height * self.dpi / 72))
            groups: dict[tuple, list] = {}
            for i, w in enumerate(data["text"]):
                word = w.strip().strip("|").strip()
                if word:
                    rect = pymupdf.Rect((data["left"][i] + ox) * sx, (data["top"][i] + oy) * sx,
                                        (data["left"][i] + data["width"][i] + ox) * sx, (data["top"][i] + data["height"][i] + oy) * sx)
                    groups.setdefault((data["block_num"][i], data["par_num"][i], data["line_num"][i]), []).append((word, rect))
            self._ocr[k] = [sorted(g, key=lambda t: t[1].x0) for g in groups.values()]
        return self._ocr[k]

    def replace(self, page_i: int, words: list[tuple[str, object]], new: str, mark: bool = True) -> None:
        import pymupdf

        rect = pymupdf.Rect(words[0][1])
        for _, r in words[1:]:
            rect |= r
        self.edits.setdefault(page_i, []).append((rect, new, mark))

    # ------------------------------------------------------------------ apply
    def apply(self, changes: list[Change]) -> None:
        for c in changes:
            d = self.discs.get(c.disc_id)
            handler = getattr(self, f"_rule_{c.rule_id.replace('-', '_')}", None)
            if not d or not handler:
                c.detail = "not applied automatically (PDF source without CAD): A&E to revise per the markup"
                continue
            try:
                c.detail = handler(d) or ""
                c.applied = not c.detail.startswith("not applied")
            except Exception as exc:  # noqa: BLE001
                log.warning("redline %s (%s) could not be applied: %s", c.redline_id, c.rule_id, exc, extra={"site_id": self.site_id})
                c.detail = f"not applied: {exc}"

    def _schedule_rows(self):
        """A-4 equipment rows: (row words, sector, position, status, type, catalog key)."""
        out = []
        for ln in self.lines(3, (0, 0, 0.82, 0.78)):
            words = [w for w in ln if w[0]]
            if len(words) < 10 or sector_code(words[0][0]) is None or words[0][0].upper() not in {v.upper() for v in SECTOR_NAMES.values()}:
                continue
            st, typ = words[3][0].upper(), words[4][0].upper()
            if st not in ("EXISTING", "PROPOSED", "REMOVE") or typ not in ("ANTENNA", "AAU", "RRU"):
                continue
            kind = {"ANTENNA": "passive", "AAU": "air", "RRU": "radio"}[typ]
            model = " ".join(w[0] for w in words[6:-3])
            out.append((words, sector_code(words[0][0]), int(re.sub(r"\D", "", words[2][0]) or 0), st, kind, _key_of(self.ref, model, kind)))
        return out

    def _rule_FLD_03(self, d: Discrepancy) -> str:
        meas = _measured_rc(self.f)
        rows = 0
        for words, sec, pos, st, kind, key in self._schedule_rows():
            v = meas.get((sec, pos, key))
            if st == "EXISTING" and kind != "radio" and v is not None and re.fullmatch(r"\d{2,3}", words[-3][0]):
                self.replace(3, [words[-3]], _g(v))
                rows += 1
        keys = 0
        new = sorted({round(float(x), 1) for x in d.found or []})
        old = {int(float(x)) for x in d.expected or []}
        still_used = {int(i.rad_center_ft) for i in self.f.cd_items if i.status != "Existing" and i.rad_center_ft is not None}
        for ln in self.lines(1):
            txt = " ".join(w[0] for w in ln).upper()
            m = re.match(r"^([ABCD])(\d)\b", txt)
            if m and "(E)" in txt:
                i_rc = next((i for i, w in enumerate(ln) if w[0].upper() == "RC"), None)
                k = next((key for (s, p, key) in meas if (s, p) == (m.group(1), int(m.group(2)))), None)
                if i_rc is not None and i_rc + 1 < len(ln) and k:
                    self.replace(1, [ln[i_rc + 1]], f"{_g(meas[(m.group(1), int(m.group(2)), k)])}'")
                    keys += 1
            m = re.search(r"RAD CENTER (\d{2,3})'", txt)
            if m and int(m.group(1)) in old:
                i0 = next(i for i, w in enumerate(ln) if w[0].upper() == "RAD")
                new_txt = f"(E) RAD CENTER {_ft_in(new[0])} (MEASURED)" if len(new) == 1 else \
                    f"(E) RAD CENTER {_ft_in(new[0])} TO {_ft_in(new[-1])} (MEASURED)"
                if int(m.group(1)) in still_used:      # proposed equipment still at the drawn height: add, do not replace
                    r = ln[i0][1]
                    self.adds.append((1, r.x0, r.y1 + r.height * 1.6, new_txt, r.height / 0.72))
                else:
                    self.replace(1, ln[i0:], new_txt)
        return f"A-4: rad center of {rows} existing antenna row(s) and {keys} A-2 key line(s) revised to measured values ({'/'.join(map(_g, new))} ft)"

    def _rule_RFC_04(self, d: Discrepancy) -> str:
        moves = {}
        for key, want in (d.expected or {}).items():
            have = (d.found or {}).get(key, [])
            for a, b in zip(sorted(set(have) - set(want)), sorted(set(want) - set(have))):
                moves[(key, a)] = b
        rows = 0
        for words, sec, pos, st, kind, key in self._schedule_rows():
            if sec == d.sector and (key, pos) in moves:
                self.replace(3, [words[2]], str(moves[(key, pos)]))
                rows += 1
        relabel = 0
        for page_i in (1, 2):                        # A-2 equipment key, A-3 symbol labels where legible
            for ln in self.lines(page_i):
                txt = " ".join(w[0] for w in ln)
                m = re.match(rf"^{d.sector}(\d)$", ln[0][0]) if ln else None
                if not m:
                    continue
                key = _key_of(self.ref, re.sub(r"^\S+\s+\(\w\)\s+", "", re.sub(r"\s+RC\s+[\d.']+$", "", txt)))
                b = moves.get((key, int(m.group(1))))
                if b:
                    self.replace(page_i, [ln[0]], f"{d.sector}{b}")
                    relabel += 1
        mv = "; ".join(f"{_model(self.ref, k).upper()} POS {a} TO {b}" for (k, a), b in moves.items())
        self.notes.append(f"{SECTOR_NAMES[d.sector].upper()} POSITIONS REVISED PER RFDS {self.f.rfds_revision}: {mv}. "
                          f"SYMBOLS ARE SHOWN AT REV {self.n - 1} LOCATIONS - A&E TO RE-DRAFT IN CAD.")
        return (f"A-4: {rows} schedule row position(s) revised; {relabel} label(s) on A-2/A-3 renumbered; A-3 revision note "
                f"({mv}); symbol locations left for the A&E (no CAD source)")

    # ------------------------------------------------------------------ output
    def save(self, path: Path, changes: list[Change], *, title: str) -> Path:
        import pymupdf

        today = date.today().isoformat()
        prev_date = ""
        # title blocks: revision and issue status on every sheet
        for i in range(len(self.pdf)):
            for ln in self.lines(i, (0.81, 0, 1, 1)):
                txt = " ".join(w[0] for w in ln).upper()
                m = re.match(r"^REV\s*\d+\s+(\d{4}-\d{2}-\d{2})$", txt)
                if m:
                    prev_date = m.group(1)
                    self.replace(i, ln, f"REV {self.n}  {today}", mark=False)
                elif txt.startswith("ISSUED FOR CONSTRUCTION") and self.issue != "ISSUED FOR CONSTRUCTION":
                    self.replace(i, ln, self.issue, mark=False)
        for i, edits in self.edits.items():
            page = self.pdf[i]
            for rect, _, _ in edits:
                page.add_redact_annot(rect + (-0.8, -0.8, 0.8, 0.8), fill=(1, 1, 1))
            page.apply_redactions(images=getattr(pymupdf, "PDF_REDACT_IMAGE_NONE", 0),
                                  graphics=getattr(pymupdf, "PDF_REDACT_LINE_ART_REMOVE_IF_COVERED", 1))
            for rect, new, mark in edits:
                fs = max(4.0, min(rect.height / 0.72, 14))
                width = pymupdf.get_text_length(new, "helv", fs)
                if width > rect.width + 1:
                    page.draw_rect(pymupdf.Rect(rect.x0 - 0.5, rect.y0 - 0.5, rect.x0 + width + 1, rect.y1 + 0.5), color=None, fill=(1, 1, 1))
                page.insert_text((rect.x0, rect.y1 - 0.4), new, fontsize=fs, fontname="helv", color=(0, 0, 0))
                if mark:
                    self._delta(page, rect.x0 - 9, (rect.y0 + rect.y1) / 2)
        for i, x, y, new, fs in self.adds:
            page = self.pdf[i]
            page.insert_text((x, y), new, fontsize=fs, fontname="helv", color=(0, 0, 0))
            self._delta(page, x - 9, y - fs * 0.35)
        if self.notes:          # A-3: free strip between the drawing and the title block
            page, s = self.pdf[2], self._scale(2)
            x, y = self._map(2, W - 96, 48)
            page.insert_text((x, y), f"REVISION {self.n} NOTES", fontsize=1.8 * s, fontname="helv", color=self.RED)
            self._delta(page, x - 10, y - 2)
            y += 3.4 * s
            for k, note in enumerate(self.notes, start=1):
                for ln in textwrap.wrap(f"{k}. {note}", 44):
                    page.insert_text((x, y), ln, fontsize=1.35 * s, fontname="helv", color=self.RED)
                    y += 2.4 * s
        # revision history in each title block and the revision list on T-1
        for i in range(len(self.pdf)):
            page, s = self.pdf[i], self._scale(i)
            x, y = self._map(i, W - 55, 104)
            page.insert_text((x, y), "REVISIONS", fontsize=1.6 * s, fontname="helv")
            page.insert_text((x, y + 4.5 * s), f"{self.n - 1}  {prev_date}  ISSUED FOR CONSTRUCTION", fontsize=1.3 * s, fontname="helv")
            page.insert_text((x, y + 8 * s), f"{self.n}  {today}  REDLINES INCORPORATED", fontsize=1.3 * s, fontname="helv", color=self.RED)
        page, s = self.pdf[0], self._scale(0)
        x, y = self._map(0, 150, 58)
        page.insert_text((x, y), f"REVISION {self.n} - REDLINES INCORPORATED", fontsize=2.4 * s, fontname="helv", color=self.RED)
        y += 5 * s
        for k, c in enumerate(changes, start=1):
            state = "APPLIED" if c.applied else "OPEN"
            for j, ln in enumerate(textwrap.wrap(f"{k}. [{c.sheet}] {c.markup} ({c.disc_id}, redline {c.status}, {state})", 98)):
                page.insert_text((x + (2 if j == 0 else 3) * s, y), ln, fontsize=1.45 * s, fontname="helv", color=self.RED)
                y += 3 * s
        self.pdf.set_metadata({**(self.pdf.metadata or {}), "title": title, "creator": "ScopeIQ"})
        self.pdf.save(str(path), garbage=3, deflate=True)
        self.pdf.close()
        return path

    def _delta(self, page, x: float, y: float, size: float = 7.0) -> None:
        pts = [(x, y + size * 0.45), (x + size, y + size * 0.45), (x + size / 2, y - size * 0.55), (x, y + size * 0.45)]
        page.draw_polyline(pts, color=self.RED, width=0.8)
        page.insert_text((x + size / 2 - size * 0.17, y + size * 0.33), str(self.n), fontsize=size * 0.6, fontname="helv", color=self.RED)
