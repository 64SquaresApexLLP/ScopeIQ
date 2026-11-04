"""Discrepancies: list/filter, detail with evidence and history, workflow actions, assignment, comments,
and A&E redline revision lifecycle (Send to A&E -> A&E REV 2 -> Keep visible until redline removed)."""
import uuid

from fastapi import APIRouter, Depends

from api.deps import current_user, repo, require, site_scope, workflow
from api.schemas import AeRevisionIn, AssignIn, CommentIn, TransitionIn
from scopeiq.common.audit import AuditTrail
from scopeiq.db.repository import now_iso

router = APIRouter(prefix="/discrepancies", tags=["discrepancies"])


def _allowed_sites(user):
    scope = site_scope(user)
    return {s["SITE_ID"] for s in repo().select("CORE.SITE", scope)} if scope else None


def _enrich_discrepancy(d: dict, redlines_by_disc: dict[str, list], user_role: str, wf) -> dict:
    linked_rls = redlines_by_disc.get(d["DISC_ID"], [])
    d["REDLINES"] = linked_rls
    latest_rl = linked_rls[0] if linked_rls else None
    d["REDLINE_ID"] = latest_rl["REDLINE_ID"] if latest_rl else None
    d["REDLINE_STATUS"] = latest_rl["STATUS"] if latest_rl else None

    # Check if redline was already removed/closed or discrepancy officially closed
    is_closed = d.get("STATUS") == "CLOSED" or (latest_rl and latest_rl.get("STATUS") == "CLOSED")

    # An improved revision was received if:
    # 1. REASON_CODE is RC-AE-REVISED, or
    # 2. Linked redline is INCORPORATED or COMPLETED, or
    # 3. Discrepancy is RESOLVED while having a linked redline.
    is_ae_revised = (
        d.get("REASON_CODE") == "RC-AE-REVISED"
        or (latest_rl and latest_rl.get("STATUS") in ("INCORPORATED", "COMPLETED", "CLOSED"))
        or (d.get("STATUS") in ("RESOLVED", "CLOSED") and latest_rl is not None)
    )
    is_sent_to_ae = (
        d.get("STATUS") == "REDLINED"
        or (latest_rl and latest_rl.get("STATUS") in ("IN_REVIEW", "WORK_QUEUE", "SENT_TO_AE", "ACKNOWLEDGED"))
    )

    rl_rev = latest_rl.get("DOC_REVISION") if latest_rl else None
    if rl_rev and rl_rev not in ("REV 1", "REV 0"):
        rev_label = rl_rev
    else:
        rev_label = "REV 2"

    if is_closed and is_ae_revised:
        d["AE_STATUS"] = "REDLINE_REMOVED"
        d["AE_REVISION_LABEL"] = rev_label
        d["REDLINE_PENDING_REMOVAL"] = False
    elif is_ae_revised:
        d["AE_STATUS"] = "IMPROVED_REV_RECEIVED"
        d["AE_REVISION_LABEL"] = rev_label
        d["REDLINE_PENDING_REMOVAL"] = True
    elif is_sent_to_ae:
        d["AE_STATUS"] = "SENT_TO_AE"
        d["AE_REVISION_LABEL"] = None
        d["REDLINE_PENDING_REMOVAL"] = False
    elif d.get("STATUS") == "RFI_RAISED":
        d["AE_STATUS"] = "RFI_RAISED"
        d["AE_REVISION_LABEL"] = None
        d["REDLINE_PENDING_REMOVAL"] = False
    else:
        d["AE_STATUS"] = "OPEN"
        d["AE_REVISION_LABEL"] = None
        d["REDLINE_PENDING_REMOVAL"] = False

    d["ACTIONS"] = [a["action"] for a in wf.actions("DISCREPANCY", d["STATUS"], user_role)]
    return d


