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

    # 5. Delete physical files from disk
    removed_paths: list[str] = []
    if delete_files:
        try:
            st = get_settings()
            backend_code_dir = Path(__file__).resolve().parents[2]
            workspace_dirs = [
                backend_code_dir,
                Path("/Users/adarshsharma/Documents/Projects/ScopeIQ2/ScopeIQ/code"),
            ]

            for base in workspace_dirs:
                if not base.exists():
                    continue

                # Output sites folder
                p_site = base / "output" / "sites" / sid
                if p_site.is_dir():
                    shutil.rmtree(p_site, ignore_errors=True)
                    removed_paths.append(str(p_site))

                # Output evidence folder
                p_ev = base / "output" / "evidence" / sid
                if p_ev.is_dir():
                    shutil.rmtree(p_ev, ignore_errors=True)
                    removed_paths.append(str(p_ev))

                # Output uploads folder
                p_up = base / "output" / "uploads" / sid
                if p_up.is_dir():
                    shutil.rmtree(p_up, ignore_errors=True)
                    removed_paths.append(str(p_up))

                # SharePoint local store folder
                p_sp = base / "output" / "sharepoint" / "Ericsson-Scoping" / "Sites" / sid
                if p_sp.is_dir():
                    shutil.rmtree(p_sp, ignore_errors=True)
                    removed_paths.append(str(p_sp))

            # Data/Input-Data/Sites/{site_id} — seed/input documents for the pipeline
            # We walk up from the backend code dir to the repo root (3 levels up from code/backend)
            try:
                backend_code_dir = Path(__file__).resolve().parents[2]
                repo_root = backend_code_dir.parent.parent  # code/backend → code → repo root
                p_input = repo_root / "Data" / "Input-Data" / "Sites" / sid
                if p_input.is_dir():
                    shutil.rmtree(p_input, ignore_errors=True)
                    removed_paths.append(str(p_input))
                    log.info("Deleted input-data folder: %s", p_input)
            except Exception as exc:
                log.debug("Could not delete Data/Input-Data/Sites/%s: %s", sid, exc)

            # Store deletion via store interface
            try:
                store = get_store()
                if hasattr(store, "delete_site_folder"):
                    store.delete_site_folder(sid)
            except Exception as e:
                log.debug("Store delete_site_folder notice: %s", e)

        except Exception as exc:
            log.warn("Error cleaning file paths for %s: %s", sid, exc)

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
        "total_records_deleted": sum(deleted_counts.values()),
    }
