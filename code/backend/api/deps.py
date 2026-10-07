"""Shared API dependencies: mock authentication (signed bearer token), request context, role guards and
access to the long-lived services (repository, reference data, workflow engine, pipeline)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from functools import lru_cache
from typing import Callable

from fastapi import Depends, Header, Request

from scopeiq.common.context import current, set_context
from scopeiq.common.errors import AuthenticationError, PermissionDenied
from scopeiq.config import get_settings
from scopeiq.db.repository import Repository, get_repository
from scopeiq.reference.loader import ReferenceData, load_reference
from scopeiq.services.pipeline import PipelineService
from scopeiq.services.seed import ensure_reference_loaded
from scopeiq.workflow.engine import WorkflowEngine


# ------------------------------------------------------------------ services
def repo() -> Repository:
    return get_repository()


@lru_cache(maxsize=1)
def _ref() -> ReferenceData:
    r = get_repository()
    ensure_reference_loaded(r)
    src = get_settings().get("reference.source", "csv")
    return load_reference(repository=r if src == "database" else None)


def ref() -> ReferenceData:
    return _ref()


def reload_reference() -> ReferenceData:
    _ref.cache_clear()
    return _ref()


def workflow() -> WorkflowEngine:
    return WorkflowEngine(ref(), repo())


def pipeline() -> PipelineService:
    return PipelineService(repo(), ref())


# ------------------------------------------------------------------ mock auth
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def issue_token(user: dict) -> str:
    st = get_settings()
    payload = {"sub": user["USER_ID"], "role": user["ROLE_CODE"], "name": user["DISPLAY_NAME"], "org": user.get("ORGANISATION", ""),
               "sp": user.get("SERVICE_PROVIDER", ""), "exp": int(time.time()) + 60 * int(st.get("api.token_ttl_minutes", 480))}
    body = _b64(json.dumps(payload).encode())
    sig = _b64(hmac.new(str(st.get("api.token_secret")).encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def decode_token(token: str) -> dict:
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(str(get_settings().get("api.token_secret")).encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            raise ValueError("bad signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except Exception as exc:  # noqa: BLE001
        raise AuthenticationError("Invalid token") from exc
    if payload["exp"] < time.time():
        raise AuthenticationError("Session expired - log in again")
    return payload


async def current_user(request: Request, authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif request.query_params.get("access_token"):      # file downloads opened in a browser / OS viewer
        token = request.query_params["access_token"]
    else:
        raise AuthenticationError("Missing bearer token")
    user = decode_token(token)
    c = current()
    set_context(c.__class__(correlation_id=c.correlation_id, user_id=user["sub"], role=user["role"], site_id=c.site_id, component="api"))
    request.state.user = user
    return user


def require(*roles: str) -> Callable:
    """Dependency factory: the caller's role must be one of `roles` (ADMIN always passes)."""
    async def dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles and user["role"] != "ADMIN":
            raise PermissionDenied(f"Role {user['role']} cannot do this", details={"allowed": list(roles)})
        return user
    return dep


def site_scope(user: dict) -> dict:
    """Data scope per persona: a CX SP sees only its own sites."""
    if user["role"] == "CX_SP":
        return {"CX_SP": user.get("sp") or user.get("org")}
    return {}
