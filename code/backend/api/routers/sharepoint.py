"""SharePoint: sites (one folder per site), the admin action that creates a site + its folder, and file upload into the selected
site's folder. The library behind it is chosen by `sharepoint.provider` (local folder or Microsoft Graph) - see
scopeiq/integrations/sharepoint.py."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from api.deps import check_site_scope, current_user, repo, require, site_scope
from scopeiq.common.audit import AuditTrail
from scopeiq.common.errors import Conflict, NotFound, ValidationError
from scopeiq.config import get_settings
from scopeiq.db.repository import now_iso
from scopeiq.integrations.sharepoint import TYPE_FOLDERS, detect_doc_type, get_store, validate_site_id

router = APIRouter(tags=["sharepoint"])


class SiteIn(BaseModel):
    site_id: str = Field(description="4 letters + 4 digits, e.g. TXDA1024")
    site_name: str = Field(min_length=2, max_length=120)
    city: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=2, max_length=2)
    stream: Literal["BOM", "DESIGN", "DEPLOYMENT"] = "BOM"
    structure_type: Literal["Monopole", "Self-support tower", "Guyed tower", "Rooftop"] = "Monopole"
    height_ft: float | None = Field(default=None, ge=0, le=2000)
    address: str = ""
    market: str = ""


@router.get("/sharepoint/status")
def status(user: dict = Depends(require("ADMIN"))):
    s = get_store()
    return {"provider": s.name, "location": s.location, "document_types": TYPE_FOLDERS,
            "max_upload_mb": int(get_settings().get("sharepoint.max_upload_mb", 400))}


@router.get("/sharepoint/sites")
def list_sites(user: dict = Depends(require("ADMIN"))):
    """Every site that has a SharePoint folder, with its file count. Admin only."""
    store, r = get_store(), repo()
    scope = site_scope(user)
    rows = {s["SITE_ID"]: s for s in r.select("CORE.SITE", scope or None, order_by="SITE_ID")}
    # Auto-provision folder for database sites if not present
    if hasattr(store, "site_exists") and hasattr(store, "create_site_folder"):
        for sid in rows:
            if not store.site_exists(sid):
                store.create_site_folder(sid)
    out = []
    for sid in store.list_site_ids():
        if scope and sid not in rows:
            continue
        files = store.list_files(sid)
        s = rows.get(sid, {})
        out.append({"site_id": sid, "site_name": s.get("SITE_NAME") or "", "city": s.get("CITY") or "", "state": s.get("STATE") or "",
                    "stream": s.get("STREAM") or "", "files": len(files), "bytes": sum(f["size"] for f in files),
                    "in_database": sid in rows})
    return {"location": store.location, "provider": store.name, "sites": out}


@router.post("/admin/sites")
def create_site(body: SiteIn, user: dict = Depends(require("ADMIN"))):
    """Admin: create a site. This creates its folder tree in SharePoint and the site record, so the site shows up for uploads."""
    sid = validate_site_id(body.site_id)
    store, r = get_store(), repo()
    if r.select("CORE.SITE", {"SITE_ID": sid}):
        raise Conflict(f"Site {sid} already exists")
    if hasattr(store, "site_exists") and store.site_exists(sid):
        lib_root = getattr(store, "library_root", "Ericsson-Scoping/Sites")
        folder = {"path": f"{lib_root}/{sid}"}
    else:
        folder = store.create_site_folder(sid)                      # SharePoint first: if it fails, no database row is left behind
    row = {"SITE_ID": sid, "SITE_NAME": body.site_name.strip(), "MARKET": body.market or get_settings().get("app.market", ""),
           "CUSTOMER": get_settings().get("app.carrier", ""), "ADDRESS": body.address, "CITY": body.city.strip(), "STATE": body.state.upper(),
           "STRUCTURE_TYPE": body.structure_type, "HEIGHT_FT": body.height_ft, "SITE_STATUS": "New", "STREAM": body.stream,
           "WORKFLOW_STATE": "ASSIGNED", "ASSIGNED_DATE": now_iso()[:10], "UPDATED_AT": now_iso(), "UPDATED_BY": user["sub"]}
    r.insert("CORE.SITE", [row])
    AuditTrail.record(entity_type="SITE", entity_id=sid, action="CREATE",
                      after={"site_name": row["SITE_NAME"], "city": row["CITY"], "state": row["STATE"], "sharepoint_path": folder["path"]},
                      site_id=sid, source="api")
    return {"site": row, "sharepoint": folder}


class SiteUpdate(BaseModel):
    site_name: str | None = None
    city: str | None = None
    state: str | None = None
    address: str | None = None
    structure_type: Literal["Monopole", "Self-support tower", "Guyed tower", "Rooftop"] | None = None
    height_ft: float | None = None
    stream: Literal["BOM", "DESIGN", "DEPLOYMENT"] | None = None


@router.patch("/admin/sites/{site_id}")
def update_site(site_id: str, body: SiteUpdate, user: dict = Depends(require("ADMIN"))):
    """Admin: update site name, city, state, or other metadata."""
    sid = validate_site_id(site_id)
    r = repo()
    existing = r.select("CORE.SITE", {"SITE_ID": sid})
    if not existing:
        raise NotFound(f"Site {sid} not found")
    updates: dict = {}
    if body.site_name is not None and body.site_name.strip():
        updates["SITE_NAME"] = body.site_name.strip()
    if body.city is not None and body.city.strip():
        updates["CITY"] = body.city.strip()
    if body.state is not None and body.state.strip():
        updates["STATE"] = body.state.strip().upper()
    if body.address is not None:
        updates["ADDRESS"] = body.address.strip()
    if body.structure_type is not None:
        updates["STRUCTURE_TYPE"] = body.structure_type
    if body.height_ft is not None:
        updates["HEIGHT_FT"] = body.height_ft
    if body.stream is not None:
        updates["STREAM"] = body.stream
    if updates:
        updates["UPDATED_AT"] = now_iso()
        updates["UPDATED_BY"] = user["sub"]
        r.update("CORE.SITE", updates, {"SITE_ID": sid})
    return {"site": r.get("CORE.SITE", SITE_ID=sid)}


@router.get("/sharepoint/sites/{site_id}/files")
def site_files(site_id: str, user: dict = Depends(require("ADMIN"))):
    sid = validate_site_id(site_id)
    store = get_store()
    if not store.site_exists(sid):
        raise NotFound(f"Site {sid} has no folder in SharePoint")
    if repo().select("CORE.SITE", {"SITE_ID": sid}):
        check_site_scope(user, sid)
    files = store.list_files(sid)
    for f in files:
        f["doc_type"] = detect_doc_type(f["name"])
    return {"site_id": sid, "location": f"{store.location} / {sid}", "files": files}


from scopeiq.services.document_compare import inspect_file_against_site


@router.post("/sharepoint/sites/{site_id}/check-content")
async def check_content(site_id: str, file: UploadFile = File(...), doc_type: str | None = Form(default=None),
                        user: dict = Depends(require("ADMIN"))):
    """Pre-upload inspection for SharePoint: checks if file data is NEW, DUPLICATE, or UPDATED with additions."""
    sid = validate_site_id(site_id)
    store = get_store()
    if not store.site_exists(sid):
        raise NotFound(f"Site {sid} has no folder in SharePoint")
    data = await file.read()
    if not data:
        raise ValidationError("File is empty")
    inspection = inspect_file_against_site(sid, file.filename or "", data, doc_type=doc_type, repo=repo())
    return inspection.to_dict()


@router.post("/sharepoint/sites/{site_id}/upload")
async def upload(site_id: str, file: UploadFile = File(...), doc_type: str | None = Form(default=None),
                 replace_file: str | None = Form(default=None),
                 user: dict = Depends(require("ADMIN"))):
    """Upload one file into the selected site's folder. The site comes from the path, so a file can only go to that one site."""
    sid = validate_site_id(site_id)
    store = get_store()
    if not store.site_exists(sid):
        raise NotFound(f"Site {sid} has no folder in SharePoint")
    if repo().select("CORE.SITE", {"SITE_ID": sid}):
        check_site_scope(user, sid)
    if doc_type and doc_type not in TYPE_FOLDERS:
        raise ValidationError(f"Unknown document type {doc_type}", details={"allowed": list(TYPE_FOLDERS)})
    data = await file.read()
    saved = store.upload(sid, file.filename or "", data, doc_type or None, replace_file=replace_file)
    inspection = inspect_file_against_site(sid, file.filename or "", data, doc_type=doc_type, repo=repo(), exclude_filename=file.filename)
    AuditTrail.record(entity_type="SHAREPOINT_FILE", entity_id=f"{sid}/{saved['folder']}/{saved['name']}",
                      action="REPLACE_FILE" if (replace_file or saved.get("replaced")) else "UPLOAD",
                      after={"doc_type": saved["doc_type"], "size": saved["size"], "replaced": saved["replaced"],
                             "replace_file": replace_file}, site_id=sid, source="api")
    out = {"site_id": sid, **saved}
    if inspection.status == "UPDATED":
        out["is_updated"] = True
        out["updated_from"] = inspection.existing_file
        out["diff"] = inspection.to_dict()["diff"]
        out["message"] = f"Changes detected: Contains updates compared to '{inspection.existing_file}'."
    elif inspection.status == "DUPLICATE":
        out["is_duplicate"] = True
        out["already_exists"] = True
        out["duplicate_of"] = inspection.existing_file
        out["message"] = f"Already exists: Identical content matches '{inspection.existing_file}'."
    return out

