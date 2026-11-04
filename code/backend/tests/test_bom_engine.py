"""BOM engine: it reads the rules from the Excel files, works for any site, reports what it cannot do instead of failing, and builds every
result fresh. None of these tests needs the sample sites: the designs are built here, and the Excel files are copied and edited."""
import shutil
from pathlib import Path

import openpyxl
import pytest

from scopeiq.bom.design_stage import design_items, read_design_documents
from scopeiq.bom.engine import generate
from scopeiq.bom.rulebook import RulebookError, interpret_quantity, interpret_trigger, load_rulebook
from scopeiq.common.errors import ExtractionError, MissingDataError
from scopeiq.config import get_settings
from scopeiq.domain import Document, SiteFacts, SourceRef
from scopeiq.engine.design import Device, SiteModel


@pytest.fixture()
def xlsx(tmp_path):
    """Editable copies of the two Excel files."""
    src = Path(get_settings().path("paths.reference_xlsx_dir"))
    for n in ("bom_rules.xlsx", "material_catalog.xlsx"):
        shutil.copy(src / n, tmp_path / n)
    return tmp_path


def _book(xlsx, name="bom_rules.xlsx"):
    return openpyxl.load_workbook(xlsx / name)


def _rulebook(xlsx):
    return load_rulebook(xlsx / "bom_rules.xlsx", xlsx / "material_catalog.xlsx")


def _site(site_id="TXNEW0001", *, rooftop=False, horizontal=120, devices=None, **kw):
    m = SiteModel("FINAL", site_id, rooftop, "R3", market="DFW")
    m.devices = devices if devices is not None else [Device("A", 1, "R4449", "radio", "New", 110, "RFDS", SourceRef("d", "RFDS", "R3", "Final Config")),
                                                       Device("A", 1, "NNH4", "passive", "New", 110, "RFDS", SourceRef("d", "RFDS", "R3", "Final Config"))]
    m.horizontal_ft, m.horizontal_basis = horizontal, "CD"
    m.refs["trunk"] = SourceRef("c", "CD", "REV 1", "A-4")
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def _qty(res, key, rule=None):
    return sum(l.total_qty for l in res.lines if l.catalog_key == key and (rule is None or l.rule_id == rule))


# ------------------------------------------------------------------------------------------------ the Excel files are read
def test_every_rule_of_the_real_workbook_is_understood():
    rb = load_rulebook()
    assert len(rb.rules) == 41 and all(r.applied for r in rb.rules), [(r.rule_id, r.problem) for r in rb.rules if not r.applied]
    assert rb.length_factor == 1.10 and rb.tower_margin_ft == 5 and [k for _, k in rb.trunk_steps][0] == "HYB100"
    assert len(rb.catalog.items) == 49 and not rb.issues


@pytest.mark.parametrize("text,expr,spare", [("1 per radio", "1", "0"), ("2 per site (+1 spare)", "2", "1"), ("+1 spare per site", "0", "1"),
                                              ("ports per radio", "ports", "0"), ("per MA", "ma_qty", "0"),
                                              ("ceil(devices / 6) trunks", "ceil(powered_new / 6)", "0"),
                                              ("3 per trunk if length > 200 ft, else 2", "3 if trunk_length_ft > 200 else 2", "0"),
                                              ("ceil(max(0, added W - removed W) / 3000)", "ceil(max(0, added_w - removed_w) / 3000)", "0")])
def test_quantity_text_is_turned_into_an_expression(text, expr, spare):
    assert interpret_quantity(text) == (expr, spare, "")


def test_text_that_is_not_understood_is_reported_not_guessed():
    assert interpret_quantity("as needed")[0] is None and interpret_quantity("ceil(widgets / 4)")[0] is None
    assert interpret_trigger("When the customer asks nicely") is None and interpret_trigger("New remote radio") == "NEW_RADIO"


