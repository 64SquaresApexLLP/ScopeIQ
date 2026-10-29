"""Stage 4: the decision (is a redline / an RFI needed?) and the redlined CD drawing it leads to."""
from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from scopeiq.config import get_settings
from scopeiq.domain import Discrepancy, Redline, SiteFacts
from scopeiq.engine.redlines import decide, draft_redlines_and_rfis
from scopeiq.outputs.redline_markup import remove_redlined_cd, write_redlined_cd
from scopeiq.services.pipeline import STEP_DEFS
from tests.test_seeded_issues import EXPECTED

SEEDED_SITES = {k.split("-")[0] for k in EXPECTED}


def _disc(rule, outcome, target="CD", status="OPEN", **kw):
    return Discrepancy(f"DSC-{rule}", "TXAA0001", rule, "CD_VS_FIELD", "MEDIUM", outcome, f"{rule} finding", "", sector=kw.pop("sector", "B"),
                       position=kw.pop("position", 3), expected=kw.pop("expected", "pipe"), found=kw.pop("found", "none"), target_doc=target, status=status)


# ------------------------------------------------------------------ the decision (no data needed)
def test_no_mismatch_means_no_redlined_drawing(ref):
    d = decide(SiteFacts("TXAA0001"), [], ref)
    assert not d.required and d.redline_count == 0 and d.rfi_count == 0
    assert "No mismatch" in d.reason


def test_a_drawing_mismatch_requires_a_redline(ref):
    d = decide(SiteFacts("TXAA0001"), [_disc("FLD-02", "REDLINE")], ref)
    assert d.required and d.items[0].redline == "REQUIRED" and not d.items[0].rfi and d.items[0].on_cd_drawing


def test_a_question_first_finding_is_marked_up_subject_to_the_rfi(ref):
    f = SiteFacts("TXAA0001")
    d = decide(f, [_disc("FLD-04", "RFI", sector="A", position=None, expected=0.0, found=348.0)], ref)
    assert d.items[0].redline == "SUBJECT_TO_RFI" and d.items[0].rfi and d.required


@pytest.mark.parametrize("outcome,target,status,why", [
    ("FLAG", "CD", "OPEN", "does not change the drawing"),
    ("REVIEW", "ANY", "OPEN", "does not name a drawing"),
    ("BOM_CHANGE", "BOM_REV0", "OPEN", "not a drawing"),
    ("REDLINE", "CD", "DISMISSED", "already dismissed"),
    ("REDLINE", "CD", "RESOLVED", "already resolved"),
])
def test_findings_that_do_not_change_the_drawing_get_no_redline(ref, outcome, target, status, why):
    d = decide(SiteFacts("TXAA0001"), [_disc("FLD-02", outcome, target, status)], ref)
    assert d.items[0].redline == "NONE" and not d.required and why in d.items[0].redline_reason
    assert "none of them changes the CD drawing" in d.reason


def test_a_rule_without_a_markup_gets_no_redline(ref):
    d = decide(SiteFacts("TXAA0001"), [_disc("CBL-01", "RFI")], ref)
    assert d.items[0].redline == "NONE" and "no drawing markup" in d.items[0].redline_reason and d.items[0].rfi


def test_rfi_is_needed_for_rfi_and_escalate_only(ref):
    discs = [_disc("DOC-01", "RFI", "REGISTRY"), _disc("SA-01", "ESCALATE", "MA_SA"), _disc("FLD-02", "REDLINE"), _disc("EXT-01", "REVIEW", "ANY"),
             _disc("RFC-02", "RFI", status="DISMISSED")]
    d = decide(SiteFacts("TXAA0001"), discs, ref)
    assert {i.rule_id for i in d.items if i.rfi} == {"DOC-01", "SA-01"}                 # a dismissed finding asks nothing either
    assert d.rfi_count == 2


def test_only_what_was_decided_is_drafted(ref):
    f = SiteFacts("TXAA0001")
    f.cd_revision = "REV 1"
    discs = [_disc("FLD-02", "REDLINE"), _disc("FLD-02", "REDLINE", status="DISMISSED")]
    discs[1].disc_id = "DSC-other"
    redlines, rfis = draft_redlines_and_rfis(f, discs, ref)
    assert len(redlines) == 1 and redlines[0].disc_id == "DSC-FLD-02" and not rfis


def test_nothing_to_redline_writes_no_drawing_and_clears_an_old_one(tmp_path):
    f = SiteFacts("TXAA0001")
    f.cd_revision = "REV 1"
    stale = tmp_path / "TXAA0001_CD_REV1_REDLINED.pdf"
    stale.write_bytes(b"%PDF-1.4 old")
    assert write_redlined_cd(facts=f, discs=[], redlines=[], dxf_path=None, pdf_path=None, out_dir=tmp_path, ref=None) == {}
    assert not stale.exists()
    stale.write_bytes(b"%PDF-1.4 old")
    remove_redlined_cd(tmp_path, f)
    assert not stale.exists()


