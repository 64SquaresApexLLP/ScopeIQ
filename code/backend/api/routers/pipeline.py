"""Pipeline: run one site or all sites, list runs. Runs are synchronous in the POC (seconds per site;
OCR'd PDFs take longer); in Snowflake the same service runs as a Snowpark procedure from a task."""
from fastapi import APIRouter, Depends

from api.deps import current_user, pipeline, repo, require
from api.schemas import RunIn

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


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
    return repo().select("CORE.PIPELINE_RUN", {"SITE_ID": site_id} if site_id else None, order_by="STARTED_AT DESC", limit=limit)


@router.get("/sites")
def available_sites(user: dict = Depends(current_user)):
    return pipeline().site_ids()
