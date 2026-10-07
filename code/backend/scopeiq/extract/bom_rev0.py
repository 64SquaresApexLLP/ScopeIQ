"""REV 0 preliminary BOM (xlsx) extraction. Every row is matched to the catalog by manufacturer P/N first,
then customer P/N, then model text; unmatched rows are kept (catalog_key None) so the validator can flag them."""
from __future__ import annotations

from pathlib import Path

import openpyxl

from scopeiq.common.errors import ExtractionError
from scopeiq.common.logging import get_logger, log_call
from scopeiq.domain import ExtractedField, Rev0Line, sector_code
from scopeiq.reference.catalog import Catalog

log = get_logger(__name__)
REQUIRED = ("Sector", "Model", "Manufacturer P/N", "Design Qty", "Spare Qty", "Action")


@log_call()
def extract_rev0(path: Path, *, site_id: str, doc_id: str, catalog: Catalog) -> tuple[list[Rev0Line], dict, list[ExtractedField]]:
    try:
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"BOM {Path(path).name} could not be opened: {exc}", cause=exc) from exc
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [str(h or "").strip() for h in next(rows)]
    missing = [c for c in REQUIRED if c not in header]
    if missing:
        raise ExtractionError("REV 0 BOM is missing columns", details={"missing": missing, "file": Path(path).name})
    ix = {h: i for i, h in enumerate(header)}
    lines, fields, meta = [], [], {}
    for n, r in enumerate(rows, start=2):
        if not any(r):
            continue
        get = lambda c: r[ix[c]] if c in ix else None  # noqa: E731
        if not get("Model") and not get("Manufacturer P/N"):
            if r[0]:
                meta.setdefault("notes", []).append(str(r[0]))      # footer note rows
            continue
        pn, cpn, model = str(get("Manufacturer P/N") or ""), str(get("Customer P/N") or ""), str(get("Model") or "")
        cat = catalog.by_part_number(pn) or catalog.by_part_number(cpn) or catalog.by_model(model)
        score = 1.0 if cat else 0.0
        if not cat:
            cat, score = catalog.resolve(model)
        sec = str(get("Sector") or "Site")
        line = Rev0Line(row=n, sector="SITE" if sec.upper() == "SITE" else sector_code(sec), catalog_key=cat.key if cat else None,
                        model=model, mfr_pn=pn, customer_pn=cpn, design_qty=float(get("Design Qty") or 0),
                        spare_qty=float(get("Spare Qty") or 0), action=str(get("Action") or ""), rule_id=str(get("BOM Rule") or ""),
                        source=str(get("Source Drawing") or ""))
        lines.append(line)
        meta.setdefault("revision", get("Revision"))
        meta.setdefault("status", get("Status"))
        meta.setdefault("market", get("Market"))
        fields.append(ExtractedField(doc_id, site_id, f"row {n}", f"BOM:{line.sector}:{line.catalog_key or model}",
                                     {"design": line.design_qty, "spare": line.spare_qty}, 0.99 if score >= 0.99 else round(0.9 * score, 3),
                                     "XLSX", needs_review=cat is None or score < 0.99))
    wb.close()
    log.info("REV 0 BOM: %d lines (%d unmatched)", len(lines), sum(1 for l in lines if not l.catalog_key), extra={"site_id": site_id})
    return lines, meta, fields
