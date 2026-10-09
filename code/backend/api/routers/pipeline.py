"""Pipeline: start a run (in the background, or wait for it), follow its steps, and read what each step produced.

POST /pipeline/sites/{id}/start    starts a run and returns its run_id at once; poll GET /pipeline/runs/{run_id}
POST /pipeline/sites/{id}/run      runs to completion before answering (scripts, tests)
GET  /pipeline/runs/{run_id}       the run with its steps: status, timing, counts, one-line message per step
GET  /pipeline/runs/{run_id}/steps/{key}   the rows the step produced (documents, findings, BOM, redlines ...)
In Snowflake the same service runs as a Snowpark procedure from a task."""
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from api.deps import check_site_scope, current_user, pipeline, repo, require, site_scope
from api.schemas import RunIn
from scopeiq.common.errors import NotFound
from scopeiq.config import get_settings
from scopeiq.services.pipeline import APPLY_PREFIX, STEP_DEFS

router = APIRouter(prefix="/pipeline", tags=["pipeline"])
STEP_KEYS = [k for k, _ in STEP_DEFS]


@router.post("/sites/{site_id}/start")
def start_site(site_id: str, user: dict = Depends(require("SCOPER", "REVIEWER"))):
    return pipeline().start_site(site_id, triggered_by=user["sub"])


@router.post("/sites/{site_id}/run")
def run_site(site_id: str, user: dict = Depends(require("SCOPER", "REVIEWER"))):
    return pipeline().run_site(site_id, triggered_by=user["sub"])


@router.post("/run")
def run_many(body: RunIn, user: dict = Depends(require("SCOPER", "REVIEWER"))):
    svc = pipeline()
    if not body.site_ids:
        return svc.run_all(triggered_by=user["sub"])
    out = []
    for sid in body.site_ids:
        try:
            out.append(svc.run_site(sid, triggered_by=user["sub"]))
        except Exception as exc:  # noqa: BLE001 - report per site, keep going
            out.append({"site_id": sid, "status": "FAILED", "error": getattr(exc, "to_dict", lambda: {"message": str(exc)})()})
    return out


@router.get("/runs")
def runs(site_id: str | None = None, limit: int = 50, user: dict = Depends(current_user)):
    rows = repo().select("CORE.PIPELINE_RUN", {"SITE_ID": site_id} if site_id else None, order_by="STARTED_AT DESC", limit=limit)
    scope = site_scope(user)
    if scope:
        ok = {s["SITE_ID"] for s in repo().select("CORE.SITE", scope)}
        rows = [r for r in rows if r["SITE_ID"] in ok]
    return rows


def _run(run_id: str, user: dict) -> dict:
    rows = repo().select("CORE.PIPELINE_RUN", {"RUN_ID": run_id}, limit=1)
    if not rows:
        raise NotFound(f"Run {run_id} not found")
    check_site_scope(user, rows[0]["SITE_ID"])
    return rows[0]


@router.get("/sites/{site_id}/latest")
def latest_run(site_id: str, user: dict = Depends(current_user)):
    """The newest pipeline run of a site (running or finished), or null when it has never run."""
    check_site_scope(user, site_id)
    rows = repo().select("CORE.PIPELINE_RUN", {"SITE_ID": site_id}, order_by="STARTED_AT DESC", limit=30)
    return next((r for r in rows if r["RUN_ID"].startswith("RUN-")), None)


# ---- implement changes: approved redlines -> next CD revision
@router.post("/sites/{site_id}/apply")
def apply_changes(site_id: str, user: dict = Depends(require("REVIEWER", "AE_ENGINEER", "SCOPER"))):
    """Build the next CD revision from the approved redlines (background job; poll GET /pipeline/runs/{run_id})."""
    check_site_scope(user, site_id)
    return pipeline().start_apply(site_id, triggered_by=user["sub"])


