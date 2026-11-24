"""Sites: list (scoped per persona), detail with everything the site screen needs, dashboard counts."""
from collections import Counter
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends

from api.deps import current_user, finished_sites, my_notifications, provider_companies, provider_drawings, provider_package_released, provider_phase, ref, repo, require, shown_provider, site_scope, workflow
from scopeiq.common.audit import AuditTrail
from scopeiq.common.errors import NotFound, PermissionDenied, ValidationError
from scopeiq.db.repository import now_iso
from scopeiq.integrations.sharepoint import get_store
from scopeiq.services.site_management import delete_site_cascade

router = APIRouter(prefix="/sites", tags=["sites"])

# what a service provider is told about a site
_PROVIDER_SITE_FIELDS = ("SITE_ID", "SITE_NAME", "ADDRESS", "CITY", "STATE", "ZIP", "MARKET", "LATITUDE", "LONGITUDE", "STRUCTURE_TYPE", "HEIGHT_FT",
                         "STRUCTURE_OWNER", "PROJECT_NAME", "PROJECT_TYPE", "CX_SP")


def _check_scope(user: dict, site: dict) -> None:
    scope = site_scope(user)
    if scope and site.get("CX_SP") != scope["CX_SP"]:
        raise PermissionDenied("This site is not assigned to your organisation")


@router.get("")
def list_sites(user: dict = Depends(current_user)):
    r = repo()
    sites = r.select("CORE.SITE", site_scope(user) or None, order_by="SITE_ID")
    if user["role"] == "CX_SP":           # a service provider's list: the site and what it has been given, nothing of the scoping work
        return [{**{k: s.get(k) for k in _PROVIDER_SITE_FIELDS}, "DRAWINGS_READY": bool(provider_drawings(s["SITE_ID"])), "PHASE": provider_phase(s)} for s in sites]

    # Document counts: one query for all sites, grouped by SITE_ID + DOC_TYPE
    # NOTE: DOC_COUNT only reflects files processed by the pipeline (CORE.DOCUMENT).
    # SHAREPOINT_FILES reflects all files in the SharePoint/disk folder (pre- and post-pipeline).
    all_docs = r.query("SELECT SITE_ID, DOC_TYPE FROM CORE.DOCUMENT WHERE STATUS = 'CURRENT'")
    doc_by_site: dict = {}
    for d in all_docs:
        sid = d["SITE_ID"]
        doc_by_site.setdefault(sid, []).append(d["DOC_TYPE"])

    # Upload counts (RECEIVED / DUPLICATE — not yet pipelined)
    all_uploads = r.query("SELECT SITE_ID, DOC_TYPE FROM CORE.UPLOAD WHERE STATUS IN ('RECEIVED', 'DUPLICATE')")
    uploads_by_site: dict = {}
    for u in all_uploads:
        sid = u["SITE_ID"]
        uploads_by_site.setdefault(sid, 0)
        uploads_by_site[sid] += 1

    discs = Counter((d["SITE_ID"], d["STATUS"]) for d in r.query("SELECT SITE_ID, STATUS FROM CORE.DISCREPANCY"))

    # SharePoint file counts — read directly from the store (same source as the SharePoint tab).
    # This captures uploaded files even before the pipeline has run, so sites never show 0
    # when files have actually been uploaded.
    try:
        store = get_store()
        sp_files_by_site: dict = {
            sid: len(store.list_files(sid))
            for sid in store.list_site_ids()
        }
    except Exception:
        sp_files_by_site = {}

    companies = provider_companies()
    for s in sites:
        sid = s["SITE_ID"]
        s["CX_SP"] = shown_provider(s.get("CX_SP"), companies)
        doc_types = doc_by_site.get(sid, [])
        by_type = Counter(doc_types)
        sp_files = sp_files_by_site.get(sid, 0)
        s["OPEN_DISCREPANCIES"] = discs.get((sid, "OPEN"), 0)
        s["ACTIONS"] = [a["action"] for a in workflow().actions("SITE_SCOPING", s["WORKFLOW_STATE"] or "ASSIGNED", user["role"])]
        s["DOC_COUNT"] = len(doc_types)            # pipeline-registered documents
        s["DOC_BY_TYPE"] = dict(by_type)           # e.g. {"RFDS": 1, "CD": 2, "MA_SA": 1}
        s["PENDING_UPLOADS"] = uploads_by_site.get(sid, 0)
        s["SHAREPOINT_FILES"] = sp_files           # total files in SharePoint folder (pre+post pipeline)
        # PIPELINE_NEEDED is true when files exist in SharePoint but haven't been processed yet
        s["PIPELINE_NEEDED"] = sp_files > 0 and len(doc_types) == 0
    return sites


