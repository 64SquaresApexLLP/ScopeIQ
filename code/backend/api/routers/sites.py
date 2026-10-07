"""Sites: list (scoped per persona), detail with everything the site screen needs, dashboard counts."""
from collections import Counter

from fastapi import APIRouter, Depends

from api.deps import current_user, repo, site_scope, workflow
from scopeiq.common.errors import PermissionDenied

router = APIRouter(prefix="/sites", tags=["sites"])


def _check_scope(user: dict, site: dict) -> None:
    scope = site_scope(user)
    if scope and site.get("CX_SP") != scope["CX_SP"]:
        raise PermissionDenied("This site is not assigned to your organisation")


@router.get("")
def list_sites(user: dict = Depends(current_user)):
    r = repo()
    sites = r.select("CORE.SITE", site_scope(user) or None, order_by="SITE_ID")
    discs = Counter((d["SITE_ID"], d["STATUS"]) for d in r.query("SELECT SITE_ID, STATUS FROM CORE.DISCREPANCY"))
    for s in sites:
        s["OPEN_DISCREPANCIES"] = discs.get((s["SITE_ID"], "OPEN"), 0)
        s["ACTIONS"] = [a["action"] for a in workflow().actions("SITE_SCOPING", s["WORKFLOW_STATE"] or "ASSIGNED", user["role"])]
    return sites


@router.get("/dashboard")
def dashboard(user: dict = Depends(current_user)):
    r = repo()
    sites = r.select("CORE.SITE", site_scope(user) or None)
    ids = {s["SITE_ID"] for s in sites}
    d = [x for x in r.query("SELECT SITE_ID, STATUS, SEVERITY, OUTCOME, RULE_ID FROM CORE.DISCREPANCY") if x["SITE_ID"] in ids]
    est = [x for x in r.query("SELECT SITE_ID, CYCLE_DAYS, TOTAL_USD FROM CORE.ESTIMATE") if x["SITE_ID"] in ids]
    inbox = r.query("SELECT COUNT(*) AS N FROM WF.NOTIFICATION WHERE ROLE_CODE = %s AND READ_AT IS NULL", [user["role"]])[0]["N"]
    return {"sites": len(sites), "by_state": Counter(s["WORKFLOW_STATE"] for s in sites), "by_stream": Counter(s["STREAM"] for s in sites),
            "discrepancies": {"total": len(d), "by_status": Counter(x["STATUS"] for x in d), "by_outcome": Counter(x["OUTCOME"] for x in d),
                              "by_severity": Counter(x["SEVERITY"] for x in d)},
            "redlines": Counter(x["STATUS"] for x in r.query("SELECT STATUS, SITE_ID FROM CORE.REDLINE") if x["SITE_ID"] in ids),
            "rfis": Counter(x["STATUS"] for x in r.query("SELECT STATUS, SITE_ID FROM CORE.RFI") if x["SITE_ID"] in ids),
            "ehs_open": sum(1 for x in r.query("SELECT STATUS, SITE_ID FROM CORE.EHS_ALERT") if x["SITE_ID"] in ids and x["STATUS"] == "OPEN"),
            "estimate_total_usd": round(sum(x["TOTAL_USD"] or 0 for x in est), 2), "inbox_unread": inbox}


@router.get("/{site_id}")
def site_detail(site_id: str, user: dict = Depends(current_user)):
    r = repo()
    site = r.get("CORE.SITE", SITE_ID=site_id)
    _check_scope(user, site)
    run_id = site.get("LAST_RUN_ID")
    by_run = lambda t: r.select(t, {"SITE_ID": site_id, "RUN_ID": run_id}) if run_id else []  # noqa: E731
    return {
        "site": site,
        "actions": workflow().actions("SITE_SCOPING", site["WORKFLOW_STATE"] or "ASSIGNED", user["role"]),
        "milestones": r.select("CORE.MILESTONE", {"SITE_ID": site_id}, order_by="SEQ"),
        "documents": r.select("CORE.DOCUMENT", {"SITE_ID": site_id}, order_by="DOC_TYPE, REVISION_RANK"),
        "sectors": by_run("CORE.SECTOR_INFO"),
        "trunks": by_run("CORE.TRUNK_MEASURE"),
        "analyses": by_run("CORE.ANALYSIS_RESULT"),
        "delta": sorted(by_run("CORE.EQUIPMENT_DELTA"), key=lambda x: x["SEQ"]),
        "requirements": by_run("CORE.SITE_REQUIREMENT"),
        "estimate": by_run("CORE.ESTIMATE"),
        "ehs_alerts": [dict(a, ACTIONS=[x["action"] for x in workflow().actions("EHS_ALERT", a["STATUS"], user["role"])])
                       for a in r.select("CORE.EHS_ALERT", {"SITE_ID": site_id})],
        "last_run": r.select("CORE.PIPELINE_RUN", {"RUN_ID": run_id}) if run_id else [],
        "workflow_history": workflow().history("SITE_SCOPING", site_id),
    }


@router.get("/{site_id}/config")
def config_lines(site_id: str, source: str | None = None, user: dict = Depends(current_user)):
    r = repo()
    site = r.get("CORE.SITE", SITE_ID=site_id)
    _check_scope(user, site)
    where = {"SITE_ID": site_id, "RUN_ID": site["LAST_RUN_ID"]}
    if source:
        where["SOURCE"] = source
    return r.select("CORE.CONFIG_LINE", where, order_by="SOURCE, SECTOR, POSITION")


@router.get("/{site_id}/evidence")
def evidence(site_id: str, selected_only: bool = False, user: dict = Depends(current_user)):
    r = repo()
    _check_scope(user, r.get("CORE.SITE", SITE_ID=site_id))
    where = {"SITE_ID": site_id}
    if selected_only:
        where["SELECTED"] = True
    frames = r.select("CORE.EVIDENCE_FRAME", where, order_by="FRAME_INDEX")
    for f in frames:
        f["URL"] = f"/files/{f['PATH']}"
    return {"frames": frames, "field_objects": r.select("CORE.FIELD_OBJECT", {"SITE_ID": site_id})}


@router.get("/{site_id}/fields")
def extracted_fields(site_id: str, needs_review: bool | None = None, user: dict = Depends(current_user)):
    r = repo()
    site = r.get("CORE.SITE", SITE_ID=site_id)
    where = {"SITE_ID": site_id, "RUN_ID": site["LAST_RUN_ID"]}
    if needs_review is not None:
        where["NEEDS_REVIEW"] = bool(needs_review)
    return r.select("CORE.EXTRACTED_FIELD", where)
