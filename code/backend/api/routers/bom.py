"""BOM revisions: list, lines with traceability, changes vs REV 0, scoper edits (reason-coded and audited,
DRAFT only - approved/FBA revisions are immutable), workflow, and xlsx export."""
import uuid
from pathlib import Path

import openpyxl
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from api.deps import check_site_scope, current_user, ref, repo, require, site_scope, workflow
from api.schemas import BomLineAddIn, BomLineEditIn, TransitionIn
from scopeiq.common.audit import AuditTrail
from scopeiq.common.errors import ImmutableRecordError, NotFound, ValidationError
from scopeiq.config import get_settings
from scopeiq.db.repository import now_iso
from scopeiq.domain import BomLine
from scopeiq.outputs.exports import write_bom_xlsx

router = APIRouter(prefix="/bom", tags=["bom"])


def _editable(rev: dict) -> None:
    if rev.get("LOCKED") or rev["STATUS"] != "DRAFT":
        raise ImmutableRecordError(f"{rev['REV_LABEL']} is {rev['STATUS']} and cannot be edited - create a new revision",
                                   details={"bom_rev_id": rev["BOM_REV_ID"], "status": rev["STATUS"]})


@router.get("/revisions")
def revisions_by_status(status: str | None = None, user: dict = Depends(current_user)):
    """Approval queues: e.g. IN_REVIEW for the reviewer, SP_REVIEW for the CX SP, SP_AGREED for Ericsson."""
    revs = repo().select("CORE.BOM_REVISION", {"STATUS": status} if status else None, order_by="SITE_ID, REV_NO")
    scope = site_scope(user)
    if scope:
        ok = {x["SITE_ID"] for x in repo().select("CORE.SITE", scope)}
        revs = [r for r in revs if r["SITE_ID"] in ok]
    return [r for r in revs if r["KIND"] != "TOOL_REV0"]


@router.get("/sites/{site_id}/revisions")
def revisions(site_id: str, user: dict = Depends(current_user)):
    revs = repo().select("CORE.BOM_REVISION", {"SITE_ID": site_id}, order_by="REV_NO")
    for r in revs:
        r["ACTIONS"] = [a["action"] for a in workflow().actions("BOM_REVISION", r["STATUS"], user["role"])] if r["KIND"] != "TOOL_REV0" else []
    return revs


def _find_site_bom_xlsx(r, site: dict, site_id: str, run_id: str | None) -> tuple[Path | None, dict]:
    """Locate the generated Excel BOM workbook for a site, returning (path, run_bom_meta)."""
    base = Path(get_settings().path("paths.output_dir")).resolve()
    run = r.select("CORE.PIPELINE_RUN", {"RUN_ID": run_id})[0] if run_id else None
    bom_meta = ((run or {}).get("SUMMARY") or {}).get("design", {}).get("bom") or {}
    rel = bom_meta.get("file") or ((run or {}).get("SUMMARY") or {}).get("files", {}).get("bom_xlsx")
    candidates = []
    if rel:
        candidates.append((base / rel).resolve())
    candidates.append((base / "sites" / site_id / "bom" / f"{site_id}_BOM.xlsx").resolve())
    for p in candidates:
        if base in p.parents and p.is_file():
            return p, bom_meta
    return None, bom_meta


