"""Data access layer. One Repository interface, two backends:

  * SqliteRepository    - local demo / tests (file under output/), no Snowflake account needed
  * SnowflakeRepository - the target platform (SCOPEIQ_<ENV> database), via snowflake-connector-python

Callers use logical table names ("CORE.DISCREPANCY") and plain dict rows; the backend maps names, JSON
(VARIANT) columns and SQL dialect. The repository also registers itself as the writer for the shared audit,
application-log and error-log components, so those land in AUDIT.* tables in every environment.
"""
from __future__ import annotations

import json
import re
import sqlite3
import os
import threading
from decimal import Decimal
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from scopeiq.common.audit import AuditTrail
from scopeiq.common.errors import DataAccessError, ErrorRecorder, NotFound
from scopeiq.common.logging import DbSinkHandler, get_logger, sql_logging_enabled
from scopeiq.config import get_settings
from scopeiq.db.schema import REF_TABLE_FILES, TABLES, Table, get_table, tables

log = get_logger("db.repository")      # 'scopeiq.db.*' loggers are never written back to APP_LOG (no recursion)

_FQN = re.compile(r"\b(RAW|REF|CORE|WF|AUDIT)\.([A-Z_]+)\b")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


class Repository:
    backend = "abstract"

    # -- lifecycle -------------------------------------------------------------------------------
    def init_schema(self) -> None: ...
    def close(self) -> None: ...

    # -- primitives (implemented per backend) ----------------------------------------------------
    def query(self, sql: str, params: Iterable | None = None) -> list[dict]: raise NotImplementedError
    def execute(self, sql: str, params: Iterable | None = None) -> int: raise NotImplementedError
    def insert(self, fqn: str, rows: list[dict]) -> int: raise NotImplementedError
    def upsert(self, fqn: str, rows: list[dict], keys: list[str] | None = None) -> int: raise NotImplementedError

    # -- generic helpers -------------------------------------------------------------------------
    def select(self, fqn: str, where: dict | None = None, *, order_by: str | None = None, limit: int | None = None) -> list[dict]:
        t = get_table(fqn)
        sql, params = f"SELECT * FROM {t.fqn}", []
        if where:
            clauses = []
            for k, v in where.items():
                if v is None:
                    clauses.append(f"{k} IS NULL")
                elif isinstance(v, (list, tuple, set)):
                    clauses.append(f"{k} IN ({', '.join(['%s'] * len(v))})")
                    params += list(v)
                else:
                    clauses.append(f"{k} = %s")
                    params.append(v)
            sql += " WHERE " + " AND ".join(clauses)
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return self._decode(t, self.query(sql, params))

    def get(self, fqn: str, **keys) -> dict:
        rows = self.select(fqn, keys, limit=1)
        if not rows:
            raise NotFound(f"{fqn} {keys} not found", details={"table": fqn, **keys})
        return rows[0]

    def update(self, fqn: str, values: dict, where: dict) -> int:
        t = get_table(fqn)
        sets = ", ".join(f"{k} = %s" for k in values)
        conds = " AND ".join(f"{k} = %s" for k in where)
        return self.execute(f"UPDATE {t.fqn} SET {sets} WHERE {conds}", [self._enc(t, k, v) for k, v in values.items()] + list(where.values()))

    def delete_where(self, fqn: str, where: dict) -> int:
        t = get_table(fqn)
        return self.execute(f"DELETE FROM {t.fqn} WHERE " + " AND ".join(f"{k} = %s" for k in where), list(where.values()))

    def fetch_reference(self, name: str) -> list[dict]:
        """Rows of a REF table with CSV semantics (strings, '' for null) for the reference loader."""
        file = {"material_catalog": "material_catalog.csv", "users": "users.csv"}.get(name) or f"{name}.csv"
        tname = next((t for t, f in REF_TABLE_FILES.items() if f == file), None)
        if not tname:
            raise DataAccessError(f"No REF table for {name}")
        rows = self.select(f"REF.{tname}")
        out = []
        for r in rows:
            r = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in r.items()}   # Snowflake NUMBER -> Decimal
            out.append({k: ("" if v is None else (v.isoformat() if isinstance(v, (date, datetime)) else
                                                  (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))))
                        for k, v in r.items() if k not in ("LOADED_AT", "LOADED_BY")})
        return out

    # -- JSON (VARIANT) handling -----------------------------------------------------------------
    @staticmethod
    def _enc(t: Table, col: str, v: Any) -> Any:
        c = next((c for c in t.columns if c.name == col), None)
        if c and c.type == "V" and v is not None and not isinstance(v, str):
            return json.dumps(v, default=_jsonable)
        if c and c.type == "B" and v is not None:
            return bool(v)
        if isinstance(v, (dict, list)):
            return json.dumps(v, default=_jsonable)
        return v

    @staticmethod
    def _decode(t: Table, rows: list[dict]) -> list[dict]:
        vcols = {c.name for c in t.columns if c.type == "V"}
        bcols = {c.name for c in t.columns if c.type == "B"}
        for r in rows:
            for k in list(r):
                ku = k.upper()
                if ku != k:
                    r[ku] = r.pop(k)
            for k in vcols:
                if isinstance(r.get(k), str):
                    try:
                        r[k] = json.loads(r[k])
                    except ValueError:
                        pass
            for k in bcols:
                if r.get(k) is not None:
                    r[k] = bool(r[k])
        return rows

    def _row(self, t: Table, r: dict) -> list:
        return [self._enc(t, c, r.get(c)) for c in t.column_names]

    # -- shared component writers ----------------------------------------------------------------
    def register_writers(self) -> None:
        st = get_settings()

        def audit_writer(entry: dict):
            self.insert("AUDIT.AUDIT_LOG", [entry])

        def error_writer(entry: dict):
            self.insert("AUDIT.ERROR_LOG", [dict(entry, ERROR_ID=uuid.uuid4().hex, ERROR_TS=now_iso())])

        AuditTrail.set_writer(audit_writer)
        ErrorRecorder.set_writer(error_writer)
        if st.get("logging.db_sink", False):
            def log_writer(entries: list[dict]):
                self.insert("AUDIT.APP_LOG", [dict(e, LOG_ID=uuid.uuid4().hex) for e in entries])
            DbSinkHandler.set_writer(log_writer)

    @contextmanager
    def transaction(self):
        yield self


