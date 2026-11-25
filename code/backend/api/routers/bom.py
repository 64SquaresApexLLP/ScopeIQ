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
from scopeiq.services import bom_revisions

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
    check_site_scope(user, site_id)
    revs = repo().select("CORE.BOM_REVISION", {"SITE_ID": site_id}, order_by="REV_NO")
    for r in revs:
        r["ACTIONS"] = [a["action"] for a in workflow().actions("BOM_REVISION", r["STATUS"], user["role"])] if r["KIND"] != "TOOL_REV0" else []
    return revs


def _find_site_bom_xlsx(r, site: dict, site_id: str, run_id: str | None) -> tuple[Path | None, dict]:
    """Locate the generated Excel BOM workbook for a site, returning (path, run_bom_meta)."""
    base = Path(get_settings().path("paths.output_dir")).resolve()
    runs = r.select("CORE.PIPELINE_RUN", {"RUN_ID": run_id}) if run_id else []
    run = runs[0] if runs else None
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


def _pick(r, site_id: str, rev: str | None) -> dict | None:
    """The revision asked for, else the site's latest generated one."""
    revs = bom_revisions.generated(r, site_id)
    return (next((x for x in revs if x["BOM_REV_ID"] == rev), None) if rev else None) or (revs[-1] if revs else None)


def _sheet_rows(bom_lines: list[dict]) -> list[list]:
    from scopeiq.domain import SECTOR_NAMES
    return [[l.get("SITE_ID"), l.get("MARKET"), SECTOR_NAMES.get(l.get("SECTOR"), l.get("SECTOR") or "Site"), l.get("TECHNOLOGY"), l.get("BAND"), l.get("CATEGORY"),
             l.get("MANUFACTURER"), l.get("MODEL"), l.get("MANUFACTURER_PN"), l.get("CUSTOMER_PN"), l.get("DESCRIPTION"), l.get("UOM"),
             l.get("DESIGN_QTY"), l.get("SPARE_QTY"), l.get("TOTAL_QTY"), l.get("UNIT_COST_USD", 0.0) or 0.0, l.get("TOTAL_COST_USD", 0.0) or 0.0,
             l.get("SUPPLY"), l.get("ACTION"), l.get("SOURCE"), l.get("DRAWING"), l.get("RULE_ID"), l.get("REVISION"), l.get("STATUS")] for l in bom_lines]


def _export_name(site_id: str, rev: dict | None) -> str:
    return f"{site_id}_BOM" + (f"_{rev['REV_LABEL'].replace(' ', '')}" if rev else "") + ("_FBA" if rev and rev.get("STATUS") == "FBA" else "") + ".xlsx"


@router.get("/sites/{site_id}/preview")
def site_bom_preview(site_id: str, rev: str | None = None, user: dict = Depends(current_user)):
    """The BOM of a site as a table: the revision asked for, else the latest. available=False if there is none yet."""
    from scopeiq.bom.export import COLUMNS as _BOM_COLS
    site = check_site_scope(user, site_id)
    r = repo()
    picked = _pick(r, site_id, rev)
    bom_lines = bom_revisions.lines_of(r, site_id, picked)
    none = {"available": False, "site_id": site_id, "run_id": None, "file_name": None, "download_path": None, "summary": {}, "sheets": [], "lines": [], "issues": []}
    if not bom_lines:
        return none
    run_id = (picked or {}).get("RUN_ID") or site.get("LAST_RUN_ID")
    _, bom_meta = _find_site_bom_xlsx(r, site, site_id, run_id)
    issues = bom_meta.get("issue_list") or []
    install_lines = [l for l in bom_lines if str(l.get("ACTION") or "").lower() == "install"]
    remove_lines = [l for l in bom_lines if str(l.get("ACTION") or "").lower() == "remove"]
    needs_review = sum(1 for l in bom_lines if "review" in str(l.get("STATUS") or "").lower() or "not in" in str(l.get("STATUS") or "").lower())
    label = (picked or {}).get("REV_LABEL")
    return {
        "available": True, "site_id": site_id, "run_id": run_id, "rev_id": (picked or {}).get("BOM_REV_ID"),
        "file_name": _export_name(site_id, picked),
        "download_path": f"/bom/sites/{site_id}/export" + (f"?rev={picked['BOM_REV_ID']}" if picked else ""),
        "summary": {"lines": len(bom_lines), "install_lines": len(install_lines), "remove_lines": len(remove_lines),
                    "install_qty": round(sum(float(l.get("TOTAL_QTY") or 0) for l in install_lines), 2),
                    "remove_qty": round(sum(float(l.get("TOTAL_QTY") or 0) for l in remove_lines), 2),
                    "needs_review": needs_review, "issues_count": len(issues),
                    "total_material_cost": round(sum(float(l.get("TOTAL_COST_USD") or 0.0) for l in install_lines), 2),
                    "revision": label or bom_meta.get("revision")},
        "sheets": [{"name": site_id, "columns": list(_BOM_COLS), "rows": _sheet_rows(bom_lines)}],
        "lines": bom_lines, "issues": issues,
    }