@router.get("")
def list_discrepancies(site_id: str | None = None, status: str | None = None, outcome: str | None = None, severity: str | None = None,
                       rule_id: str | None = None, assigned_to: str | None = None, user: dict = Depends(current_user)):
    r = repo()
    where = {k.upper(): v for k, v in dict(site_id=site_id, status=status, outcome=outcome, severity=severity, rule_id=rule_id,
                                            assigned_to=assigned_to).items() if v}
    rows = r.select("CORE.DISCREPANCY", where or None, order_by="SITE_ID, SEVERITY, RULE_ID")
    allowed = _allowed_sites(user)
    wf = workflow()

    # Preload all redlines for the relevant site(s)
    rl_where = {"SITE_ID": site_id} if site_id else None
    redlines_by_disc: dict[str, list] = {}
    for rl in r.select("CORE.REDLINE", rl_where, order_by="CREATED_AT DESC"):
        if rl.get("DISC_ID"):
            redlines_by_disc.setdefault(rl["DISC_ID"], []).append(rl)

    out = []
    # Preload all workflow events for these discrepancies and their linked redlines
    all_disc_ids = {d["DISC_ID"] for d in rows}
    all_rl_ids = {rl["REDLINE_ID"] for rls in redlines_by_disc.values() for rl in rls}
    all_entity_ids = all_disc_ids | all_rl_ids

    events_by_entity: dict[str, list] = {}
    if all_entity_ids:
        all_events = r.select("WF.WORKFLOW_EVENT", None, order_by="EVENT_TS ASC")
        for e in all_events:
            eid = e.get("ENTITY_ID")
            if eid in all_entity_ids:
                events_by_entity.setdefault(eid, []).append(e)

    for d in rows:
        if allowed is not None and d["SITE_ID"] not in allowed:
            continue
        _enrich_discrepancy(d, redlines_by_disc, user["role"], wf)

        did = d["DISC_ID"]
        disc_evts = list(events_by_entity.get(did, []))
        for rl in d.get("REDLINES", []):
            disc_evts.extend(events_by_entity.get(rl["REDLINE_ID"], []))
        disc_evts.sort(key=lambda x: str(x.get("EVENT_TS", "")))
        d["HISTORY"] = disc_evts

        out.append(d)
    return out


@router.get("/{disc_id}")
def get_discrepancy(disc_id: str, user: dict = Depends(current_user)):
    r = repo()
    d = r.get("CORE.DISCREPANCY", DISC_ID=disc_id)
    wf = workflow()
    d["COMMENTS"] = r.select("WF.COMMENT", {"ENTITY_TYPE": "DISCREPANCY", "ENTITY_ID": disc_id}, order_by="CREATED_AT")
    d["EVIDENCE_URLS"] = [f"/files/{e}" for e in (d.get("EVIDENCE") or []) if str(e).endswith((".jpg", ".png"))]

    linked_rls = r.select("CORE.REDLINE", {"DISC_ID": disc_id}, order_by="CREATED_AT DESC")
    _enrich_discrepancy(d, {disc_id: linked_rls}, user["role"], wf)

    # Combine history of discrepancy and linked redlines
    evts = wf.history("DISCREPANCY", disc_id)
    for rl in linked_rls:
        evts.extend(r.select("WF.WORKFLOW_EVENT", {"ENTITY_TYPE": "REDLINE", "ENTITY_ID": rl["REDLINE_ID"]}))
    evts.sort(key=lambda x: str(x.get("EVENT_TS", "")))
    d["HISTORY"] = evts
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


