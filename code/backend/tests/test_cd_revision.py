"""Implement changes: approved redlines become the next CD revision. Re-reading the revised DXF with the CD extractor
shows the corrected drawing, so incorporating it would make the redlined findings resolve."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from scopeiq.config import get_settings

pytestmark = pytest.mark.needs_data


@pytest.fixture(scope="module")
def implemented(pipeline_results, repo, ref):
    """Approve every redline of every site, implement them, and return {site: finished 'implement changes' run}."""
    from scopeiq.services.pipeline import PipelineService
    svc = PipelineService(repo, ref)
    out = {}
    for site, res in pipeline_results.items():
        if not res["summary"]["redlines"]:
            continue
        for r in repo.select("CORE.REDLINE", {"SITE_ID": site}):
            repo.update("CORE.REDLINE", {"STATUS": "APPROVED"}, {"REDLINE_ID": r["REDLINE_ID"]})
        run_id = svc.start_apply(site)["run_id"]
        t0 = time.time()
        while time.time() - t0 < 600:
            run = repo.get("CORE.PIPELINE_RUN", RUN_ID=run_id)
            if run["STATUS"] != "RUNNING":
                break
            time.sleep(1)
        out[site] = run
    return out


def _file(run, kind):
    return get_settings().path("paths.output_dir") / run["SUMMARY"]["files"][kind]


def _reread(implemented, site, ref):
    from scopeiq.extract.cd import extract_cd_dxf
    return extract_cd_dxf(_file(implemented[site], "revised_cd_dxf"), site_id=site, doc_id="REV2", revision="REV 2", catalog=ref.catalog)


def test_every_site_with_cd_redlines_gets_a_revision(implemented):
    assert len(implemented) >= 9
    for site, run in implemented.items():
        assert run["STATUS"] == "SUCCEEDED", (site, run["WARNINGS"])
        assert _file(run, "revised_cd_pdf").is_file(), site
        log = json.loads(_file(run, "revised_cd_changes").read_text(encoding="utf-8"))
        assert log["to_revision"] == "REV 2" and log["issued"] == "ISSUED FOR CONSTRUCTION"
        not_applied = [c for c in log["changes"] if not c["applied"]]
        assert not not_applied, (site, not_applied)
        assert [s["status"] for s in run["STEPS"]] == ["DONE", "DONE", "DONE"]


def test_rev2_dxf_resolves_the_redlines(implemented, ref):
    # FLD-02: the spare pipe that is not in the field is gone
    r = _reread(implemented, "TXDA1024", ref)
    assert not [i for i in r.items if i.kind == "pipe" and i.sector == "B" and i.position == 3 and i.status == "Existing"]
    # FLD-06 + MNT-01: measured route on the cable schedule, reinforcement in the scope of work
    r = _reread(implemented, "TXCA0977", ref)
    assert r.trunk and r.trunk.horizontal_ft == 18 and r.trunk.specified_ft == 150      # same plan as BOM REV 1 (measured 18.2 ft -> 18)
    assert any("REINFORC" in s for s in r.scope_lines)
    # FLD-05: the delta sled is proposed
    r = _reread(implemented, "TXRI0906", ref)
    assert r.sectors["D"].sled["CD"] is False
    # RFC-01: alpha re-oriented to the RFDS azimuth
    r = _reread(implemented, "TXFW2217", ref)
    assert r.sectors["A"].azimuth["CD"] == 30
    assert all(i.azimuth_deg == 30 for i in r.items if i.sector == "A" and i.azimuth_deg is not None)
    # RFC-02 + FLD-06: radio added at beta 1, route corrected
    r = _reread(implemented, "TXGR0719", ref)
    assert any(i.sector == "B" and i.position == 1 and i.catalog_key == "R4460" and i.status == "New" for i in r.items)
    assert r.trunk and r.trunk.horizontal_ft == 80
    # FLD-01: unrecorded equipment shown and marked for removal
    r = _reread(implemented, "TXMK1112", ref)
    assert any(i.sector == "C" and i.position == 3 and i.catalog_key == "SBNHH" and i.status == "Remove" for i in r.items)
    r = _reread(implemented, "TXPL0588", ref)
    assert any(i.sector == "C" and i.position == 1 and i.catalog_key == "RRUS11" and i.status == "Remove" for i in r.items)
    assert any("REINFORC" in s for s in r.scope_lines)


def test_unapproved_redlines_are_not_implemented(pipeline_results, repo, ref):
    """Nothing is applied until a reviewer approves; the change log says why."""
    from scopeiq.outputs.cd_revision import write_revised_cd
    site = "TXDA1024"
    rows = repo.select("CORE.REDLINE", {"SITE_ID": site})
    from scopeiq.domain import Redline
    drafts = [Redline(r["REDLINE_ID"], site, r["DOC_TYPE"], r["DOC_REVISION"] or "", r["SHEET"], r["DISC_ID"], r["MARKUP"], "", "", "DRAFT") for r in rows]
    assert write_revised_cd(site_id=site, dxf_path=Path("unused.dxf"), pdf_path=None, out_dir=Path("unused"), redlines=drafts,
                            discrepancies=[], facts=None, ref=ref) == {}