# ------------------------------------------------------------------------------------------------ it follows the Excel files
def test_changing_a_quantity_in_the_excel_changes_the_bom(xlsx):
    base = generate(_site(), _rulebook(xlsx))
    wb = _book(xlsx)
    ws = wb["BOM Rules"]
    row = next(r for r in ws.iter_rows(min_row=2) if r[0].value == "R-RAD-04")
    row[3].value = "3 per radio"
    wb.save(xlsx / "bom_rules.xlsx")
    changed = generate(_site(), _rulebook(xlsx))
    assert _qty(base, "SFP10") == 2 and _qty(changed, "SFP10") == 3
    assert base.revision != changed.revision                  # every line says which version of the rules made it


def test_a_new_rule_and_a_new_catalog_item_work_without_code_changes(xlsx):
    wb = _book(xlsx, "material_catalog.xlsx")
    ws = wb.active
    hdr = [c.value for c in ws[1]]
    new = {"Catalog Key": "LIGHTNING", "Category": "Ancillary", "Subcategory": "Consumables", "Manufacturer": "Acme", "Model": "LR-1",
           "Manufacturer P/N": "ACM-LR1", "Customer P/N": "CA-000001", "Description": "Lightning rod kit", "UOM": "KIT", "Supply (CFM/VFM)": "VFM",
           "Customer Approved": "Y", "Unit Cost (USD)": 99}
    ws.insert_rows(ws.max_row - 1)                           # above the note under the table
    for j, h in enumerate(hdr):
        ws.cell(row=ws.max_row - 2, column=j + 1, value=new.get(h))
    wb.save(xlsx / "material_catalog.xlsx")
    wb = _book(xlsx)
    wb["BOM Rules"].append(["R-NEW-01", "New remote radio", "LIGHTNING", "2 per radio", "added by the team"])
    wb.save(xlsx / "bom_rules.xlsx")
    res = generate(_site(), _rulebook(xlsx))
    assert _qty(res, "LIGHTNING", "R-NEW-01") == 2 and not res.issues


def test_a_rule_the_engine_cannot_read_is_reported_and_the_rest_still_works(xlsx):
    wb = _book(xlsx)
    wb["BOM Rules"].append(["R-ODD-01", "Whenever the moon is full", "GK6", "1 per radio", ""])
    wb["BOM Rules"].append(["R-ODD-02", "New remote radio", "GK6", "a handful", ""])
    wb["BOM Rules"].append(["R-ODD-03", "New remote radio", "NOT-A-PART", "1 per radio", ""])
    wb.save(xlsx / "bom_rules.xlsx")
    res = generate(_site(), _rulebook(xlsx))
    codes = {(i.code, i.rule_id) for i in res.issues}
    assert {("RULE_NOT_APPLIED", "R-ODD-01"), ("RULE_NOT_APPLIED", "R-ODD-02"), ("RULE_CHILD_UNKNOWN", "R-ODD-03")} <= codes
    assert _qty(res, "SFP10") == 2 and res.lines                    # the other rules are unaffected


def test_a_missing_note_holds_the_trunks_instead_of_assuming_a_length(xlsx):
    wb = _book(xlsx)
    ws = wb["Trunk Lengths"]
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and "Required length" in c.value:
                c.value = None
    wb.save(xlsx / "bom_rules.xlsx")
    res = generate(_site(), _rulebook(xlsx))
    assert res.trunk["held"] and not any(l.catalog_key.startswith("HYB") for l in res.lines)
    assert any(i.code in ("NO_LENGTH_FACTOR", "TRUNK_HELD") for i in res.issues)


def test_a_missing_file_stops_the_stage_with_a_clear_message(tmp_path):
    with pytest.raises(RulebookError, match="not found"):
        load_rulebook(tmp_path / "bom_rules.xlsx", tmp_path / "material_catalog.xlsx")


