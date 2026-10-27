"""Documents: the registry per site, optional artifact upload (CD / RFDS / MA-SA / BOM / drone files) and download.
An upload is stored under output/uploads/<site>/<folder>/ and recorded in CORE.UPLOAD; the next pipeline run
registers it and, if it is a newer revision, it supersedes the folder copy.
"""
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from api.deps import current_user, repo, require
from scopeiq.common.audit import AuditTrail
from scopeiq.common.errors import Conflict, NotFound, ValidationError
from scopeiq.config import get_settings
from scopeiq.db.repository import now_iso
from scopeiq.extract.registry import classify
from scopeiq.services.document_compare import inspect_file_against_site

router = APIRouter(tags=["documents"])

# document type chosen in the app -> sub-folder (same layout as the site folders)
UPLOAD_FOLDERS = {"RFDS": "rfds", "CD": "cds", "MA_SA": "ma_sa", "BOM_REV0": "bom", "DRONE_META": "drone", "DRONE_VENDOR": "drone",
                  "DRONE_POINTCLOUD": "drone", "DRONE_IMAGE": "drone/imagery", "DRONE_VIDEO": "drone/video"}
MAX_BYTES = 400 * 1024 * 1024


@router.get("/sites/{site_id}/documents")
def list_documents(site_id: str, user: dict = Depends(current_user)):
    docs = repo().select("CORE.DOCUMENT", {"SITE_ID": site_id}, order_by="DOC_TYPE, REVISION_RANK")
    uploads = repo().select("CORE.UPLOAD", {"SITE_ID": site_id}, order_by="UPLOADED_AT")
    return {"documents": docs, "uploads": uploads, "upload_types": list(UPLOAD_FOLDERS)}


@router.get("/sites/{site_id}/documents/check-hash")
def check_hash(site_id: str, hash: str, user: dict = Depends(current_user)):
    """Pre-upload check: detects if a document with the exact same SHA-256 hash exists on the site."""
    repo().get("CORE.SITE", SITE_ID=site_id)
    h = hash.strip().lower()
    dup_docs = repo().select("CORE.DOCUMENT", {"SITE_ID": site_id, "FILE_HASH": h})
    dup_uploads = repo().select("CORE.UPLOAD", {"SITE_ID": site_id, "FILE_HASH": h})
    dup_name = dup_docs[0]["FILE_NAME"] if dup_docs else dup_uploads[0]["FILE_NAME"] if dup_uploads else None
    dup_type = dup_docs[0].get("DOC_TYPE") if dup_docs else dup_uploads[0].get("DOC_TYPE") if dup_uploads else None
    source = "DOCUMENT" if dup_docs else "UPLOAD" if dup_uploads else None
    return {
        "exists": bool(dup_name),
        "already_exists": bool(dup_name),
        "duplicate_of": dup_name,
        "doc_type": dup_type,
        "source": source,
        "hash": h,
        "message": f"Already exists! Identical file content already exists as '{dup_name}'." if dup_name else None,
        "warning": f"Already exists: Duplicate document detected with identical content as '{dup_name}' (SHA-256 match)." if dup_name else None
    }


@router.post("/sites/{site_id}/documents/check-content")
async def check_content(site_id: str, file: UploadFile = File(...), doc_type: str | None = Form(default=None),
                        user: dict = Depends(current_user)):
    """Pre-upload content inspection: checks whether the file has new data, duplicate data, or updated data with new additions."""
    repo().get("CORE.SITE", SITE_ID=site_id)
    name = Path(file.filename or "").name
    data = await file.read()
    if not data or len(data) > MAX_BYTES:
        raise ValidationError("File is empty or larger than 400 MB")
    
    inspection = inspect_file_against_site(site_id, name, data, doc_type=doc_type, repo=repo())
    return inspection.to_dict()


