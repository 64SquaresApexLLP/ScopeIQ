"""What an A&E engineer may reach, over the API, on a database of its own: the sites that have redlines or RFIs for the firm (with counts), those
redlines and RFIs, and CD / SA-MA documents. Nothing of the scoping workbench."""
import pytest
from fastapi.testclient import TestClient

from tests.test_api import login


@pytest.fixture(scope="module")
def client(ref):
    from api.main import app
    from scopeiq.db.repository import SqliteRepository, get_repository, set_repository
    from scopeiq.services.seed import load_reference_tables
    previous = get_repository()
    r = SqliteRepository(":memory:")
    r.init_schema()
    load_reference_tables(r)
    set_repository(r)
    with TestClient(app) as c:
        yield c
    set_repository(previous)


def _world():
    """TXAE0001: a finished run, an open and a completed redline, an RFI to the firm (sent), an RFI draft, and an RFI for Admin.
    TXAE0002: a finished run with an RFI for Admin only. TXAE0003: a redline but no finished run."""
    from scopeiq.db.repository import get_repository, now_iso
    r = get_repository()
    site = lambda i, **kw: {"SITE_ID": i, "SITE_NAME": f"Site {i}", "CITY": "Dallas", "STATE": "TX", "STRUCTURE_TYPE": "Monopole", "STREAM": "BOM",
                            "WORKFLOW_STATE": "IN_SCOPING", "CX_SP": "Acme Towers", "PROJECT_NAME": "Secret project", **kw}
    r.insert("CORE.SITE", [site("TXAE0001"), site("TXAE0002"), site("TXAE0003")])
    run = lambda i: {"RUN_ID": f"RUN-{i}", "SITE_ID": i, "STARTED_AT": now_iso(), "STATUS": "SUCCEEDED"}
    r.insert("CORE.PIPELINE_RUN", [run("TXAE0001"), run("TXAE0002")])
    red = lambda i, site_id, status: {"REDLINE_ID": i, "SITE_ID": site_id, "STATUS": status, "DOC_TYPE": "CD", "SHEET": "A-3"}
    r.insert("CORE.REDLINE", [red("RL-1", "TXAE0001", "WORK_QUEUE"), red("RL-2", "TXAE0001", "COMPLETED"), red("RL-3", "TXAE0003", "WORK_QUEUE")])
    rfi = lambda i, site_id, to, status: {"RFI_ID": i, "SITE_ID": site_id, "TO_PARTY": to, "STATUS": status, "SUBJECT": f"Subject {i}", "QUESTION": "?"}
    r.insert("CORE.RFI", [rfi("RFI-1", "TXAE0001", "AE_ENGINEER", "IN_REVIEW"), rfi("RFI-2", "TXAE0001", "AE_ENGINEER", "DRAFT"),
                          rfi("RFI-3", "TXAE0001", "ADMIN", "SUBMITTED"), rfi("RFI-4", "TXAE0002", "ADMIN", "SUBMITTED")])
    doc = lambda i, t: {"DOC_ID": f"DOC-{i}", "SITE_ID": "TXAE0001", "DOC_TYPE": t, "FILE_NAME": f"TXAE0001_{i}.pdf", "REL_PATH": f"sites/TXAE0001/{i}.pdf",
                        "FILE_FORMAT": "PDF", "REVISION": "REV 1", "REVISION_RANK": 1, "STATUS": "CURRENT"}
    r.insert("CORE.DOCUMENT", [doc("cd", "CD"), doc("masa", "MA_SA"), doc("rfds", "RFDS"), doc("bom", "BOM_REV0")])


def test_an_ae_engineer_gets_a_sites_list_of_its_own_work_and_nothing_else(client):
    _world()
    ae, admin = login(client, "ae1"), login(client, "admin")
    sites = {s["SITE_ID"]: s for s in client.get("/sites", headers=ae).json()}
    assert set(sites) == {"TXAE0001"}                                                    # a site with only an Admin RFI, or no finished run, is not its work
    s = sites["TXAE0001"]
    assert (s["REDLINES"], s["OPEN_REDLINES"], s["RFIS"], s["OPEN_RFIS"]) == (2, 1, 1, 1)    # open = not completed / answered; drafts and Admin RFIs do not count
    assert {"SITE_ID", "SITE_NAME", "CITY", "STATE", "STRUCTURE_TYPE"} <= set(s)
    assert not {"STREAM", "WORKFLOW_STATE", "CX_SP", "PROJECT_NAME", "OPEN_DISCREPANCIES", "DOC_COUNT", "ACTIONS"} & set(s)
    assert {x["SITE_ID"] for x in client.get("/sites", headers=admin).json()} >= {"TXAE0001", "TXAE0002", "TXAE0003"}     # the scoping team still sees every site

    detail = client.get("/sites/TXAE0001", headers=ae).json()                           # opening a site: the site, no documents, no scoping state
    assert detail["documents"] == [] and detail["revision_check"] is None and detail["last_run"] == []
    assert not {"STREAM", "WORKFLOW_STATE", "CX_SP", "PROJECT_NAME"} & set(detail["site"])
    assert client.get("/sites/dashboard", headers=ae).json() == {"sites": 3}              # no pipeline, finding or estimate counts


def test_an_ae_engineer_sees_its_redlines_and_the_rfis_addressed_to_the_firm(client):
    ae, admin = login(client, "ae1"), login(client, "admin")
    assert sorted(x["REDLINE_ID"] for x in client.get("/redlines?site_id=TXAE0001", headers=ae).json()) == ["RL-1", "RL-2"]
    assert [x["RFI_ID"] for x in client.get("/rfis", headers=ae).json()] == ["RFI-1"]      # not the Admin RFIs, not the unsent draft
    assert {x["RFI_ID"] for x in client.get("/rfis", headers=admin).json()} >= {"RFI-1", "RFI-3", "RFI-4"}


def test_an_ae_engineer_is_kept_out_of_the_scoping_workbench_and_other_files(client):
    ae, admin = login(client, "ae1"), login(client, "admin")
    for path in ("/sites/TXAE0001/handshake", "/sites/TXAE0001/delta", "/sites/TXAE0001/estimate", "/pipeline/runs", "/discrepancies", "/bom/revisions",
                 "/reference/rate_card", "/workflow/SITE_SCOPING/TXAE0001/history", "/sites/service-providers", "/sites/TXAE0001/provider"):
        assert client.get(path, headers=ae).status_code == 403, path
    assert client.post("/pipeline/sites/TXAE0001/start", headers=ae).status_code == 403
    assert client.get("/redlines", headers=ae).status_code == 200 and client.get("/rfis", headers=ae).status_code == 200      # its own work still opens

    docs = {d["DOC_TYPE"] for d in client.get("/sites/TXAE0001/documents", headers=ae).json()["documents"]}
    assert docs == {"CD", "MA_SA"}                                                         # the drawings and analyses it works on, not the RFDS or the BOM
    assert {d["DOC_TYPE"] for d in client.get("/sites/TXAE0001/documents", headers=admin).json()["documents"]} == {"CD", "MA_SA", "RFDS", "BOM_REV0"}
    ok = lambda doc_id: client.get(f"/documents/{doc_id}/preview", headers=ae).status_code
    assert ok("DOC-rfds") == 403 and ok("DOC-bom") == 403 and ok("DOC-cd") != 403 and ok("DOC-masa") != 403
