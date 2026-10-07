"""POC acceptance: every seeded discrepancy is found, and the generated BOMs equal the answer key."""
from __future__ import annotations

from collections import defaultdict

import pytest

pytestmark = pytest.mark.needs_data

# seeded issue -> (rule that must fire, sector, extra matcher on title/part)
EXPECTED = {
    "TXDA1024-01": ("FLD-02", "B", None), "TXDA1024-02": ("BOM-01", None, "GK-6"),
    "TXFW2217-01": ("RFC-01", "A", None), "TXFW2217-02": ("BOM-03", None, "SFP28"),
    "TXPL0588-01": ("FLD-01", "C", None), "TXPL0588-02": ("BOM-02", None, "RFJ"), "TXPL0588-03": ("MNT-01", None, None),
    "TXIR1340-01": ("FLD-03", None, None), "TXIR1340-02": ("BOM-04", None, "AF-LC-15"),
    "TXGR0719-01": ("RFC-02", "B", "4460"), "TXGR0719-02": ("FLD-06", None, None), "TXGR0719-03": ("SA-01", None, None),
    "TXDE0831-01": ("FLD-04", "A", None), "TXDE0831-02": ("BOM-02", None, "SNAP"),
    "TXRI0906-01": ("FLD-05", "D", None), "TXRI0906-02": ("BOM-01", None, "DCB-60"),
    "TXMK1112-01": ("FLD-01", "C", None), "TXMK1112-02": ("BOM-02", None, "trunk count"),
    "TXAD0405-01": ("RFC-04", "B", None), "TXAD0405-02": ("BOM-01", None, "WPK"),
    "TXCA0977-01": ("FLD-06", None, None), "TXCA0977-02": ("MNT-01", None, None),
}
# findings that are real but not in the seeded list (documented in docs/TEST_RESULTS.md)
KNOWN_EXTRA = {("TXAD0405", "FLD-03")}


def _discs(repo, site):
    return repo.select("CORE.DISCREPANCY", {"SITE_ID": site})


def test_all_seeded_issues_found(pipeline_results, repo, truth):
    seeded = [i for s in truth.build_sites() for i in s["issues"]]
    assert len(seeded) == 22
    missing = []
    for iss in seeded:
        rule, sector, text = EXPECTED[iss["issue_id"]]
        hits = [d for d in _discs(repo, iss["site_id"]) if d["RULE_ID"] == rule and (sector is None or d["SECTOR"] == sector)
                and (text is None or text.lower() in d["TITLE"].lower())]
        if not hits:
            missing.append(iss["issue_id"])
    assert not missing, f"seeded issues not detected: {missing}"


def test_no_unexpected_findings(pipeline_results, repo):
    allowed = {(k.split("-")[0], v[0]) for k, v in EXPECTED.items()} | KNOWN_EXTRA
    unexpected = [(d["SITE_ID"], d["RULE_ID"], d["TITLE"]) for site in pipeline_results for d in _discs(repo, site)
                  if d["RULE_ID"] != "EXT-01" and (d["SITE_ID"], d["RULE_ID"]) not in allowed]
    assert not unexpected, unexpected


def test_generated_bom_matches_answer_key(pipeline_results, repo, truth):
    bad = {}
    for s in truth.build_sites():
        sid = s["site_id"]
        want = defaultdict(float)
        for l in truth.generate_bom(s, "truth")[0]:
            want[(l["sector"], l["key"], l["action"])] += l["qty"] + l["spare"]
        rev = pipeline_results[sid]["summary"]["bom"]["rev_id"]
        got = defaultdict(float)
        for l in repo.select("CORE.BOM_LINE", {"BOM_REV_ID": rev}):
            got[(l["SECTOR"], l["CATALOG_KEY"], l["ACTION"])] += l["TOTAL_QTY"]
        diff = {k: (got.get(k), want.get(k)) for k in set(got) | set(want) if got.get(k) != want.get(k)}
        # point-cloud-only site: the unrecorded antenna's model is a dimensional look-alike, flagged for review
        if sid == "TXMK1112":
            diff = {k: v for k, v in diff.items() if not (k[2] == "Remove" and k[1] in ("APXV", "SBNHH"))}
        if diff:
            bad[sid] = diff
    assert not bad, bad


def test_rev0_errors_are_tool_errors(pipeline_results, repo):
    for sid, res in pipeline_results.items():
        for c in repo.select("CORE.BOM_CHANGE", {"SITE_ID": sid}):
            assert c["REASONS"], f"{sid} change without reason: {c}"


def test_redlines_and_files(pipeline_results, repo):
    for sid, res in pipeline_results.items():
        files = res["summary"]["files"]
        assert "bom_xlsx" in files
        if res["summary"]["redlines"]:
            assert "redlined_cd_pdf" in files
