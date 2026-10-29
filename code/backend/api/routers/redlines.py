"""Redlines and the red-marked CD PDFs; RFIs with answers. Both move through the workflow."""
from fastapi import APIRouter, Depends

from api.deps import check_site_scope, current_user, pipeline, repo, require, site_scope, workflow
from api.schemas import RfiAnswerIn, TransitionIn
from scopeiq.common.errors import PermissionDenied, ValidationError
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
    proofs: dict[str, list] = {}
    for p in repo().select("CORE.REDLINE_PROOF", {"SITE_ID": site_id} if site_id else None, order_by="REDLINE_ID, RANK"):
        proofs.setdefault(p["REDLINE_ID"], []).append({**p, "URL": f"/files/{p['PATH']}"})

    # Retrieve all workflow events for redlines to track who submitted and who gave responses
    redline_ids = {x["REDLINE_ID"] for x in rows}
    all_events = repo().select("WF.WORKFLOW_EVENT", {"ENTITY_TYPE": "REDLINE"}, order_by="EVENT_TS ASC")
    events_by_id: dict[str, list] = {}
    for e in all_events:
        if e["ENTITY_ID"] in redline_ids:
            events_by_id.setdefault(e["ENTITY_ID"], []).append(e)

    for x in rows:
        x["PDF_URL"] = f"/files/{x['PDF_PATH']}" if x.get("PDF_PATH") else None
        x["PROOF"] = proofs.get(x["REDLINE_ID"], [])            # the drone footage that shows what the redline is about
        x["ACTIONS"] = [a["action"] for a in workflow().actions("REDLINE", x["STATUS"], user["role"])] if user.get("role") in ("AE_ENGINEER", "ADMIN") else []

        rl_events = events_by_id.get(x["REDLINE_ID"], [])

        # Submitter attribution
        submit_evt = next((e for e in rl_events if e["ACTION"] in ("SUBMIT", "SEND", "CREATE")), None)
        if submit_evt:
            x["SUBMITTED_BY"] = submit_evt["ACTOR_USER_ID"]
            x["SUBMITTED_ROLE"] = submit_evt["ACTOR_ROLE"]
            x["SUBMITTED_AT"] = submit_evt["EVENT_TS"]
        else:
            resp_evts = [e for e in rl_events if e["ACTION"] in ("REVIEW_DONE", "ACKNOWLEDGE", "COMPLETE", "INCORPORATE", "REJECT")]
            x["SUBMITTED_BY"] = "scoper" if resp_evts else (x.get("UPDATED_BY") or "scoper")
            x["SUBMITTED_ROLE"] = "SCOPER"
            x["SUBMITTED_AT"] = x.get("CREATED_AT")

        # Specific action tracking
        rev_evt = next((e for e in reversed(rl_events) if e["ACTION"] in ("REVIEW_DONE", "ACKNOWLEDGE")), None)
        if rev_evt:
            x["REVIEWED_BY"] = rev_evt["ACTOR_USER_ID"]
            x["REVIEWED_ROLE"] = rev_evt["ACTOR_ROLE"]
            x["REVIEWED_AT"] = rev_evt["EVENT_TS"]
            x["REVIEWED_COMMENT"] = rev_evt.get("COMMENT")
        else:
            x["REVIEWED_BY"] = None
            x["REVIEWED_ROLE"] = None
            x["REVIEWED_AT"] = None
            x["REVIEWED_COMMENT"] = None

        comp_evt = next((e for e in reversed(rl_events) if e["ACTION"] in ("COMPLETE", "INCORPORATE")), None)
        if comp_evt:
            x["COMPLETED_BY"] = comp_evt["ACTOR_USER_ID"]
            x["COMPLETED_ROLE"] = comp_evt["ACTOR_ROLE"]
            x["COMPLETED_AT"] = comp_evt["EVENT_TS"]
            x["COMPLETED_COMMENT"] = comp_evt.get("COMMENT")
        else:
            x["COMPLETED_BY"] = None
            x["COMPLETED_ROLE"] = None
            x["COMPLETED_AT"] = None
            x["COMPLETED_COMMENT"] = None

        rej_evt = next((e for e in reversed(rl_events) if e["ACTION"] == "REJECT"), None)
        if rej_evt:
            x["REJECTED_BY"] = rej_evt["ACTOR_USER_ID"]
            x["REJECTED_ROLE"] = rej_evt["ACTOR_ROLE"]
            x["REJECTED_AT"] = rej_evt["EVENT_TS"]
            x["REJECTED_REASON"] = rej_evt.get("REASON_CODE")
            x["REJECTED_COMMENT"] = rej_evt.get("COMMENT")
        else:
            x["REJECTED_BY"] = None
            x["REJECTED_ROLE"] = None
            x["REJECTED_AT"] = None
            x["REJECTED_REASON"] = None
            x["REJECTED_COMMENT"] = None

        # Latest response from AE_ENGINEER or ADMIN
        response_evts = [e for e in rl_events if e["ACTION"] in ("REVIEW_DONE", "ACKNOWLEDGE", "COMPLETE", "INCORPORATE", "REJECT")]
        if response_evts:
            last = response_evts[-1]
            x["LAST_RESPONSE"] = {
                "ACTION": last["ACTION"],
                "ACTOR_USER_ID": last["ACTOR_USER_ID"],
                "ACTOR_ROLE": last["ACTOR_ROLE"],
                "EVENT_TS": last["EVENT_TS"],
                "COMMENT": last.get("COMMENT"),
                "REASON_CODE": last.get("REASON_CODE"),
            }
        else:
            x["LAST_RESPONSE"] = None

    return rows


