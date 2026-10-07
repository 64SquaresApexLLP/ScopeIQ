"""Shared fixtures. Tests run the real pipeline on the sample sites against an in-memory SQLite database."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SCOPEIQ_ENV", "test")
os.environ["SCOPEIQ__LOGGING__CONSOLE"] = "false"

from scopeiq.config import get_settings, reset_settings_cache  # noqa: E402

reset_settings_cache()
GENERATOR = get_settings().path("paths.data_root") / "DataDetails" / "generator"
SITES_DIR = get_settings().path("paths.sites_dir")


def pytest_collection_modifyitems(config, items):
    if not SITES_DIR.exists():
        skip = pytest.mark.skip(reason=f"sample data not found at {SITES_DIR}")
        for it in items:
            if "needs_data" in it.keywords:
                it.add_marker(skip)


@pytest.fixture(scope="session")
def ref():
    from scopeiq.reference.loader import load_reference
    return load_reference()


@pytest.fixture(scope="session")
def repo():
    from scopeiq.db.repository import SqliteRepository, set_repository
    from scopeiq.services.seed import load_reference_tables
    r = SqliteRepository(":memory:")
    r.init_schema()
    load_reference_tables(r)
    set_repository(r)
    yield r
    set_repository(None)


@pytest.fixture(scope="session")
def truth():
    """The data generator is the answer key: its site models hold the seeded issues and the true BOM."""
    if not GENERATOR.exists():
        pytest.skip("generator (answer key) not available")
    sys.path.insert(0, str(GENERATOR))
    import model as M  # type: ignore
    return M


@pytest.fixture(scope="session")
def pipeline_results(repo, ref):
    """Run the whole pipeline once for every sample site."""
    from scopeiq.common.context import bind
    from scopeiq.services.pipeline import PipelineService
    svc = PipelineService(repo, ref)
    with bind(user_id="system", role="SYSTEM"):
        return {sid: svc.run_site(sid) for sid in svc.site_ids()}
