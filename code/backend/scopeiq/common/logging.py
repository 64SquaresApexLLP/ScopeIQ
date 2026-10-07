"""Single logging setup for every ScopeIQ component (pipeline, API, scripts).

Behaviour is controlled only by configuration (SCOPEIQ_ENV + config/*.yaml + SCOPEIQ__LOGGING__* variables):
  dev  -> DEBUG everywhere, payloads and SQL traced, readable text format
  test -> INFO, SQL traced, JSON
  prod -> WARNING, plus INFO for the loggers in logging.info_loggers; PII masked; JSON

Every record carries correlation_id, user, role, site_id and component from scopeiq.common.context, so one
failing request can be followed through API -> service -> engine -> database.

Usage:
    from scopeiq.common.logging import get_logger, log_call
    log = get_logger(__name__)
    log.info("BOM generated", extra={"lines": 42})

    @log_call()                       # entry/exit at DEBUG, duration, slow-call WARNING, errors at ERROR
    def generate(...): ...
"""
from __future__ import annotations

import functools
import json
import logging
import logging.handlers
import random
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable

from scopeiq.common import context
from scopeiq.config import get_settings

ROOT_NAME = "scopeiq"
_CONFIGURED = False
_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {"message", "asctime"}
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _mask(text: str) -> str:
    return _EMAIL.sub("***@***", text)


class ContextFilter(logging.Filter):
    """Adds context fields and applies DEBUG sampling."""

    def __init__(self, sample_rate: float):
        super().__init__()
        self.sample_rate = sample_rate

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == logging.DEBUG and self.sample_rate < 1.0 and random.random() > self.sample_rate:
            return False
        c = context.current()
        record.correlation_id = c.correlation_id
        record.user_id = c.user_id
        record.role = c.role
        record.site_id = getattr(record, "site_id", None) or c.site_id
        record.component = c.component
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, mask_pii: bool):
        super().__init__()
        self.mask_pii = mask_pii

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", None),
            "user": getattr(record, "user_id", None),
            "site_id": getattr(record, "site_id", None),
            "component": getattr(record, "component", None),
            "where": f"{record.module}.{record.funcName}:{record.lineno}",
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED and k not in payload
                  and k not in ("user_id", "role")}
        if extras:
            payload["extra"] = extras
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        out = json.dumps(payload, default=str)
        return _mask(out) if self.mask_pii else out


class TextFormatter(logging.Formatter):
    def __init__(self, mask_pii: bool):
        super().__init__("%(asctime)s %(levelname)-7s [%(correlation_id)s|%(user_id)s|%(site_id)s] %(name)s: %(message)s")
        self.mask_pii = mask_pii

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED
                  and k not in ("correlation_id", "user_id", "role", "site_id", "component")}
        if extras:
            base += "  " + json.dumps(extras, default=str)
        return _mask(base) if self.mask_pii else base


class DbSinkHandler(logging.Handler):
    """Buffers records for the APP_LOG table. The repository registers a writer via set_writer()."""

    _writer: Callable[[list[dict]], None] | None = None

    @classmethod
    def set_writer(cls, writer: Callable[[list[dict]], None] | None) -> None:
        cls._writer = writer

    def emit(self, record: logging.LogRecord) -> None:
        if DbSinkHandler._writer is None or record.name.startswith(f"{ROOT_NAME}.db"):
            return  # never log the logger's own SQL into the DB (avoids recursion)
        try:
            DbSinkHandler._writer([{
                "LOG_TS": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "LEVEL": record.levelname,
                "LOGGER": record.name,
                "MESSAGE": record.getMessage()[:4000],
                "CORRELATION_ID": getattr(record, "correlation_id", None),
                "USER_ID": getattr(record, "user_id", None),
                "SITE_ID": getattr(record, "site_id", None),
                "COMPONENT": getattr(record, "component", None),
                "DETAIL": json.dumps({k: v for k, v in record.__dict__.items() if k not in _RESERVED}, default=str)[:8000],
            }])
        except Exception:  # pragma: no cover - logging must never break the caller
            self.handleError(record)


