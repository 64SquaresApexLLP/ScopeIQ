"""Deploy ScopeIQ to a Snowflake environment (works on Windows, macOS, Linux).

    pip install -r ../backend/requirements-snowflake.txt
    set SNOWFLAKE_ACCOUNT=xy12345.us-east-1        (PowerShell: $env:SNOWFLAKE_ACCOUNT="...")
    set SNOWFLAKE_USER=me
    set SNOWFLAKE_AUTHENTICATOR=externalbrowser    (or SNOWFLAKE_PASSWORD=..., or SNOWFLAKE_PRIVATE_KEY_PATH=...)

    python deploy_snowflake.py --env dev --all              # 01..12, uploads included
    python deploy_snowflake.py --env dev --steps 03 05      # selected scripts only
    python deploy_snowflake.py --env dev --upload           # (re)upload data, code zip, reference CSVs, seed
    python deploy_snowflake.py --env dev --dry-run --all    # print what would run

Each numbered script runs in its own session, prefixed with config/env_<env>.sql so the variables are set.
99_teardown.sql is never part of --all.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = HERE.parent
POC = CODE.parent                     # the ScopeIQ-POC folder
ALL_STEPS = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
UPLOAD_BEFORE = {"03"}                # uploads happen after 02 (stages exist) and before 03


def connect(role: str | None):
    import snowflake.connector
    args = {"account": os.environ["SNOWFLAKE_ACCOUNT"], "user": os.environ["SNOWFLAKE_USER"],
            "password": os.environ.get("SNOWFLAKE_PASSWORD"), "authenticator": os.environ.get("SNOWFLAKE_AUTHENTICATOR"),
            "private_key_file": os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"), "role": role or os.environ.get("SNOWFLAKE_ROLE"),
            "application": "ScopeIQ-deploy"}
    return snowflake.connector.connect(**{k: v for k, v in args.items() if v})


def script(step: str) -> Path:
    found = sorted(HERE.glob(f"{step}_*.sql"))
    if not found:
        sys.exit(f"no script for step {step}")
    return found[0]


def run_sql(conn, text: str, label: str, dry: bool) -> None:
    print(f"--- {label}")
    if dry:
        return
    for cur in conn.execute_stream(io.StringIO(text), remove_comments=True):
        try:
            rows = cur.fetchmany(5)
        except Exception:  # noqa: BLE001 - statements without a result set
            rows = []
        q = (cur.query or "").strip().splitlines()[0][:100] if cur.query else ""
        print(f"  ok  {q}" + (f"  -> {rows[0]}" if rows and len(rows) == 1 else ""))


def put_tree(conn, local: Path, stage: str, dry: bool) -> int:
    n = 0
    for p in sorted(local.rglob("*")):
        if not p.is_file() or p.name.startswith(".") or "__pycache__" in p.parts:
            continue
        rel_dir = p.parent.relative_to(local).as_posix()
        target = f"{stage}/{rel_dir}" if rel_dir != "." else stage
        sql = f"PUT 'file://{p.as_posix()}' '{target}' AUTO_COMPRESS = FALSE OVERWRITE = TRUE"
        n += 1
        if not dry:
            conn.cursor().execute(sql)
    print(f"  uploaded {n} files from {local} to {stage}")
    return n


def upload(conn, env_sql: str, dry: bool) -> None:
    db = next(l.split("'")[1] for l in env_sql.splitlines() if l.startswith("SET SCOPEIQ_DB"))
    print(f"--- uploads to {db}")
    data = POC / "Data"
    if not dry:
        conn.cursor().execute(f"USE DATABASE {db}")
    put_tree(conn, data / "Input-Data", f"@{db}.RAW.SITE_DOCS/Input-Data", dry)
    put_tree(conn, data / "Reference-Data", f"@{db}.RAW.SITE_DOCS/Reference-Data", dry)
    put_tree(conn, CODE / "reference_data", f"@{db}.RAW.SCOPEIQ_CODE/reference_data", dry)
    zip_ = CODE / "dist" / "scopeiq_code.zip"
    if not zip_.exists():
        sys.exit("dist/scopeiq_code.zip missing: run  python backend/scripts/generate_snowflake_sql.py  first")
    if not dry:
        conn.cursor().execute(f"PUT 'file://{zip_.as_posix()}' '@{db}.RAW.SCOPEIQ_CODE' AUTO_COMPRESS = FALSE OVERWRITE = TRUE")
    if (HERE / "seed").is_dir():
        put_tree(conn, HERE / "seed", f"@{db}.RAW.SEED", dry)
    if not dry:
        for st in ("SITE_DOCS", "SCOPEIQ_CODE"):
            conn.cursor().execute(f"ALTER STAGE {db}.RAW.{st} REFRESH")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", choices=["dev", "test", "prod"], required=True)
    ap.add_argument("--steps", nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--role", help="role to connect with (default ACCOUNTADMIN for 01, else SNOWFLAKE_ROLE)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    env_sql = (HERE / "config" / f"env_{a.env}.sql").read_text(encoding="utf-8")
    steps = ALL_STEPS if a.all else a.steps
    conn = None if a.dry_run else connect(a.role or "ACCOUNTADMIN")
    for step in steps:
        if step in UPLOAD_BEFORE and (a.all or a.upload):
            upload(conn, env_sql, a.dry_run)
        run_sql(conn, env_sql + "\n" + script(step).read_text(encoding="utf-8"), script(step).name, a.dry_run)
    if a.upload and not (a.all or UPLOAD_BEFORE & set(steps)):
        upload(conn, env_sql, a.dry_run)
    print("done")


if __name__ == "__main__":
    main()
