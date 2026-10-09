"""Redlines and the red-marked CD PDFs; RFIs with answers. Both move through the workflow."""
from fastapi import APIRouter, Depends

from api.deps import check_site_scope, current_user, pipeline, repo, require, site_scope, workflow
from api.schemas import RfiAnswerIn, TransitionIn
from scopeiq.common.errors import ValidationError
from scopeiq.db.repository import now_iso

router = APIRouter(tags=["redlines & RFIs"])


def _scoped(rows, user):
    scope = site_scope(user)
    if not scope:
        return rows
    ok = {s["SITE_ID"] for s in repo().select("CORE.SITE", scope)}
    return [x for x in rows if x["SITE_ID"] in ok]


@router.get("/redlines")
def list_redlines(site_id: str | None = None, status: str | None = None, user: dict = Depends(current_user)):
    where = {k: v for k, v in {"SITE_ID": site_id, "STATUS": status}.items() if v}
    rows = _scoped(repo().select("CORE.REDLINE", where or None, order_by="SITE_ID, SHEET"), user)
    for x in rows:
        x["PDF_URL"] = f"/files/{x['PDF_PATH']}" if x.get("PDF_PATH") else None
        x["ACTIONS"] = [a["action"] for a in workflow().actions("REDLINE", x["STATUS"], user["role"])]
    return rows


@router.post("/redlines/{redline_id}/transition")
def redline_transition(redline_id: str, body: TransitionIn, user: dict = Depends(current_user)):
    row = repo().get("CORE.REDLINE", REDLINE_ID=redline_id)
    check_site_scope(user, row["SITE_ID"])
    incorporate = body.action.upper() == "INCORPORATE" and row["DOC_TYPE"] == "CD"
    if incorporate and not pipeline().latest_revision(row["SITE_ID"]):
        raise ValidationError("Implement the approved changes first, then incorporate - there is no revised drawing yet")
    out = workflow().transition("REDLINE", redline_id, body.action, reason_code=body.reason_code, comment=body.comment)
    if incorporate:        # the revised drawing becomes the site's CD revision; the next run reads it and the findings resolve
        out["issued"] = pipeline().register_revised_cd(row["SITE_ID"], user["sub"])
    return out


@router.get("/rfis")
def list_rfis(site_id: str | None = None, status: str | None = None, user: dict = Depends(current_user)):
    where = {k: v for k, v in {"SITE_ID": site_id, "STATUS": status}.items() if v}
    rows = _scoped(repo().select("CORE.RFI", where or None, order_by="SITE_ID"), user)
    for x in rows:
        x["ACTIONS"] = [a["action"] for a in workflow().actions("RFI", x["STATUS"], user["role"])]
    return rows


@router.post("/rfis/{rfi_id}/transition")
def rfi_transition(rfi_id: str, body: TransitionIn, user: dict = Depends(current_user)):
    if body.action.upper() == "ANSWER":
        raise ValidationError("Use POST /rfis/{id}/answer to answer an RFI")
    return workflow().transition("RFI", rfi_id, body.action, reason_code=body.reason_code, comment=body.comment)


@router.post("/rfis/{rfi_id}/answer")
def answer_rfi(rfi_id: str, body: RfiAnswerIn, user: dict = Depends(require("ERICSSON"))):
    return workflow().transition("RFI", rfi_id, "ANSWER", comment=body.answer, extra_updates={"ANSWER": body.answer, "UPDATED_AT": now_iso()})