def _read_xlsx_sheets(path: Path) -> list[dict]:
    """Read all sheets of an Excel workbook as column headers + JSON-safe row arrays."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheets = []
    try:
        for name in wb.sheetnames:
            ws = wb[name]
            all_rows = list(ws.iter_rows(values_only=True))
            if not all_rows:
                continue
            headers = [str(c) if c is not None else "" for c in all_rows[0]]
            # Trim trailing empty columns if any
            while headers and headers[-1] == "":
                headers.pop()
            col_count = len(headers)
            data_rows = []
            for row in all_rows[1:]:
                vals = list(row[:col_count])
                if any(v is not None and str(v).strip() != "" for v in vals):
                    data_rows.append([v if isinstance(v, (int, float, bool, str)) or v is None else str(v) for v in vals])
            sheets.append({"name": name, "columns": headers, "rows": data_rows})
    finally:
        wb.close()
    return sheets


@router.get("/sites/{site_id}/preview")
def site_bom_preview(site_id: str, user: dict = Depends(current_user)):
    """Return the generated BOM preview (Excel sheets + structured lines) for a site, or available=False if none yet."""
    site = check_site_scope(user, site_id)
    r = repo()
    bom_lines = r.select("CORE.BOM_OUTPUT_LINE", {"SITE_ID": site_id}, order_by="SECTOR, RULE_ID, CATALOG_KEY")
    run_id = bom_lines[0]["RUN_ID"] if bom_lines else site.get("LAST_RUN_ID")
    xlsx_path, bom_meta = _find_site_bom_xlsx(r, site, site_id, run_id)

    # Fallback: check if a generated BOM_REVISION exists when BOM_OUTPUT_LINE is empty
    rev_fallback = None
    if not bom_lines and not xlsx_path:
        revs = [x for x in r.select("CORE.BOM_REVISION", {"SITE_ID": site_id}, order_by="REV_NO DESC") if x.get("KIND") != "TOOL_REV0"]
        if revs:
            rev_fallback = revs[0]
            rev_lines = r.select("CORE.BOM_LINE", {"BOM_REV_ID": rev_fallback["BOM_REV_ID"]})
            cat = ref().catalog
            for l in rev_lines:
                it = cat.items.get(l["CATALOG_KEY"])
                bom_lines.append({
                    "LINE_ID": l["LINE_ID"],
                    "RUN_ID": rev_fallback.get("RUN_ID"),
                    "SITE_ID": site_id,
                    "MARKET": site.get("MARKET") or "",
                    "SECTOR": l.get("SECTOR"),
                    "TECHNOLOGY": it.technology if it else "",
                    "BAND": it.bands if it else "",
                    "CATEGORY": it.category if it else "",
                    "MANUFACTURER": it.manufacturer if it else "",
                    "MODEL": it.model if it else l.get("CATALOG_KEY"),
                    "MANUFACTURER_PN": it.mfr_pn if it else "",
                    "CUSTOMER_PN": it.customer_pn if it else "",
                    "DESCRIPTION": it.description if it else "",
                    "UOM": it.uom if it else "",
                    "DESIGN_QTY": l.get("DESIGN_QTY"),
                    "SPARE_QTY": l.get("SPARE_QTY"),
                    "TOTAL_QTY": l.get("TOTAL_QTY"),
                    "UNIT_COST_USD": (it.unit_cost if it else 0.0) if str(l.get("ACTION") or "").lower() == "install" else 0.0,
                    "TOTAL_COST_USD": round(((it.unit_cost if it else 0.0) if str(l.get("ACTION") or "").lower() == "install" else 0.0) * float(l.get("TOTAL_QTY") or 0.0), 2),
                    "SUPPLY": it.supply if it else "",
                    "ACTION": l.get("ACTION"),
                    "SOURCE": l.get("SOURCE"),
                    "DRAWING": "",
                    "RULE_ID": l.get("RULE_ID"),
                    "REVISION": rev_fallback.get("REV_LABEL"),
                    "STATUS": rev_fallback.get("STATUS"),
                    "CATALOG_KEY": l.get("CATALOG_KEY"),
                })

    if not bom_lines and not xlsx_path:
        return {
            "available": False,
            "site_id": site_id,
            "run_id": None,
            "file_name": None,
            "download_path": None,
            "summary": {},
            "sheets": [],
            "lines": [],
            "issues": [],
        }

    sheets = _read_xlsx_sheets(xlsx_path) if xlsx_path else []
    if not sheets and bom_lines:
        from scopeiq.bom.export import COLUMNS as _BOM_COLS
        from scopeiq.domain import SECTOR_NAMES

        sheets = [{
            "name": site_id,
            "columns": list(_BOM_COLS),
            "rows": [
                [
                    l.get("SITE_ID"), l.get("MARKET"), SECTOR_NAMES.get(l.get("SECTOR"), l.get("SECTOR") or "Site"),
                    l.get("TECHNOLOGY"), l.get("BAND"), l.get("CATEGORY"), l.get("MANUFACTURER"), l.get("MODEL"),
                    l.get("MANUFACTURER_PN"), l.get("CUSTOMER_PN"), l.get("DESCRIPTION"), l.get("UOM"),
                    l.get("DESIGN_QTY"), l.get("SPARE_QTY"), l.get("TOTAL_QTY"),
                    l.get("UNIT_COST_USD", 0.0) or 0.0, l.get("TOTAL_COST_USD", 0.0) or 0.0,
                    l.get("SUPPLY"), l.get("ACTION"),
                    l.get("SOURCE"), l.get("DRAWING"), l.get("RULE_ID"), l.get("REVISION"), l.get("STATUS"),
                ]
                for l in bom_lines
            ],
        }]

    issues = bom_meta.get("issue_list") or []
    install_lines = [l for l in bom_lines if str(l.get("ACTION") or "").lower() == "install"]
    remove_lines = [l for l in bom_lines if str(l.get("ACTION") or "").lower() == "remove"]
    needs_review = sum(1 for l in bom_lines if "review" in str(l.get("STATUS") or "").lower() or "not in" in str(l.get("STATUS") or "").lower())
    total_material_cost = round(sum(float(l.get("TOTAL_COST_USD") or 0.0) for l in install_lines), 2)

    download_path = (
        f"/bom/sites/{site_id}/export"
        if xlsx_path
        else (f"/bom/revisions/{rev_fallback['BOM_REV_ID']}/export" if rev_fallback else None)
    )

    return {
        "available": True,
        "site_id": site_id,
        "run_id": run_id,
        "file_name": xlsx_path.name if xlsx_path else f"{site_id}_BOM.xlsx",
        "download_path": download_path,
        "summary": {
            "lines": len(bom_lines) or (len(sheets[0]["rows"]) if sheets else 0),
            "install_lines": len(install_lines),
            "remove_lines": len(remove_lines),
            "install_qty": round(sum(float(l.get("TOTAL_QTY") or 0) for l in install_lines), 2),
            "remove_qty": round(sum(float(l.get("TOTAL_QTY") or 0) for l in remove_lines), 2),
            "needs_review": needs_review,
            "issues_count": len(issues),
            "total_material_cost": total_material_cost,
            "revision": bom_meta.get("revision") or (rev_fallback.get("REV_LABEL") if rev_fallback else None),
        },
        "sheets": sheets,
        "lines": bom_lines,
        "issues": issues,
    }


@router.get("/sites/{site_id}/export")
def export_site_bom(site_id: str, user: dict = Depends(current_user)):
    """Download the generated Excel BOM workbook for a site."""
    site = check_site_scope(user, site_id)
    r = repo()
    bom_lines = r.select("CORE.BOM_OUTPUT_LINE", {"SITE_ID": site_id}, limit=1)
    run_id = bom_lines[0]["RUN_ID"] if bom_lines else site.get("LAST_RUN_ID")
    xlsx_path, _ = _find_site_bom_xlsx(r, site, site_id, run_id)
    if not xlsx_path:
        raise NotFound(f"BOM Excel workbook is not available for site {site_id}")
    return FileResponse(
        xlsx_path,
        filename=xlsx_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/revisions/{rev_id}")
def revision(rev_id: str, user: dict = Depends(current_user)):
    r = repo().get("CORE.BOM_REVISION", BOM_REV_ID=rev_id)
    r["ACTIONS"] = workflow().actions("BOM_REVISION", r["STATUS"], user["role"]) if r["KIND"] != "TOOL_REV0" else []
    r["EDITABLE"] = not r.get("LOCKED") and r["STATUS"] == "DRAFT"
    r["HISTORY"] = workflow().history("BOM_REVISION", rev_id)
    return r


@router.get("/revisions/{rev_id}/lines")
def lines(rev_id: str, user: dict = Depends(current_user)):
    cat = ref().catalog
    rows = repo().select("CORE.BOM_LINE", {"BOM_REV_ID": rev_id})
    for l in rows:
        it = cat.items.get(l["CATALOG_KEY"])
        l["MODEL"], l["DESCRIPTION"], l["UOM"], l["MFR_PN"] = (it.model, it.description, it.uom, it.mfr_pn) if it else (l["CATALOG_KEY"], "", "", "")
        l["APPROVED_PART"] = bool(it and it.approved)
    order = {"A": 0, "B": 1, "C": 2, "D": 3, "SITE": 9}
    return sorted(rows, key=lambda l: (order.get(l["SECTOR"], 5), l["ACTION"] != "Install", l["RULE_ID"] or "", l["CATALOG_KEY"]))


@router.get("/revisions/{rev_id}/changes")
def changes(rev_id: str, user: dict = Depends(current_user)):
    return repo().select("CORE.BOM_CHANGE", {"TO_REV_ID": rev_id})


@router.patch("/lines/{line_id}")
def edit_line(line_id: str, body: BomLineEditIn, user: dict = Depends(require("SCOPER", "REVIEWER"))):
    r = repo()
    line = r.get("CORE.BOM_LINE", LINE_ID=line_id)
    _editable(r.get("CORE.BOM_REVISION", BOM_REV_ID=line["BOM_REV_ID"]))
    if body.reason_code not in ref().reason_codes:
        raise ValidationError(f"Unknown reason code {body.reason_code}")
    upd = {"DESIGN_QTY": line["DESIGN_QTY"] if body.design_qty is None else body.design_qty,
           "SPARE_QTY": line["SPARE_QTY"] if body.spare_qty is None else body.spare_qty}
    upd.update(TOTAL_QTY=upd["DESIGN_QTY"] + upd["SPARE_QTY"], REASON_CODE=body.reason_code, EDITED_BY=user["sub"], EDITED_AT=now_iso())
    r.update("CORE.BOM_LINE", upd, {"LINE_ID": line_id})
    AuditTrail.record(entity_type="BOM_LINE", entity_id=line_id, action="EDIT_QTY", before={k: line[k] for k in ("DESIGN_QTY", "SPARE_QTY")},
                      after=upd, reason_code=body.reason_code, comment=body.comment, site_id=line["SITE_ID"], source="api")
    return r.get("CORE.BOM_LINE", LINE_ID=line_id)


@router.post("/revisions/{rev_id}/lines")
def add_line(rev_id: str, body: BomLineAddIn, user: dict = Depends(require("SCOPER", "REVIEWER"))):
    r = repo()
    rev = r.get("CORE.BOM_REVISION", BOM_REV_ID=rev_id)
    _editable(rev)
    if body.catalog_key not in ref().catalog:
        raise NotFound(f"Catalog key {body.catalog_key} not found")
    row = {"LINE_ID": uuid.uuid4().hex, "BOM_REV_ID": rev_id, "SITE_ID": rev["SITE_ID"], "SECTOR": body.sector, "CATALOG_KEY": body.catalog_key,
           "DESIGN_QTY": body.design_qty, "SPARE_QTY": body.spare_qty, "TOTAL_QTY": body.design_qty + body.spare_qty, "ACTION": body.action,
           "RULE_ID": "MANUAL", "SOURCE": f"Manual line by {user['sub']}", "REASON_CODE": body.reason_code, "TRACE": {"manual": True},
           "EDITED_BY": user["sub"], "EDITED_AT": now_iso()}
    r.insert("CORE.BOM_LINE", [row])
    AuditTrail.record(entity_type="BOM_LINE", entity_id=row["LINE_ID"], action="CREATE", after=row, reason_code=body.reason_code,
                      comment=body.comment, site_id=rev["SITE_ID"], source="api")
    return row


@router.delete("/lines/{line_id}")
def delete_line(line_id: str, reason_code: str, comment: str | None = None, user: dict = Depends(require("SCOPER", "REVIEWER"))):
    r = repo()
    line = r.get("CORE.BOM_LINE", LINE_ID=line_id)
    _editable(r.get("CORE.BOM_REVISION", BOM_REV_ID=line["BOM_REV_ID"]))
    AuditTrail.record(entity_type="BOM_LINE", entity_id=line_id, action="DELETE", before=line, reason_code=reason_code, comment=comment,
                      site_id=line["SITE_ID"], source="api")
    r.delete_where("CORE.BOM_LINE", {"LINE_ID": line_id})
    return {"deleted": line_id}


@router.post("/revisions/{rev_id}/transition")
def transition(rev_id: str, body: TransitionIn, user: dict = Depends(current_user)):
    return workflow().transition("BOM_REVISION", rev_id, body.action, reason_code=body.reason_code, comment=body.comment)


@router.get("/revisions/{rev_id}/export")
def export(rev_id: str, user: dict = Depends(current_user)):
    r = repo()
    rev = r.get("CORE.BOM_REVISION", BOM_REV_ID=rev_id)
    rows = r.select("CORE.BOM_LINE", {"BOM_REV_ID": rev_id})
    lines_ = [BomLine(x["SITE_ID"], x["SECTOR"], x["CATALOG_KEY"], x["DESIGN_QTY"], x["SPARE_QTY"] or 0, x["ACTION"], x["RULE_ID"] or "",
                      x["SOURCE"] or "", x["PARENT_KEY"] or "", x["REASON_CODE"] or "") for x in rows if x["CATALOG_KEY"] in ref().catalog]
    ch = [{"sector": c["SECTOR"], "part": c["CATALOG_KEY"], "action": c["ACTION"], "rev0_qty": c["FROM_QTY"], "rev1_qty": c["TO_QTY"],
           "delta": c["DELTA"], "reasons": c["REASONS"] or []} for c in r.select("CORE.BOM_CHANGE", {"TO_REV_ID": rev_id})]
    site = r.get("CORE.SITE", SITE_ID=rev["SITE_ID"])
    path = Path(get_settings().path("paths.output_dir")) / "exports" / f"{rev_id}.xlsx"
    write_bom_xlsx(path, rev["SITE_ID"], site.get("MARKET") or "", lines_, ref(), rev["REV_LABEL"], rev["STATUS"], ch)
    return FileResponse(path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
