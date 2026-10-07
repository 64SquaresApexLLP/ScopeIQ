"""Seeding: load the reference CSV library into REF.* tables and the personas' users (idempotent)."""
from __future__ import annotations

import csv

from scopeiq.common.logging import get_logger
from scopeiq.config import get_settings
from scopeiq.db.repository import Repository, now_iso
from scopeiq.db.schema import REF_TABLE_FILES, get_table

log = get_logger(__name__)


def load_reference_tables(repo: Repository, *, loaded_by: str = "seed") -> dict:
    src = get_settings().path("paths.reference_data_dir")
    counts = {}
    for table, file in REF_TABLE_FILES.items():
        t = get_table(f"REF.{table}")
        with open(src / file, newline="", encoding="utf-8-sig") as f:
            rows = [{k: (v if v != "" else None) for k, v in r.items()} for r in csv.DictReader(f)]
        for r in rows:
            r["LOADED_AT"], r["LOADED_BY"] = now_iso(), loaded_by
        repo.execute(f"DELETE FROM {t.fqn}")
        repo.insert(t.fqn, rows)
        counts[table] = len(rows)
    log.info("reference tables loaded: %s", counts)
    return counts


def ensure_reference_loaded(repo: Repository) -> None:
    if not repo.query("SELECT COUNT(*) AS N FROM REF.MATERIAL_CATALOG")[0]["N"]:
        load_reference_tables(repo)
