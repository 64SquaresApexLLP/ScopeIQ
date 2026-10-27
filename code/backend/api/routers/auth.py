"""Sign-in. Roles in auth.password_roles (SCOPER) sign in with a username + password the admin created (CORE.USER_LOGIN);
the other roles still use the demo login (pick an account, any non-empty password). Returns a signed bearer token."""
from fastapi import APIRouter, Depends

from api.deps import current_user, issue_token, ref, repo
from api.schemas import LoginIn
from scopeiq.common.audit import AuditTrail
from scopeiq.common.context import bind
from scopeiq.common.errors import AuthenticationError
from scopeiq.common.passwords import DUMMY_HASH, verify_password
from scopeiq.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def password_roles() -> set[str]:
    return set(get_settings().get("auth.password_roles", []) or [])


@router.get("/users")
def demo_users():
    """Accounts and personas for the login screen; `password_required` tells the screen to ask for a username + password."""
    personas = {p["ROLE_CODE"]: p for p in ref().rows("personas")}
    protected = password_roles()
    return [{"user_id": u["USER_ID"], "name": u["DISPLAY_NAME"], "role": u["ROLE_CODE"], "organisation": u["ORGANISATION"],
             "persona": personas.get(u["ROLE_CODE"], {}).get("PERSONA_NAME"), "password_required": u["ROLE_CODE"] in protected}
            for u in ref().rows("users") if u.get("ACTIVE", "Y") == "Y"]


def _credential_user(username: str, password: str) -> dict:
    rows = repo().select("CORE.USER_LOGIN", {"USERNAME": username.strip().lower()})
    row = rows[0] if rows else None
    ok = verify_password(password, row["PASSWORD_HASH"] if row else DUMMY_HASH)
    if not row or not ok or not row.get("ACTIVE") or row["ROLE_CODE"] not in password_roles():
        raise AuthenticationError("Incorrect username or password")
    return {"USER_ID": row["USERNAME"], "ROLE_CODE": row["ROLE_CODE"], "DISPLAY_NAME": row["DISPLAY_NAME"] or row["USERNAME"],
            "ORGANISATION": row.get("ORGANISATION") or "", "SERVICE_PROVIDER": ""}


def _demo_user(user_id: str | None) -> dict:
    user = next((u for u in ref().rows("users") if u["USER_ID"] == user_id and u.get("ACTIVE", "Y") == "Y"), None)
    if not user:
        raise AuthenticationError("Unknown user")
    if user["ROLE_CODE"] in password_roles():
        raise AuthenticationError("This role signs in with a username and password")
    return user


@router.post("/login")
def login(body: LoginIn):
    user = _credential_user(body.username, body.password) if body.username else _demo_user(body.user_id)
    with bind(user_id=user["USER_ID"], role=user["ROLE_CODE"]):
        AuditTrail.record(entity_type="SESSION", entity_id=user["USER_ID"], action="LOGIN", source="api")
    persona = next((p for p in ref().rows("personas") if p["ROLE_CODE"] == user["ROLE_CODE"]), {})
    return {"token": issue_token(user), "user": {"user_id": user["USER_ID"], "name": user["DISPLAY_NAME"], "role": user["ROLE_CODE"],
                                                 "organisation": user["ORGANISATION"], "service_provider": user.get("SERVICE_PROVIDER"),
                                                 "persona": persona.get("PERSONA_NAME"), "key_screens": persona.get("KEY_SCREENS")}}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user