def configure_logging(force: bool = False) -> None:
    """Idempotent. Call once at process start (API startup, CLI main); get_logger() calls it lazily."""
    global _CONFIGURED
    if _CONFIGURED and not force:
        return
    s = get_settings()
    cfg = s.section("logging")
    level = getattr(logging, str(cfg.get("level", "INFO")).upper())
    mask = bool(cfg.get("mask_pii", True))
    fmt = JsonFormatter(mask) if cfg.get("format") == "json" else TextFormatter(mask)
    root = logging.getLogger(ROOT_NAME)
    root.handlers.clear()
    root.setLevel(logging.DEBUG)       # handlers decide; lets info_loggers pass in prod
    root.propagate = False
    flt = ContextFilter(float(cfg.get("sample_debug_rate", 1.0)))

    def add(handler: logging.Handler, lvl: int) -> None:
        handler.setLevel(lvl)
        handler.setFormatter(fmt)
        handler.addFilter(flt)
        root.addHandler(handler)

    if cfg.get("console", True):
        add(logging.StreamHandler(sys.stderr), logging.DEBUG)
    if cfg.get("file", True):
        log_dir = s.path("paths.log_dir")
        log_dir.mkdir(parents=True, exist_ok=True)
        add(logging.handlers.RotatingFileHandler(log_dir / f"scopeiq_{s.env}.log", maxBytes=int(cfg.get("file_max_bytes", 5 << 20)),
                                                 backupCount=int(cfg.get("file_backup_count", 5)), encoding="utf-8"), logging.DEBUG)
    if cfg.get("db_sink", True):
        add(DbSinkHandler(), getattr(logging, str(cfg.get("db_sink_level", "WARNING")).upper()))

    # Logger-level thresholds: root level for everything, INFO exceptions for named loggers (prod).
    logging.getLogger(ROOT_NAME).setLevel(level)
    for name in cfg.get("info_loggers", []) or []:
        logging.getLogger(name).setLevel(min(level, logging.INFO))
    for noisy in ("urllib3", "snowflake.connector", "botocore", "PIL", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    if not name.startswith(ROOT_NAME):
        name = f"{ROOT_NAME}.{name}"
    return logging.getLogger(name)


def payloads_enabled() -> bool:
    return bool(get_settings().get("logging.log_payloads", False))


def sql_logging_enabled() -> bool:
    return bool(get_settings().get("logging.log_sql", False))


def log_call(logger: logging.Logger | None = None, *, log_args: bool | None = None) -> Callable:
    """Decorator: DEBUG entry/exit with duration, WARNING when slower than logging.slow_call_ms, ERROR with
    traceback on exception (the exception is re-raised unchanged)."""

    def deco(fn: Callable) -> Callable:
        lg = logger or get_logger(fn.__module__)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            show_args = payloads_enabled() if log_args is None else log_args
            if lg.isEnabledFor(logging.DEBUG):
                lg.debug("-> %s", fn.__qualname__, extra={"call_args": _short(args, kwargs)} if show_args else None)
            t0 = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception:
                lg.exception("!! %s failed after %.0f ms", fn.__qualname__, (time.perf_counter() - t0) * 1000)
                raise
            ms = (time.perf_counter() - t0) * 1000
            slow = float(get_settings().get("logging.slow_call_ms", 1500))
            if ms >= slow:
                lg.warning("slow call %s took %.0f ms", fn.__qualname__, ms)
            elif lg.isEnabledFor(logging.DEBUG):
                lg.debug("<- %s %.1f ms", fn.__qualname__, ms)
            return result

        return wrapper

    return deco


def _short(args, kwargs, limit: int = 300) -> str:
    text = ", ".join([repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()])
    return text if len(text) <= limit else text[:limit] + "..."
