"""ScopeIQ API (FastAPI). Start with:  uvicorn api.main:app --reload   (from code/backend)

Cross-cutting concerns live here: a correlation id per request (echoed in X-Correlation-ID and carried into
every log line, audit row and error), an access log, optional request/response payload logging (enabled per
environment with logging.log_payloads), and one JSON error envelope for every AppError:
    {"error": {"code": "SIQ-NF-404", "message": "...", "correlation_id": "...", "details": {...}}}
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routers import admin, auth, bom, discrepancies, documents, estimate, pipeline, redlines, sites, workflow
from scopeiq.common.context import RunContext, current, reset_context, set_context
from scopeiq.common.errors import AppError, ErrorRecorder
from scopeiq.common.logging import configure_logging, get_logger, payloads_enabled
from scopeiq.config import get_settings

log = get_logger("api")
access = get_logger("api.access")   # kept at INFO in prod (logging.info_loggers)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    from api.deps import ref, repo
    repo()       # creates the schema on first use (SQLite) and wires audit / error / log writers
    ref()        # loads REF.* from CSV if the tables are empty
    st = get_settings()
    log.info("ScopeIQ API started (env=%s, database=%s)", st.env, st.get("database.backend"))
    yield


def create_app() -> FastAPI:
    st = get_settings()
    app = FastAPI(title="ScopeIQ API", version=str(st.get("app.version")), lifespan=lifespan,
                  description="BOM, site design and deployment scoping: documents, discrepancies, redlines, RFIs, BOM revisions, "
                              "estimates and workflow. Authenticate with POST /auth/login (mock personas).")
    app.add_middleware(CORSMiddleware, allow_origins=st.get("api.cors_origins", ["*"]), allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["X-Correlation-ID"])

    @app.middleware("http")
    async def context_and_access_log(request: Request, call_next):
        cid = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex[:16]
        token = set_context(RunContext(correlation_id=cid, component="api"))
        t0 = time.perf_counter()
        try:
            if payloads_enabled() and request.method in ("POST", "PATCH", "PUT"):
                body = await request.body()
                if request.headers.get("content-type", "").startswith("application/json"):
                    log.debug("request %s %s body=%s", request.method, request.url.path, body[:2000].decode(errors="replace"))
            response = await call_next(request)
            ms = (time.perf_counter() - t0) * 1000
            access.info("%s %s -> %d (%.0f ms)", request.method, request.url.path, response.status_code, ms,
                     extra={"status": response.status_code, "duration_ms": round(ms)})
            response.headers["X-Correlation-ID"] = cid
            return response
        finally:
            reset_context(token)

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        if exc.http_status >= 500:
            ErrorRecorder.record(exc, where=f"api {request.method} {request.url.path}")
        else:
            log.warning("%s %s: %s %s", request.method, request.url.path, exc.code, exc.message)
        body = exc.to_dict(include_details=not get_settings().is_prod or exc.http_status < 500)
        return JSONResponse({"error": body}, status_code=exc.http_status)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        return JSONResponse({"error": {"code": "SIQ-VAL-400", "message": "Invalid request", "correlation_id": current().correlation_id,
                                       "details": {"errors": jsonable(exc.errors())}}}, status_code=400)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        ErrorRecorder.record(exc, where=f"api {request.method} {request.url.path}")
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"error": {"code": "SIQ-SYS-500", "message": "Unexpected error - quote the correlation id to support",
                                       "correlation_id": current().correlation_id}}, status_code=500)

    for r in (auth, sites, documents, pipeline, discrepancies, redlines, bom, estimate, workflow, admin):
        app.include_router(r.router)

    out = Path(st.path("paths.output_dir"))
    out.mkdir(parents=True, exist_ok=True)
    app.mount("/files", StaticFiles(directory=str(out)), name="files")

    @app.get("/health", tags=["health"])
    def health():
        from api.deps import repo
        ok = True
        try:
            repo().query("SELECT 1 AS OK")
        except Exception:  # noqa: BLE001
            ok = False
        return {"status": "ok" if ok else "degraded", "env": st.env, "database": st.get("database.backend"), "version": st.get("app.version")}

    return app


def jsonable(errors: list) -> list:
    return [{k: (v if isinstance(v, (str, int, float, list, type(None))) else str(v)) for k, v in e.items()} for e in errors]


app = create_app()
