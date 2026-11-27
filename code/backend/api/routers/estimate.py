"""Delta, service drivers, site requirements, estimate and EH&S alerts for a site's latest run."""
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends

from api.deps import check_site_scope, current_user, ref, repo, require, shown_provider, workflow
from api.schemas import SpQuoteIn, TransitionIn
from scopeiq.common.audit import AuditTrail
from scopeiq.db.repository import now_iso
from scopeiq.services import bom_revisions

router = APIRouter(tags=["estimate"])

# the handshake and review events shown on the Handshake tab (never pipeline steps)
HANDSHAKE_EVENTS = {"SUBMIT_TO_SP", "AGREE", "REQUEST_CHANGES", "APPROVE_FBA", "REJECT_FBA", "RETURN_TO_SCOPER", "TRIGGER_REWORK", "SUBMIT_REVIEW", "HOLD", "RELEASE", "SP_AGREE", "SP_REQUEST_CHANGES", "SUBMIT_FBA"}


# who may change the lines of a BOM that is still with the scoping team, and in which states of the site
EDIT_ROLES = ("SCOPER", "REVIEWER", "ADMIN")
EDIT_STATES = ("IN_SCOPING", "IN_REVIEW", "REWORK")


def _changes(r, site_id: str, rev: dict, lines: list[dict]) -> list[dict]:
    """What differs from the revision before, line by line, with the reason given for each change (empty for REV 1)."""
    rows = r.select("CORE.BOM_CHANGE", {"TO_REV_ID": rev["BOM_REV_ID"]}, order_by="SECTOR, CATALOG_KEY")
    names: dict = {}
    for x in lines:
        names.setdefault(x.get("CATALOG_KEY"), x)
    prev = next((g for g in reversed(bom_revisions.generated(r, site_id)) if g["REV_NO"] < rev["REV_NO"]), None)
    if prev:
        for x in bom_revisions.lines_of(r, site_id, prev):
            names.setdefault(x.get("CATALOG_KEY"), x)
    return [{**c, "model": (names.get(c.get("CATALOG_KEY")) or {}).get("MODEL") or c.get("CATALOG_KEY"),
             "description": (names.get(c.get("CATALOG_KEY")) or {}).get("DESCRIPTION"), "from_rev": prev["REV_LABEL"] if prev else None} for c in rows]


def _latest(site_id: str) -> str | None:
    return repo().get("CORE.SITE", SITE_ID=site_id).get("LAST_RUN_ID")


@router.get("/sites/{site_id}/delta")
def delta(site_id: str, user: dict = Depends(current_user)):
    check_site_scope(user, site_id)
    return sorted(repo().select("CORE.EQUIPMENT_DELTA", {"SITE_ID": site_id, "RUN_ID": _latest(site_id)}), key=lambda x: x["SEQ"])


@router.get("/sites/{site_id}/estimate")
def site_estimate(site_id: str, user: dict = Depends(current_user)):
    check_site_scope(user, site_id)
    r, run = repo(), _latest(site_id)
    where = {"SITE_ID": site_id, "RUN_ID": run}
    drivers = r.select("CORE.DRIVER_LINE", where, order_by="DRIVER_CODE, SECTOR")
    return {"estimate": next(iter(r.select("CORE.ESTIMATE", where)), None), "drivers": drivers,
            "requirements": next(iter(r.select("CORE.SITE_REQUIREMENT", where)), None),
            "services_total": round(sum(d["AMOUNT"] or 0 for d in drivers), 2)}


