"""BOM revisions as the guide describes them: every generated BOM is a revision, a revision the provider has seen is never changed, a change request ends
in the next revision, each revision keeps who/when/why and its line-by-line difference from the one before, and every edit needs a reason code.
On a database of its own, so no sample data is needed."""
import pytest
from fastapi.testclient import TestClient

from tests.test_api import SP_COMPANIES, login


@pytest.fixture()
def repo(ref):
    from scopeiq.db.repository import SqliteRepository, get_repository, set_repository
    from scopeiq.services.seed import load_reference_tables
    previous = get_repository()
    r = SqliteRepository(":memory:")
    r.init_schema()
    load_reference_tables(r)
    set_repository(r)
    yield r
    set_repository(previous)


@pytest.fixture()
def client(repo):
    from api.main import app
    with TestClient(app) as c:
        yield c


def _lines(repo, site, rev_id, rows):
    """Lines of a run: rows are (key, qty, action)."""
    from scopeiq.common.ids import stable_id
    repo.insert("CORE.BOM_OUTPUT_LINE", [{"LINE_ID": stable_id("BOM", rev_id, i), "RUN_ID": "RUN-1", "SITE_ID": site, "SECTOR": "A", "CATEGORY": "Antenna", "MODEL": k,
                                          "DESCRIPTION": k, "UOM": "EA", "DESIGN_QTY": q, "SPARE_QTY": 0, "TOTAL_QTY": q, "ACTION": a, "UNIT_COST_USD": 10.0,
                                          "TOTAL_COST_USD": 10.0 * q, "CATALOG_KEY": k, "BOM_REV_ID": rev_id, "RULE_ID": "KIT-1"} for i, (k, q, a) in enumerate(rows)])


def _run(repo, site, run_id, rows):
    """What the BOM stage does for one run."""
    from scopeiq.services import bom_revisions as br
    br.clear_draft(repo, site, "scoper1")
    rev = br.register(repo, site, run_id, "scoper1")
    _lines(repo, site, rev["BOM_REV_ID"], rows)
    br.finish(repo, site, rev)
    return repo.get("CORE.BOM_REVISION", BOM_REV_ID=rev["BOM_REV_ID"])


def _site(repo, site, state="IN_SCOPING", company=None):
    repo.insert("CORE.SITE", [{"SITE_ID": site, "SITE_NAME": f"Site {site}", "CX_SP": company, "WORKFLOW_STATE": state, "LAST_RUN_ID": "RUN-1"}])


def _lock(repo, rev_id, status):
    repo.update("CORE.BOM_REVISION", {"STATUS": status, "LOCKED": True}, {"BOM_REV_ID": rev_id})


def test_a_run_refreshes_the_draft_but_never_a_revision_the_provider_has_seen(repo):
    from scopeiq.services import bom_revisions as br
    _site(repo, "TXR0001")
    one = _run(repo, "TXR0001", "RUN-1", [("ANT-1", 2, "Install"), ("RRU-1", 1, "Install")])
    again = _run(repo, "TXR0001", "RUN-2", [("ANT-1", 2, "Install")])
    assert one["BOM_REV_ID"] == again["BOM_REV_ID"] == "TXR0001-REV1" and len(br.generated(repo, "TXR0001")) == 1      # a draft is rebuilt in place
    assert [x["MODEL"] for x in br.lines_of(repo, "TXR0001", again)] == ["ANT-1"]

    _lock(repo, "TXR0001-REV1", "SP_REVIEW")                                            # now the provider has it
    two = _run(repo, "TXR0001", "RUN-3", [("ANT-1", 3, "Install"), ("RRU-1", 1, "Install")])
    assert two["REV_LABEL"] == "REV 2" and two["PARENT_REV_ID"] == "TXR0001-REV1"
    first = br.generated(repo, "TXR0001")[0]
    assert first["STATUS"] == "SP_REVIEW" and [x["MODEL"] for x in br.lines_of(repo, "TXR0001", first)] == ["ANT-1"]       # REV 1 is exactly as it was sent


