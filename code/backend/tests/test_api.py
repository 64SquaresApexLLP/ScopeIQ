"""API smoke tests over the real pipeline output: login per persona, scoping, workflow guards, BOM immutability."""
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.needs_data


@pytest.fixture(scope="module")
def api_results(ref):
    """A separate database for the API tests, so their edits and transitions never touch the answer-key checks."""
    from scopeiq.common.context import bind
    from scopeiq.db.repository import SqliteRepository, get_repository, set_repository
    from scopeiq.services.pipeline import PipelineService
    from scopeiq.services.seed import load_reference_tables
    previous = get_repository()
    r = SqliteRepository(":memory:")
    r.init_schema()
    load_reference_tables(r)
    set_repository(r)
    svc = PipelineService(r, ref)
    with bind(user_id="system", role="SYSTEM"):
        yield {sid: svc.run_site(sid) for sid in svc.site_ids()}
    set_repository(previous)


@pytest.fixture(scope="module")
def client(api_results):
    from api.main import app
    with TestClient(app) as c:
        yield c


def login(client, user_id):
    r = client.post("/auth/login", json={"user_id": user_id, "password": "demo"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health_and_auth(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/sites").status_code == 401
    assert client.get("/sites").json()["error"]["code"] == "SIQ-AUTH-401"
    users = client.get("/auth/users").json()
    assert {u["role"] for u in users} >= {"SCOPER", "REVIEWER", "CX_SP", "ERICSSON", "ADMIN"}


def test_sites_and_detail(client, api_results):
    h = login(client, "scoper1")
    sites = client.get("/sites", headers=h).json()
    assert {s["SITE_ID"] for s in sites} == set(api_results)
    sid = sorted(api_results)[0]
    d = client.get(f"/sites/{sid}", headers=h).json()
    assert d["site"]["SITE_ID"] == sid and d["delta"] and d["documents"]
    assert client.get("/sites/dashboard", headers=h).json()["discrepancies"]["total"] > 0
    est = client.get(f"/sites/{sid}/estimate", headers=h).json()
    assert est["estimate"]["TOTAL_USD"] > 0


def test_cx_sp_sees_only_own_sites(client):
    h = login(client, "sp_prairie")
    sites = client.get("/sites", headers=h).json()
    assert sites and all(s["CX_SP"].startswith("Prairie") for s in sites)


def test_discrepancy_workflow(client):
    h = login(client, "scoper1")
    d = next(x for x in client.get("/discrepancies?status=OPEN", headers=h).json() if "DISMISS" in x["ACTIONS"])
    # dismiss needs a reason and a comment
    r = client.post(f"/discrepancies/{d['DISC_ID']}/transition", json={"action": "DISMISS"}, headers=h)
    assert r.status_code == 400 and "reason" in r.json()["error"]["message"]
    r = client.post(f"/discrepancies/{d['DISC_ID']}/transition", json={"action": "CONFIRM"}, headers=h)
    assert r.status_code == 200 and r.json()["to_state"] == "CONFIRMED"
    # a CX SP cannot act on discrepancies
    assert client.post(f"/discrepancies/{d['DISC_ID']}/transition", json={"action": "RAISE_RFI"},
                       headers=login(client, "sp_prairie")).status_code == 403
    client.post(f"/discrepancies/{d['DISC_ID']}/comments", json={"text": "checked against photos"}, headers=h)
    full = client.get(f"/discrepancies/{d['DISC_ID']}", headers=h).json()
    assert full["HISTORY"][-1]["TO_STATE"] == "CONFIRMED" and full["COMMENTS"]
    audit = client.get(f"/audit?entity_id={d['DISC_ID']}", headers=login(client, "reviewer1")).json()
    assert any(a["ACTION"] == "TRANSITION" for a in audit)


def test_bom_edit_then_lock(client, api_results):
    h, rv = login(client, "scoper1"), login(client, "reviewer1")
    sid = sorted(api_results)[0]
    revs = client.get(f"/bom/sites/{sid}/revisions", headers=h).json()
    rev0 = next(r for r in revs if r["KIND"] == "TOOL_REV0")
    rev1 = next(r for r in revs if r["KIND"] == "GENERATED")
    line = client.get(f"/bom/revisions/{rev1['BOM_REV_ID']}/lines", headers=h).json()[0]
    # REV 0 (the tool export) is locked
    l0 = client.get(f"/bom/revisions/{rev0['BOM_REV_ID']}/lines", headers=h).json()[0]
    assert client.patch(f"/bom/lines/{l0['LINE_ID']}", json={"spare_qty": 1, "reason_code": "RC-FIELD-COND"}, headers=h).status_code == 409
    r = client.patch(f"/bom/lines/{line['LINE_ID']}", json={"spare_qty": 1, "reason_code": "RC-FIELD-COND", "comment": "spare"}, headers=h)
    assert r.status_code == 200 and r.json()["SPARE_QTY"] == 1
    assert client.post(f"/bom/revisions/{rev1['BOM_REV_ID']}/transition", json={"action": "SUBMIT_REVIEW"}, headers=h).status_code == 200
    assert client.post(f"/bom/revisions/{rev1['BOM_REV_ID']}/transition", json={"action": "APPROVE"}, headers=rv).status_code == 200
    r = client.patch(f"/bom/lines/{line['LINE_ID']}", json={"spare_qty": 2, "reason_code": "RC-FIELD-COND"}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "SIQ-LOCK-409"
    x = client.get(f"/bom/revisions/{rev1['BOM_REV_ID']}/export", headers=h)
    assert x.status_code == 200 and x.content[:2] == b"PK"


def test_files_and_reference(client, api_results):
    h = login(client, "scoper1")
    red = client.get("/redlines", headers=h).json()
    pdf = next(x["PDF_URL"] for x in red if x["PDF_URL"])
    assert client.get(pdf).content[:4] == b"%PDF"
    assert len(client.get("/reference/material_catalog", headers=h).json()) > 10
    assert client.get("/logs/errors", headers=h).status_code == 403
    assert client.get("/workflow/inbox", headers=login(client, "reviewer1")).status_code == 200


def test_upload_validation(client, api_results):
    h = login(client, "scoper1")
    sid = sorted(api_results)[0]
    r = client.post(f"/sites/{sid}/documents/upload", data={"doc_type": "CD"}, files={"file": ("notes.txt", b"x")}, headers=h)
    assert r.status_code == 400
