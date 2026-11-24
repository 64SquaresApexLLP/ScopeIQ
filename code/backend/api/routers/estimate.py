"""Delta, service drivers, site requirements, estimate and EH&S alerts for a site's latest run."""
from pathlib import Path
import uuid

from fastapi import APIRouter, Depends

from api.deps import check_site_scope, current_user, ref, repo, require, shown_provider, workflow
from api.schemas import SpQuoteIn, TransitionIn
from scopeiq.common.audit import AuditTrail
from scopeiq.db.repository import now_iso

router = APIRouter(tags=["estimate"])

# the handshake and review events shown on the Handshake tab (never pipeline steps)
HANDSHAKE_EVENTS = {"SUBMIT_TO_SP", "AGREE", "REQUEST_CHANGES", "APPROVE_FBA", "REJECT_FBA", "RETURN_TO_SCOPER", "TRIGGER_REWORK", "SP_AGREE", "SP_REQUEST_CHANGES", "SUBMIT_FBA"}


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
def get_handshake_detail(site_id: str, user: dict = Depends(current_user)):
    site = check_site_scope(user, site_id)
    r = repo()
    state = site.get("WORKFLOW_STATE") or "IN_SCOPING"
    wf = workflow()
    all_actions = wf.actions("SITE_SCOPING", state, user["role"])
    header = {"site_id": site_id, "site_name": site.get("SITE_NAME"), "market": site.get("MARKET"), "cx_sp": shown_provider(site.get("CX_SP")), "workflow_state": state,
              "state_description": (wf.state_row("SITE_SCOPING", state) or {}).get("DESCRIPTION"), "package_out": wf.is_out_for_approval(state)}
    # 6.2 Equipment Delta (SoW Summary)
    run_id = site.get("LAST_RUN_ID")
    deltas = r.select("CORE.EQUIPMENT_DELTA", {"SITE_ID": site_id, "RUN_ID": run_id}, order_by="SEQ") if run_id else []

    # 6.2 BOM Summary & Lines
    boms = r.select("CORE.BOM_OUTPUT_LINE", {"SITE_ID": site_id, "RUN_ID": run_id}, order_by="CATEGORY, SECTOR") if run_id else []
    if not boms and run_id:
        revs_for_lines = [x for x in r.select("CORE.BOM_REVISION", {"SITE_ID": site_id}, order_by="REV_NO DESC") if x.get("KIND") != "TOOL_REV0"]
        if revs_for_lines:
            rev_fallback = revs_for_lines[0]
            rev_lines = r.select("CORE.BOM_LINE", {"BOM_REV_ID": rev_fallback["BOM_REV_ID"]})
            cat = ref().catalog
            for l in rev_lines:
                it = cat.items.get(l["CATALOG_KEY"])
                qty = float(l.get("TOTAL_QTY") or l.get("DESIGN_QTY") or 1.0)
                unit_cost = float(it.unit_cost if it and it.unit_cost else 0.0)
                boms.append({
                    "LINE_ID": l["LINE_ID"],
                    "RUN_ID": rev_fallback.get("RUN_ID"),
                    "SITE_ID": site_id,
                    "MARKET": site.get("MARKET") or "",
                    "SECTOR": l.get("SECTOR"),
                    "TECHNOLOGY": it.technology if it else "",
                    "BAND": (", ".join(it.bands) if isinstance(it.bands, (list, tuple)) else str(it.bands or "")) if it else "",
                    "CATEGORY": it.category if it else "Materials",
                    "SUBCATEGORY": it.subcategory if it else "",
                    "MANUFACTURER": it.manufacturer if it else "",
                    "MODEL": it.model if it else l.get("CATALOG_KEY"),
                    "DESCRIPTION": it.description if it else "",
                    "UOM": it.uom if it else "EA",
                    "DESIGN_QTY": float(l.get("DESIGN_QTY") or qty),
                    "SPARE_QTY": float(l.get("SPARE_QTY") or 0.0),
                    "TOTAL_QTY": qty,
                    "QTY": qty,
                    "UNIT_COST_USD": unit_cost,
                    "TOTAL_COST_USD": round(qty * unit_cost, 2),
                    "ACTION": l.get("ACTION") or "Install",
                    "SOURCE": l.get("SOURCE") or "",
                    "RULE_ID": l.get("RULE_ID") or "",
                    "CATALOG_KEY": l.get("CATALOG_KEY"),
                })
    install_count = sum(1 for b in boms if b.get("ACTION") == "Install" or (b.get("QTY") or 0) > 0)
    remove_count = sum(1 for b in boms if b.get("ACTION") == "Remove")
    total_cost = sum(float(b.get("TOTAL_COST_USD") or 0.0) for b in boms)

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

    # 6.2 Active Revision & FBA Status
    revs = r.select("CORE.BOM_REVISION", {"SITE_ID": site_id}, order_by="REV_NO DESC")
    active_rev = revs[0] if revs else None
    has_bom = len(boms) > 0 or bool(active_rev and active_rev.get("KIND") != "TOOL_REV0")
    has_pipeline_run = bool(site.get("LAST_RUN_ID"))
    rev_label = active_rev.get("REV_LABEL") if active_rev else ("REV 1" if has_bom else "-")
    is_fba_locked = state == "FBA_APPROVED" or bool(active_rev and active_rev.get("STATUS") == "FBA")

    # Audit history: Only show Handshake and Review events, never pipeline steps
    history = [h for h in wf.history("SITE_SCOPING", site_id) if h.get("ACTION") in HANDSHAKE_EVENTS]
    if not has_pipeline_run and len(cds) == 0 and not has_bom:
        history = []

    # the steps this role can take from here (send for final approval, approve, return ...); a BOM must exist to move on
    workflow_actions = all_actions if has_bom else []

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