@router.post("/sites/{site_id}/quote")
def submit_sp_quote(site_id: str, body: SpQuoteIn, user: dict = Depends(require("CX_SP", "SCOPER", "REVIEWER"))):
    site = check_site_scope(user, site_id)
    r = repo()
    run = site.get("LAST_RUN_ID")
    where = {"SITE_ID": site_id, "RUN_ID": run} if run else {"SITE_ID": site_id}
    est = next(iter(r.select("CORE.ESTIMATE", where)), None)
    drivers = r.select("CORE.DRIVER_LINE", where)
    baseline = float(est.get("SERVICES_USD") if est and est.get("SERVICES_USD") else sum(d.get("AMOUNT") or 0.0 for d in drivers))
    variance_amount = round(body.quote_amount - baseline, 2)
    variance_pct = round((variance_amount / baseline) * 100, 2) if baseline > 0 else 0.0
    abs_pct = abs(variance_pct)
    if abs_pct <= 5.0:
        status = "MATCH"
    elif abs_pct <= 15.0:
        status = "TOLERANCE_WARNING"
    else:
        status = "OUT_OF_TOLERANCE"

    quote_id = f"Q-{site_id}-{uuid.uuid4().hex[:8]}"
    ts = now_iso()
    sp_name = user.get("sp") or user.get("org") or site.get("CX_SP") or user["sub"]
    row = {
        "QUOTE_ID": quote_id,
        "SITE_ID": site_id,
        "SP_NAME": sp_name,
        "QUOTE_AMOUNT": body.quote_amount,
        "BASELINE_AMOUNT": baseline,
        "VARIANCE_AMOUNT": variance_amount,
        "VARIANCE_PCT": variance_pct,
        "STATUS": status,
        "NOTES": body.notes or "",
        "BREAKDOWN": body.breakdown or [],
        "SUBMITTED_BY": user["sub"],
        "SUBMITTED_AT": ts,
    }
    r.insert("CORE.SP_QUOTE", [row])
    AuditTrail.record(entity_type="SP_QUOTE", entity_id=quote_id, action="SUBMIT", after=row, site_id=site_id, source="api")
    return row


@router.get("/sites/{site_id}/quotes")
def get_sp_quotes(site_id: str, user: dict = Depends(current_user)):
    check_site_scope(user, site_id)
    return repo().select("CORE.SP_QUOTE", {"SITE_ID": site_id}, order_by="SUBMITTED_AT DESC")