@router.post("/{disc_id}/send-to-ae")
def send_to_ae(disc_id: str, user: dict = Depends(current_user)):
    """Scoper or Admin sends discrepancy and drafting instructions to A&E."""
    r = repo()
    d = r.get("CORE.DISCREPANCY", DISC_ID=disc_id)
    sid = d["SITE_ID"]
    now = now_iso()

    # Find or create linked redline
    rls = r.select("CORE.REDLINE", {"DISC_ID": disc_id})
    if rls:
        for rl in rls:
            r.update("CORE.REDLINE", {"STATUS": "SENT_TO_AE", "UPDATED_AT": now, "UPDATED_BY": user["sub"]}, {"REDLINE_ID": rl["REDLINE_ID"]})
    else:
        new_rl_id = f"RDL-{uuid.uuid4().hex[:12].upper()}"
        from_val = d.get("EXPECTED", {}).get("v") if isinstance(d.get("EXPECTED"), dict) else d.get("EXPECTED")
        to_val = d.get("FOUND", {}).get("v") if isinstance(d.get("FOUND"), dict) else d.get("FOUND")
        from_str = f"{from_val[0]} ft" if isinstance(from_val, list) and from_val else str(from_val or "As drawn")
        to_str = f"{to_val[0]} ft" if isinstance(to_val, list) and to_val else str(to_val or "As measured")
        markup = f"REVISE {d.get('TARGET_DOC', 'CD')} SHEET {d.get('TARGET_SHEET', 'A-2')}: {d.get('TITLE', '')} ({from_str} -> {to_str})."
        new_rl = {
            "REDLINE_ID": new_rl_id,
            "SITE_ID": sid,
            "DISC_ID": disc_id,
            "DOC_TYPE": d.get("TARGET_DOC") or "CD",
            "DOC_REVISION": "REV 1",
            "SHEET": d.get("TARGET_SHEET") or "A-2",
            "MARKUP": markup,
            "CHANGE_FROM": from_str,
            "CHANGE_TO": to_str,
            "STATUS": "SENT_TO_AE",
            "PDF_PATH": None,
            "CREATED_AT": now,
            "UPDATED_AT": now,
            "UPDATED_BY": user["sub"],
        }
        r.insert("CORE.REDLINE", [new_rl])

    # Update discrepancy status to REDLINED
    r.update("CORE.DISCREPANCY", {"STATUS": "REDLINED", "UPDATED_AT": now, "UPDATED_BY": user["sub"]}, {"DISC_ID": disc_id})

    # Record workflow event
    evt = {
        "EVENT_ID": uuid.uuid4().hex,
        "ENTITY_TYPE": "DISCREPANCY",
        "ENTITY_ID": disc_id,
        "SITE_ID": sid,
        "FROM_STATE": d["STATUS"],
        "ACTION": "SEND_TO_AE",
        "TO_STATE": "REDLINED",
        "ACTOR_USER_ID": user["sub"],
        "ACTOR_ROLE": user["role"],
        "REASON_CODE": None,
        "COMMENT": "Sent discrepancy to A&E for drawing revision",
        "EVENT_TS": now,
        "CORRELATION_ID": None,
    }
    r.insert("WF.WORKFLOW_EVENT", [evt])

    # Audit log
    AuditTrail.record(entity_type="DISCREPANCY", entity_id=disc_id, action="SEND_TO_AE",
                      before={"STATUS": d["STATUS"]}, after={"STATUS": "REDLINED"}, site_id=sid, source="api")

    # Notify A&E
    note = {
        "NOTIFICATION_ID": uuid.uuid4().hex,
        "ROLE_CODE": "AE_ENGINEER",
        "USER_ID": None,
        "SITE_ID": sid,
        "ENTITY_TYPE": "REDLINE",
        "ENTITY_ID": disc_id,
        "TITLE": f"Redline sent to A&E for {sid}",
        "BODY": f"Discrepancy {d.get('RULE_ID')} ({d.get('TITLE')}) sent to A&E for drawing revision.",
        "SEVERITY": "INFO",
        "READ": False,
        "CREATED_AT": now,
    }
    r.insert("WF.NOTIFICATION", [note])

    return get_discrepancy(disc_id, user)


