"""Stores the Microsoft credentials from the local .env as Snowflake SECRET objects (SCOPEIQ_DB.APP). Values are never printed.

    python scripts/store_secrets.py           # create the secrets that do not exist yet; existing ones are left alone
    python scripts/store_secrets.py --update  # set new values on existing secrets (use after rotating a credential)

Nothing is dropped or replaced."""
import argparse
import os
from pathlib import Path

import snowflake.connector

ENV = Path(__file__).resolve().parent.parent / ".env"
SECRETS = {"MS_TENANT_ID": "MS_TENANT_ID", "MS_CLIENT_ID": "MS_CLIENT_ID", "MS_CLIENT_SECRET": "MS_CLIENT_SECRET", "SHAREPOINT_SITE_URL": "SHAREPOINT_SITE_URL"}


def read_env() -> dict:
    out = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def lit(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\'") + "'"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    args = ap.parse_args()
    env = read_env()
    missing = [k for k in SECRETS.values() if not env.get(k)]
    if missing:
        raise SystemExit("missing in .env: " + ", ".join(missing))
    con = snowflake.connector.connect(connection_name=os.environ.get("SNOWFLAKE_CONNECTION", "scopeiq"), database="SCOPEIQ_DB", schema="APP", warehouse="SCOPEIQ_WH")
    cur = con.cursor()
    try:
        for name, key in SECRETS.items():
            cur.execute(f"SHOW SECRETS LIKE '{name}' IN SCHEMA SCOPEIQ_DB.APP")
            exists = bool(cur.fetchall())
            if exists and not args.update:
                print(f"kept     {name} (already exists)")
            elif exists:
                cur.execute(f"ALTER SECRET SCOPEIQ_DB.APP.{name} SET SECRET_STRING = {lit(env[key])}")
                print(f"updated  {name}")
            else:
                cur.execute(f"CREATE SECRET SCOPEIQ_DB.APP.{name} TYPE = GENERIC_STRING SECRET_STRING = {lit(env[key])}")
                print(f"created  {name}")
    finally:
        cur.close()
        con.close()


if __name__ == "__main__":
    main()