def _generate_bom_xlsx_from_lines(site_id: str, bom_lines: list[dict], target_path: Path, rev: dict | None = None) -> Path:
    from scopeiq.bom.export import COLUMNS as _BOM_COLS, WIDTHS, HEADER
    from scopeiq.domain import SECTOR_NAMES
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = site_id
    ws.append(list(_BOM_COLS))
    for l in bom_lines:
        ws.append([
            l.get("SITE_ID"), l.get("MARKET"), SECTOR_NAMES.get(l.get("SECTOR"), l.get("SECTOR") or "Site"),
            l.get("TECHNOLOGY"), l.get("BAND"), l.get("CATEGORY"), l.get("MANUFACTURER"), l.get("MODEL"),
            l.get("MANUFACTURER_PN"), l.get("CUSTOMER_PN"), l.get("DESCRIPTION"), l.get("UOM"),
            l.get("DESIGN_QTY"), l.get("SPARE_QTY"), l.get("TOTAL_QTY"),
            l.get("UNIT_COST_USD", 0.0) or 0.0, l.get("TOTAL_COST_USD", 0.0) or 0.0,
            l.get("SUPPLY"), l.get("ACTION"),
            l.get("SOURCE"), l.get("DRAWING"), l.get("RULE_ID"), l.get("REVISION"), l.get("STATUS"),
        ])
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), HEADER
    ws.freeze_panes = "A2"
    for col, w in zip("ABCDEFGHIJKLMNOPQRSTUVWX", WIDTHS):
        ws.column_dimensions[col].width = w
    for r_idx in range(2, len(bom_lines) + 2):
        ws[f"P{r_idx}"].number_format = "$#,##0.00"
        ws[f"Q{r_idx}"].number_format = "$#,##0.00"
    if rev:                      # the upload file carries its status: which revision it is, and who approved it when
        st = wb.create_sheet("Status")
        for k, v in (("Site", site_id), ("Revision", rev.get("REV_LABEL")), ("Status", rev.get("STATUS")), ("Locked", "Yes" if rev.get("LOCKED") else "No"),
                     ("Generated", rev.get("CREATED_AT")), ("Approved by", rev.get("APPROVED_BY")), ("Approved on", rev.get("APPROVED_AT"))):
            st.append([k, v])
        st.column_dimensions["A"].width, st.column_dimensions["B"].width = 16, 36
    target_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(target_path)
    return target_path