# ------------------------------------------------------------------ the real sites
pytestmark_data = pytest.mark.needs_data


@pytest.mark.needs_data
def test_run_has_the_four_stages(pipeline_results):
    from scopeiq.services.pipeline import LAST_STAGE
    if LAST_STAGE != "REDLINES":
        pytest.skip("a different last stage is configured")
    assert [k for k, _ in STEP_DEFS] == ["INGEST", "EXTRACT", "RECONCILE", "REDLINES"]


@pytest.mark.needs_data
def test_a_redlined_drawing_exists_exactly_when_the_decision_says_so(pipeline_results):
    out = get_settings().path("paths.output_dir")
    for sid, res in pipeline_results.items():
        dec, files = res["summary"].get("redline_decision"), res["summary"].get("files", {})
        if dec is None:
            continue
        assert ("redlined_cd_pdf" in files) == dec["required"], (sid, dec["reason"])
        if dec["required"]:
            pdf = PdfReader(str(out / files["redlined_cd_pdf"]))
            assert len(pdf.pages) == 6, sid                              # summary page + the five sheets
            assert dec["redlines"] >= 1


@pytest.mark.needs_data
def test_every_redline_and_rfi_comes_from_a_live_finding(pipeline_results, repo):
    for sid, res in pipeline_results.items():
        if sid not in SEEDED_SITES or "redline_decision" not in res["summary"]:
            continue
        discs = {d["DISC_ID"]: d for d in repo.select("CORE.DISCREPANCY", {"SITE_ID": sid, "RUN_ID": res["run_id"]})}
        for r in repo.select("CORE.REDLINE", {"SITE_ID": sid}):
            if r["DISC_ID"] in discs:
                assert discs[r["DISC_ID"]]["OUTCOME"] in ("REDLINE", "RFI"), (sid, r["REDLINE_ID"])
        rfis = repo.select("CORE.RFI", {"SITE_ID": sid})
        for x in rfis:
            for disc_id in x["DISC_IDS"]:
                if disc_id in discs:
                    assert discs[disc_id]["OUTCOME"] in ("RFI", "ESCALATE"), (sid, x["RFI_ID"])


@pytest.mark.needs_data
def test_markup_is_placed_for_dxf_and_pdf_only_sites(pipeline_results):
    out = get_settings().path("paths.output_dir")
    for sid, method in (("TXDA1024", "DXF"), ("TXIR1340", "PDF_OCR")):
        res = pipeline_results[sid]
        assert res["summary"]["cd_method"].startswith(method[:3]), sid
        files = res["summary"]["files"]
        assert ("redlined_cd_dxf" in files) == (method == "DXF")             # the editable copy exists only when a DXF was compared
        text = "".join(p.extract_text() or "" for p in PdfReader(str(out / files["redlined_cd_pdf"])).pages[:1])
        assert "REDLINE SUMMARY" in text and sid in text


@pytest.mark.needs_data
def test_dismissing_the_only_finding_leaves_no_redlined_drawing(pipeline_results, repo, ref):
    """End to end: the decision turns to 'no redline needed', no drawing is written, and the old one is removed."""
    from scopeiq.common.context import bind
    from scopeiq.services.pipeline import PipelineService

    out = get_settings().path("paths.output_dir")
    before = pipeline_results["TXDA1024"]["summary"]["files"]["redlined_cd_pdf"]
    assert (out / before).exists()
    disc = repo.select("CORE.DISCREPANCY", {"SITE_ID": "TXDA1024", "RULE_ID": "FLD-02"})[0]
    repo.update("CORE.DISCREPANCY", {"STATUS": "DISMISSED", "UPDATED_BY": "reviewer1"}, {"DISC_ID": disc["DISC_ID"]})
    try:
        with bind(user_id="system", role="SYSTEM"):
            res = PipelineService(repo, ref).run_site("TXDA1024")
        assert res["summary"]["redline_decision"]["required"] is False
        assert "redlined_cd_pdf" not in res["summary"]["files"] and not (out / before).exists()
        assert all(r["PDF_PATH"] is None for r in repo.select("CORE.REDLINE", {"SITE_ID": "TXDA1024"}))
    finally:                                                            # leave the shared test data as it was
        repo.update("CORE.DISCREPANCY", {"STATUS": "OPEN", "UPDATED_BY": "system"}, {"DISC_ID": disc["DISC_ID"]})
        with bind(user_id="system", role="SYSTEM"):
            PipelineService(repo, ref).run_site("TXDA1024")