@router.post("/redlines/{redline_id}/transition")
def redline_transition(redline_id: str, body: TransitionIn, user: dict = Depends(current_user)):
    row = repo().get("CORE.REDLINE", REDLINE_ID=redline_id)
    check_site_scope(user, row["SITE_ID"])
    act = body.action.upper()
    incorporate = act in ("INCORPORATE", "COMPLETE") and row["DOC_TYPE"] == "CD"
    out = workflow().transition("REDLINE", redline_id, body.action, reason_code=body.reason_code, comment=body.comment)
    if incorporate and pipeline().latest_revision(row["SITE_ID"]):
        out["issued"] = pipeline().register_revised_cd(row["SITE_ID"], user["sub"])
    return out


@router.get("/rfis")
def list_rfis(site_id: str | None = None, status: str | None = None, to_party: str | None = None, user: dict = Depends(current_user)):
    where = {k: v for k, v in {"SITE_ID": site_id, "STATUS": status, "TO_PARTY": to_party}.items() if v}

    # Filter by TO_PARTY if explicitly provided in query params:
    # All authorized roles (ADMIN, AE_ENGINEER, SCOPER, REVIEWER) oversee all RFIs across sites
    # for full project context, while action/answer permissions are enforced per role.

    rows = _scoped(repo().select("CORE.RFI", where or None, order_by="SITE_ID"), user)
    for x in rows:
        acts = [a["action"] for a in workflow().actions("RFI", x["STATUS"], user["role"])]
        # AE_ENGINEER only has action buttons on RFIs addressed to AE_ENGINEER:
        if user["role"] == "AE_ENGINEER" and x.get("TO_PARTY") != "AE_ENGINEER":
            acts = []
        # ADMIN / ERICSSON only has review/answer action buttons on RFIs addressed to Admin:
        # For RFIs sent to A&E, only A&E Engineer starts review and answers; Admin can only CLOSE once answered.
        if user["role"] in ("ADMIN", "ERICSSON") and x.get("TO_PARTY") == "AE_ENGINEER":
            acts = [a for a in acts if a == "CLOSE"]
        x["ACTIONS"] = acts
    return rows


@router.post("/rfis/{rfi_id}/transition")
def rfi_transition(rfi_id: str, body: TransitionIn, user: dict = Depends(current_user)):
    if body.action.upper() == "ANSWER":
        raise ValidationError("Use POST /rfis/{id}/answer to answer an RFI")
    action = "SUBMIT" if body.action.upper() == "SEND" else body.action
    row = repo().get("CORE.RFI", RFI_ID=rfi_id)
    if action == "START_REVIEW":
        if row.get("TO_PARTY") == "AE_ENGINEER" and user["role"] != "AE_ENGINEER":
            raise PermissionDenied("Only A&E Engineer can start review on RFIs addressed to A&E")
        if row.get("TO_PARTY") != "AE_ENGINEER" and user["role"] == "AE_ENGINEER":
            raise PermissionDenied("A&E Engineer cannot start review on RFIs addressed to Admin")
    return workflow().transition("RFI", rfi_id, action, reason_code=body.reason_code, comment=body.comment)


@router.post("/rfis/{rfi_id}/answer")
def answer_rfi(rfi_id: str, body: RfiAnswerIn, user: dict = Depends(require("ADMIN", "ERICSSON", "AE_ENGINEER"))):
    row = repo().get("CORE.RFI", RFI_ID=rfi_id)
    if row.get("TO_PARTY") == "AE_ENGINEER" and user["role"] != "AE_ENGINEER":
        raise PermissionDenied("Only A&E Engineer can answer RFIs addressed to A&E")
    if row.get("TO_PARTY") != "AE_ENGINEER" and user["role"] == "AE_ENGINEER":
        raise PermissionDenied("A&E Engineer cannot answer RFIs addressed to Admin")
    return workflow().transition("RFI", rfi_id, "ANSWER", comment=body.answer, extra_updates={"ANSWER": body.answer, "UPDATED_AT": now_iso()})