def test_each_revision_keeps_what_changed_from_the_one_before(repo):
    from scopeiq.services import bom_revisions as br
    _site(repo, "TXR0002")
    _run(repo, "TXR0002", "RUN-1", [("ANT-1", 2, "Install"), ("RRU-1", 1, "Install"), ("OLD-1", 1, "Remove")])
    assert repo.select("CORE.BOM_CHANGE", {"SITE_ID": "TXR0002"}) == []                  # the first revision has nothing before it
    _lock(repo, "TXR0002-REV1", "SP_CHANGES_REQUESTED")
    two = _run(repo, "TXR0002", "RUN-2", [("ANT-1", 4, "Install"), ("OLD-1", 1, "Remove"), ("NEW-1", 2, "Install")])
    diff = {c["CATALOG_KEY"]: (c["FROM_QTY"], c["TO_QTY"], c["DELTA"]) for c in repo.select("CORE.BOM_CHANGE", {"TO_REV_ID": two["BOM_REV_ID"]})}
    assert diff == {"ANT-1": (2, 4, 2), "RRU-1": (1, 0, -1), "NEW-1": (0, 2, 2)}          # changed, removed and added; the unchanged line is not listed
    assert two["TOTALS"]["lines"] == 3 and br.current_revision(repo, "TXR0002")["BOM_REV_ID"] == two["BOM_REV_ID"]


def test_a_site_made_before_revisions_gets_its_rev_1_in_the_state_it_is_in(repo):
    from scopeiq.services import bom_revisions as br
    _site(repo, "TXR0003", "SP_HANDSHAKE")
    repo.insert("CORE.BOM_OUTPUT_LINE", [{"LINE_ID": "OLD1", "RUN_ID": "RUN-1", "SITE_ID": "TXR0003", "MODEL": "ANT-1", "CATALOG_KEY": "ANT-1", "TOTAL_QTY": 1, "ACTION": "Install"}])
    assert [x["LINE_ID"] for x in br.lines_of(repo, "TXR0003", None)] == ["OLD1"]
    rev = br.ensure(repo, "TXR0003", "admin")
    assert rev["REV_LABEL"] == "REV 1" and rev["STATUS"] == "SP_REVIEW" and rev["LOCKED"]   # it was already with the provider
    assert [x["LINE_ID"] for x in br.lines_of(repo, "TXR0003", rev)] == ["OLD1"]
    _run(repo, "TXR0003", "RUN-2", [("ANT-1", 5, "Install")])                              # the next run makes REV 2 and leaves REV 1 alone
    assert [x["TOTAL_QTY"] for x in br.lines_of(repo, "TXR0003", br.generated(repo, "TXR0003")[0])] == [1]


def test_edits_need_a_reason_and_only_a_draft_can_be_edited(client, repo):
    from scopeiq.services import bom_revisions as br
    site = "TXR0004"
    _site(repo, site)
    rev = _run(repo, site, "RUN-1", [("ANT-1", 2, "Install")])
    scoper, reviewer, sp, ae = (login(client, w) for w in ("scoper1", "reviewer1", "sp_prairie", "ae1"))
    line = br.lines_of(repo, site, rev)[0]["LINE_ID"]
    edit = lambda h, **b: client.patch(f"/bom/lines/{line}", json=b, headers=h)

    assert edit(sp, design_qty=9, reason_code="RC-FIELD-COND").status_code == 403 and edit(ae, design_qty=9, reason_code="RC-FIELD-COND").status_code == 403
    assert edit(scoper, design_qty=9, reason_code="RC-NOPE").status_code == 400            # a reason from the list
    assert edit(scoper, design_qty=9).status_code == 400                                   # and a reason is required
    done = edit(scoper, design_qty=3, spare_qty=1, reason_code="RC-FIELD-COND", comment="Drone shows a fourth position")
    assert done.status_code == 200 and done.json()["TOTAL_QTY"] == 4 and done.json()["TOTAL_COST_USD"] == 40.0
    assert done.json()["EDITED_BY"] == "scoper1" and done.json()["REASON_CODE"] == "RC-FIELD-COND" and done.json()["EDITED_AT"]    # who, why and when

    _lock(repo, rev["BOM_REV_ID"], "SP_REVIEW")
    assert edit(scoper, design_qty=1, reason_code="RC-FIELD-COND").status_code in (400, 403, 409)       # sent to the provider: never changed again
    assert br.lines_of(repo, site, rev)[0]["TOTAL_QTY"] == 4


