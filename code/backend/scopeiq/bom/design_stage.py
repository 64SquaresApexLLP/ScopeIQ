"""Stage 5: read the RFDS and the MA/SA report of the site and turn them into structured design items.

For each document the format is checked first (Excel workbook or PDF), the matching reader is chosen, and the values are read in this
run. The result is a list of items (one per piece of equipment or mount change) with the catalog details of the model, stored in
CORE.DESIGN_ITEM. The BOM stage then works from these items; it never reads an earlier run's results.

The run stops here, with the reason, when the RFDS is missing or cannot be read (there is no design to price without it), or when an
MA/SA report is present but cannot be read (the mount reinforcement would silently be missing). A site with no MA/SA report at all
continues, and the BOM says that mount reinforcement was not evaluated.
"""
from __future__ import annotations

from pathlib import Path

from scopeiq.bom.engine import _source
from scopeiq.bom.rulebook import Rulebook
from scopeiq.common.errors import ExtractionError, MissingDataError
from scopeiq.common.logging import get_logger
from scopeiq.db.repository import now_iso
from scopeiq.domain import SECTOR_NAMES, SiteFacts
from scopeiq.engine.design import SiteModel
from scopeiq.extract import ma_sa, rfds
from scopeiq.common.ids import stable_id

log = get_logger(__name__)

READERS = {"xlsx": "Excel workbook reader", "xlsm": "Excel workbook reader", "pdf": "PDF text reader"}


def _doc_info(d) -> dict:
    ext = str(d.file_format or Path(d.file_name).suffix.lstrip(".")).lower()
    return {"doc_type": d.doc_type, "file_name": d.file_name, "format": ext.upper(), "revision": d.revision, "status": d.status,
            "tool": READERS.get(ext, "no reader for this format")}


def read_design_documents(facts: SiteFacts, catalog, required: list[str]) -> list[dict]:
    """Read the RFDS and the MA/SA report into `facts`. Returns what was found and how it was read, for the stage's card."""
    paths = facts.site.get("doc_paths", {})
    out: list[dict] = []
    for doc_type, label in (("RFDS", "RFDS"), ("MA_SA", "MA/SA report")):
        d = facts.doc(doc_type)
        if d is None:
            if doc_type in required:
                raise MissingDataError(f"The {label} for site {facts.site_id} is missing. Upload it to the site's SharePoint folder, then run the pipeline again.",
                                       details={"site_id": facts.site_id, "missing": doc_type})
            out.append({"doc_type": doc_type, "file_name": "", "format": "", "revision": "", "status": "MISSING", "tool": "",
                        "note": "No report found: mount reinforcement was not evaluated" if doc_type == "MA_SA" else "Not found"})
            continue
        info = _doc_info(d)
        path = Path(paths.get(d.doc_id) or "")
        if info["tool"].startswith("no reader") or not path.is_file():
            raise ExtractionError(f"The {label} {d.file_name} cannot be read: "
                                  f"{'the file is not on disk' if not path.is_file() else 'format .' + info['format'].lower() + ' is not supported (Excel or PDF expected)'}.",
                                  details={"site_id": facts.site_id, "source": doc_type})
        if doc_type == "RFDS":
            r = rfds.extract_rfds(path, site_id=facts.site_id, doc_id=d.doc_id, catalog=catalog)
            if not r.final and not r.existing:
                raise ExtractionError(f"The RFDS {d.file_name} was read but lists no equipment. Nothing to price.", details={"site_id": facts.site_id, "source": "RFDS"})
            facts.rfds_revision, facts.rfds_date, facts.rfds_history = r.revision, r.date, r.history
            facts.rfds_existing, facts.rfds_final = r.existing, r.final
            facts.basebands, facts.dc_load_added_w = r.basebands, r.dc_load_w
            facts.fields += r.fields
            for k, v in (r.site or {}).items():
                facts.site.setdefault(f"rfds_{k.lower().replace(' (ft)', '_ft').replace(' ', '_')}", v)
            info.update(template=r.template, values=len(r.fields), revision=r.revision or info["revision"])
        else:
            ma, sa, fields = ma_sa.extract_ma_sa(path, site_id=facts.site_id, doc_id=d.doc_id, catalog=catalog)
            if ma is None and sa is None:
                raise ExtractionError(f"The MA/SA report {d.file_name} was read but holds no analysis result.", details={"site_id": facts.site_id, "source": "MA_SA"})
            facts.ma, facts.sa = ma, sa
            facts.fields += fields
            info.update(values=len(fields), result=getattr(ma, "result", None) or getattr(sa, "result", None))
        out.append(info)
    return out


def design_items(m: SiteModel, rb: Rulebook, run_id: str) -> list[dict]:
    """One row per piece of equipment and per mount change, with the catalog details printed beside it."""
    rows: list[dict] = []
    ts = now_iso()

    def row(sector, position, kind, key, model_text, action, qty, ref, **extra):
        it = rb.catalog.items.get(key) if key else None
        src, drawing = _source([ref])
        rows.append({"ITEM_ID": stable_id("DSN", run_id, len(rows)), "RUN_ID": run_id, "SITE_ID": m.site_id, "MARKET": m.market, "SECTOR": sector,
                     "POSITION": position, "KIND": kind, "TECHNOLOGY": (it.technology if it else "") or "", "BAND": (it.bands if it else "") or extra.get("bands", ""),
                     "CATEGORY": it.category if it else "", "SUBCATEGORY": it.subcategory if it else "", "MANUFACTURER": it.manufacturer if it else "",
                     "MODEL": it.model if it else model_text, "MANUFACTURER_PN": it.mfr_pn if it else "", "CUSTOMER_PN": it.customer_pn if it else "",
                     "DESCRIPTION": it.description if it else "Model not found in the material catalog", "UOM": it.uom if it else "EA",
                     "SUPPLY": it.supply if it else "", "ACTION": action, "QTY": qty, "RAD_CENTER_FT": extra.get("rad_center_ft"),
                     "AZIMUTH_DEG": extra.get("azimuth_deg"), "CATALOG_KEY": key or "", "MATCH_STATUS": "Matched" if it else "Not in catalog",
                     "SOURCE": src, "DRAWING": drawing, "SOURCE_DOC_ID": ref.doc_id if ref else "", "CONFIDENCE": extra.get("confidence"), "CREATED_AT": ts})

    for d in m.devices:
        row(d.sector, d.position, d.kind, d.key, d.model_text, {"New": "Install", "Remove": "Remove"}.get(d.status, "Existing"), 1.0, d.ref,
            bands=d.bands, rad_center_ft=d.rad_center_ft)
    for bb in m.basebands:
        row("SITE", None, "baseband", bb, "", "Install", 1.0, next((d.ref for d in m.devices if d.basis == "RFDS" and d.ref), None))
    for model in m.unmatched_basebands:
        row("SITE", None, "baseband", None, model, "Install", 1.0, None)
    for mod in m.ma_mods:
        row(str(mod.get("sector") or "SITE"), None, "mount reinforcement", mod.get("kit_key"), str(mod.get("text") or mod.get("kit_key") or ""), "Install",
            float(mod.get("qty") or 0), m.refs.get("ma"))
    return rows


def sector_label(code: str) -> str:
    return SECTOR_NAMES.get(code, "Site")
