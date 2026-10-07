"""Reusable audit trail (guide section 13: log every human edit with who, when and a reason code).

AuditTrail.record() is the only way any component writes an audit entry. The repository registers a writer
(AUDIT_LOG table); without one, entries are kept in memory (tests, offline pipeline runs) and logged to
the 'scopeiq.audit' logger, which stays at INFO even in prod.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from scopeiq.common import context
from scopeiq.common.errors import ValidationError
from scopeiq.common.logging import get_logger
from scopeiq.config import get_settings

log = get_logger("scopeiq.audit")

# Actions that change a business record made by a person must carry a reason code (see reference_data/reason_codes.csv).
REASON_REQUIRED = {"UPDATE", "DELETE", "OVERRIDE", "REJECT", "DISMISS", "REOPEN", "EDIT_QTY", "REWORK"}


class AuditTrail:
    _writer: Callable[[dict], None] | None = None
    _memory: list[dict] = []
    _reason_codes: set[str] | None = None

    @classmethod
    def set_writer(cls, writer: Callable[[dict], None] | None) -> None:
        cls._writer = writer

    @classmethod
    def set_reason_codes(cls, codes: set[str] | None) -> None:
        cls._reason_codes = codes

    @classmethod
    def record(cls, *, entity_type: str, entity_id: str, action: str, before: Any = None, after: Any = None,
               reason_code: str | None = None, comment: str | None = None, site_id: str | None = None,
               source: str = "app") -> dict:
        if not get_settings().get("audit.enabled", True):
            return {}
        c = context.current()
        human = c.user_id != "system"
        if human and action.upper() in REASON_REQUIRED and not reason_code:
            raise ValidationError(f"A reason code is required for {action} on {entity_type}",
                                  details={"entity_type": entity_type, "entity_id": entity_id})
        if reason_code and cls._reason_codes is not None and reason_code not in cls._reason_codes:
            raise ValidationError(f"Unknown reason code {reason_code}", details={"reason_code": reason_code})
        keep = get_settings().get("audit.capture_before_after", True)
        entry = {
            "AUDIT_ID": uuid.uuid4().hex,
            "EVENT_TS": datetime.now(timezone.utc).isoformat(),
            "ENTITY_TYPE": entity_type,
            "ENTITY_ID": str(entity_id),
            "SITE_ID": site_id or c.site_id,
            "ACTION": action.upper(),
            "ACTOR_USER_ID": c.user_id,
            "ACTOR_ROLE": c.role,
            "REASON_CODE": reason_code,
            "COMMENT": comment,
            "BEFORE_VALUE": json.dumps(before, default=str) if keep and before is not None else None,
            "AFTER_VALUE": json.dumps(after, default=str) if keep and after is not None else None,
            "CORRELATION_ID": c.correlation_id,
            "SOURCE": source,
        }
        if cls._writer:
            cls._writer(entry)
        else:
            cls._memory.append(entry)
        log.info("audit %s %s/%s by %s", entry["ACTION"], entity_type, entity_id, c.user_id,
                 extra={"reason_code": reason_code})
        return entry

    @classmethod
    def memory(cls) -> list[dict]:
        return list(cls._memory)

    @classmethod
    def clear_memory(cls) -> None:
        cls._memory.clear()