@router.get("/sites/{site_id}/handshake")
def get_handshake_detail(site_id: str, rev: str | None = None, user: dict = Depends(current_user)):
    site = check_site_scope(user, site_id)
    r = repo()
    state = site.get("WORKFLOW_STATE") or "IN_SCOPING"
    wf = workflow()
    all_actions = wf.actions("SITE_SCOPING", state, user["role"])
    header = {"site_id": site_id, "site_name": site.get("SITE_NAME"), "market": site.get("MARKET"), "cx_sp": shown_provider(site.get("CX_SP")), "workflow_state": state,
              "state_description": (wf.state_row("SITE_SCOPING", state) or {}).get("DESCRIPTION"), "owner_role": (wf.state_row("SITE_SCOPING", state) or {}).get("OWNER_ROLE"), "package_out": wf.is_out_for_approval(state)}
    # 6.2 Equipment Delta (SoW Summary)
    run_id = site.get("LAST_RUN_ID")
    deltas = bom_revisions.scope_items(r, site_id, run_id)

    # the BOM: every generated BOM is a revision; the one shown is the one asked for, else the latest
    revs = list(reversed(bom_revisions.generated(r, site_id)))
    latest = revs[0] if revs else None
    active_rev = next((x for x in revs if x["BOM_REV_ID"] == rev), latest) if rev else latest
    boms = bom_revisions.lines_of(r, site_id, active_rev) if active_rev else bom_revisions.lines_of(r, site_id, None)
    install_count = sum(1 for b in boms if str(b.get("ACTION") or "").lower() == "install")
    remove_count = sum(1 for b in boms if str(b.get("ACTION") or "").lower() == "remove")
    total_cost = sum(float(b.get("TOTAL_COST_USD") or 0.0) for b in boms if str(b.get("ACTION") or "").lower() == "install")

    # 6.2 CD Drawings
    cds = [d for d in r.select("CORE.DOCUMENT", {"SITE_ID": site_id, "DOC_TYPE": "CD"}, order_by="REVISION_RANK DESC") if d.get("STATUS") == "CURRENT"]
    redlines = r.select("CORE.REDLINE", {"SITE_ID": site_id})
    if redlines and any(x.get("PDF_PATH") for x in redlines):
        red_file = next((x["PDF_PATH"] for x in redlines if x.get("PDF_PATH")), None)
        if red_file and not any("REDLINED" in c.get("FILE_NAME", "") for c in cds):
            cds.append({
                "DOC_ID": f"DOC-{site_id}-REDLINE",
                "SITE_ID": site_id,
                "DOC_TYPE": "CD_REDLINE",
                "FILE_NAME": Path(red_file).name,
                "REL_PATH": red_file,
                "FILE_FORMAT": "PDF",
                "REVISION": "REDLINED",
                "REVISION_RANK": 99,
                "STATUS": "CURRENT",
            })

    # the revision shown, and what changed from the one before
    has_bom = len(boms) > 0 or bool(revs)
    has_pipeline_run = bool(site.get("LAST_RUN_ID"))
    rev_label = active_rev.get("REV_LABEL") if active_rev else ("REV 1" if has_bom else "-")
    is_fba_locked = state == "FBA_APPROVED" or bool(active_rev and active_rev.get("STATUS") == "FBA")
    is_latest = bool(active_rev and latest and active_rev["BOM_REV_ID"] == latest["BOM_REV_ID"])
    changes = _changes(r, site_id, active_rev, boms) if active_rev else []
    editable = bool(is_latest and bom_revisions.is_draft(active_rev) and user["role"] in EDIT_ROLES and state in EDIT_STATES)
    history = [h for h in wf.history("SITE_SCOPING", site_id) if h.get("ACTION") in HANDSHAKE_EVENTS]
    if not has_pipeline_run and len(cds) == 0 and not has_bom:
        history = []

    # the steps this role can take from here (send for final approval, approve, return ...); a BOM must exist to move on
    workflow_actions = all_actions if has_bom else []
    # a revision the provider has seen cannot change: after a change request or a rework, the next revision is started from it
    can_start_next = bool(is_latest and active_rev and not bom_revisions.is_draft(active_rev) and user["role"] in EDIT_ROLES
                          and state in ("IN_SCOPING", "REWORK"))

    return {
        **header,
        "current_bom_rev": rev_label,
        "is_fba_locked": is_fba_locked,
        "workflow_actions": workflow_actions,
        "has_bom": has_bom,
        "has_run_pipeline": has_pipeline_run,
        "delta": deltas,
        "cd_documents": cds,
        "bom_lines": boms,
        "revisions": [{"id": x["BOM_REV_ID"], "label": x["REV_LABEL"], "status": x["STATUS"], "locked": bool(x.get("LOCKED")), "created_at": x.get("CREATED_AT"),
                       "created_by": x.get("CREATED_BY"), "approved_at": x.get("APPROVED_AT"), "approved_by": x.get("APPROVED_BY"), "notes": x.get("NOTES"),
                       "totals": x.get("TOTALS") or {}, "is_latest": x["BOM_REV_ID"] == (latest or {}).get("BOM_REV_ID")} for x in revs],
        "selected_rev": active_rev["BOM_REV_ID"] if active_rev else None,
        "selected_rev_status": active_rev["STATUS"] if active_rev else None,
        "is_latest_rev": is_latest,
        "bom_editable": editable,
        "can_start_next_rev": can_start_next,
        "bom_changes": changes,
        "bom_summary": {
            "lines_count": len(boms),
            "install_count": install_count,
            "remove_count": remove_count,
            "total_material_cost": total_cost,
            "revision": rev_label,
            "file_name": f"{site_id}_BOM.xlsx",
            "is_locked": is_fba_locked,
        },
        "workflow_history": history,
    }


@router.get("/ehs-alerts")
def ehs_alerts(site_id: str | None = None, status: str | None = None, user: dict = Depends(current_user)):
    where = {k: v for k, v in {"SITE_ID": site_id, "STATUS": status}.items() if v}
    rows = repo().select("CORE.EHS_ALERT", where or None, order_by="SITE_ID")
    for x in rows:
        x["ACTIONS"] = [a["action"] for a in workflow().actions("EHS_ALERT", x["STATUS"], user["role"])]
    return rows


@router.post("/ehs-alerts/{alert_id}/transition")
def ehs_transition(alert_id: str, body: TransitionIn, user: dict = Depends(current_user)):
    return workflow().transition("EHS_ALERT", alert_id, body.action, reason_code=body.reason_code, comment=body.comment)
