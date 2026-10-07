"""DDL generation from the schema registry (one source of truth for Snowflake and SQLite)."""
from __future__ import annotations

from scopeiq.db.schema import LAYERS, Table, tables

SF_TYPES = {"S": "VARCHAR", "N": "NUMBER(18,4)", "I": "NUMBER(38,0)", "B": "BOOLEAN", "T": "TIMESTAMP_TZ", "D": "DATE", "V": "VARIANT"}
LITE_TYPES = {"S": "TEXT", "N": "REAL", "I": "INTEGER", "B": "INTEGER", "T": "TEXT", "D": "TEXT", "V": "TEXT"}


def snowflake_table(t: Table) -> str:
    cols = [f"    {c.name:<24} {SF_TYPES[c.type]}{' NOT NULL' if c.not_null else ''}" for c in t.columns]
    if t.pk:
        cols.append(f"    CONSTRAINT PK_{t.name} PRIMARY KEY ({', '.join(t.pk)})")
    comment = t.comment.replace("'", "''")
    return f"CREATE TABLE IF NOT EXISTS {t.layer}.{t.name} (\n" + ",\n".join(cols) + f"\n) COMMENT = '{comment}';\n"


def snowflake_ddl(layer: str | None = None) -> str:
    out = []
    for lyr in [layer] if layer else LAYERS:
        out.append(f"-- ---------------------------------------------------------------- {lyr}\n")
        out += [snowflake_table(t) + "\n" for t in tables(lyr)]
    return "".join(out)


def sqlite_ddl() -> str:
    out = []
    for t in tables():
        cols = [f"{c.name} {LITE_TYPES[c.type]}" for c in t.columns]
        if t.pk:
            cols.append(f"PRIMARY KEY ({', '.join(t.pk)})")
        out.append(f"CREATE TABLE IF NOT EXISTS {t.layer}__{t.name} ({', '.join(cols)});")
    idx = [("CORE__DISCREPANCY", "SITE_ID"), ("CORE__BOM_LINE", "BOM_REV_ID"), ("CORE__CONFIG_LINE", "SITE_ID, RUN_ID"),
           ("CORE__EXTRACTED_FIELD", "SITE_ID, RUN_ID"), ("WF__WORKFLOW_EVENT", "ENTITY_TYPE, ENTITY_ID"), ("AUDIT__AUDIT_LOG", "ENTITY_TYPE, ENTITY_ID"),
           ("WF__NOTIFICATION", "ROLE_CODE, READ_AT")]
    out += [f"CREATE INDEX IF NOT EXISTS IX_{t}_{i.replace(', ', '_')} ON {t} ({i});" for t, i in idx]
    return "\n".join(out)