@router.get("/sites/{site_id}/revision")
def latest_revision(site_id: str, user: dict = Depends(current_user)):
    """The newest implemented revision (files and the per-redline applied / not applied log), the running job, or null."""
    check_site_scope(user, site_id)
    rows = repo().select("CORE.PIPELINE_RUN", {"SITE_ID": site_id}, order_by="STARTED_AT DESC", limit=30)
    jobs = [r for r in rows if r["RUN_ID"].startswith(APPLY_PREFIX)]
    done = pipeline().latest_revision(site_id)
    return {"job": jobs[0] if jobs else None, "revision": done}


@router.get("/runs/{run_id}/file/{kind}")
def run_file(run_id: str, kind: str, user: dict = Depends(current_user)):
    """Authenticated download of a file a run wrote (revised drawing, change log)."""
    run = _run(run_id, user)
    rel = ((run.get("SUMMARY") or {}).get("files") or {}).get(kind)
    base = Path(get_settings().path("paths.output_dir")).resolve()
    path = (base / rel).resolve() if rel else None
    if not path or base not in path.parents or not path.is_file():
        raise NotFound(f"File {kind} is not available for run {run_id}")
    return FileResponse(path, filename=path.name)


@router.get("/runs/{run_id}")
def get_run(run_id: str, user: dict = Depends(current_user)):
    return _run(run_id, user)


@router.get("/runs/{run_id}/steps/{key}")
def step_detail(run_id: str, key: str, user: dict = Depends(current_user)):
    """What a step produced, read from the tables the run wrote (so it matches the rest of the app)."""
    key = key.upper()
    if key not in STEP_KEYS:
        raise NotFound(f"Unknown step {key}", details={"steps": STEP_KEYS})
    run = _run(run_id, user)
    r, sid = repo(), run["SITE_ID"]
    by_run = {"SITE_ID": sid, "RUN_ID": run_id}
    if key == "INGEST":
        return {"documents": r.select("CORE.DOCUMENT", {"SITE_ID": sid}, order_by="DOC_TYPE, REVISION_RANK")}
    if key == "EXTRACT":
        fields = r.select("CORE.EXTRACTED_FIELD", by_run)
        fields.sort(key=lambda f: (not f.get("NEEDS_REVIEW"), f.get("CONFIDENCE") or 0))
        return {"total": len(fields), "needs_review": sum(1 for f in fields if f.get("NEEDS_REVIEW")), "fields": fields[:150],
                "config_lines": r.select("CORE.CONFIG_LINE", by_run, order_by="SOURCE, SECTOR, POSITION")[:300]}
    if key == "RECONCILE":
        return {"discrepancies": r.select("CORE.DISCREPANCY", by_run, order_by="SEVERITY, RULE_ID")}
    if key == "DELTA":
        return {"delta": r.select("CORE.EQUIPMENT_DELTA", by_run, order_by="SEQ")}
    if key == "GENERATE":
        revs = r.select("CORE.BOM_REVISION", {"SITE_ID": sid, "RUN_ID": run_id})
        rev = max(revs, key=lambda x: x["REV_NO"]) if revs else None
        return {"revision": rev, "changes": r.select("CORE.BOM_CHANGE", {"TO_REV_ID": rev["BOM_REV_ID"]}) if rev else [],
                "lines": len(r.select("CORE.BOM_LINE", {"BOM_REV_ID": rev["BOM_REV_ID"]})) if rev else 0}
    if key == "ESTIMATE":
        est = r.select("CORE.ESTIMATE", by_run)
        return {"estimate": est[0] if est else None, "drivers": r.select("CORE.DRIVER_LINE", by_run),
                "requirements": (r.select("CORE.SITE_REQUIREMENT", by_run) or [None])[0]}
    if key == "REDLINES":
        return {"redlines": r.select("CORE.REDLINE", {"SITE_ID": sid}, order_by="SHEET"), "rfis": r.select("CORE.RFI", {"SITE_ID": sid})}
    return {"files": (run.get("SUMMARY") or {}).get("files", {})}


@router.get("/sites")
def available_sites(user: dict = Depends(current_user)):
    return pipeline().site_ids()
