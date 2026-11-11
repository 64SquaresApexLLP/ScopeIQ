"""Settings from environment variables. A local .env file is read when present (it is git-ignored); inside Snowflake the same
names come from the app's secrets / environment. Nothing secret is written in code."""
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


def get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def microsoft() -> dict:
    return {"tenant_id": get("MS_TENANT_ID"), "client_id": get("MS_CLIENT_ID"), "client_secret": get("MS_CLIENT_SECRET")}


def sharepoint_site_url() -> str:
    return get("SHAREPOINT_SITE_URL")
