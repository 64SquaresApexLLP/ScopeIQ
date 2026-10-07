"""Documents: the registry per site, optional artifact upload (CD / RFDS / MA-SA / BOM / drone files) and download.
An upload is stored under output/uploads/<site>/<folder>/ and recorded in CORE.UPLOAD; the next pipeline run
registers it and, if it is a newer revision, it supersedes the folder copy."""
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from api.deps import current_user, repo, require
from scopeiq.common.audit import AuditTrail
from scopeiq.common.errors import NotFound, ValidationError
from scopeiq.config import get_settings
from scopeiq.db.repository import now_iso
from scopeiq.extract.registry import classify

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


@router.post("/sites/{site_id}/documents/upload")
async def upload(site_id: str, doc_type: str = Form(...), file: UploadFile = File(...),
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
    dest = Path(get_settings().path("paths.upload_dir")) / site_id / folder / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    dup = [u for u in repo().select("CORE.UPLOAD", {"SITE_ID": site_id, "FILE_HASH": digest})]
    dest.write_bytes(data)
    row = {"UPLOAD_ID": uuid.uuid4().hex, "SITE_ID": site_id, "DOC_TYPE": doc_type, "FILE_NAME": name,
           "STAGE_PATH": f"uploads/{site_id}/{folder}/{name}", "SIZE_BYTES": len(data), "FILE_HASH": digest, "UPLOADED_BY": user["sub"],
           "UPLOADED_AT": now_iso(), "STATUS": "DUPLICATE" if dup else "RECEIVED", "DOC_ID": None,
           "MESSAGE": "Same content uploaded before" if dup else "Run the pipeline to register and reconcile"}
    repo().insert("CORE.UPLOAD", [row])
    AuditTrail.record(entity_type="UPLOAD", entity_id=row["UPLOAD_ID"], action="UPLOAD", after={k: row[k] for k in ("DOC_TYPE", "FILE_NAME", "SIZE_BYTES")},
                      site_id=site_id, source="api")
    return row


@router.get("/documents/{doc_id}/download")
def download(doc_id: str, user: dict = Depends(current_user)):
    d = repo().get("CORE.DOCUMENT", DOC_ID=doc_id)
    st = get_settings()
    prefix, _, rest = (d["REL_PATH"] or "").partition("/")
    base = st.path("paths.sites_dir") if prefix == "sites" else st.path("paths.upload_dir")
    path = base / rest
    if not path.is_file():
        raise NotFound(f"File for {doc_id} is not available on this server")
    return FileResponse(path, filename=path.name)
