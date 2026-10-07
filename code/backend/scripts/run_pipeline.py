"""Run the ScopeIQ pipeline from the command line.

    python scripts/run_pipeline.py                 # all sites under paths.sites_dir
    python scripts/run_pipeline.py TXDA1024        # one or more sites
    SCOPEIQ_ENV=test python scripts/run_pipeline.py --backend snowflake

Results go to the configured database (local SQLite by default) and to output/sites/<SITE_ID>/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scopeiq.common.context import bind  # noqa: E402
from scopeiq.common.logging import configure_logging, get_logger  # noqa: E402
from scopeiq.config import get_settings, reset_settings_cache  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sites", nargs="*", help="site ids (default: all)")
    ap.add_argument("--backend", choices=["local", "snowflake"], help="override database.backend")
    ap.add_argument("--user", default="system")
    args = ap.parse_args()
    if args.backend:
        os.environ["SCOPEIQ__DATABASE__BACKEND"] = args.backend
        reset_settings_cache()
    configure_logging()
    log = get_logger("cli")
    from scopeiq.db.repository import get_repository
    from scopeiq.reference.loader import load_reference
    from scopeiq.services.pipeline import PipelineService
    from scopeiq.services.seed import ensure_reference_loaded

    repo = get_repository()
    ensure_reference_loaded(repo)
    ref = load_reference()
    svc = PipelineService(repo, ref)
    sites = args.sites or svc.site_ids()
    results = []
    with bind(user_id=args.user, role="SYSTEM" if args.user == "system" else "ADMIN", component="cli"):
        for sid in sites:
            try:
                res = svc.run_site(sid, triggered_by=args.user)
                s = res["summary"]
                results.append((sid, "OK", s["discrepancies"], s["bom"]["rev_label"], s["redlines"], s["rfis"], len(res["warnings"])))
            except Exception as exc:  # noqa: BLE001
                log.error("site %s failed: %s", sid, exc)
                results.append((sid, "FAILED", str(exc)[:80], "", "", "", ""))
    print(f"\n{'SITE':10} {'STATUS':8} {'DISCREP':>7} {'BOM':>6} {'REDLINES':>8} {'RFIS':>5} {'WARN':>5}")
    for r in results:
        print(f"{r[0]:10} {r[1]:8} {str(r[2]):>7} {str(r[3]):>6} {str(r[4]):>8} {str(r[5]):>5} {str(r[6]):>5}")
    print(f"\nEnvironment: {get_settings().env}   database: {get_settings().get('database.backend')}   output: {get_settings().path('paths.output_dir')}")
    return 0 if all(r[1] == "OK" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