@router.post("/sites/{site_id}/documents/upload")
async def upload(site_id: str, doc_type: str = Form(...), file: UploadFile = File(...),
                 confirm_duplicate: bool = Form(default=False),
                 confirm_update: bool = Form(default=False),
                 replace_file: str | None = Form(default=None),
                 action: str | None = Form(default=None),
                 user: dict = Depends(require("SCOPER", "AE_ENGINEER", "DRONE_VENDOR", "CX_SP", "ERICSSON"))):
    repo().get("CORE.SITE", SITE_ID=site_id)
    if doc_type not in UPLOAD_FOLDERS:
        raise ValidationError(f"Unknown document type {doc_type}", details={"allowed": list(UPLOAD_FOLDERS)})
    name = Path(file.filename or "").name
    if not name:
        raise ValidationError("File name missing")
    folder = UPLOAD_FOLDERS[doc_type]
    if classify(f"{folder}/{name}") != doc_type:
        raise ValidationError(f"'{name}' does not look like a {doc_type} file - use the site naming convention "
                              f"(e.g. {site_id}_CD_REV2.pdf, {site_id}_RFDS_R4.xlsx)", details={"folder": folder})
    data = await file.read()
    if not data or len(data) > MAX_BYTES:
        raise ValidationError("File is empty or larger than 400 MB")
    
    digest = hashlib.sha256(data).hexdigest()
    is_replace = bool(replace_file or (action and action.upper() == "REPLACE"))

    # Content inspection against site documents
    inspection = inspect_file_against_site(site_id, name, data, doc_type=doc_type, repo=repo())

    # Fallback to fast hash query in DB if inspection returned NEW but exact hash exists in DB
    if inspection.status == "NEW":
        dup_docs = repo().select("CORE.DOCUMENT", {"SITE_ID": site_id, "FILE_HASH": digest})
        dup_uploads = repo().select("CORE.UPLOAD", {"SITE_ID": site_id, "FILE_HASH": digest})
        d_name = dup_docs[0]["FILE_NAME"] if dup_docs else dup_uploads[0]["FILE_NAME"] if dup_uploads else None
        if d_name:
            inspection.status = "DUPLICATE"
            inspection.existing_file = d_name
            inspection.message = f"Already exists! A file with identical content already exists as '{d_name}'."
            inspection.warning = f"Already exists: Identical document content already exists on this site as '{d_name}' (SHA-256: {digest[:12]}...)."

    # 1. Duplicate data check (Same data -> Already exists, no replace option)
    if inspection.status == "DUPLICATE" and not confirm_duplicate and not is_replace:
        target_name = inspection.existing_file or name
        warning_msg = f"Already exists: Identical document content already exists on this site as '{target_name}' (SHA-256: {digest[:12]}...)."
        raise Conflict(
            f"Already exists! This file has identical content (SHA-256: {digest[:12]}...) to existing document '{target_name}'.",
            details={
                "status": "DUPLICATE",
                "is_duplicate": True,
                "already_exists": True,
                "can_replace": False,
                "duplicate_of": target_name,
                "file_hash": digest,
                "file_name": name,
                "doc_type": doc_type,
                "warning": warning_msg,
                "message": f"Already exists! The content inside this file is identical to '{target_name}'. Upload is not required.",
            }
        )

    # 2. Updated data check (file uploaded with changes -> Show replace file option)
    if inspection.status == "UPDATED" and not confirm_update and not is_replace:
        target_name = inspection.existing_file or name
        raise Conflict(
            f"Changes detected! This file contains changes compared to '{target_name}'. "
            f"Do you want to replace '{target_name}' with this file?",
            details={
                "status": "UPDATED",
                "is_updated": True,
                "already_exists": False,
                "can_replace": True,
                "updated_from": target_name,
                "file_hash": digest,
                "file_name": name,
                "doc_type": doc_type,
                "warning": f"Changes detected! File contains modifications/updates compared to '{target_name}'.",
                "message": f"Replace existing file '{target_name}' with this updated file?",
                "diff": inspection.to_dict()["diff"],
            }
        )

    # Destination file on disk
    dest = Path(get_settings().path("paths.upload_dir")) / site_id / folder / name
    dest.parent.mkdir(parents=True, exist_ok=True)

    target_replace_file = replace_file or (inspection.existing_file if is_replace else None)

    # Handle replacement of existing file
    if is_replace and target_replace_file:
        # If target has a different filename in the same upload folder, clean it up
        old_upload_path = Path(get_settings().path("paths.upload_dir")) / site_id / folder / target_replace_file
        if old_upload_path.is_file() and old_upload_path.resolve() != dest.resolve():
            try:
                old_upload_path.unlink()
            except Exception:
                pass

        # Update previous upload records in DB to SUPERSEDED
        try:
            for u in repo().select("CORE.UPLOAD", {"SITE_ID": site_id, "FILE_NAME": target_replace_file}):
                repo().update("CORE.UPLOAD", {"UPLOAD_ID": u["UPLOAD_ID"]}, {"STATUS": "SUPERSEDED"})
        except Exception:
            pass

        # Also mark document in CORE.DOCUMENT as SUPERSEDED if present
        try:
            for d in repo().select("CORE.DOCUMENT", {"SITE_ID": site_id, "FILE_NAME": target_replace_file}):
                repo().update("CORE.DOCUMENT", {"DOC_ID": d["DOC_ID"]}, {"STATUS": "SUPERSEDED"})
        except Exception:
            pass

    dest.write_bytes(data)

    is_dup = inspection.status == "DUPLICATE" and not is_replace
    is_upd = inspection.status == "UPDATED" and not is_replace

    if is_replace:
        msg = f"Replaced {target_replace_file} ({'updated data' if inspection.status == 'UPDATED' else 'duplicate replacement'})"
        upload_status = "RECEIVED"
    elif is_dup:
        msg = f"Duplicate of {inspection.existing_file} (identical data)"
        upload_status = "DUPLICATE"
    elif is_upd:
        msg = f"Updated data based on {inspection.existing_file} ({inspection.summary})"
        upload_status = "RECEIVED"
    else:
        msg = "Run the pipeline to register and reconcile"
        upload_status = "RECEIVED"

    row = {
        "UPLOAD_ID": uuid.uuid4().hex,
        "SITE_ID": site_id,
        "DOC_TYPE": doc_type,
        "FILE_NAME": name,
        "STAGE_PATH": f"uploads/{site_id}/{folder}/{name}",
        "SIZE_BYTES": len(data),
        "FILE_HASH": digest,
        "UPLOADED_BY": user["sub"],
        "UPLOADED_AT": now_iso(),
        "STATUS": upload_status,
        "DOC_ID": None,
        "MESSAGE": msg,
    }
    repo().insert("CORE.UPLOAD", [row])

    AuditTrail.record(
        entity_type="UPLOAD",
        entity_id=row["UPLOAD_ID"],
        action="REPLACE_FILE" if is_replace else "UPLOAD",
        after={k: row[k] for k in ("DOC_TYPE", "FILE_NAME", "SIZE_BYTES")},
        site_id=site_id,
        source="api",
    )

    out = dict(row)
    out["is_duplicate"] = is_dup
    out["duplicate_of"] = inspection.existing_file if is_dup else None
    out["is_updated"] = is_upd
    out["updated_from"] = inspection.existing_file if is_upd else None
    out["replaced"] = is_replace
    out["replaced_file"] = target_replace_file if is_replace else None
    out["diff"] = inspection.to_dict()["diff"] if inspection.status == "UPDATED" else None
    out["warning"] = f"Warning: Document has identical content to '{inspection.existing_file}'" if is_dup else None
    return out


@router.get("/documents/{doc_id}/download")
def download(doc_id: str, user: dict = Depends(current_user)):
    d = repo().get("CORE.DOCUMENT", DOC_ID=doc_id)
    st = get_settings()
    prefix, _, rest = (d["REL_PATH"] or "").partition("/")
    if prefix == "sites":
        base = st.path("paths.sites_dir")
    elif prefix == "sharepoint":
        base = st.path("sharepoint.local_root") / st.get("sharepoint.library_root", "Ericsson-Scoping/Sites")
    else:
        base = st.path("paths.upload_dir")
    path = base / rest
    if not path.is_file():
        raise NotFound(f"File for {doc_id} is not available on this server")
    return FileResponse(path, filename=path.name)