# ------------------------------------------------------------------------------------------------ any site
def test_different_sites_give_different_boms_from_their_own_data():
    rb = load_rulebook()
    small = generate(_site("TXAAA0001"), rb)
    big = generate(_site("TXBBB0002", horizontal=60, devices=[
        Device(s, p, k, kind, "New", 120, "RFDS", SourceRef("d", "RFDS", "R4", "Final Config")) for s in "ABC" for p in (1, 2)
        for k, kind in (("R4460", "radio"), ("AIR6449", "air"))] + [Device("A", 3, "R2217", "radio", "Remove", 100, "RFDS", None)]), rb)
    assert {l.site_id for l in small.lines} == {"TXAAA0001"} and {l.site_id for l in big.lines} == {"TXBBB0002"}
    assert _qty(big, "R4460", "R-EQ-01") == 6 and _qty(small, "R4460", "R-EQ-01") == 0
    assert big.trunk["count"] == 2 and small.trunk["count"] == 1               # ceil(12 / 6) and ceil(1 / 6), from the rule text
    assert any(l.action == "Remove" and l.catalog_key == "R2217" for l in big.lines)
    assert generate(_site("TXAAA0001"), rb).lines == small.lines                # the same input gives the same result, every time


def test_towers_and_rooftops_size_the_trunk_differently():
    rb = load_rulebook()
    tower = generate(_site(rooftop=False, horizontal=100), rb)
    roof = generate(_site(rooftop=True, horizontal=100, vertical_ft=30), rb)
    assert tower.trunk["vertical_ft"] == 115                                    # highest new rad center (110) + the margin in the Excel note (5)
    assert roof.trunk["vertical_ft"] == 30 and roof.trunk["length_ft"] < tower.trunk["length_ft"]


def test_a_model_that_is_not_in_the_catalog_is_listed_for_review_never_dropped():
    rb = load_rulebook()
    unknown = Device("B", 1, None, "unknown", "New", 100, "RFDS", SourceRef("d", "RFDS", "R3", "Final Config"), None, "Radio 9999 X1")
    res = generate(_site(devices=_site().devices + [unknown]), rb)
    line = next(l for l in res.lines if l.model == "Radio 9999 X1")
    assert line.status.startswith("Review") and line.action == "Install"
    assert any(i.code == "MODEL_NOT_IN_CATALOG" for i in res.issues)
    assert _qty(res, "R4449") > 0                                                # the other equipment is unaffected


def test_an_undocumented_route_holds_the_trunks_and_says_so():
    res = generate(_site(horizontal=None), load_rulebook())
    assert res.trunk["held"] and "Route length not documented" in res.trunk["reason"]
    assert not any(l.catalog_key.startswith("HYB") for l in res.lines) and any(i.code == "TRUNK_HELD" for i in res.issues)


def test_the_engine_does_not_raise_on_an_empty_or_odd_design():
    rb = load_rulebook()
    assert generate(_site(devices=[]), rb).lines                                 # only the per-site items
    odd = Device("Z", None, None, "unknown", "Remove", None, "RFDS", None, None, "??")
    assert generate(_site(devices=[odd]), rb).issues


def test_source_and_drawing_come_from_where_the_facts_were_read():
    res = generate(_site(), load_rulebook())
    radio = next(l for l in res.lines if l.rule_id == "R-RAD-01")
    assert radio.source == "RFDS R3" and radio.drawing == "Final Config"
    hanger = next(l for l in res.lines if l.rule_id == "R-TRK-04")
    assert hanger.source == "CD REV 1" and hanger.drawing == "A-4"
    assert next(l for l in res.lines if l.rule_id == "R-SITE-02").source == "Rule only (no document)"   # no document behind it, and it says so


