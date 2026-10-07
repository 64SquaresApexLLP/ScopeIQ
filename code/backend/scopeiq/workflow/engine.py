"""Workflow state machine driven by WORKFLOW_STATE / WORKFLOW_TRANSITION reference rows.

Entities: SITE_SCOPING, DISCREPANCY, REDLINE, RFI, BOM_REVISION, EHS_ALERT. A transition is allowed only if
a row exists for (entity, from-state or '*', action) and the actor's role is in ALLOWED_ROLES. Reasons and
comments are enforced per row. Each transition writes WF.WORKFLOW_EVENT, an AUDIT_LOG entry and inbox
notifications for NOTIFY_ROLES. Locked states (e.g. an FBA-approved BOM) reject edits.
"""
from __future__ import annotations

import uuid

from scopeiq.common.audit import AuditTrail
from scopeiq.common.context import current
from scopeiq.common.errors import PermissionDenied, ValidationError, WorkflowError
from scopeiq.common.logging import get_logger
from scopeiq.db.repository import Repository, now_iso
from scopeiq.reference.loader import ReferenceData

log = get_logger(__name__)

# entity type -> (table, id column, status column)
ENTITY_TABLES = {
    "SITE_SCOPING": ("CORE.SITE", "SITE_ID", "WORKFLOW_STATE"),
    "DISCREPANCY": ("CORE.DISCREPANCY", "DISC_ID", "STATUS"),
    "REDLINE": ("CORE.REDLINE", "REDLINE_ID", "STATUS"),
    "RFI": ("CORE.RFI", "RFI_ID", "STATUS"),
    "BOM_REVISION": ("CORE.BOM_REVISION", "BOM_REV_ID", "STATUS"),
    "EHS_ALERT": ("CORE.EHS_ALERT", "ALERT_ID", "STATUS"),
}


