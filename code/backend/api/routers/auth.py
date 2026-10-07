"""Mock login: pick a demo user (any non-empty password). Returns a signed bearer token with the persona."""
from fastapi import APIRouter, Depends

from api.deps import current_user, issue_token, ref
from api.schemas import LoginIn
from scopeiq.common.audit import AuditTrail
from scopeiq.common.context import bind
from scopeiq.common.errors import AuthenticationError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/users")
def demo_users():
    """Demo accounts and personas for the login screen."""
    personas = {p["ROLE_CODE"]: p for p in ref().rows("personas")}
    return [{"user_id": u["USER_ID"], "name": u["DISPLAY_NAME"], "role": u["ROLE_CODE"], "organisation": u["ORGANISATION"],
             "persona": personas.get(u["ROLE_CODE"], {}).get("PERSONA_NAME")} for u in ref().rows("users") if u.get("ACTIVE", "Y") == "Y"]


@router.post("/login")
def login(body: LoginIn):
    user = next((u for u in ref().rows("users") if u["USER_ID"] == body.user_id and u.get("ACTIVE", "Y") == "Y"), None)
    if not user or not body.password:
        raise AuthenticationError("Unknown user or empty password")
    with bind(user_id=user["USER_ID"], role=user["ROLE_CODE"]):
        AuditTrail.record(entity_type="SESSION", entity_id=user["USER_ID"], action="LOGIN", source="api")
    persona = next((p for p in ref().rows("personas") if p["ROLE_CODE"] == user["ROLE_CODE"]), {})
    return {"token": issue_token(user), "user": {"user_id": user["USER_ID"], "name": user["DISPLAY_NAME"], "role": user["ROLE_CODE"],
                                                 "organisation": user["ORGANISATION"], "service_provider": user.get("SERVICE_PROVIDER"),
                                                 "persona": persona.get("PERSONA_NAME"), "key_screens": persona.get("KEY_SCREENS")}}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user