def test_design_items_carry_the_requested_fields_from_the_catalog():
    rb = load_rulebook()
    rows = design_items(_site(), rb, "RUN-X")
    radio = next(r for r in rows if r["CATALOG_KEY"] == "R4449")
    assert (radio["MANUFACTURER"], radio["MODEL"], radio["MANUFACTURER_PN"], radio["CUSTOMER_PN"], radio["UOM"], radio["SUPPLY"], radio["BAND"],
            radio["TECHNOLOGY"], radio["MARKET"], radio["SOURCE"], radio["DRAWING"]) == \
        ("Ericsson", "Radio 4449 B5 B12", "KRC 909 201/1", "CA-987285", "EA", "CFM", "B5/B12", "LTE/NR", "DFW", "RFDS R3", "Final Config")


# ------------------------------------------------------------------------------------------------ stage 5 stops when it cannot read
def _facts(tmp_path, docs):
    f = SiteFacts("TXNEW0001")
    for i, (dt, name, data) in enumerate(docs):
        p = tmp_path / name
        p.write_bytes(data)
        f.documents.append(Document(f"DOC-{i}", f.site_id, dt, name, name, Path(name).suffix.lstrip(".").upper(), "R3", 3, "h", len(data), status="CURRENT"))
        f.site.setdefault("doc_paths", {})[f"DOC-{i}"] = str(p)
    return f


def test_stage_5_stops_when_the_rfds_is_missing(tmp_path):
    with pytest.raises(MissingDataError, match="RFDS"):
        read_design_documents(_facts(tmp_path, []), load_rulebook().catalog, ["RFDS"])


def test_stage_5_stops_when_the_rfds_cannot_be_read(tmp_path):
    with pytest.raises(ExtractionError):
        read_design_documents(_facts(tmp_path, [("RFDS", "TXNEW0001_RFDS_R3.xlsx", b"not a workbook")]), load_rulebook().catalog, ["RFDS"])
    with pytest.raises(ExtractionError, match="not supported"):
        read_design_documents(_facts(tmp_path, [("RFDS", "TXNEW0001_RFDS_R3.docx", b"x")]), load_rulebook().catalog, ["RFDS"])


def test_stage_5_stops_when_an_ma_sa_report_exists_but_cannot_be_read(tmp_path):
    with pytest.raises(ExtractionError):
        read_design_documents(_facts(tmp_path, [("MA_SA", "TXNEW0001_MA_SA_R0.pdf", b"%PDF-broken")]), load_rulebook().catalog, [])


# ------------------------------------------------------------------------------------------------ nothing old is shown
def test_a_new_run_removes_the_design_and_bom_of_the_earlier_run(repo, ref, tmp_path):
    from scopeiq.services.pipeline import PipelineService

    svc = PipelineService(repo, ref)
    svc.output_dir = tmp_path
    repo.insert("CORE.DESIGN_ITEM", [{"ITEM_ID": "DSN-OLD", "RUN_ID": "RUN-OLD", "SITE_ID": "TXOLD0001", "MODEL": "old"}])
    repo.insert("CORE.BOM_OUTPUT_LINE", [{"LINE_ID": "BOM-OLD", "RUN_ID": "RUN-OLD", "SITE_ID": "TXOLD0001", "MODEL": "old"}])
    (tmp_path / "sites" / "TXOLD0001" / "bom").mkdir(parents=True)
    (tmp_path / "sites" / "TXOLD0001" / "bom" / "old.xlsx").write_text("x")
    svc._clear_design_outputs("TXOLD0001")
    assert not repo.select("CORE.DESIGN_ITEM", {"SITE_ID": "TXOLD0001"}) and not repo.select("CORE.BOM_OUTPUT_LINE", {"SITE_ID": "TXOLD0001"})
    assert not (tmp_path / "sites" / "TXOLD0001" / "bom").exists()


def test_stages_5_and_6_are_part_of_the_run_and_can_be_skipped():
    from scopeiq.services.pipeline import STEP_DEFS, RunProgress

    assert [k for k, _ in STEP_DEFS][-3:] == ["REDLINES", "DESIGN", "BOM"]
    steps = RunProgress.initial()
    assert [s["key"] for s in steps][-2:] == ["DESIGN", "BOM"]
