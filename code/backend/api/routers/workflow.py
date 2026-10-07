"""Workflow: available actions, generic transition (site scoping and any entity), history, role inbox."""
from fastapi import APIRouter, Depends

from api.deps import current_user, repo, workflow
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
    state = row.get(st_col) or workflow().initial_state(e)
    return {"state": state, "actions": workflow().actions(e, state, user["role"])}


@router.post("/{entity}/{entity_id}/transition")
def transition(entity: str, entity_id: str, body: TransitionIn, user: dict = Depends(current_user)):
    return workflow().transition(_entity(entity), entity_id, body.action, reason_code=body.reason_code, comment=body.comment)


@router.get("/{entity}/{entity_id}/history")
def history(entity: str, entity_id: str, user: dict = Depends(current_user)):
    return workflow().history(_entity(entity), entity_id)


@router.get("/inbox")
def inbox(unread_only: bool = True, limit: int = 100, user: dict = Depends(current_user)):
    sql = "SELECT * FROM WF.NOTIFICATION WHERE (ROLE_CODE = %s OR USER_ID = %s)" + (" AND READ_AT IS NULL" if unread_only else "")
    rows = repo().query(sql + " ORDER BY CREATED_AT DESC", [user["role"], user["sub"]])
    return rows[:limit]


@router.post("/inbox/{notification_id}/read")
def mark_read(notification_id: str, user: dict = Depends(current_user)):
    repo().update("WF.NOTIFICATION", {"READ_AT": now_iso()}, {"NOTIFICATION_ID": notification_id})
    return {"notification_id": notification_id, "read": True}
