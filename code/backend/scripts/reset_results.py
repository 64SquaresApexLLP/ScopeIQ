"""Clear the stored results of pipeline runs, so a site shows nothing until the pipeline has run on it.

    python scripts/reset_results.py --site TXDA1024 --yes     # one site
    python scripts/reset_results.py --all --yes               # every site

Removes run history, extracted values, discrepancies, redlines, RFIs, proof pictures, BOMs and estimates, and each site's
workflow history; the site goes back to ASSIGNED. Kept: the sites themselves, their documents, milestones, logins, reference
data and the audit/error logs. Generated drawings and pictures under <output>/sites are removed too. Stop the backend first.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scopeiq.config import get_settings  # noqa: E402
from scopeiq.db.repository import get_repository  # noqa: E402
from scopeiq.db.schema import tables  # noqa: E402

RESULT_TABLES = ["CORE.PIPELINE_RUN", "CORE.EXTRACTED_FIELD", "CORE.CONFIG_LINE", "CORE.EXTRACTED_COMPARISON_RECORD", "CORE.FIELD_OBJECT",
                 "CORE.EVIDENCE_FRAME", "CORE.ANALYSIS_RESULT", "CORE.TRUNK_MEASURE", "CORE.REV0_LINE", "CORE.DISCREPANCY", "CORE.REDLINE",
                 "CORE.REDLINE_PROOF", "CORE.RFI", "CORE.EQUIPMENT_DELTA", "CORE.BOM_LINE", "CORE.BOM_CHANGE", "CORE.BOM_REVISION",
                 "CORE.DRIVER_LINE", "CORE.SITE_REQUIREMENT", "CORE.EHS_ALERT", "CORE.ESTIMATE", "WF.WORKFLOW_EVENT", "WF.NOTIFICATION"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", help="one site id")
    ap.add_argument("--all", action="store_true", help="every site")
    ap.add_argument("--yes", action="store_true", help="confirm that the results are to be deleted")
    args = ap.parse_args()
    if bool(args.site) == bool(args.all):
        print("Give either --site <id> or --all.")
        return 1
    if not args.yes:
        print("This deletes stored pipeline results. Run again with --yes to confirm.")
        return 1
    repo = get_repository()
    known = {t.fqn for t in tables()}
    sites = [args.site] if args.site else [s["SITE_ID"] for s in repo.select("CORE.SITE")]
    out = Path(get_settings().path("paths.output_dir"))
    for sid in sites:
        removed = 0
        for table in (t for t in RESULT_TABLES if t in known):
            try:
                removed += len(repo.select(table, {"SITE_ID": sid}))
            except Exception:  # noqa: BLE001 - only the count is lost; the delete below is what matters
                pass
            repo.delete_where(table, {"SITE_ID": sid})
        repo.update("CORE.SITE", {"WORKFLOW_STATE": "ASSIGNED"}, {"SITE_ID": sid})
        for folder in (out / "sites" / sid, out / "evidence" / sid):
            shutil.rmtree(folder, ignore_errors=True)
        print(f"{sid}: {removed} stored result row(s) removed, site back to ASSIGNED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