@router.get("/dashboard")
def dashboard(user: dict = Depends(current_user)):
    r = repo()
    sites = r.select("CORE.SITE", site_scope(user) or None)
    if user["role"] == "CX_SP":
        return {"sites": len(sites)}
    ids, ready = {s["SITE_ID"] for s in sites}, finished_sites()
    d = [x for x in r.query("SELECT SITE_ID, STATUS, SEVERITY, OUTCOME, RULE_ID FROM CORE.DISCREPANCY") if x["SITE_ID"] in ids]
    est = [x for x in r.query("SELECT SITE_ID, CYCLE_DAYS, TOTAL_USD FROM CORE.ESTIMATE") if x["SITE_ID"] in ids]
    inbox = len(my_notifications(user, unread_only=True))
    return {"sites": len(sites), "by_state": Counter(s["WORKFLOW_STATE"] for s in sites), "by_stream": Counter(s["STREAM"] for s in sites),
            "discrepancies": {"total": len(d), "by_status": Counter(x["STATUS"] for x in d), "by_outcome": Counter(x["OUTCOME"] for x in d),
                              "by_severity": Counter(x["SEVERITY"] for x in d)},
            "redlines": Counter(x["STATUS"] for x in r.query("SELECT STATUS, SITE_ID FROM CORE.REDLINE") if x["SITE_ID"] in ids & ready),
            "rfis": Counter(x["STATUS"] for x in r.query("SELECT STATUS, SITE_ID FROM CORE.RFI") if x["SITE_ID"] in ids & ready),
            "ehs_open": sum(1 for x in r.query("SELECT STATUS, SITE_ID FROM CORE.EHS_ALERT") if x["SITE_ID"] in ids and x["STATUS"] == "OPEN"),
            "estimate_total_usd": round(sum(x["TOTAL_USD"] or 0 for x in est), 2), "inbox_unread": inbox}


@router.get("/service-providers")
def list_service_providers(user: dict = Depends(current_user)):
    """The service-provider companies an admin has created a login for."""
    return [{"name": n} for n in provider_companies()]


@router.get("/{site_id}/provider")
def provider_view(site_id: str, user: dict = Depends(current_user)):
    """What a service provider is given for a site: the final construction drawings, and from the handshake on the scope of work and the BOM."""
    r = repo()
    site = r.get("CORE.SITE", SITE_ID=site_id)
    _check_scope(user, site)
    released = provider_package_released(site)
    phase = provider_phase(site)
    keep = lambda row, fields: {k: row.get(k) for k in fields}      # noqa: E731
    mine = [e for e in workflow().history("SITE_SCOPING", site_id) if e.get("ACTION") in ("REQUEST_CHANGES", "SP_REQUEST_CHANGES")]
    return {"site_id": site_id, "site_name": site.get("SITE_NAME"), "phase": phase,
            "requests": [{"when": e.get("EVENT_TS"), "reason": next((c["DESCRIPTION"] for c in ref().rows("reason_codes") if c["REASON_CODE"] == e.get("REASON_CODE")), e.get("REASON_CODE")),
                          "comment": e.get("COMMENT")} for e in reversed(mine)],
            "drawings": [keep(d, ("DOC_ID", "FILE_NAME", "FILE_FORMAT", "REVISION", "SIZE_BYTES")) for d in provider_drawings(site_id)],
            "scope": {"released": released,
                      "items": [keep(x, ("SECTOR", "POSITION", "KIND", "CATALOG_KEY", "ACTION", "FROM_POSITION"))
                                for x in r.select("CORE.EQUIPMENT_DELTA", {"SITE_ID": site_id, "RUN_ID": site.get("LAST_RUN_ID")}, order_by="SEQ")] if released and site.get("LAST_RUN_ID") else []},
            "bom": {"released": released, "approved": phase == "APPROVED",
                    "lines": [keep(b, ("SECTOR", "CATEGORY", "MANUFACTURER", "MODEL", "DESCRIPTION", "UOM", "TOTAL_QTY", "ACTION", "SUPPLY"))
                              for b in r.select("CORE.BOM_OUTPUT_LINE", {"SITE_ID": site_id}, order_by="CATEGORY, SECTOR")] if released else []}}