# =================================================================================== SQLite
class SqliteRepository(Repository):
    backend = "local"

    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = threading.RLock()
        self._shared: sqlite3.Connection | None = None   # ":memory:" must be one connection, shared by all threads

    @property
    def conn(self) -> sqlite3.Connection:
        if self.path == ":memory:" and self._shared is not None:
            return self._shared
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL") if self.path != ":memory:" else None
            c.execute("PRAGMA foreign_keys=OFF")
            self._local.conn = c
            if self.path == ":memory:":
                self._shared = c
        return c

    @staticmethod
    def phys(fqn: str) -> str:
        layer, name = fqn.split(".")
        return f"{layer}__{name}"

    def _sql(self, sql: str) -> str:
        sql = _FQN.sub(lambda m: f"{m.group(1)}__{m.group(2)}", sql)
        return sql.replace("%s", "?")

    def init_schema(self) -> None:
        from scopeiq.db.ddl import sqlite_ddl
        with self._lock:
            self.conn.executescript(sqlite_ddl())
            self.conn.commit()

    def query(self, sql: str, params: Iterable | None = None) -> list[dict]:
        q = self._sql(sql)
        t0 = time.perf_counter()
        try:
            with self._lock:
                cur = self.conn.execute(q, list(params or []))
                rows = [dict(r) for r in cur.fetchall()]
        except sqlite3.Error as exc:
            raise DataAccessError(f"Query failed: {exc}", cause=exc, details={"sql": q[:500]}) from exc
        if sql_logging_enabled():
            log.debug("SQL %s (%d rows, %.1f ms)", q[:400], len(rows), (time.perf_counter() - t0) * 1000)
        return rows

    def execute(self, sql: str, params: Iterable | None = None) -> int:
        q = self._sql(sql)
        with self._lock:
            try:
                cur = self.conn.execute(q, list(params or []))
                self.conn.commit()
            except sqlite3.Error as exc:
                self.conn.rollback()
                raise DataAccessError(f"Statement failed: {exc}", cause=exc, details={"sql": q[:500]}) from exc
        if sql_logging_enabled():
            log.debug("SQL %s (%d rows)", q[:400], cur.rowcount)
        return cur.rowcount

    def _write(self, fqn: str, rows: list[dict], verb: str) -> int:
        if not rows:
            return 0
        t = get_table(fqn)
        cols = t.column_names
        sql = f"{verb} INTO {self.phys(t.fqn)} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
        with self._lock:
            try:
                self.conn.executemany(sql, [self._row(t, r) for r in rows])
                self.conn.commit()
            except sqlite3.Error as exc:
                self.conn.rollback()
                raise DataAccessError(f"Write to {fqn} failed: {exc}", cause=exc, details={"table": fqn, "rows": len(rows)}) from exc
        if sql_logging_enabled():
            log.debug("%s %s: %d rows", verb, fqn, len(rows))
        return len(rows)

    def insert(self, fqn: str, rows: list[dict]) -> int:
        return self._write(fqn, rows, "INSERT")

    def upsert(self, fqn: str, rows: list[dict], keys: list[str] | None = None) -> int:
        t = get_table(fqn)
        if keys and keys != t.pk:
            n = 0
            for r in rows:
                self.delete_where(fqn, {k: r[k] for k in keys})
                n += self.insert(fqn, [r])
            return n
        return self._write(fqn, rows, "INSERT OR REPLACE")

    def close(self) -> None:
        c = getattr(self._local, "conn", None)
        if c:
            c.close()
            self._local.conn = None


