"""Snowpark stored-procedure entry point (see snowflake/07_procedures.sql).

Inside Snowflake the procedure: 1) points the configuration at a scratch folder, 2) downloads the site's files
from the SITE_DOCS stage (same layout as ScopeIQ-POC/Data) plus app uploads, 3) runs the same PipelineService the
API and CLI use, writing through the Snowpark session into the CORE/WF/AUDIT tables, and 4) uploads the generated
files (BOM workbook, redlined CD, packages, evidence frames) to the SCOPEIQ_OUTPUT stage.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

WORK = Path("/tmp/scopeiq")


def _download(session, stage: str, prefix: str, dest: Path) -> int:
    """Copy every staged file under `prefix` to dest/<path below prefix>, keeping the folder layout."""
    rows = session.sql(f"SELECT RELATIVE_PATH FROM DIRECTORY({stage}) WHERE STARTSWITH(RELATIVE_PATH, ?)", params=[prefix]).collect()
    for r in rows:
        rel = r["RELATIVE_PATH"]
        out = dest / rel[len(prefix):].lstrip("/")
        out.parent.mkdir(parents=True, exist_ok=True)
        with session.file.get_stream(f"{stage}/{rel}") as src, open(out, "wb") as f:
            f.write(src.read())
    return len(rows)


def _upload(session, local: Path, stage: str) -> int:
    n = 0
    for d, _, files in os.walk(local):
        if not files:
            continue
        rel = Path(d).relative_to(local).as_posix()
        target = f"{stage}/{rel}/" if rel != "." else f"{stage}/"
        for fn in files:
            session.file.put(str(Path(d) / fn), target, auto_compress=False, overwrite=True)
            n += 1
    return n


def _settings(session, db: str) -> dict:
    """APP.SETTINGS is written by 07_procedures.sql from the environment variables file (config/env_<env>.sql)."""
    try:
        return {r["KEY"]: r["VALUE"] for r in session.sql(f"SELECT KEY, VALUE FROM {db}.APP.SETTINGS").collect()}
    except Exception:  # noqa: BLE001
        return {}


def run(session, site_ids: str = "", triggered_by: str = "snowflake-task") -> str:
    db = session.get_current_database().strip('"')
    cfg = _settings(session, db)
    env = cfg.get("SCOPEIQ_ENV", "dev")
    docs_stage, out_stage = f"@{db}.RAW.SITE_DOCS", f"@{db}.RAW.SCOPEIQ_OUTPUT"
    data, out = WORK / "Data", WORK / "output"
    os.environ.update({
        "SCOPEIQ_ENV": env,
        "SCOPEIQ__LOGGING__LEVEL": cfg.get("APP_LOG_LEVEL", "INFO"),
        "SCOPEIQ__PATHS__DATA_ROOT": str(data), "SCOPEIQ__PATHS__SITES_DIR": str(data / "Input-Data" / "Sites"),
        "SCOPEIQ__PATHS__SITETRACKER_DIR": str(data / "Input-Data" / "SiteTracker"), "SCOPEIQ__PATHS__OUTPUT_DIR": str(out),
        "SCOPEIQ__PATHS__UPLOAD_DIR": str(out / "uploads"), "SCOPEIQ__PATHS__LOG_DIR": str(out / "logs"),
        "SCOPEIQ__LOGGING__FILE": "false",            # Snowflake captures stdout/stderr in the event table
        "SCOPEIQ__REFERENCE__SOURCE": "database",     # REF.* tables are the reference library in Snowflake
        "SCOPEIQ__ENGINE__OCR_ENABLED": "false",      # no Tesseract in a warehouse; see EXECUTION_GUIDE (SPCS job)
    })
    from scopeiq.common.context import bind
    from scopeiq.common.logging import configure_logging
    from scopeiq.config import reset_settings_cache
    from scopeiq.db.repository import SnowparkRepository, set_repository
    from scopeiq.reference.loader import load_reference
    from scopeiq.services.pipeline import PipelineService

    reset_settings_cache()
    configure_logging(force=True)
    repo = SnowparkRepository(session, db)
    set_repository(repo)
    _download(session, docs_stage, "Input-Data/SiteTracker/", data / "Input-Data" / "SiteTracker")
    wanted = [s.strip() for s in site_ids.split(",") if s.strip()]
    if not wanted:
        wanted = [r["SITE_ID"] for r in session.sql(
            f"SELECT DISTINCT SITE_ID FROM {db}.RAW.FILE_REGISTRY WHERE AREA = 'SITE' AND SITE_ID IS NOT NULL").collect()]
    for sid in wanted:
        _download(session, docs_stage, f"Input-Data/Sites/{sid}/", data / "Input-Data" / "Sites" / sid)
        _download(session, docs_stage, f"uploads/{sid}/", out / "uploads" / sid)
    svc = PipelineService(repo, load_reference(repository=repo))
    results = []
    with bind(user_id=triggered_by, role="SYSTEM", component="snowpark"):
        for sid in wanted:
            try:
                r = svc.run_site(sid, triggered_by=triggered_by)
                results.append({"site_id": sid, "status": r["status"], "run_id": r["run_id"]})
            except Exception as exc:  # noqa: BLE001 - one bad site must not stop the batch
                results.append({"site_id": sid, "status": "FAILED", "error": str(exc)[:500]})
    files = _upload(session, out / "sites", f"{out_stage}/sites") + _upload(session, out / "evidence", f"{out_stage}/evidence")
    return json.dumps({"sites": results, "files_uploaded": files})
