"""Site deletion and lifecycle management service for ScopeIQ.

Provides comprehensive cascade deletion for a site across:
  1. All database tables in CORE, WF, AUDIT, and RAW.
  2. All filesystem artifacts: SharePoint folders, output sites, evidence frames, uploads.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from scopeiq.common.audit import AuditTrail
from scopeiq.common.logging import get_logger
from scopeiq.config import get_settings
from scopeiq.db.repository import Repository
from scopeiq.integrations.sharepoint import get_store

log = get_logger("site_management")

# Tables in deletion order (child tables before parent tables)
CASCADE_CORE_TABLES = [
    "CORE.REDLINE_PROOF",
    "CORE.REDLINE",
    "CORE.RFI",
    "CORE.BOM_CHANGE",
    "CORE.BOM_LINE",
    "CORE.BOM_REVISION",
    "CORE.DISCREPANCY",
    "CORE.EHS_ALERT",
    "CORE.EQUIPMENT_DELTA",
    "CORE.DRIVER_LINE",
    "CORE.SITE_REQUIREMENT",
    "CORE.ESTIMATE",
    "CORE.EVIDENCE_FRAME",
    "CORE.FIELD_OBJECT",
    "CORE.REV0_LINE",
    "CORE.ANALYSIS_RESULT",
    "CORE.TRUNK_MEASURE",
    "CORE.SECTOR_INFO",
    "CORE.CONFIG_LINE",
    "CORE.EXTRACTED_COMPARISON_RECORD",
    "CORE.EXTRACTED_FIELD",
    "CORE.PIPELINE_RUN",
    "CORE.UPLOAD",
    "CORE.DOCUMENT",
    "CORE.MILESTONE",
    "CORE.SITE",
]

CASCADE_WF_TABLES = [
    "WF.COMMENT",
    "WF.NOTIFICATION",
    "WF.WORKFLOW_EVENT",
]

CASCADE_AUDIT_TABLES = [
    "AUDIT.AUDIT_LOG",
    "AUDIT.APP_LOG",
    "AUDIT.ERROR_LOG",
]


def delete_site_cascade(repo: Repository, site_id: str, delete_files: bool = True, deleted_by: str = "admin") -> dict[str, Any]:
    """Completely delete a site, its documents, run history, findings, and files.

    Args:
        repo: Repository instance (SnowflakeRepository or SqliteRepository)
        site_id: The 4-letter + 4-digit site ID (e.g., 'TXDA1024')
        delete_files: If True, remove SharePoint and output folders from disk.
        deleted_by: User ID performing the deletion.

    Returns:
        Dictionary detailing deleted row counts and file statuses.
    """
    sid = site_id.strip().upper()
    existing = repo.select("CORE.SITE", {"SITE_ID": sid})
    site_record = existing[0] if existing else None

    deleted_counts: dict[str, int] = {}

    # 1. Delete all CORE records (detail tables up to SITE)
    for tbl in CASCADE_CORE_TABLES:
        try:
            cnt = repo.delete_where(tbl, {"SITE_ID": sid})
            if cnt:
                deleted_counts[tbl] = cnt
        except Exception as exc:
            log.debug("Failed deleting from %s for %s: %s", tbl, sid, exc)

    # 2. Delete all WF records (workflow history, comments, notifications)
    for tbl in CASCADE_WF_TABLES:
        try:
            cnt = repo.delete_where(tbl, {"SITE_ID": sid})
            if cnt:
                deleted_counts[tbl] = cnt
        except Exception as exc:
            log.debug("Failed deleting from %s for %s: %s", tbl, sid, exc)

    # 3. Delete site-specific AUDIT logs
    for tbl in CASCADE_AUDIT_TABLES:
        try:
            cnt = repo.delete_where(tbl, {"SITE_ID": sid})
            if cnt:
                deleted_counts[tbl] = cnt
        except Exception as exc:
            log.debug("Failed deleting audit log %s for %s: %s", tbl, sid, exc)

    # 4. Delete RAW ST records if present
    for raw_tbl, key_col in [("RAW.ST_SITE", "NAME"), ("RAW.ST_PROJECT", "SITE__C")]:
        try:
            cnt = repo.delete_where(raw_tbl, {key_col: sid})
            if cnt:
                deleted_counts[raw_tbl] = cnt
        except Exception:
            pass

    # 5. Delete the site's files from the folders the app is configured to use (never a path built from where the code happens to sit)
    removed_paths: list[str] = []
    failed_paths: list[str] = []
    if delete_files:
        st = get_settings()
        output = Path(st.path("paths.output_dir"))
        folders = [output / "sites" / sid,                    # redlined drawings and proof pictures
                   output / "evidence" / sid,                 # video frames
                   Path(st.path("paths.upload_dir")) / sid,   # revised drawings issued by the app
                   Path(st.path("paths.sites_dir")) / sid,    # the site's input folder
                   Path(st.path("sharepoint.local_root")) / str(st.get("sharepoint.library_root", "Ericsson-Scoping/Sites")) / sid]   # local document library
        for folder in folders:
            if not folder.exists():
                continue
            shutil.rmtree(folder, ignore_errors=True)
            (failed_paths if folder.exists() else removed_paths).append(str(folder))     # say so when a file was locked and the folder is still there
        try:                                                  # a document library that is not a local folder (SharePoint) deletes its own copy
            get_store().delete_site_folder(sid)
        except Exception as exc:  # noqa: BLE001
            log.warning("library folder for %s was not deleted: %s", sid, exc)
        if failed_paths:
            log.warning("could not remove %s for site %s", failed_paths, sid)

    # 6. Audit Trail record
    try:
        AuditTrail.record(
            entity_type="SITE",
            entity_id=sid,
            action="CASCADE_DELETE",
            before=site_record,
            site_id=sid,
            source="site_management",
            comment=f"Deleted by {deleted_by} with full cascade: documents, run history, and files."
        )
    except Exception:
        pass

    return {
        "site_id": sid,
        "deleted_tables": deleted_counts,
        "removed_paths": removed_paths,
        "failed_paths": failed_paths,
        "total_records_deleted": sum(deleted_counts.values()),
    }