@router.post("/{disc_id}/submit-ae-revision")
def submit_ae_revision(disc_id: str, body: AeRevisionIn, user: dict = Depends(current_user)):
    """A&E Engineer sends improved drawing version (e.g. REV 2) resolving the discrepancy."""
    r = repo()
    d = r.get("CORE.DISCREPANCY", DISC_ID=disc_id)
    sid = d["SITE_ID"]
    now = now_iso()
    rev_label = body.revision.strip() or "REV 2"

    # Mark linked redlines as INCORPORATED
    rls = r.select("CORE.REDLINE", {"DISC_ID": disc_id})
    for rl in rls:
        r.update("CORE.REDLINE", {"STATUS": "INCORPORATED", "DOC_REVISION": rev_label, "UPDATED_AT": now, "UPDATED_BY": user["sub"]}, {"REDLINE_ID": rl["REDLINE_ID"]})

    # Update discrepancy status to RESOLVED with reason RC-AE-REVISED
    r.update("CORE.DISCREPANCY", {"STATUS": "RESOLVED", "REASON_CODE": "RC-AE-REVISED", "UPDATED_AT": now, "UPDATED_BY": user["sub"]}, {"DISC_ID": disc_id})

    # Record workflow event
    evt = {
        "EVENT_ID": uuid.uuid4().hex,
        "ENTITY_TYPE": "DISCREPANCY",
        "ENTITY_ID": disc_id,
        "SITE_ID": sid,
        "FROM_STATE": d["STATUS"],
        "ACTION": "AE_SUBMIT_REVISION",
        "TO_STATE": "RESOLVED",
        "ACTOR_USER_ID": user["sub"],
        "ACTOR_ROLE": user["role"],
        "REASON_CODE": "RC-AE-REVISED",
        "COMMENT": body.comment or f"A&E issued improved version {rev_label} incorporating redline",
        "EVENT_TS": now,
        "CORRELATION_ID": None,
    }
    r.insert("WF.WORKFLOW_EVENT", [evt])

    # Audit log
    AuditTrail.record(entity_type="DISCREPANCY", entity_id=disc_id, action="AE_SUBMIT_REVISION",
                      before={"STATUS": d["STATUS"]}, after={"STATUS": "RESOLVED", "REASON_CODE": "RC-AE-REVISED", "REVISION": rev_label},
                      site_id=sid, source="api")

    # Notify Scoper and Admin
    for role_code in ("SCOPER", "ADMIN"):
        r.insert("WF.NOTIFICATION", [{
            "NOTIFICATION_ID": uuid.uuid4().hex,
            "ROLE_CODE": role_code,
            "USER_ID": None,
            "SITE_ID": sid,
            "ENTITY_TYPE": "DISCREPANCY",
            "ENTITY_ID": disc_id,
            "TITLE": f"Improved version ({rev_label}) received from A&E",
            "BODY": f"A&E has issued {rev_label} for {sid}. Please review discrepancy and remove redline.",
            "SEVERITY": "INFO",
            "READ": False,
            "CREATED_AT": now,
        }])

    return get_discrepancy(disc_id, user)


@router.post("/{disc_id}/remove-redline")
def remove_redline(disc_id: str, user: dict = Depends(current_user)):
    """Scoper or Reviewer accepts improved drawing revision and removes the redline, officially closing the finding."""
    r = repo()
    d = r.get("CORE.DISCREPANCY", DISC_ID=disc_id)
    sid = d["SITE_ID"]
    now = now_iso()

    # Close/remove linked redlines
    rls = r.select("CORE.REDLINE", {"DISC_ID": disc_id})
    for rl in rls:
        r.update("CORE.REDLINE", {"STATUS": "CLOSED", "UPDATED_AT": now, "UPDATED_BY": user["sub"]}, {"REDLINE_ID": rl["REDLINE_ID"]})

    # Close the discrepancy
    r.update("CORE.DISCREPANCY", {"STATUS": "CLOSED", "REASON_CODE": "RC-AE-REVISED", "UPDATED_AT": now, "UPDATED_BY": user["sub"]}, {"DISC_ID": disc_id})

    # Record workflow event
    evt = {
        "EVENT_ID": uuid.uuid4().hex,
        "ENTITY_TYPE": "DISCREPANCY",
        "ENTITY_ID": disc_id,
        "SITE_ID": sid,
        "FROM_STATE": d["STATUS"],
        "ACTION": "REMOVE_REDLINE",
        "TO_STATE": "CLOSED",
        "ACTOR_USER_ID": user["sub"],
        "ACTOR_ROLE": user["role"],
        "REASON_CODE": "RC-AE-REVISED",
        "COMMENT": "Redline removed and discrepancy closed following CD revision verification",
        "EVENT_TS": now,
        "CORRELATION_ID": None,
    }
    r.insert("WF.WORKFLOW_EVENT", [evt])

    # Audit log
    AuditTrail.record(entity_type="DISCREPANCY", entity_id=disc_id, action="REMOVE_REDLINE",
                      before={"STATUS": d["STATUS"]}, after={"STATUS": "CLOSED"}, site_id=sid, source="api")

    # Notify all parties
    for role_code in ("AE_ENGINEER", "ADMIN"):
        r.insert("WF.NOTIFICATION", [{
            "NOTIFICATION_ID": uuid.uuid4().hex,
            "ROLE_CODE": role_code,
            "USER_ID": None,
            "SITE_ID": sid,
            "ENTITY_TYPE": "DISCREPANCY",
            "ENTITY_ID": disc_id,
            "TITLE": f"Redline removed for {sid}",
            "BODY": f"Redline on {d.get('RULE_ID')} was removed by {user['sub']}. Finding is now closed.",
            "SEVERITY": "INFO",
            "READ": False,
            "CREATED_AT": now,
        }])

    return get_discrepancy(disc_id, user)
