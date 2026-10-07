"""BOM revisions: list, lines with traceability, changes vs REV 0, scoper edits (reason-coded and audited,
DRAFT only - approved/FBA revisions are immutable), workflow, and xlsx export."""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from api.deps import current_user, ref, repo, require, site_scope, workflow
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
