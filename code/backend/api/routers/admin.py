"""Reference data (browse, reload from CSV into REF.*), audit trail, application and error logs, runtime config."""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.deps import current_user, ref, reload_reference, repo, require
from api.schemas import LoginCreateIn, LoginUpdateIn
from scopeiq.common.audit import AuditTrail
from scopeiq.common.errors import Conflict, NotFound, ValidationError
from scopeiq.common.logging import get_logger
from scopeiq.common.passwords import hash_password
from scopeiq.config import get_settings
from scopeiq.db.repository import now_iso
from scopeiq.services.admin_account import ADMIN_ROLE
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


# ------------------------------------------------------------------ sign-in credentials (CORE.USER_LOGIN)
_LOGIN_FIELDS = ("USERNAME", "ROLE_CODE", "DISPLAY_NAME", "ORGANISATION", "ACTIVE", "CREATED_AT", "CREATED_BY", "UPDATED_AT", "UPDATED_BY")


def _check_password(password: str) -> None:
    n = int(get_settings().get("auth.min_password_length", 8))
    if len(password) < n:
        raise ValidationError(f"Password must be at least {n} characters")


@router.get("/admin/logins")
def list_logins(user: dict = Depends(require("ADMIN"))):
    """Logins the admin created. The password hash is never returned."""
    return [{k: r.get(k) for k in _LOGIN_FIELDS} for r in repo().select("CORE.USER_LOGIN", None, order_by="USERNAME")]


@router.post("/admin/logins")
def create_login(body: LoginCreateIn, user: dict = Depends(require("ADMIN"))):
    """Admin: create a username + password for a role that signs in with a password (auth.password_roles, e.g. SCOPER)."""
    role, username = body.role.upper(), body.username.strip().lower()
    if role == ADMIN_ROLE:
        raise ValidationError("There is only one admin login; it is created with scripts/create_admin.py")
    if role not in set(get_settings().get("auth.password_roles", []) or []):
        raise ValidationError(f"Role {role} does not sign in with a password", details={"allowed": get_settings().get("auth.password_roles", [])})
    _check_password(body.password)
    r = repo()
    if r.select("CORE.USER_LOGIN", {"USERNAME": username}):
        raise Conflict(f"Username {username} already exists")
    org = next((u["ORGANISATION"] for u in ref().rows("users") if u["ROLE_CODE"] == role), "")
    row = {"USERNAME": username, "ROLE_CODE": role, "DISPLAY_NAME": body.display_name.strip(), "ORGANISATION": org,
           "PASSWORD_HASH": hash_password(body.password), "ACTIVE": True, "CREATED_AT": now_iso(), "CREATED_BY": user["sub"],
           "UPDATED_AT": now_iso(), "UPDATED_BY": user["sub"]}
    r.insert("CORE.USER_LOGIN", [row])
    AuditTrail.record(entity_type="USER_LOGIN", entity_id=username, action="CREATE", after={"role": role, "display_name": row["DISPLAY_NAME"]},
                      source="api")
    return {k: row[k] for k in _LOGIN_FIELDS}


@router.patch("/admin/logins/{username}")
def update_login(username: str, body: LoginUpdateIn, user: dict = Depends(require("ADMIN"))):
    """Admin: disable / enable a login, or set a new password."""
    r, username = repo(), username.strip().lower()
    rows = r.select("CORE.USER_LOGIN", {"USERNAME": username})
    if not rows:
        raise NotFound(f"Username {username} not found")
    if rows[0]["ROLE_CODE"] == ADMIN_ROLE:          # the one admin is managed with scripts/create_admin.py, so it cannot lock itself out
        raise ValidationError("The admin login is managed with scripts/create_admin.py and cannot be changed here")
    values: dict = {"UPDATED_AT": now_iso(), "UPDATED_BY": user["sub"]}
    if body.active is not None:
        values["ACTIVE"] = body.active
    if body.password is not None:
        _check_password(body.password)
        values["PASSWORD_HASH"] = hash_password(body.password)
    r.update("CORE.USER_LOGIN", values, {"USERNAME": username})
    actions = ([("ENABLE" if body.active else "DISABLE")] if body.active is not None else []) + (["PASSWORD_RESET"] if body.password is not None else [])
    for action in actions:                                        # account actions, not business edits, so no reason code
        AuditTrail.record(entity_type="USER_LOGIN", entity_id=username, action=action, source="api")
    return {k: r.get("CORE.USER_LOGIN", USERNAME=username).get(k) for k in _LOGIN_FIELDS}


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