# =================================================================================== Snowflake
class SnowflakeRepository(Repository):
    backend = "snowflake"
    CHUNK = 200

    def __init__(self, cfg: dict):
        try:
            import snowflake.connector  # noqa: F401
        except ImportError as exc:
            raise DataAccessError("snowflake-connector-python is not installed (pip install -r requirements-snowflake.txt)") from exc
        self.cfg = cfg
        self.database = cfg["database"]
        self._conn = None
        self._lock = threading.RLock()

    @property
    def conn(self):
        if self._conn is None:
            import snowflake.connector
            args = {k: v for k, v in {
                "account": self.cfg.get("account"), "user": self.cfg.get("user"), "password": self.cfg.get("password") or None,
                "authenticator": self.cfg.get("authenticator") or None, "private_key_file": self.cfg.get("private_key_path") or None,
                "role": self.cfg.get("role"), "warehouse": self.cfg.get("warehouse"), "database": self.database,
                "application": "ScopeIQ", "session_parameters": {"QUERY_TAG": f"scopeiq-{get_settings().env}"}}.items() if v}
            token = Path("/snowflake/session/token")
            if args.get("authenticator") == "oauth" and token.exists():   # inside Snowpark Container Services
                args.update(token=token.read_text(), host=os.environ.get("SNOWFLAKE_HOST"), account=os.environ.get("SNOWFLAKE_ACCOUNT"))
                args.pop("user", None)
            try:
                self._conn = snowflake.connector.connect(**args)
            except Exception as exc:  # noqa: BLE001
                raise DataAccessError(f"Snowflake connection failed: {exc}", cause=exc,
                                      details={"account": self.cfg.get("account"), "database": self.database}) from exc
        return self._conn

    def _sql(self, sql: str) -> str:
        return _FQN.sub(lambda m: f"{self.database}.{m.group(1)}.{m.group(2)}", sql)

    def query(self, sql: str, params: Iterable | None = None) -> list[dict]:
        q = self._sql(sql)
        try:
            with self.conn.cursor() as cur:
                cur.execute(q, list(params or []))
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        except DataAccessError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DataAccessError(f"Snowflake query failed: {exc}", cause=exc, details={"sql": q[:500]}) from exc
        if sql_logging_enabled():
            log.debug("SQL %s (%d rows)", q[:400], len(rows))
        return rows

    def execute(self, sql: str, params: Iterable | None = None) -> int:
        q = self._sql(sql)
        try:
            with self.conn.cursor() as cur:
                cur.execute(q, list(params or []))
                return cur.rowcount or 0
        except Exception as exc:  # noqa: BLE001
            raise DataAccessError(f"Snowflake statement failed: {exc}", cause=exc, details={"sql": q[:500]}) from exc

    def insert(self, fqn: str, rows: list[dict]) -> int:
        """Multi-row INSERT ... SELECT FROM VALUES so JSON columns can go through PARSE_JSON."""
        t = get_table(fqn)
        for i in range(0, len(rows), self.CHUNK):
            chunk = rows[i:i + self.CHUNK]
            params = [v for r in chunk for v in self._row(t, r)]
            self.execute(f"INSERT INTO {t.fqn} ({', '.join(t.column_names)}) SELECT {self._parse_cols(t)} "
                         f"FROM VALUES {self._plain_values(t, len(chunk))}", params)
        return len(rows)

    @staticmethod
    def _plain_values(t: Table, n: int) -> str:
        return ", ".join(["(" + ", ".join(["%s"] * len(t.columns)) + ")"] * n)

    @staticmethod
    def _parse_cols(t: Table) -> str:
        return ", ".join(f"PARSE_JSON(COLUMN{j + 1})" if c.type == "V" else f"COLUMN{j + 1}" for j, c in enumerate(t.columns))

    def upsert(self, fqn: str, rows: list[dict], keys: list[str] | None = None) -> int:
        t = get_table(fqn)
        keys = keys or t.pk
        if not keys:
            return self.insert(fqn, rows)
        names = t.column_names
        src_cols = ", ".join(f"{e} AS {c}" for e, c in zip(self._parse_cols(t).split(", "), names))
        on = " AND ".join(f"t.{k} = s.{k}" for k in keys)
        upd = ", ".join(f"t.{c} = s.{c}" for c in names if c not in keys)
        ins = f"({', '.join(names)}) VALUES ({', '.join('s.' + c for c in names)})"
        for i in range(0, len(rows), self.CHUNK):
            chunk = rows[i:i + self.CHUNK]
            params = [v for r in chunk for v in self._row(t, r)]
            self.execute(f"MERGE INTO {t.fqn} t USING (SELECT {src_cols} FROM VALUES {self._plain_values(t, len(chunk))}) s ON {on} "
                         f"WHEN MATCHED THEN UPDATE SET {upd} WHEN NOT MATCHED THEN INSERT {ins}", params)
        return len(rows)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class SnowparkRepository(SnowflakeRepository):
    """Same SQL as SnowflakeRepository, executed through a Snowpark session (inside a stored procedure)."""
    backend = "snowpark"

    def __init__(self, session, database: str | None = None):
        self.session = session
        self.database = database or session.get_current_database().strip('"')
        self.cfg = {"database": self.database}
        self._conn = None
        self._lock = threading.RLock()

    def query(self, sql: str, params: Iterable | None = None) -> list[dict]:
        q = self._sql(sql).replace("%s", "?")
        try:
            rows = [r.as_dict() for r in self.session.sql(q, params=list(params or []) or None).collect()]
        except Exception as exc:  # noqa: BLE001
            raise DataAccessError(f"Snowpark query failed: {exc}", cause=exc, details={"sql": q[:500]}) from exc
        if sql_logging_enabled():
            log.debug("SQL %s (%d rows)", q[:400], len(rows))
        return rows

    def execute(self, sql: str, params: Iterable | None = None) -> int:
        q = self._sql(sql).replace("%s", "?")
        try:
            self.session.sql(q, params=list(params or []) or None).collect()
            return 0
        except Exception as exc:  # noqa: BLE001
            raise DataAccessError(f"Snowpark statement failed: {exc}", cause=exc, details={"sql": q[:500]}) from exc

    def close(self) -> None:
        pass


# =================================================================================== factory
_repo: Repository | None = None
_repo_lock = threading.Lock()


def get_repository(*, init: bool = True) -> Repository:
    """Process-wide repository for the configured backend (database.backend: local | snowflake)."""
    global _repo
    with _repo_lock:
        if _repo is None:
            st = get_settings()
            backend = st.get("database.backend", "local")
            if backend == "snowflake":
                _repo = SnowflakeRepository(dict(st.section("database").get("snowflake", {})))
            else:
                _repo = SqliteRepository(st.path("database.sqlite_path"))
                if init:
                    _repo.init_schema()
            _repo.register_writers()
            log.info("repository ready: %s", backend)
        return _repo


def set_repository(repo: Repository | None) -> None:
    """Tests inject an in-memory repository."""
    global _repo
    _repo = repo
    if repo:
        repo.register_writers()
