"""Unit tests for the reusable building blocks."""
from __future__ import annotations

import pytest

from scopeiq.common.errors import PermissionDenied, ValidationError, WorkflowError
from scopeiq.reference.expressions import evaluate


def test_expressions_are_safe():
    assert evaluate("ceil(powered_new / 6)", {"powered_new": 7}) == 2
    assert evaluate("3 if trunk_length_ft > 200 else 2", {"trunk_length_ft": 250}) == 3
    with pytest.raises(Exception):
        evaluate("__import__('os').system('echo hi')", {})


def test_catalog_resolves_ocr_text(ref):
    item, score = ref.catalog.resolve("Nnh4-65B-R6", kinds=("passive",))
    assert item.key == "NNH4" and score > 0.8
    item, _ = ref.catalog.resolve("RADIO 2217 B6GA", kinds=("radio",), cutoff=0.6)
    assert item.key == "R2217"


def test_trunk_step(ref):
    from scopeiq.engine.bom import trunk_plan
    from scopeiq.engine.design import Device, SiteModel
    m = SiteModel("FINAL", "X", False, "R3", devices=[Device("A", 1, "AIR6449", "air", "New", 190, "RFDS")] * 7)
    m.vertical_ft, m.horizontal_ft, m.horizontal_basis = 195, 80, "FIELD"
    tp = trunk_plan(m, ref)
    assert tp["count"] == 2 and tp["length_ft"] == 350 and tp["required_ft"] == 302.5


def test_missing_route_is_never_assumed(ref):
    from scopeiq.engine.bom import trunk_plan
    from scopeiq.engine.design import Device, SiteModel
    m = SiteModel("FINAL", "X", False, "R3", devices=[Device("A", 1, "R4449", "radio", "New", 100, "RFDS")])
    m.vertical_ft = 105
    tp = trunk_plan(m, ref)
    assert tp["held"] and "never assumed" in tp["reason"]


def test_workflow_enforces_roles_and_reasons(repo, ref):
    from scopeiq.common.context import bind
    from scopeiq.workflow.engine import WorkflowEngine
    repo.upsert("CORE.DISCREPANCY", [{"DISC_ID": "D-T1", "SITE_ID": "S1", "STATUS": "OPEN"}])
    wf = WorkflowEngine(ref, repo)
    with bind(user_id="sp_prairie", role="CX_SP"):
        with pytest.raises(PermissionDenied):
            wf.transition("DISCREPANCY", "D-T1", "CONFIRM")
    with bind(user_id="scoper1", role="SCOPER"):
        with pytest.raises(ValidationError):
            wf.transition("DISCREPANCY", "D-T1", "DISMISS")              # needs reason + comment
        with pytest.raises(WorkflowError):
            wf.transition("DISCREPANCY", "D-T1", "RESOLVE")              # not allowed from OPEN
        out = wf.transition("DISCREPANCY", "D-T1", "CONFIRM")
        assert out["to_state"] == "CONFIRMED"
    assert repo.get("CORE.DISCREPANCY", DISC_ID="D-T1")["STATUS"] == "CONFIRMED"
    assert wf.history("DISCREPANCY", "D-T1")[0]["ACTOR_USER_ID"] == "scoper1"


def test_audit_requires_reason_for_human_edits(repo):
    from scopeiq.common.audit import AuditTrail
    from scopeiq.common.context import bind
    with bind(user_id="scoper1", role="SCOPER"):
        with pytest.raises(ValidationError):
            AuditTrail.record(entity_type="BOM_LINE", entity_id="x", action="EDIT_QTY")


def test_logging_levels_follow_environment():
    from scopeiq.config import get_settings
    assert get_settings().env == "test"
    import yaml
    from pathlib import Path
    cfg = Path(__file__).resolve().parents[1] / "scopeiq" / "config"
    prod = yaml.safe_load((cfg / "prod.yaml").read_text())
    dev = yaml.safe_load((cfg / "dev.yaml").read_text())
    assert prod["logging"]["level"] == "WARNING" and dev["logging"]["level"] == "DEBUG"
    assert prod["logging"]["log_payloads"] is False and dev["logging"]["log_payloads"] is True


def test_drone_objects_are_identified_from_the_material_catalog(ref):
    from scopeiq.domain import FieldObject
    from scopeiq.extract.drone import identify_object
    cat = ref.catalog
    ant = FieldObject("O1", "Antenna", "A", 0.0, 0.0, 145.0, (71.7, 20.6, 8.2), "", 0.95)          # inches: height, width, depth
    got = identify_object(ant, cat)
    assert got["catalog_key"] == "NNH4" and got["basis"] == "Size match" and got["mfr_pn"] and got["manufacturer"]
    labelled = FieldObject("O2", "Antenna", "A", 0.0, 0.0, 145.0, (71.7, 20.6, 8.2), "APXVSPP18-C-A20", 0.95)
    assert identify_object(labelled, cat)["basis"] == "Vendor label"                                  # the vendor's own label wins over size
    pipe = identify_object(FieldObject("O3", "Mount pipe", "A", 0.0, None, 145.0, (94.6, 3.8, 3.1), "", 0.9), cat)
    assert pipe["catalog_key"] == "PIPE" and pipe["basis"] == "Object type"
    assert identify_object(FieldObject("O4", "Cable route", None, None, None, None, None, "", 0.9, route_length_ft=30), cat) is None
    assert identify_object(FieldObject("O5", "Antenna", "A", 0.0, 0.0, 145.0, (400.0, 90.0, 60.0), "", 0.9), cat)["catalog_key"] is None   # nothing that size
