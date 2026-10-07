"""Deterministic identifiers so re-running the pipeline on the same inputs produces the same keys."""
from __future__ import annotations

import hashlib


def stable_id(prefix: str, *parts: object, length: int = 12) -> str:
    raw = "|".join(str(p) for p in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode()).hexdigest()[:length].upper()}"


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
