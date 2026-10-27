"""Pipeline step 1 - Ingest: register every file of a site folder (or an upload) as a DOCUMENT row.

Site id, document type and revision are parsed from the folder and file name; the SHA-256 hash catches
duplicate uploads, and when several revisions of one document type exist only the latest is CURRENT
(the others become SUPERSEDED), so checks always compare the right revisions (guide 5.1).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from scopeiq.common.errors import ValidationError
from scopeiq.common.ids import file_sha256, stable_id
from scopeiq.common.logging import get_logger, log_call
from scopeiq.domain import Document

log = get_logger(__name__)

# (folder, filename pattern) -> document type
TYPE_RULES = [
    ("rfds", re.compile(r"RFDS", re.I), "RFDS"),
    ("cds", re.compile(r"_CD_|_PCD_", re.I), "CD"),
    ("ma_sa", re.compile(r"(?<![A-Za-z0-9])(?:MA|SA)(?![A-Za-z0-9])", re.I), "MA_SA"),
    ("bom", re.compile(r"BOM", re.I), "BOM_REV0"),
    ("drone", re.compile(r"capture_metadata\.json$", re.I), "DRONE_META"),
    ("drone", re.compile(r"vendor_measurements\.csv$", re.I), "DRONE_VENDOR"),
    ("drone", re.compile(r"\.la[sz]$", re.I), "DRONE_POINTCLOUD"),
    ("imagery", re.compile(r"\.(jpe?g|png|tif)$", re.I), "DRONE_IMAGE"),
    ("video", re.compile(r"\.(mp4|mov|avi)$", re.I), "DRONE_VIDEO"),
]
REV_PATTERNS = [re.compile(r"_(R\d+)\b", re.I), re.compile(r"_REV ?(\d+)", re.I), re.compile(r"_(REV\d+)", re.I)]
SITE_RE = re.compile(r"\b([A-Z]{4}\d{4})\b")


def classify(rel_path: str) -> str | None:
    parts = [p.lower() for p in Path(rel_path).parts]
    if "drone" in parts and "imagery" not in parts and "video" not in parts and not re.search(r"\.(json|csv|la[sz])$", rel_path, re.I):
        parts = parts + (["imagery"] if re.search(r"\.(jpe?g|png|tif)$", rel_path, re.I) else ["video"])
    name = Path(rel_path).name
    for folder, pat, typ in TYPE_RULES:
        if folder in parts and pat.search(name):
            return typ
    return None


def parse_revision(name: str) -> tuple[str, int]:
    """'TXDA1024_RFDS_R3.xlsx' -> ('R3', 3); 'TXDA1024_CD_REV1.pdf' -> ('REV 1', 1); 'TXDA1024_CD_REV0.pdf' -> ('REV 0', 0)."""
    stem = Path(name).stem
    m = re.search(r"(?:^|[-_\s])REV[ _-]?(\d+)(?:[-_\s]|$)", stem, re.I)
    if m:
        return f"REV {int(m.group(1))}", int(m.group(1))
    m = re.search(r"(?:^|[-_\s])R(\d+)(?:[-_\s]|$)", stem, re.I)
    if m:
        return f"R{int(m.group(1))}", int(m.group(1))
    m = re.search(r"(?:^|[-_\s])V(\d+)(?:[-_\s]|$)", stem, re.I)
    if m:
        return f"V{int(m.group(1))}", int(m.group(1))
    m = re.search(r"\bREV ?(\d+)\b", stem, re.I)
    if m:
        return f"REV {int(m.group(1))}", int(m.group(1))
    return "", 0


def file_format(path: Path) -> str:
    return path.suffix.lstrip(".").upper()


def make_document(site_id: str, path: Path, rel_path: str, *, source: str = "folder", doc_type: str | None = None) -> Document:
    typ = doc_type or classify(rel_path)
    if not typ:
        raise ValidationError(f"Cannot tell the document type of {rel_path}", details={"path": rel_path})
    sid = SITE_RE.search(path.name)
    if sid and sid.group(1) != site_id:
        raise ValidationError(f"File {path.name} belongs to {sid.group(1)}, not {site_id}",
                              details={"file": path.name, "site_id": site_id})
    rev, rank = parse_revision(path.name)
    digest = file_sha256(path)
    return Document(doc_id=stable_id("DOC", site_id, rel_path, digest), site_id=site_id, doc_type=typ, file_name=path.name,
                    rel_path=rel_path.replace("\\", "/"), file_format=file_format(path), revision=rev, revision_rank=rank,
                    file_hash=digest, size_bytes=path.stat().st_size,
                    doc_date=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date().isoformat(), source=source)


def resolve_current(docs: list[Document]) -> list[Document]:
    """Mark duplicates (same hash) and superseded revisions.
    The highest revision per doc_type across all formats is CURRENT; any strictly lower revision rank is SUPERSEDED.
    Ensures that if CD REV 0 and CD REV 1 exist, REV 1 is picked and REV 0 is superseded.
    """
    seen: dict[str, Document] = {}
    for d in sorted(docs, key=lambda d: d.rel_path):
        if d.file_hash in seen:
            d.status = "DUPLICATE"
            continue
        seen[d.file_hash] = d
        d.status = "CURRENT"
    groups: dict[str, list[Document]] = {}
    for d in docs:
        if d.status == "CURRENT" and d.doc_type in ("RFDS", "CD", "MA_SA", "BOM_REV0"):
            groups.setdefault(d.doc_type, []).append(d)
    for grp in groups.values():
        top = max(x.revision_rank for x in grp)
        for d in grp:
            if d.revision_rank < top:
                d.status = "SUPERSEDED"
    return docs


@log_call()
def register_site_folder(site_dir: Path, site_id: str | None = None, *, upload_dir: Path | None = None,
                         paths: dict | None = None) -> list[Document]:
    """Register the site folder plus any app uploads and SharePoint files for the site (same sub-folder layout). Uploaded revisions
    take part in revision resolution, so a corrected CD REV 2 uploaded by the A&E supersedes REV 1.
    `paths` (optional) is filled with doc_id -> absolute file path."""
    from scopeiq.config import get_settings
    st = get_settings()
    site_dir = Path(site_dir)
    site_id = site_id or site_dir.name
    docs = []
    roots = [(site_dir, "sites", "folder")]
    if upload_dir and Path(upload_dir).is_dir():
        roots.append((Path(upload_dir), "uploads", "upload"))
    try:
        sp_local = st.path("sharepoint.local_root")
        sp_lib = st.get("sharepoint.library_root", "Ericsson-Scoping/Sites")
        sp_site_dir = Path(sp_local) / sp_lib / site_id
        if sp_site_dir.is_dir():
            roots.append((sp_site_dir, "sharepoint", "sharepoint"))
    except Exception:
        pass
    files_by_subpath: dict[str, tuple[Path, str, str]] = {}
    for root, prefix, source in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.name.startswith("."):
                continue
            subpath = p.relative_to(root).as_posix()
            if subpath in files_by_subpath:
                prev_p, _, _ = files_by_subpath[subpath]
                if p.stat().st_mtime > prev_p.stat().st_mtime:
                    files_by_subpath[subpath] = (p, prefix, source)
            else:
                files_by_subpath[subpath] = (p, prefix, source)

    for subpath, (p, prefix, source) in sorted(files_by_subpath.items()):
        rel = f"{prefix}/{site_id}/{subpath}"
        try:
            d = make_document(site_id, p, rel, source=source)
        except ValidationError as exc:
            log.warning("skipped unrecognised file %s: %s", rel, exc.message, extra={"site_id": site_id})
            continue
        docs.append(d)
        if paths is not None:
            paths[d.doc_id] = p
    resolve_current(docs)
    log.info("registered %d documents for %s", len(docs), site_id, extra={"site_id": site_id,
             "by_type": {t: sum(1 for d in docs if d.doc_type == t) for t in sorted({d.doc_type for d in docs})}})
    return docs
