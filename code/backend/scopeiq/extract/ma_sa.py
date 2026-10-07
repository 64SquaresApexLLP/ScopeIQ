"""Mount Analysis (MA) and Structural Analysis (SA) report extraction (text-layer PDF).

Page 1 = MA summary (result, capacity, required modifications, proposed loading analysed),
page 2 = SA summary (result, controlling member capacity). Pages are recognised by their title, not position.
"""
from __future__ import annotations

import re
from pathlib import Path

from scopeiq.common.logging import get_logger, log_call
from scopeiq.domain import AnalysisResult, ConfigItem, ExtractedField, SourceRef, sector_code
from scopeiq.extract.pdftext import pdf_pages_text
from scopeiq.reference.catalog import Catalog

log = get_logger(__name__)

KV_RE = re.compile(r"^\s{0,20}(Report|Date|Mount type|Structure|Owner|Governing standard|Result|Mount capacity \(proposed loading\)|"
                   r"Capacity after modifications|Controlling member capacity|RFDS revision)\s{2,}(.+?)\s*$")
MOD_RE = re.compile(r"^\s*(Alpha|Beta|Gamma|Delta|Site)\s{2,}(.+?)\s{2,}(\d+)\s*$")
LOAD_RE = re.compile(r"^\s*(Alpha|Beta|Gamma|Delta)\s{2,}(\d)\s{2,}(.+?)\s{2,}(Retain|Add|Remove|Existing)\s{2,}(\d+(?:\.\d+)?)\s*$")
KIT_RE = re.compile(r"\(([A-Z]{2,5}-\d+)\)")
ACTION = {"Retain": "Existing", "Existing": "Existing", "Add": "New", "Remove": "Remove"}


def _pct(v: str | None) -> float | None:
    m = re.search(r"([\d.]+)\s*%", v or "")
    return float(m.group(1)) if m else None


def _parse_page(text: str, kind: str, site_id: str, doc_id: str, page: int, catalog: Catalog) -> AnalysisResult:
    kv: dict[str, str] = {}
    mods, loading = [], []
    for line in text.splitlines():
        m = KV_RE.match(line)
        if m:
            kv.setdefault(m.group(1), m.group(2).strip())
            continue
        m = LOAD_RE.match(line)
        if m:
            sec, pos, model, act, rc = m.groups()
            kinds = ("radio",) if model.upper().startswith(("RADIO", "RRUS")) else ("air", "passive")
            cat, score = catalog.resolve(model, kinds=kinds)
            loading.append(ConfigItem(site_id, "MA_LOADING", sector_code(sec), int(pos), cat.kind if cat else kinds[0],
                                      cat.key if cat else None, model, ACTION[act], rad_center_ft=float(rc),
                                      ref=SourceRef(doc_id, "MA_SA", "R0", str(page), "Proposed loading"), confidence=round(0.97 * score, 3)))
            continue
        m = MOD_RE.match(line)
        if m and "Modification" not in line:
            sec, txt, qty = m.groups()
            kit = KIT_RE.search(txt)
            kit_key = None
            if kit:
                cat, _ = catalog.resolve(kit.group(1))
                kit_key = cat.key if cat else kit.group(1).split("-")[0]
            mods.append({"sector": sector_code(sec) if sec != "Site" else "SITE", "kit_key": kit_key, "qty": int(qty), "text": txt.strip()})
    rid = kv.get("Report", "")
    return AnalysisResult(kind=kind, report_id=rid, date=kv.get("Date", ""), result=kv.get("Result", "").upper(),
                          capacity_pct=_pct(kv.get("Mount capacity (proposed loading)") or kv.get("Controlling member capacity")),
                          capacity_after_pct=_pct(kv.get("Capacity after modifications")), rfds_revision=kv.get("RFDS revision"),
                          modifications=mods, loading=loading,
                          ref=SourceRef(doc_id, "MA_SA", rid.rsplit("-", 1)[-1] if rid else "", str(page), kind))


@log_call()
def extract_ma_sa(path: Path, *, site_id: str, doc_id: str, catalog: Catalog) -> tuple[AnalysisResult | None, AnalysisResult | None, list[ExtractedField]]:
    ma = sa = None
    for i, text in enumerate(pdf_pages_text(path), start=1):
        head = text.strip()[:200].upper()
        if "MOUNT ANALYSIS" in head:
            ma = _parse_page(text, "MA", site_id, doc_id, i, catalog)
        elif "STRUCTURAL ANALYSIS" in head:
            sa = _parse_page(text, "SA", site_id, doc_id, i, catalog)
    fields = []
    for r in (ma, sa):
        if r:
            fields.append(ExtractedField(doc_id, site_id, r.ref.page, f"{r.kind}:result", r.result, 0.98 if r.result else 0.0,
                                         "PDF_TEXT", needs_review=not r.result))
            fields.append(ExtractedField(doc_id, site_id, r.ref.page, f"{r.kind}:capacity_pct", r.capacity_pct, 0.98, "PDF_TEXT"))
            for m in r.modifications:
                fields.append(ExtractedField(doc_id, site_id, r.ref.page, f"{r.kind}:mod:{m['sector']}", m, 0.97, "PDF_TEXT",
                                             needs_review=m["kit_key"] is None))
    log.info("MA %s (%s%%), SA %s (%s%%), %d modifications", ma.result if ma else "-", ma.capacity_pct if ma else "-",
             sa.result if sa else "-", sa.capacity_pct if sa else "-", len(ma.modifications) if ma else 0, extra={"site_id": site_id})
    return ma, sa, fields
