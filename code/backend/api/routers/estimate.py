"""Delta, service drivers, site requirements, estimate and EH&S alerts for a site's latest run."""
from fastapi import APIRouter, Depends

from api.deps import current_user, repo, require, workflow
from api.schemas import TransitionIn

router = APIRouter(tags=["estimate"])


def _latest(site_id: str) -> str | None:
    return repo().get("CORE.SITE", SITE_ID=site_id).get("LAST_RUN_ID")


@router.get("/sites/{site_id}/delta")
def delta(site_id: str, user: dict = Depends(current_user)):
    return sorted(repo().select("CORE.EQUIPMENT_DELTA", {"SITE_ID": site_id, "RUN_ID": _latest(site_id)}), key=lambda x: x["SEQ"])


@router.get("/sites/{site_id}/estimate")
def site_estimate(site_id: str, user: dict = Depends(current_user)):
    r, run = repo(), _latest(site_id)
    where = {"SITE_ID": site_id, "RUN_ID": run}
    drivers = r.select("CORE.DRIVER_LINE", where, order_by="DRIVER_CODE, SECTOR")
    return {"estimate": next(iter(r.select("CORE.ESTIMATE", where)), None), "drivers": drivers,
            "requirements": next(iter(r.select("CORE.SITE_REQUIREMENT", where)), None),
            "services_total": round(sum(d["AMOUNT"] or 0 for d in drivers), 2)}


@router.get("/ehs-alerts")
def ehs_alerts(site_id: str | None = None, status: str | None = None, user: dict = Depends(current_user)):
    where = {k: v for k, v in {"SITE_ID": site_id, "STATUS": status}.items() if v}
    rows = repo().select("CORE.EHS_ALERT", where or None, order_by="SITE_ID")
    for x in rows:
        x["ACTIONS"] = [a["action"] for a in workflow().actions("EHS_ALERT", x["STATUS"], user["role"])]
    return rows


@router.post("/ehs-alerts/{alert_id}/transition")
def ehs_transition(alert_id: str, body: TransitionIn, user: dict = Depends(current_user)):
    return workflow().transition("EHS_ALERT", alert_id, body.action, reason_code=body.reason_code, comment=body.comment)
