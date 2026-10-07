"""Discrepancies: list/filter, detail with evidence and history, workflow actions, assignment, comments."""
import uuid

from fastapi import APIRouter, Depends

from api.deps import current_user, repo, require, site_scope, workflow
from api.schemas import AssignIn, CommentIn, TransitionIn
from scopeiq.common.audit import AuditTrail
from scopeiq.db.repository import now_iso

router = APIRouter(prefix="/discrepancies", tags=["discrepancies"])


def _allowed_sites(user):
    scope = site_scope(user)
    return {s["SITE_ID"] for s in repo().select("CORE.SITE", scope)} if scope else None


@router.get("")
def list_discrepancies(site_id: str | None = None, status: str | None = None, outcome: str | None = None, severity: str | None = None,
                       rule_id: str | None = None, assigned_to: str | None = None, user: dict = Depends(current_user)):
    where = {k.upper(): v for k, v in dict(site_id=site_id, status=status, outcome=outcome, severity=severity, rule_id=rule_id,
                                            assigned_to=assigned_to).items() if v}
    rows = repo().select("CORE.DISCREPANCY", where or None, order_by="SITE_ID, SEVERITY, RULE_ID")
    allowed = _allowed_sites(user)
    wf = workflow()
    out = []
    for d in rows:
        if allowed is not None and d["SITE_ID"] not in allowed:
            continue
        d["ACTIONS"] = [a["action"] for a in wf.actions("DISCREPANCY", d["STATUS"], user["role"])]
        out.append(d)
    return out


@router.get("/{disc_id}")
def get_discrepancy(disc_id: str, user: dict = Depends(current_user)):
    r = repo()
    d = r.get("CORE.DISCREPANCY", DISC_ID=disc_id)
    d["ACTIONS"] = workflow().actions("DISCREPANCY", d["STATUS"], user["role"])
    d["HISTORY"] = workflow().history("DISCREPANCY", disc_id)
    d["COMMENTS"] = r.select("WF.COMMENT", {"ENTITY_TYPE": "DISCREPANCY", "ENTITY_ID": disc_id}, order_by="CREATED_AT")
    d["REDLINES"] = r.select("CORE.REDLINE", {"DISC_ID": disc_id})
    d["EVIDENCE_URLS"] = [f"/files/{e}" for e in (d.get("EVIDENCE") or []) if str(e).endswith((".jpg", ".png"))]
    return d


@router.post("/{disc_id}/transition")
def transition(disc_id: str, body: TransitionIn, user: dict = Depends(current_user)):
    return workflow().transition("DISCREPANCY", disc_id, body.action, reason_code=body.reason_code, comment=body.comment)


@router.post("/{disc_id}/assign")
def assign(disc_id: str, body: AssignIn, user: dict = Depends(require("SCOPER", "REVIEWER"))):
    r = repo()
    before = r.get("CORE.DISCREPANCY", DISC_ID=disc_id)
    r.update("CORE.DISCREPANCY", {"ASSIGNED_TO": body.user_id, "UPDATED_AT": now_iso(), "UPDATED_BY": user["sub"]}, {"DISC_ID": disc_id})
    AuditTrail.record(entity_type="DISCREPANCY", entity_id=disc_id, action="ASSIGN", before={"ASSIGNED_TO": before.get("ASSIGNED_TO")},
                      after={"ASSIGNED_TO": body.user_id}, site_id=before["SITE_ID"], source="api")
    return {"disc_id": disc_id, "assigned_to": body.user_id}


@router.post("/{disc_id}/comments")
def comment(disc_id: str, body: CommentIn, user: dict = Depends(current_user)):
    d = repo().get("CORE.DISCREPANCY", DISC_ID=disc_id)
    row = {"COMMENT_ID": uuid.uuid4().hex, "ENTITY_TYPE": "DISCREPANCY", "ENTITY_ID": disc_id, "SITE_ID": d["SITE_ID"], "USER_ID": user["sub"],
           "COMMENT_TEXT": body.text, "CREATED_AT": now_iso()}
    repo().insert("WF.COMMENT", [row])
    return row
