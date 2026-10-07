"""Environment-driven settings.

The active environment comes from SCOPEIQ_ENV (dev | test | prod, default dev). Settings are the merge of
base.yaml, <env>.yaml and SCOPEIQ__SECTION__KEY environment variables, in that order. A backend/.env file
(KEY=VALUE lines, see .env.example) fills environment variables that are not already set.
"""
from __future__ import annotations

import os
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent
CODE_ROOT = CONFIG_DIR.parents[2]          # .../code
VALID_ENVS = ("dev", "test", "prod")


def _deep_merge(a: dict, b: dict) -> dict:
    out = deepcopy(a)
    for k, v in (b or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _coerce(raw: str) -> Any:
    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _env_overrides(prefix: str = "SCOPEIQ__") -> dict:
    out: dict = {}
    for key, raw in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = [p.lower() for p in key[len(prefix):].split("__") if p]
        node = out
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = _coerce(raw)
    return out


class Settings:
    """Read-only view over the merged configuration with dotted access: settings.get('logging.level')."""

    def __init__(self, env: str, data: dict):
        self.env = env
        self._data = data

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def section(self, name: str) -> dict:
        return deepcopy(self._data.get(name, {}))

    def path(self, dotted: str) -> Path:
        """Resolve a configured path relative to the code/ folder."""
        p = Path(self.get(dotted))
        return p if p.is_absolute() else (CODE_ROOT / p).resolve()

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    def as_dict(self) -> dict:
        return deepcopy(self._data)


def _load_dotenv() -> None:
    f = CODE_ROOT / "backend" / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_settings(env: str | None = None) -> Settings:
    _load_dotenv()
    env = (env or os.environ.get("SCOPEIQ_ENV", "dev")).lower()
    if env not in VALID_ENVS:
        raise ValueError(f"SCOPEIQ_ENV must be one of {VALID_ENVS}, got {env!r}")
    data = yaml.safe_load((CONFIG_DIR / "base.yaml").read_text())
    env_file = CONFIG_DIR / f"{env}.yaml"
    if env_file.exists():
        data = _deep_merge(data, yaml.safe_load(env_file.read_text()) or {})
    data = _deep_merge(data, _env_overrides())
    return Settings(env, data)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
