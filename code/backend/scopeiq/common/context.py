"""Per-request / per-run context (correlation id, user, site) carried through logs, audit and errors."""
from __future__ import annotations

import contextvars
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class RunContext:
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    user_id: str = "system"
    role: str = "SYSTEM"
    site_id: str | None = None
    component: str = "core"


_ctx: contextvars.ContextVar[RunContext] = contextvars.ContextVar("scopeiq_ctx", default=RunContext())


def current() -> RunContext:
    return _ctx.get()


@contextmanager
def bind(**changes):
    """Temporarily bind context values: `with bind(site_id='TXDA1024'): ...`"""
    token = _ctx.set(replace(_ctx.get(), **changes))
    try:
        yield _ctx.get()
    finally:
        _ctx.reset(token)


def set_context(ctx: RunContext):
    return _ctx.set(ctx)


def reset_context(token) -> None:
    _ctx.reset(token)