@router.get("/sites/{site_id}/export")
def export_site_bom(site_id: str, rev: str | None = None, user: dict = Depends(current_user)):
    """Download the BOM of a site as an Excel file: the revision asked for, else the latest. An approved (FBA) one is the file to upload."""
    check_site_scope(user, site_id)
    r = repo()
    picked = _pick(r, site_id, rev)
    bom_lines = bom_revisions.lines_of(r, site_id, picked)
    if not bom_lines:
        raise NotFound(f"BOM Excel workbook is not available for site {site_id}")
    base = Path(get_settings().path("paths.output_dir")).resolve()
    xlsx_path = _generate_bom_xlsx_from_lines(site_id, bom_lines, base / "exports" / _export_name(site_id, picked), picked)
    return FileResponse(xlsx_path, filename=xlsx_path.name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


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
    if not rows:                 # lines made by the staged pipeline already carry the part details
        rev = repo().get("CORE.BOM_REVISION", BOM_REV_ID=rev_id)
        rows = bom_revisions.lines_of(repo(), rev["SITE_ID"], rev)
    for l in rows:
        it = cat.items.get(l["CATALOG_KEY"])
        l["MODEL"] = l.get("MODEL") or (it.model if it else l["CATALOG_KEY"])
        l["DESCRIPTION"] = l.get("DESCRIPTION") or (it.description if it else "")
        l["UOM"] = l.get("UOM") or (it.uom if it else "")
        l["MFR_PN"] = l.get("MANUFACTURER_PN") or (it.mfr_pn if it else "")
        l["APPROVED_PART"] = bool(it and it.approved)
    order = {"A": 0, "B": 1, "C": 2, "D": 3, "SITE": 9}
    return sorted(rows, key=lambda l: (order.get(l["SECTOR"], 5), l["ACTION"] != "Install", l["RULE_ID"] or "", l["CATALOG_KEY"] or ""))


@router.get("/revisions/{rev_id}/changes")
def changes(rev_id: str, user: dict = Depends(current_user)):
    return repo().select("CORE.BOM_CHANGE", {"TO_REV_ID": rev_id})


OUT = "CORE.BOM_OUTPUT_LINE"
EDITORS = ("SCOPER", "REVIEWER")


def _find_line(r, line_id: str) -> tuple[str, dict]:
    """A BOM line is in the staged pipeline's table, or (older revisions) in the revision line table."""
    for table in (OUT, "CORE.BOM_LINE"):
        found = r.select(table, {"LINE_ID": line_id}, limit=1)
        if found:
            return table, found[0]
    raise NotFound(f"BOM line {line_id} not found")


def _revision_of(r, table: str, line: dict) -> dict:
    if line.get("BOM_REV_ID"):
        return r.get("CORE.BOM_REVISION", BOM_REV_ID=line["BOM_REV_ID"])
    return bom_revisions.ensure(r, line["SITE_ID"], "system")        # a line made before revisions were tracked: give the site its REV 1 now


@router.patch("/lines/{line_id}")
def edit_line(line_id: str, body: BomLineEditIn, user: dict = Depends(require(*EDITORS))):
    r = repo()
    table, line = _find_line(r, line_id)
    rev = _revision_of(r, table, line)
    _editable(rev)
    if body.reason_code not in ref().reason_codes:
        raise ValidationError(f"Unknown reason code {body.reason_code}")
    design = float(line["DESIGN_QTY"] if body.design_qty is None else body.design_qty)
    spare = float((line["SPARE_QTY"] or 0) if body.spare_qty is None else body.spare_qty)
    upd = {"DESIGN_QTY": design, "SPARE_QTY": spare, "TOTAL_QTY": design + spare, "REASON_CODE": body.reason_code, "EDITED_BY": user["sub"], "EDITED_AT": now_iso()}
    if table == OUT:
        upd["TOTAL_COST_USD"] = round((design + spare) * float(line.get("UNIT_COST_USD") or 0), 2) if str(line.get("ACTION") or "").lower() == "install" else 0.0
    r.update(table, upd, {"LINE_ID": line_id})
    AuditTrail.record(entity_type="BOM_LINE", entity_id=line_id, action="EDIT_QTY", before={k: line[k] for k in ("DESIGN_QTY", "SPARE_QTY")},
                      after=upd, reason_code=body.reason_code, comment=body.comment, site_id=line["SITE_ID"], source="api")
    if table == OUT:
        bom_revisions.finish(r, line["SITE_ID"], rev)
    return r.get(table, LINE_ID=line_id)


@router.post("/revisions/{rev_id}/lines")
def add_line(rev_id: str, body: BomLineAddIn, user: dict = Depends(require(*EDITORS))):
    r = repo()
    rev = r.get("CORE.BOM_REVISION", BOM_REV_ID=rev_id)
    _editable(rev)
    if body.catalog_key not in ref().catalog:
        raise NotFound(f"Catalog key {body.catalog_key} not found")
    if body.reason_code not in ref().reason_codes:
        raise ValidationError(f"Unknown reason code {body.reason_code}")
    staged = bool(r.select(OUT, {"BOM_REV_ID": rev_id}, limit=1)) or not r.select("CORE.BOM_LINE", {"BOM_REV_ID": rev_id}, limit=1)
    if staged:
        it = ref().catalog.items[body.catalog_key]
        install = body.action.lower() == "install"
        total = body.design_qty + body.spare_qty
        row = {"LINE_ID": uuid.uuid4().hex, "BOM_REV_ID": rev_id, "RUN_ID": rev.get("RUN_ID"), "SITE_ID": rev["SITE_ID"], "SECTOR": body.sector, "TECHNOLOGY": it.technology,
               "BAND": ", ".join(it.bands) if isinstance(it.bands, (list, tuple)) else str(it.bands or ""), "CATEGORY": it.category, "SUBCATEGORY": it.subcategory,
               "MANUFACTURER": it.manufacturer, "MODEL": it.model, "MANUFACTURER_PN": it.mfr_pn, "CUSTOMER_PN": it.customer_pn, "DESCRIPTION": it.description,
               "UOM": it.uom, "DESIGN_QTY": body.design_qty, "SPARE_QTY": body.spare_qty, "TOTAL_QTY": total, "UNIT_COST_USD": it.unit_cost if install else 0.0,
               "TOTAL_COST_USD": round(total * float(it.unit_cost or 0), 2) if install else 0.0, "SUPPLY": it.supply, "ACTION": body.action, "SOURCE": f"Added by {user['sub']}",
               "RULE_ID": "MANUAL", "STATUS": "Added", "CATALOG_KEY": body.catalog_key, "CREATED_AT": now_iso(), "REASON_CODE": body.reason_code,
               "EDITED_BY": user["sub"], "EDITED_AT": now_iso()}
        r.insert(OUT, [row])
    else:
        row = {"LINE_ID": uuid.uuid4().hex, "BOM_REV_ID": rev_id, "SITE_ID": rev["SITE_ID"], "SECTOR": body.sector, "CATALOG_KEY": body.catalog_key,
               "DESIGN_QTY": body.design_qty, "SPARE_QTY": body.spare_qty, "TOTAL_QTY": body.design_qty + body.spare_qty, "ACTION": body.action,
               "RULE_ID": "MANUAL", "SOURCE": f"Manual line by {user['sub']}", "REASON_CODE": body.reason_code, "TRACE": {"manual": True},
               "EDITED_BY": user["sub"], "EDITED_AT": now_iso()}
        r.insert("CORE.BOM_LINE", [row])
    AuditTrail.record(entity_type="BOM_LINE", entity_id=row["LINE_ID"], action="CREATE", after=row, reason_code=body.reason_code,
                      comment=body.comment, site_id=rev["SITE_ID"], source="api")
    if staged:
        bom_revisions.finish(r, rev["SITE_ID"], rev)
    return row


@router.delete("/lines/{line_id}")
def delete_line(line_id: str, reason_code: str, comment: str | None = None, user: dict = Depends(require(*EDITORS))):
    r = repo()
    table, line = _find_line(r, line_id)
    rev = _revision_of(r, table, line)
    _editable(rev)
    if reason_code not in ref().reason_codes:
        raise ValidationError(f"Unknown reason code {reason_code}")
    AuditTrail.record(entity_type="BOM_LINE", entity_id=line_id, action="DELETE", before=line, reason_code=reason_code, comment=comment,
                      site_id=line["SITE_ID"], source="api")
    r.delete_where(table, {"LINE_ID": line_id})
    if table == OUT:
        bom_revisions.note_removal(r, rev, line, reason_code)
        bom_revisions.finish(r, line["SITE_ID"], rev)
    return {"deleted": line_id}


@router.post("/sites/{site_id}/next-revision")
def next_revision(site_id: str, user: dict = Depends(require(*EDITORS))):
    """Start the next BOM revision from the current one, so it can be changed (with a reason for each change) and sent again."""
    site = check_site_scope(user, site_id)
    if (site.get("WORKFLOW_STATE") or "") not in ("IN_SCOPING", "REWORK"):
        raise ValidationError("A new revision can be started only while the site is with the scoping team")
    rev = bom_revisions.start_next(repo(), site_id, user["sub"])
    AuditTrail.record(entity_type="BOM_REVISION", entity_id=rev["BOM_REV_ID"], action="CREATE_REVISION", after=rev, site_id=site_id, source="api")
    return rev


@router.post("/revisions/{rev_id}/transition")
def transition(rev_id: str, body: TransitionIn, user: dict = Depends(current_user)):
    return workflow().transition("BOM_REVISION", rev_id, body.action, reason_code=body.reason_code, comment=body.comment)


@router.get("/revisions/{rev_id}/export")
def export(rev_id: str, user: dict = Depends(current_user)):
    r = repo()
    rev = r.get("CORE.BOM_REVISION", BOM_REV_ID=rev_id)
    if not r.select("CORE.BOM_LINE", {"BOM_REV_ID": rev_id}, limit=1):
        out = bom_revisions.lines_of(r, rev["SITE_ID"], rev)
        path = Path(get_settings().path("paths.output_dir")) / "exports" / _export_name(rev["SITE_ID"], rev)
        return FileResponse(_generate_bom_xlsx_from_lines(rev["SITE_ID"], out, path, rev), filename=path.name,
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    rows = r.select("CORE.BOM_LINE", {"BOM_REV_ID": rev_id})
    lines_ = [BomLine(x["SITE_ID"], x["SECTOR"], x["CATALOG_KEY"], x["DESIGN_QTY"], x["SPARE_QTY"] or 0, x["ACTION"], x["RULE_ID"] or "",
                      x["SOURCE"] or "", x["PARENT_KEY"] or "", x["REASON_CODE"] or "") for x in rows if x["CATALOG_KEY"] in ref().catalog]
    ch = [{"sector": c["SECTOR"], "part": c["CATALOG_KEY"], "action": c["ACTION"], "rev0_qty": c["FROM_QTY"], "rev1_qty": c["TO_QTY"],
           "delta": c["DELTA"], "reasons": c["REASONS"] or []} for c in r.select("CORE.BOM_CHANGE", {"TO_REV_ID": rev_id})]
    site = r.get("CORE.SITE", SITE_ID=rev["SITE_ID"])
    path = Path(get_settings().path("paths.output_dir")) / "exports" / f"{rev_id}.xlsx"
    write_bom_xlsx(path, rev["SITE_ID"], site.get("MARKET") or "", lines_, ref(), rev["REV_LABEL"], rev["STATUS"], ch)
    return FileResponse(path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