# ------------------------------------------------------------------ proof from the drone footage
def _facts_with_footage(visible_bearings, all_bearings=range(0, 360, 30)):
    from scopeiq.domain import FieldObject, VideoFrame
    f = SiteFacts("TXAA0001")
    f.frames = [VideoFrame(i, i / 12, float(b), None, 100.0, f"f{i}.jpg", equipment=4.0 if b in visible_bearings else 0.0,
                           box=(300, 100, 460, 200) if b in visible_bearings else None) for i, b in enumerate(all_bearings)]
    f.field_objects = [FieldObject("OBJ-1", "Mount pipe", "B", 178.0, None, 190.0, None, "", 0.9, position=3)]
    return f


def test_proof_is_a_frame_that_faces_the_place_and_shows_the_equipment():
    from scopeiq.engine.proof import choose
    f = _facts_with_footage({150, 180, 210})
    got = choose(f, _disc("FLD-02", "REDLINE"), [])
    assert got and got[0]["kind"] == "VIDEO" and got[0]["frame"].bearing_deg == 180      # faces the pipe's bearing; bare-tower frames never qualify
    assert all(c["frame"].equipment > 0 for c in got)


def test_proof_falls_back_to_a_drone_still_when_the_video_never_faces_the_place():
    from scopeiq.engine.proof import Still, choose
    f = _facts_with_footage({0, 30})                                                    # the orbit only reaches the equipment on the north side
    still = Still(Path("beta.jpg"), "Oblique sector view (Beta)", 180.0, True)
    got = choose(f, _disc("FLD-02", "REDLINE"), [still])
    assert [c["kind"] for c in got] == ["IMAGE"] and "does not face this side" in got[0]["why"]
    overview = choose(f, _disc("FLD-02", "REDLINE"), [])                                # nothing faces it at all: an overview, labelled as one
    assert overview and overview[0].get("overview")


def test_a_site_wide_finding_gets_one_clear_view_and_no_footage_means_no_proof():
    from scopeiq.engine.proof import choose
    f = _facts_with_footage({150, 180, 210})
    assert len(choose(f, _disc("FLD-06", "REDLINE", sector=None, position=None), [])) == 1
    assert choose(_facts_with_footage(set()), _disc("FLD-02", "REDLINE"), []) == []


def test_still_direction_comes_from_where_its_camera_stood(tmp_path):
    import json
    from scopeiq.engine.proof import read_stills
    meta = tmp_path / "m.json"
    meta.write_text(json.dumps({"imagery": [{"file": "a.jpg", "type": "Oblique sector view (Beta)", "camera_xyz_m": [0, -18, 59], "look_at_m": [0, 0, 56]},
                                            {"file": "o.jpg", "type": "Orthomosaic (stitched, nadir)"}]}))
    got = read_stills(meta, {"a.jpg": tmp_path / "a.jpg", "o.jpg": tmp_path / "o.jpg"})
    assert len(got) == 1 and got[0].bearing_deg == 180.0 and got[0].sector_view


@pytest.mark.needs_data
def test_every_redline_of_a_site_with_footage_carries_proof(pipeline_results, repo):
    out = get_settings().path("paths.output_dir")
    for sid, res in pipeline_results.items():
        if sid not in SEEDED_SITES or "redline_decision" not in res["summary"]:
            continue
        for r in repo.select("CORE.REDLINE", {"SITE_ID": sid}):
            proof = repo.select("CORE.REDLINE_PROOF", {"REDLINE_ID": r["REDLINE_ID"]})
            assert proof, (sid, r["REDLINE_ID"])
            assert all((out / p["PATH"]).exists() and p["CAPTION"] and p["BASIS"] for p in proof), sid
            if r["DOC_TYPE"] == "CD" and r["PDF_PATH"]:
                assert any(p["KIND"] == "SHEET" for p in proof), (sid, r["REDLINE_ID"])      # the marked sheet is attached too


def test_rfi_wording_shows_plain_numbers_for_a_list_of_measurements(ref):
    import numpy as np
    f = SiteFacts("TXAA0001")
    d = _disc("FLD-03", "RFI", sector=None, position=None, expected=[63.0], found=[np.float64(67.9)])
    _, rfis = draft_redlines_and_rfis(f, [d], ref)
    assert rfis and "67.9 ft rad center vs 63 ft" in rfis[0].question and "np." not in rfis[0].question


def test_site_without_orbit_video_stops_with_missing_data(tmp_path, ref):
    """No drone video means no proof for the redlines: the run stops at ingest and says what to supply, instead of carrying on without it."""
    import shutil

    from scopeiq.common.errors import MissingDataError
    from scopeiq.config import get_settings
    from scopeiq.engine.facts import build_site_facts

    src = next(p for p in get_settings().path("paths.sites_dir").iterdir() if (p / "drone" / "video").is_dir() and any((p / "drone" / "video").iterdir()))
    site = tmp_path / "TXZZ9999"
    shutil.copytree(src, site)
    shutil.rmtree(site / "drone" / "video")
    with pytest.raises(MissingDataError, match="Missing data: no drone orbit video"):
        build_site_facts(site, ref)
