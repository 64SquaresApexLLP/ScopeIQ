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


def finished_sites() -> set[str]:
    """Sites whose newest pipeline run succeeded. Redlines and RFIs are results of that run, so nothing is shown for a site that has not been run,
    is running, or whose last run failed (a failed run did not finish comparing, so it has no valid result)."""
    newest: dict[str, tuple[str, str]] = {}
    for x in repo().query("SELECT SITE_ID, STATUS, STARTED_AT FROM CORE.PIPELINE_RUN"):
        if x["SITE_ID"] not in newest or str(x["STARTED_AT"]) > newest[x["SITE_ID"]][0]:
            newest[x["SITE_ID"]] = (str(x["STARTED_AT"]), x["STATUS"])
    return {sid for sid, (_, status) in newest.items() if status in ("SUCCEEDED", "SUCCEEDED_WITH_WARNINGS")}


def site_scope(user: dict) -> dict:
    """Data scope per persona: a CX SP sees only its own sites."""
    if user["role"] == "CX_SP":
        return {"CX_SP": user.get("sp") or user.get("org")}
    return {}


def my_notifications(user: dict, unread_only: bool = False) -> list[dict]:
    """The caller's inbox (newest first). A CX SP only gets notifications about its own sites, never another provider's."""
    sql = "SELECT * FROM WF.NOTIFICATION WHERE (ROLE_CODE = %s OR USER_ID = %s)" + (" AND READ_AT IS NULL" if unread_only else "")
    rows = repo().query(sql + " ORDER BY CREATED_AT DESC", [user["role"], user["sub"]])
    scope = site_scope(user)
    if scope:
        own = {s["SITE_ID"] for s in repo().select("CORE.SITE", scope)}
        rows = [n for n in rows if n.get("SITE_ID") in own]
    return rows


def provider_companies() -> list[str]:
    """The service-provider companies: those an admin has created a login for. A provider exists only as an account, never as sample data."""
    return sorted({x["ORGANISATION"] for x in repo().select("CORE.USER_LOGIN", {"ROLE_CODE": "CX_SP"}) if x.get("ORGANISATION") and x.get("ACTIVE")})


def shown_provider(name: str | None, companies=None) -> str | None:
    """The provider a site is shown with. A name left in tracker data that no account belongs to reads as not assigned."""
    return name if name and name in (companies if companies is not None else provider_companies()) else None


def internal_only(user: dict = Depends(current_user)) -> dict:
    """Scoping work (pipeline, findings, redlines, estimates, BOM drafts, raw files, reference tables) is for the scoping team. A service provider is
    given its sites, the final drawings and the approved BOM, through /sites and /documents only."""
    if user["role"] == "CX_SP":
        raise PermissionDenied("Not available for your role")
    return user


def scoping_only(user: dict = Depends(current_user)) -> dict:
    """The scoping workbench (pipeline, findings, BOM, estimates, handshake data) is for the scoping team, Admin and Ericsson. An A&E engineer is given the
    redlines and RFIs addressed to its firm and the CD and SA/MA files; a service provider its handshake."""
    if user["role"] in ("CX_SP", "AE_ENGINEER"):
        raise PermissionDenied("Not available for your role")
    return user


AE_FILE_TYPES = ("CD", "MA_SA")


def ae_work() -> dict[str, dict]:
    """Per site, what an A&E engineer has to do: its redlines, and the RFIs addressed to the firm that have been sent (not drafts), with how many are
    still open. Only sites whose newest run finished count, as everywhere else. What 'open' means comes from the workflow reference."""
    wf = workflow()
    closed = lambda entity: {s["STATE"] for s in wf.states if s["ENTITY_TYPE"] == entity and s["IS_TERMINAL"] == "Y"}   # noqa: E731
    redline_done, rfi_done, ready, work = closed("REDLINE"), closed("RFI"), finished_sites(), {}
    blank = lambda: {"redlines": 0, "open_redlines": 0, "rfis": 0, "open_rfis": 0}   # noqa: E731
    for x in repo().select("CORE.REDLINE", None):
        if x["SITE_ID"] in ready:
            w = work.setdefault(x["SITE_ID"], blank())
            w["redlines"] += 1
            w["open_redlines"] += x.get("STATUS") not in redline_done
    for x in repo().select("CORE.RFI", {"TO_PARTY": "AE_ENGINEER"}):
        if x["SITE_ID"] in ready and x.get("STATUS") != "DRAFT":
            w = work.setdefault(x["SITE_ID"], blank())
            w["rfis"] += 1
            w["open_rfis"] += x.get("STATUS") not in rfi_done
    return work