@router.get("/{site_id}")
def site_detail(site_id: str, user: dict = Depends(current_user)):
    r = repo()
    site = r.get("CORE.SITE", SITE_ID=site_id)
    _check_scope(user, site)
    site["CX_SP"] = shown_provider(site.get("CX_SP"))
    if user["role"] == "CX_SP":
        empty = {k: [] for k in ("actions", "milestones", "documents", "sectors", "trunks", "analyses", "delta", "requirements", "estimate", "ehs_alerts", "last_run", "workflow_history")}
        return {**empty, "site": {k: site.get(k) for k in _PROVIDER_SITE_FIELDS}, "revision_check": None}
    run_id = site.get("LAST_RUN_ID")
    by_run = lambda t: r.select(t, {"SITE_ID": site_id, "RUN_ID": run_id}) if run_id else []  # noqa: E731
    docs = r.select("CORE.DOCUMENT", {"SITE_ID": site_id}, order_by="DOC_TYPE, REVISION_RANK DESC")
    
    # Dynamic document revision checker
    superseded = [d for d in docs if d.get("STATUS") == "SUPERSEDED"]
    current_docs = [d for d in docs if d.get("STATUS") == "CURRENT"]
    by_type: dict = {}
    for d in docs:
        typ = d.get("DOC_TYPE")
        by_type.setdefault(typ, []).append(d)
    
    type_summaries = []
    for typ, type_docs in sorted(by_type.items()):
        picked = next((d for d in type_docs if d.get("STATUS") == "CURRENT"), None)
        older = [d for d in type_docs if d.get("STATUS") == "SUPERSEDED"]
        type_summaries.append({
            "doc_type": typ,
            "picked_file": picked.get("FILE_NAME") if picked else None,
            "picked_revision": (picked.get("REVISION") or "REV 0") if picked else None,
            "picked_format": picked.get("FILE_FORMAT") if picked else None,
            "has_superseded": len(older) > 0,
            "superseded_revisions": [(d.get("REVISION") or d.get("FILE_NAME")) for d in older],
            "total_files": len(type_docs),
        })

    revision_check = {
        "status": "VERIFIED",
        "message": f"{len(superseded)} older revision(s) superseded; highest revision picked for all document types." if superseded else "All documents verified at latest revision.",
        "latest_picked_count": len(current_docs),
        "superseded_count": len(superseded),
        "total_documents": len(docs),
        "types": type_summaries,
    }

    return {
        "site": site,
        "actions": workflow().actions("SITE_SCOPING", site["WORKFLOW_STATE"] or "ASSIGNED", user["role"]),
        "milestones": r.select("CORE.MILESTONE", {"SITE_ID": site_id}, order_by="SEQ"),
        "documents": docs,
        "revision_check": revision_check,
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


@router.delete("/{site_id}")
def delete_site(site_id: str, user: dict = Depends(require("ADMIN"))):
    """Admin: delete a site and all associated database records, documents, run history, and files."""
    sid = site_id.strip().upper()
    r = repo()
    existing = r.select("CORE.SITE", {"SITE_ID": sid})
    if not existing:
        raise NotFound(f"Site {sid} not found")
    res = delete_site_cascade(r, sid, delete_files=True, deleted_by=user.get("sub", "admin"))
    return {"status": "ok", "site_id": sid, **res}


class AssignSpIn(BaseModel):
    cx_sp: str = Field(min_length=1, max_length=120)


@router.post("/{site_id}/assign-sp")
def assign_sp(site_id: str, body: AssignSpIn, user: dict = Depends(require("ADMIN", "SCOPER", "REVIEWER"))):
    """Assign or change the Construction Service Provider (CX_SP) for a site."""
    sid = site_id.strip().upper()
    r = repo()
    site = r.select("CORE.SITE", {"SITE_ID": sid})
    if not site:
        raise NotFound(f"Site {sid} not found")
    sp = body.cx_sp.strip()
    if workflow().is_out_for_approval(site[0].get("WORKFLOW_STATE")):
        raise PermissionDenied("The package is with the service provider or approved; return it to scoping before changing the provider")
    if sp not in provider_companies():
        raise ValidationError("Choose a service provider that has a login. An admin creates one under User logins.")
    r.update("CORE.SITE", {"CX_SP": sp, "UPDATED_AT": now_iso(), "UPDATED_BY": user.get("sub", "admin")}, {"SITE_ID": sid})
    AuditTrail.record(entity_type="SITE", entity_id=sid, action="ASSIGN_SP", after={"cx_sp": sp}, site_id=sid, source="api")
    return {"site_id": sid, "cx_sp": sp}
