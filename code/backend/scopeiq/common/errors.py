"""One error hierarchy for the whole platform.

Every error carries a stable code (shown to users and support), an HTTP status for the API layer, a
user-safe message and optional details. The API turns any AppError into the same JSON envelope; unexpected
exceptions become SIQ-SYS-500 with only the correlation id exposed (details stay in the logs and ERROR_LOG).
"""
from __future__ import annotations

import traceback
from typing import Any, Callable

from scopeiq.common import context


class AppError(Exception):
    code = "SIQ-SYS-500"
    http_status = 500
    default_message = "Unexpected error"

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None, cause: Exception | None = None):
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.details = details or {}
        self.__cause__ = cause

    def to_dict(self, include_details: bool = True) -> dict[str, Any]:
        out = {"code": self.code, "message": self.message, "correlation_id": context.current().correlation_id}
        if include_details and self.details:
            out["details"] = self.details
        return out


class ValidationError(AppError):
    code, http_status, default_message = "SIQ-VAL-400", 400, "Invalid input"


class AuthenticationError(AppError):
    code, http_status, default_message = "SIQ-AUTH-401", 401, "Not signed in"


class PermissionDenied(AppError):
    code, http_status, default_message = "SIQ-AUTH-403", 403, "Your role cannot perform this action"


class NotFound(AppError):
    code, http_status, default_message = "SIQ-NF-404", 404, "Record not found"


class Conflict(AppError):
    code, http_status, default_message = "SIQ-CONF-409", 409, "The record changed or is locked"


class WorkflowError(Conflict):
    code, default_message = "SIQ-WF-409", "This workflow transition is not allowed"


class ImmutableRecordError(Conflict):
    code, default_message = "SIQ-LOCK-409", "Locked (FBA or approved) revisions cannot be edited"


class ExtractionError(AppError):
    code, http_status, default_message = "SIQ-EXT-422", 422, "Document could not be read"


class RuleError(AppError):
    code, http_status, default_message = "SIQ-RULE-500", 500, "Business rule evaluation failed"


class ReferenceDataError(AppError):
    code, http_status, default_message = "SIQ-REF-500", 500, "Reference data missing or invalid"


class DataAccessError(AppError):
    code, http_status, default_message = "SIQ-DB-503", 503, "Database unavailable"


class ErrorRecorder:
    """Persists errors to ERROR_LOG through a writer registered by the repository layer."""

    _writer: Callable[[dict], None] | None = None

    @classmethod
    def set_writer(cls, writer: Callable[[dict], None] | None) -> None:
        cls._writer = writer

    @classmethod
    def record(cls, exc: BaseException, *, where: str = "") -> None:
        if cls._writer is None:
            return
        c = context.current()
        try:
            cls._writer({
                "ERROR_CODE": getattr(exc, "code", AppError.code),
                "MESSAGE": str(exc)[:4000],
                "EXCEPTION_TYPE": type(exc).__name__,
                "STACK": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-8000:],
                "WHERE_RAISED": where,
                "CORRELATION_ID": c.correlation_id,
                "USER_ID": c.user_id,
                "SITE_ID": c.site_id,
                "COMPONENT": c.component,
                "DETAILS": getattr(exc, "details", {}) or {},
            })
        except Exception:  # pragma: no cover
            pass


def wrap_errors(error_cls: type[AppError] = AppError, message: str | None = None) -> Callable:
    """Decorator converting unexpected exceptions into `error_cls` (AppErrors pass through untouched)."""

    def deco(fn: Callable) -> Callable:
        import functools

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except AppError:
                raise
            except Exception as exc:  # noqa: BLE001
                err = error_cls(message or f"{fn.__qualname__} failed: {exc}", cause=exc,
                                details={"function": fn.__qualname__, "exception": type(exc).__name__})
                ErrorRecorder.record(err, where=fn.__qualname__)
                raise err from exc

        return wrapper

    return deco
