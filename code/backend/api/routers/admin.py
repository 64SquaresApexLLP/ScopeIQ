"""Reference data (browse, reload from CSV into REF.*), audit trail, application and error logs, runtime config."""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.deps import current_user, ref, reload_reference, repo, require
from scopeiq.common.audit import AuditTrail
from scopeiq.common.errors import NotFound
from scopeiq.common.logging import get_logger
from scopeiq.config import get_settings
from scopeiq.reference.loader import TABLES
from scopeiq.services.seed import load_reference_tables

router = APIRouter(tags=["admin"])
client_log_ = get_logger("client")


@router.get("/reference")
def reference_tables(user: dict = Depends(current_user)):
    r = ref()
    return [{"table": t, "rows": len(r.rows(t)), "version": r.versions.get(t)} for t in TABLES]


@router.get("/reference/{table}")
def reference_rows(table: str, user: dict = Depends(current_user)):
    if table not in TABLES:
        raise NotFound(f"Reference table {table} not found")
    return ref().rows(table)


@router.get("/reference-codes/reasons")
def reason_codes(user: dict = Depends(current_user)):
    return ref().rows("reason_codes")


@router.post("/reference/reload")
def reload(user: dict = Depends(require("ADMIN"))):
    counts = load_reference_tables(repo(), loaded_by=user["sub"])
    reload_reference()
    AuditTrail.record(entity_type="REFERENCE", entity_id="ALL", action="RELOAD", after=counts, source="api")
    return counts


@router.get("/audit")
def audit(site_id: str | None = None, entity_type: str | None = None, entity_id: str | None = None, limit: int = 200,
          user: dict = Depends(require("ADMIN", "REVIEWER", "ERICSSON"))):
    where = {k: v for k, v in {"SITE_ID": site_id, "ENTITY_TYPE": entity_type, "ENTITY_ID": entity_id}.items() if v}
    return repo().select("AUDIT.AUDIT_LOG", where or None, order_by="EVENT_TS DESC", limit=limit)


@router.get("/logs/app")
def app_logs(level: str | None = None, limit: int = 200, user: dict = Depends(require("ADMIN"))):
    return repo().select("AUDIT.APP_LOG", {"LEVEL": level} if level else None, order_by="LOG_TS DESC", limit=limit)


@router.get("/logs/errors")
def error_logs(limit: int = 200, user: dict = Depends(require("ADMIN"))):
    return repo().select("AUDIT.ERROR_LOG", None, order_by="ERROR_TS DESC", limit=limit)


@router.get("/config")
def runtime_config(user: dict = Depends(require("ADMIN"))):
    st = get_settings()
    return {"env": st.env, "logging": st.section("logging"), "database_backend": st.get("database.backend"),
            "engine": st.section("engine"), "reference_source": st.get("reference.source", "csv")}


class ClientLogIn(BaseModel):
    level: str = Field(default="error", pattern="^(debug|info|warn|error)$")
    message: str = Field(max_length=4000)
    context: dict | None = None


@router.post("/logs/client")
def client_log(body: ClientLogIn, user: dict = Depends(current_user)):
    """The mobile app forwards its warnings and errors here (level threshold set by the app's environment)."""
    lvl = {"debug": logging.DEBUG, "info": logging.INFO, "warn": logging.WARNING, "error": logging.ERROR}[body.level]
    client_log_.log(lvl, "client: %s", body.message, extra={"client_context": body.context or {}})
    return {"logged": True}
