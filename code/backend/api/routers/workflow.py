"""Workflow: available actions, generic transition (site scoping and any entity), history, role inbox."""
from fastapi import APIRouter, Depends

from api.deps import check_site_scope, current_user, repo, workflow
from api.schemas import TransitionIn
from scopeiq.common.errors import ValidationError
from scopeiq.db.repository import now_iso
from scopeiq.workflow.engine import ENTITY_TABLES

router = APIRouter(prefix="/workflow", tags=["workflow"])


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

    # Validation: Cannot perform SP Handshake or FBA without a generated BOM
    if e == "SITE_SCOPING" and body.action in ("SP_AGREE", "SP_REQUEST_CHANGES", "APPROVE_FBA"):
        r = repo()
        boms = r.select("CORE.BOM_OUTPUT_LINE", {"SITE_ID": site_id})
        revs = [x for x in r.select("CORE.BOM_REVISION", {"SITE_ID": site_id}) if x.get("KIND") != "TOOL_REV0"]
        if not boms and not revs:
            raise ValidationError(
                f"Cannot execute '{body.action}': No Bill of Materials (BOM) has been generated for site {site_id}. Please upload documents and run the pipeline first.",
                details={"site_id": site_id, "action": body.action}
            )

    result = workflow().transition(e, entity_id, body.action, reason_code=body.reason_code, comment=body.comment)

    # Synchronization between SITE_SCOPING and BOM_REVISION for Handshake and FBA:
    if e == "SITE_SCOPING" and site_id:
        r = repo()
        site_revs = r.select("CORE.BOM_REVISION", {"SITE_ID": site_id})
        sp_revs = [s for s in site_revs if s.get("STATUS") == "SP_REVIEW"]
        if sp_revs:
            rev_id = sp_revs[0]["BOM_REV_ID"]
            if body.action == "SP_AGREE":
                workflow().transition("BOM_REVISION", rev_id, "SP_AGREE")
            elif body.action == "SP_REQUEST_CHANGES":
                workflow().transition("BOM_REVISION", rev_id, "SP_REQUEST_CHANGES", reason_code=body.reason_code, comment=body.comment)
        if body.action == "APPROVE_FBA":
            for srev in site_revs:
                if srev.get("STATUS") in ("SP_AGREED", "DRAFT", "SP_REVIEW", "RECEIVED"):
                    r.update("CORE.BOM_REVISION", {
                        "STATUS": "FBA",
                        "LOCKED": 1,
                        "APPROVED_AT": now_iso(),
                        "APPROVED_BY": user.get("user_id") or user.get("username") or "admin"
                    }, {"BOM_REV_ID": srev["BOM_REV_ID"]})

    return result


@router.get("/{entity}/{entity_id}/history")
def history(entity: str, entity_id: str, user: dict = Depends(current_user)):
    e = _entity(entity)
    table, id_col, _ = ENTITY_TABLES[e]
    row = repo().get(table, **{id_col: entity_id})
    site_id = entity_id if e == "SITE_SCOPING" else (row.get("SITE_ID") if row else None)
    if site_id:
        check_site_scope(user, site_id)
    return workflow().history(e, entity_id)


@router.get("/inbox")
def inbox(unread_only: bool = True, limit: int = 100, user: dict = Depends(current_user)):
    sql = "SELECT * FROM WF.NOTIFICATION WHERE (ROLE_CODE = %s OR USER_ID = %s)" + (" AND READ_AT IS NULL" if unread_only else "")
    rows = repo().query(sql + " ORDER BY CREATED_AT DESC", [user["role"], user["sub"]])
    return rows[:limit]


@router.post("/inbox/{notification_id}/read")
def mark_read(notification_id: str, user: dict = Depends(current_user)):
    repo().update("WF.NOTIFICATION", {"READ_AT": now_iso()}, {"NOTIFICATION_ID": notification_id})
    return {"notification_id": notification_id, "read": True}