def _latest_scoping_run(site_id: str) -> dict | None:
    """Newest scoping pipeline run for a site (ignoring CDREV- redline application jobs)."""
    runs = [
        x for x in repo().select("CORE.PIPELINE_RUN", {"SITE_ID": site_id}, order_by="STARTED_AT DESC")
        if not str(x.get("RUN_ID") or "").startswith("CDREV-")
    ]
    return runs[0] if runs else None


def _bom_generated_for_site(site_id: str, run: dict) -> bool:
    """True when the pipeline run completed BOM generation (not skipped at Stage 4) or BOM output exists."""
    steps = run.get("STEPS")
    if isinstance(steps, list) and steps:
        bom_steps = [s for s in steps if isinstance(s, dict) and s.get("key") in ("BOM", "GENERATE")]
        if bom_steps:
            return any(s.get("status") == "DONE" for s in bom_steps)
    r = repo()
    if any(x.get("KIND") != "TOOL_REV0" for x in r.select("CORE.BOM_REVISION", {"SITE_ID": site_id})):
        return True
    return bool(r.select("CORE.BOM_OUTPUT_LINE", {"SITE_ID": site_id}, limit=1))


def provider_drawings(site_id: str, site: dict | None = None) -> list[dict]:
    """The construction drawings a service provider is given: the current CD drawings once the package is released
    to the service provider (SP_HANDSHAKE onward), after a finished pipeline run has generated the BOM and no redline is open."""
    r = repo()
    site_row = site or r.get("CORE.SITE", SITE_ID=site_id)
    if not provider_package_released(site_row):
        return []
    run = _latest_scoping_run(site_id)
    if not run or run.get("STATUS") not in ("SUCCEEDED", "SUCCEEDED_WITH_WARNINGS"):
        return []
    if not _bom_generated_for_site(site_id, run):
        return []
    done = {s["STATE"] for s in workflow().states if s["ENTITY_TYPE"] == "REDLINE" and s["IS_TERMINAL"] == "Y"} | {"INCORPORATED", "CLOSED"}
    if any(x.get("STATUS") not in done for x in r.select("CORE.REDLINE", {"SITE_ID": site_id})):
        return []
    return [d for d in r.select("CORE.DOCUMENT", {"SITE_ID": site_id, "DOC_TYPE": "CD"}, order_by="FILE_NAME") if d.get("STATUS") == "CURRENT"]


def provider_package_released(site: dict) -> bool:
    """The scope of work and the BOM go to a service provider when the locked revision is sent to it for the handshake, and stay with it through
    final approval. While the package is with the scoping team, or back with it after a change request, the provider is shown none of it."""
    return workflow().is_out_for_approval(site.get("WORKFLOW_STATE"))


def provider_phase(site: dict) -> str:
    """Where a site stands for its provider: PENDING (being prepared), REVIEW (waiting for its answer), AGREED (it agreed, final approval to come) or
    APPROVED. Read from who owns the workflow state and whether it is locked."""
    wf, state = workflow(), site.get("WORKFLOW_STATE")
    row = wf.state_row("SITE_SCOPING", state) or {}
    return "APPROVED" if wf.is_locked("SITE_SCOPING", state or "") else "REVIEW" if row.get("OWNER_ROLE") == "CX_SP" else "AGREED" if wf.is_out_for_approval(state) else "PENDING"


def check_document_access(user: dict, doc: dict) -> dict:
    """The document's site must be the caller's own, and a service provider may open only the drawings it has been given."""
    check_site_scope(user, doc["SITE_ID"])
    if user["role"] == "CX_SP" and doc["DOC_ID"] not in {d["DOC_ID"] for d in provider_drawings(doc["SITE_ID"])}:
        raise PermissionDenied("This document is not available to you")
    if user["role"] == "AE_ENGINEER" and doc.get("DOC_TYPE") not in AE_FILE_TYPES:
        raise PermissionDenied("An A&E engineer can open CD and SA/MA documents only")
    return doc


def check_site_scope(user: dict, site_id: str) -> dict:
    """Load the site and refuse it when it is outside the caller's scope (a CX SP's own sites only)."""
    site = repo().get("CORE.SITE", SITE_ID=site_id)
    scope = site_scope(user)
    if scope and site.get("CX_SP") != scope["CX_SP"]:
        raise PermissionDenied("This site is not assigned to your organisation")
    return site