class WorkflowEngine:
    def __init__(self, ref: ReferenceData, repo: Repository):
        self.ref, self.repo = ref, repo
        self.transitions = ref.rows("workflow_transitions")
        self.states = ref.rows("workflow_states")

    # ---------------------------------------------------------------- queries
    def initial_state(self, entity: str) -> str:
        s = next((r for r in self.states if r["ENTITY_TYPE"] == entity and r["IS_INITIAL"] == "Y"), None)
        if not s:
            raise WorkflowError(f"No initial state for {entity}")
        return s["STATE"]

    def is_locked(self, entity: str, state: str) -> bool:
        return any(r["ENTITY_TYPE"] == entity and r["STATE"] == state and r["IS_LOCKED"] == "Y" for r in self.states)

    def actions(self, entity: str, state: str, role: str | None = None) -> list[dict]:
        out = []
        for t in self.transitions:
            if t["ENTITY_TYPE"] != entity or t["FROM_STATE"] not in (state, "*"):
                continue
            if t["FROM_STATE"] == "*" and t["TO_STATE"] == state:
                continue
            roles = t["ALLOWED_ROLES"].split(";")
            if role and role not in roles and role != "ADMIN":
                continue
            out.append({"action": t["ACTION"], "to_state": t["TO_STATE"], "requires_reason": t["REQUIRES_REASON"] == "Y",
                        "requires_comment": t["REQUIRES_COMMENT"] == "Y", "description": t["DESCRIPTION"], "roles": roles})
        return out

    def _find(self, entity: str, state: str, action: str) -> dict:
        t = next((t for t in self.transitions if t["ENTITY_TYPE"] == entity and t["FROM_STATE"] == state and t["ACTION"] == action), None)
        t = t or next((t for t in self.transitions if t["ENTITY_TYPE"] == entity and t["FROM_STATE"] == "*" and t["ACTION"] == action), None)
        if not t:
            allowed = [a["action"] for a in self.actions(entity, state)]
            raise WorkflowError(f"{action} is not allowed on {entity} in state {state}", details={"allowed": allowed})
        return t

    # ---------------------------------------------------------------- transition
    def transition(self, entity: str, entity_id: str, action: str, *, reason_code: str | None = None, comment: str | None = None,
                   site_id: str | None = None, extra_updates: dict | None = None) -> dict:
        if entity not in ENTITY_TABLES:
            raise ValidationError(f"Unknown workflow entity {entity}")
        table, id_col, st_col = ENTITY_TABLES[entity]
        row = self.repo.get(table, **{id_col: entity_id})
        state = row.get(st_col) or self.initial_state(entity)
        t = self._find(entity, state, action.upper())
        ctx = current()
        roles = t["ALLOWED_ROLES"].split(";")
        if ctx.role not in roles and ctx.role != "ADMIN":
            raise PermissionDenied(f"Role {ctx.role} cannot {action} a {entity} in {state}", details={"allowed_roles": roles})
        if t["REQUIRES_REASON"] == "Y" and not reason_code:
            raise ValidationError(f"{action} needs a reason code", details={"action": action})
        if reason_code and reason_code not in self.ref.reason_codes:
            raise ValidationError(f"Unknown reason code {reason_code}")
        if t["REQUIRES_COMMENT"] == "Y" and not (comment or "").strip():
            raise ValidationError(f"{action} needs a comment", details={"action": action})
        to_state = t["TO_STATE"]
        site_id = site_id or row.get("SITE_ID")
        updates = {st_col: to_state, **(extra_updates or {})}
        if "UPDATED_AT" in row:
            updates["UPDATED_AT"] = now_iso()
        if "UPDATED_BY" in row:
            updates["UPDATED_BY"] = ctx.user_id
        if entity == "DISCREPANCY" and reason_code:
            updates["REASON_CODE"] = reason_code
        if entity == "BOM_REVISION" and self.is_locked("BOM_REVISION", to_state):
            updates["LOCKED"] = True
            updates.setdefault("APPROVED_AT", now_iso())
            updates.setdefault("APPROVED_BY", ctx.user_id)
        self.repo.update(table, updates, {id_col: entity_id})
        event = {"EVENT_ID": uuid.uuid4().hex, "ENTITY_TYPE": entity, "ENTITY_ID": entity_id, "SITE_ID": site_id, "FROM_STATE": state,
                 "ACTION": action.upper(), "TO_STATE": to_state, "ACTOR_USER_ID": ctx.user_id, "ACTOR_ROLE": ctx.role,
                 "REASON_CODE": reason_code, "COMMENT": comment, "EVENT_TS": now_iso(), "CORRELATION_ID": ctx.correlation_id}
        self.repo.insert("WF.WORKFLOW_EVENT", [event])
        AuditTrail.record(entity_type=entity, entity_id=entity_id, action="TRANSITION", before={st_col: state}, after=updates, reason_code=reason_code,
                          comment=comment, site_id=site_id, source="workflow")
        notes = [{"NOTIFICATION_ID": uuid.uuid4().hex, "ROLE_CODE": r, "USER_ID": None, "SITE_ID": site_id, "ENTITY_TYPE": entity,
                  "ENTITY_ID": entity_id, "MESSAGE": f"{entity.replace('_', ' ').title()} {entity_id} {state} -> {to_state} ({t['DESCRIPTION']}) by {ctx.user_id}",
                  "CREATED_AT": now_iso(), "READ_AT": None} for r in t["NOTIFY_ROLES"].split(";") if r]
        if notes:
            self.repo.insert("WF.NOTIFICATION", notes)
        log.info("workflow %s %s: %s -[%s]-> %s", entity, entity_id, state, action, to_state, extra={"site_id": site_id})
        return {"entity_type": entity, "entity_id": entity_id, "from_state": state, "to_state": to_state, "event_id": event["EVENT_ID"]}

    def history(self, entity: str, entity_id: str) -> list[dict]:
        return self.repo.select("WF.WORKFLOW_EVENT", {"ENTITY_TYPE": entity, "ENTITY_ID": entity_id}, order_by="EVENT_TS")