def test_the_next_revision_is_started_from_the_last_and_the_change_is_listed_with_its_reason(client, repo):
    from scopeiq.services import bom_revisions as br
    site = "TXR0005"
    _site(repo, site, "IN_SCOPING")
    rev = _run(repo, site, "RUN-1", [("ANT-1", 2, "Install"), ("RRU-1", 1, "Install")])
    scoper = login(client, "scoper1")
    assert client.post(f"/bom/sites/{site}/next-revision", headers=scoper).json()["BOM_REV_ID"] == rev["BOM_REV_ID"]    # still a draft: nothing new is needed
    _lock(repo, rev["BOM_REV_ID"], "SP_CHANGES_REQUESTED")
    made = client.post(f"/bom/sites/{site}/next-revision", headers=scoper)
    assert made.status_code == 200 and made.json()["REV_LABEL"] == "REV 2" and made.json()["PARENT_REV_ID"] == rev["BOM_REV_ID"]
    new = br.generated(repo, site)[-1]
    lines = br.lines_of(repo, site, new)
    assert sorted(x["MODEL"] for x in lines) == ["ANT-1", "RRU-1"] and not any(x["REASON_CODE"] for x in lines)        # a copy, nothing changed yet
    target = next(x for x in lines if x["MODEL"] == "ANT-1")["LINE_ID"]
    assert client.patch(f"/bom/lines/{target}", json={"design_qty": 5, "reason_code": "RC-SP-REQUEST"}, headers=scoper).status_code == 200
    detail = client.get(f"/sites/{site}/handshake", headers=scoper).json()
    assert detail["selected_rev"] == new["BOM_REV_ID"] and detail["bom_editable"] is True
    change = detail["bom_changes"][0]
    assert (change["model"], change["FROM_QTY"], change["TO_QTY"], change["REASONS"], change["from_rev"]) == ("ANT-1", 2, 5, ["RC-SP-REQUEST"], "REV 1")
    old = client.get(f"/sites/{site}/handshake?rev={rev['BOM_REV_ID']}", headers=scoper).json()                         # the earlier revision is still readable
    assert [x["TOTAL_QTY"] for x in old["bom_lines"] if x["MODEL"] == "ANT-1"] == [2] and old["bom_editable"] is False
    assert [x["label"] for x in old["revisions"]] == ["REV 2", "REV 1"]


def test_a_revision_that_was_sent_cannot_be_sent_again_until_the_next_one_exists(client, repo):
    site = "TXR0006"
    _site(repo, site, "IN_REVIEW", SP_COMPANIES["sp_prairie"])
    rev = _run(repo, site, "RUN-1", [("ANT-1", 2, "Install")])
    reviewer, sp, scoper = login(client, "reviewer1"), login(client, "sp_prairie"), login(client, "scoper1")
    step = lambda h, action, **kw: client.post(f"/workflow/SITE_SCOPING/{site}/transition", json={"action": action, **kw}, headers=h)
    assert step(reviewer, "SUBMIT_TO_SP").status_code == 200
    assert step(sp, "REQUEST_CHANGES", reason_code="RC-SP-REQUEST", comment="Too few antennas").status_code == 200
    assert step(scoper, "SUBMIT_REVIEW").status_code == 400                                # REV 1 was already answered: it cannot go out again as it is
    assert client.get(f"/sites/{site}/handshake", headers=scoper).json()["can_start_next_rev"] is True
    assert client.post(f"/bom/sites/{site}/next-revision", headers=scoper).json()["REV_LABEL"] == "REV 2"
    assert step(scoper, "SUBMIT_REVIEW").status_code == 200 and step(reviewer, "SUBMIT_TO_SP").status_code == 200
    assert step(sp, "AGREE").status_code == 200
    assert step(login(client, "admin"), "APPROVE_FBA").status_code == 200
    detail = client.get(f"/sites/{site}/handshake", headers=login(client, "admin")).json()
    assert detail["selected_rev_status"] == "FBA" and detail["is_fba_locked"] and detail["bom_editable"] is False
    got = client.get(f"/bom/sites/{site}/export", headers=login(client, "admin"))
    assert got.status_code == 200 and "REV2_FBA" in got.headers["content-disposition"]    # the file to upload is the approved revision
    assert rev["BOM_REV_ID"] != detail["selected_rev"]


def test_a_removed_line_keeps_its_reason_in_the_difference_list(client, repo):
    from scopeiq.services import bom_revisions as br
    site = "TXR0007"
    _site(repo, site, "IN_SCOPING")
    rev = _run(repo, site, "RUN-1", [("ANT-1", 2, "Install"), ("RRU-1", 1, "Install")])
    _lock(repo, rev["BOM_REV_ID"], "SP_CHANGES_REQUESTED")
    scoper = login(client, "scoper1")
    client.post(f"/bom/sites/{site}/next-revision", headers=scoper)
    gone = next(x for x in br.lines_of(repo, site, br.generated(repo, site)[-1]) if x["MODEL"] == "RRU-1")["LINE_ID"]
    assert client.delete(f"/bom/lines/{gone}?reason_code=RC-NOPE", headers=scoper).status_code == 400
    assert client.delete(f"/bom/lines/{gone}?reason_code=RC-SP-REQUEST", headers=scoper).status_code == 200
    change = client.get(f"/sites/{site}/handshake", headers=scoper).json()["bom_changes"][0]
    assert (change["model"], change["FROM_QTY"], change["TO_QTY"], change["REASONS"]) == ("RRU-1", 1, 0, ["RC-SP-REQUEST"])
