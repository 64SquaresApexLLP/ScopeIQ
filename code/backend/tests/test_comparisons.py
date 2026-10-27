"""Stage 3 comparison log: what is compared with what, with the file names, and every mismatch is a logged discrepancy."""
from __future__ import annotations

import pytest

from scopeiq.services.pipeline import LAST_STAGE, STEP_DEFS
from tests.test_seeded_issues import EXPECTED

pytestmark = pytest.mark.needs_data


SEEDED_SITES = {k.split("-")[0] for k in EXPECTED}


def _checks(res):
    return res["summary"]["comparisons"]


def test_the_bom_stages_are_off(pipeline_results):
    if LAST_STAGE != "REDLINES":
        pytest.skip("later stages are switched on")
    assert [k for k, _ in STEP_DEFS][:3] == ["INGEST", "EXTRACT", "RECONCILE"]
    for res in pipeline_results.values():
        assert "bom" not in res["summary"]


def test_every_check_names_both_sides_and_files(pipeline_results):
    for sid, res in ((s, r) for s, r in pipeline_results.items() if s in SEEDED_SITES):
        by_id = {c["check_id"]: c for c in _checks(res)}
        eq = by_id["CD-DRONE-EQUIP"]
        assert eq["status"] != "SKIPPED", sid
        assert eq["left"]["label"] == "CD drawing" and eq["right"]["label"] == "Drone survey"
        assert eq["left"]["files"] and eq["right"]["files"], f"{sid}: file names missing"
        assert any(f.startswith(sid) for f in eq["left"]["files"] + eq["right"]["files"])
        assert eq["compared"] == len(eq["rows"]) and eq["compared"] > 0


def test_every_discrepancy_appears_as_a_mismatch_and_back(pipeline_results, repo):
    for sid, res in pipeline_results.items():
        run_id = res["run_id"]
        saved = {d["DISC_ID"]: d["RULE_ID"] for d in repo.select("CORE.DISCREPANCY", {"SITE_ID": sid, "RUN_ID": run_id})}
        linked = {d for c in _checks(res) for d in c["disc_ids"]}
        assert saved and set(saved) == linked, f"{sid}: findings {sorted(set(saved) ^ linked)} are not in the comparison log"
        for c in _checks(res):
            if c["status"] == "MISMATCH":
                assert c["disc_ids"], f"{sid} {c['check_id']}: a mismatch that was not logged as a discrepancy"
            for r in c["rows"]:
                assert (r["result"] == "MISMATCH") == bool(r["rule"]) or r["disc_id"] is None, (sid, c["check_id"], r)


def test_seeded_cd_vs_drone_mismatch_shows_the_pair(pipeline_results):
    row = next(r for c in _checks(pipeline_results["TXDA1024"]) if c["check_id"] == "CD-DRONE-PIPES" for r in c["rows"] if r["result"] == "MISMATCH")
    assert row["where"] == "Beta position 3" and row["rule"] == "FLD-02"
    assert "spare" in row["left"] and "No pipe found" in row["right"]
    az = next(r for c in _checks(pipeline_results["TXDE0831"]) if c["check_id"] == "CD-DRONE-AZ" for r in c["rows"] if r["result"] == "MISMATCH")
    assert az["where"] == "Alpha" and az["rule"] == "FLD-04"
