"""Workflow: available actions, generic transition (site scoping and any entity), history, role inbox."""
from fastapi import APIRouter, Depends

from api.deps import check_site_scope, current_user, my_notifications, repo, scoping_only, workflow
from api.schemas import TransitionIn
from scopeiq.common.context import current
from scopeiq.common.errors import ValidationError
from scopeiq.db.repository import now_iso
from scopeiq.services import bom_revisions
from scopeiq.workflow.engine import ENTITY_TABLES

router = APIRouter(prefix="/workflow", tags=["workflow"])

# Site actions after which the BOM revision moves with the site. The revision is locked while the provider reviews it, so what the provider agrees to
# is what is approved; a change request or a rework ends in the next revision (the pipeline creates it on the next run).
HANDSHAKE_ACTIONS = ("SUBMIT_TO_SP", "AGREE", "REQUEST_CHANGES", "APPROVE_FBA")
# older sites only: a revision made before revisions followed the site is moved straight to the state these lead to
LEGACY_CATCH_UP = ("AGREE", "APPROVE_FBA")


def _follow_site(site_id: str, action: str, reason_code: str | None, comment: str | None) -> None:
    """Move the site's latest generated BOM revision to the state the workflow reference gives this action (never REV 0)."""
    wf, r = workflow(), repo()
    revs = [x for x in r.select("CORE.BOM_REVISION", {"SITE_ID": site_id}, order_by="REV_NO DESC") if x.get("KIND") != "TOOL_REV0"]
    rows = [t for t in wf.transitions if t["ENTITY_TYPE"] == "BOM_REVISION" and t["ACTION"] == action]
    if not revs or not rows:
        return
    rev = revs[0]
    if any(t["FROM_STATE"] == rev["STATUS"] for t in rows):
        wf.transition("BOM_REVISION", rev["BOM_REV_ID"], action, reason_code=reason_code, comment=comment)
    elif action in LEGACY_CATCH_UP and rev["STATUS"] != rows[0]["TO_STATE"] and not (wf.state_row("BOM_REVISION", rev["STATUS"]) or {}).get("IS_TERMINAL") == "Y":
        # an older revision that never followed the site: move it straight to the state this action leads to. A locked final revision is never touched.
        updates = {"STATUS": rows[0]["TO_STATE"]}
        if wf.is_locked("BOM_REVISION", updates["STATUS"]):
            updates.update(LOCKED=True, APPROVED_AT=now_iso(), APPROVED_BY=current().user_id)
        r.update("CORE.BOM_REVISION", updates, {"BOM_REV_ID": rev["BOM_REV_ID"]})


def _entity(entity: str) -> str:
    e = entity.upper()
    if e not in ENTITY_TABLES:
        raise ValidationError(f"Unknown entity {entity}", details={"allowed": list(ENTITY_TABLES)})
    return e


@router.get("/definition")
def definition(user: dict = Depends(current_user)):
    wf = workflow()
    return {"states": wf.states, "transitions": wf.transitions}


@router.get("/{entity}/{entity_id}/actions")
def actions(entity: str, entity_id: str, user: dict = Depends(current_user)):
    e = _entity(entity)
    table, id_col, st_col = ENTITY_TABLES[e]
    row = repo().get(table, **{id_col: entity_id})
    if e == "SITE_SCOPING":
        check_site_scope(user, entity_id)
    elif row and row.get("SITE_ID"):
        check_site_scope(user, row["SITE_ID"])
    state = row.get(st_col) or workflow().initial_state(e)
    return {"state": state, "actions": workflow().actions(e, state, user["role"])}


@router.post("/{entity}/{entity_id}/transition")
def transition(entity: str, entity_id: str, body: TransitionIn, user: dict = Depends(current_user)):
    e = _entity(entity)
    table, id_col, _ = ENTITY_TABLES[e]
    row = repo().get(table, **{id_col: entity_id})
    site_id = entity_id if e == "SITE_SCOPING" else (row.get("SITE_ID") if row else None)
    if site_id:
        check_site_scope(user, site_id)

    # the handshake and the final approval work on a BOM revision: it has to exist, and what goes to the provider is a fresh one
    if e == "SITE_SCOPING" and body.action.upper() in (*HANDSHAKE_ACTIONS, "SUBMIT_REVIEW"):
        r = repo()
        rev = bom_revisions.ensure(r, site_id, user["sub"])
        if body.action.upper() in ("SUBMIT_TO_SP", "AGREE", "APPROVE_FBA") and not rev:
            raise ValidationError(
                f"Cannot execute '{body.action}': No Bill of Materials (BOM) has been generated for site {site_id}. Please upload documents and run the pipeline first.",
                details={"site_id": site_id, "action": body.action})
        if body.action.upper() == "SUBMIT_TO_SP" and not (r.get("CORE.SITE", SITE_ID=site_id).get("CX_SP") or "").strip():
            raise ValidationError("Choose the service provider for this site before sending the BOM to them.", details={"site_id": site_id})
        if body.action.upper() in ("SUBMIT_TO_SP", "SUBMIT_REVIEW") and rev and not bom_revisions.is_draft(rev):
            raise ValidationError(f"{rev['REV_LABEL']} has already been sent. Start the next revision (or run the pipeline again) before sending the BOM again.",
                                  details={"site_id": site_id, "revision": rev["REV_LABEL"], "status": rev["STATUS"]})

    result = workflow().transition(e, entity_id, body.action, reason_code=body.reason_code, comment=body.comment)

    # the BOM revision follows the site through the handshake and FBA
    if e == "SITE_SCOPING" and site_id and body.action.upper() in HANDSHAKE_ACTIONS:
        _follow_site(site_id, body.action.upper(), body.reason_code, body.comment)

    return result


@router.get("/{entity}/{entity_id}/history")
def history(entity: str, entity_id: str, user: dict = Depends(scoping_only)):
    e = _entity(entity)
    table, id_col, _ = ENTITY_TABLES[e]
    row = repo().get(table, **{id_col: entity_id})
    site_id = entity_id if e == "SITE_SCOPING" else (row.get("SITE_ID") if row else None)
    if site_id:
        check_site_scope(user, site_id)
    return workflow().history(e, entity_id)


@router.get("/inbox")
def inbox(unread_only: bool = True, limit: int = 100, user: dict = Depends(current_user)):
    return my_notifications(user, unread_only)[:limit]


@router.post("/inbox/{notification_id}/read")
def mark_read(notification_id: str, user: dict = Depends(current_user)):
    repo().update("WF.NOTIFICATION", {"READ_AT": now_iso()}, {"NOTIFICATION_ID": notification_id})
    return {"notification_id": notification_id, "read": True}
