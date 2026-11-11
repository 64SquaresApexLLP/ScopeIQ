"""Settings. Nothing secret is written in code. Two sources, in this order:
  1. inside Snowflake: the app's SECRET objects (read through Snowflake's secret function)
  2. on a laptop: environment variables, with a local .env file read when present (it is git-ignored)"""
import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(Path(__file__).resolve().parent / ".env")

# environment variable -> name of the secret attached to the Streamlit app in Snowflake
_SECRET_NAMES = {"MS_TENANT_ID": "ms_tenant_id", "MS_CLIENT_ID": "ms_client_id", "MS_CLIENT_SECRET": "ms_client_secret", "SHAREPOINT_SITE_URL": "sharepoint_site_url"}


def get(name: str, default: str = "") -> str:
    secret = _SECRET_NAMES.get(name)
    if secret:
        try:
            import _snowflake                       # only exists inside Snowflake
            value = _snowflake.get_generic_secret_string(secret)
            if value:
                return value
        except Exception:
            pass
    return os.environ.get(name, default)


def microsoft() -> dict:
    return {"tenant_id": get("MS_TENANT_ID"), "client_id": get("MS_CLIENT_ID"), "client_secret": get("MS_CLIENT_SECRET")}


def sharepoint_site_url() -> str:
    return get("SHAREPOINT_SITE_URL")
