"""The one platform admin login (CORE.USER_LOGIN, role ADMIN). It is created with scripts/create_admin.py on each
database (the server keeps its own), never from the app, so there is only ever one admin account."""
from __future__ import annotations

from scopeiq.common.errors import Conflict, ValidationError
from scopeiq.common.passwords import hash_password
from scopeiq.config import get_settings
from scopeiq.db.repository import Repository, now_iso

ADMIN_ROLE = "ADMIN"
_PUBLIC = ("USERNAME", "ROLE_CODE", "DISPLAY_NAME", "ORGANISATION", "ACTIVE", "CREATED_AT", "CREATED_BY", "UPDATED_AT", "UPDATED_BY")


def admin_username() -> str:
    return str(get_settings().get("auth.admin_username", "admin")).strip().lower()


def get_admin(repo: Repository) -> dict | None:
    rows = repo.select("CORE.USER_LOGIN", {"ROLE_CODE": ADMIN_ROLE})
    return rows[0] if rows else None


def create_admin(repo: Repository, password: str, *, reset: bool = False, by: str = "script") -> dict:
    """Create the admin login, or with reset=True set a new password on the existing one. Returns the row without the hash."""
    n = int(get_settings().get("auth.admin_min_password_length", 12))
    if len(password) < n:
        raise ValidationError(f"Admin password must be at least {n} characters")
    existing, username, ts = get_admin(repo), admin_username(), now_iso()
    if existing and not reset:
        raise Conflict(f"The admin login '{existing['USERNAME']}' already exists - use --reset to set a new password")
    if existing:
        repo.update("CORE.USER_LOGIN", {"PASSWORD_HASH": hash_password(password), "ACTIVE": True, "UPDATED_AT": ts, "UPDATED_BY": by},
                    {"USERNAME": existing["USERNAME"]})
        return {k: repo.get("CORE.USER_LOGIN", USERNAME=existing["USERNAME"]).get(k) for k in _PUBLIC}
    if repo.select("CORE.USER_LOGIN", {"USERNAME": username}):
        raise Conflict(f"Username {username} is already used by another login")
    row = {"USERNAME": username, "ROLE_CODE": ADMIN_ROLE, "DISPLAY_NAME": "Platform Admin", "ORGANISATION": "Innosquares",
           "PASSWORD_HASH": hash_password(password), "ACTIVE": True, "CREATED_AT": ts, "CREATED_BY": by, "UPDATED_AT": ts, "UPDATED_BY": by}
    repo.insert("CORE.USER_LOGIN", [row])
    return {k: row[k] for k in _PUBLIC}
