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


@pytest.fixture(scope="module", autouse=True)
def no_issued_drawings_left_behind():
    """INCORPORATE issues a revised CD into <output>/uploads, where the next pipeline run would read it as the site's
    current drawing. These tests share the output folder with the acceptance tests, so remove it afterwards."""
    yield
    import shutil
    from scopeiq.config import get_settings
    shutil.rmtree(get_settings().path("paths.upload_dir"), ignore_errors=True)


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


# ------------------------------------------------------------------------------------ pipeline progress and implement changes
import time


def wait_done(client, h, run_id, timeout=420):
    """Poll a run the way the app does until it is no longer RUNNING."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        run = client.get(f"/pipeline/runs/{run_id}", headers=h).json()
        if run["STATUS"] != "RUNNING":
            return run
        time.sleep(1)
    raise AssertionError(f"run {run_id} still RUNNING after {timeout}s")


def test_every_step_is_recorded_and_readable(client, api_results):
    h = login(client, "scoper1")
    sid = sorted(api_results)[0]
    run = client.get(f"/pipeline/sites/{sid}/latest", headers=h).json()
    steps = run["STEPS"]
    assert [s["key"] for s in steps] == ["INGEST", "EXTRACT", "RECONCILE", "DELTA", "GENERATE", "ESTIMATE", "REDLINES", "PERSIST", "FILES"]
    assert all(s["status"] == "DONE" and s["message"] and s["duration_ms"] is not None for s in steps)
    for s in steps:
        r = client.get(f"/pipeline/runs/{run['RUN_ID']}/steps/{s['key']}", headers=h)
        assert r.status_code == 200, (s["key"], r.text)
    assert client.get(f"/pipeline/runs/{run['RUN_ID']}/steps/NOPE", headers=h).status_code == 404
    recon = client.get(f"/pipeline/runs/{run['RUN_ID']}/steps/RECONCILE", headers=h).json()["discrepancies"]
    assert recon and {d["SITE_ID"] for d in recon} == {sid} and len(recon) == run["SUMMARY"]["discrepancies"]


def test_progress_is_scoped_to_the_service_provider(client, api_results):
    sp = login(client, "sp_prairie")
    own = {s["SITE_ID"] for s in client.get("/sites", headers=sp).json()}
    other = next(s for s in api_results if s not in own)
    assert client.get(f"/pipeline/sites/{other}/latest", headers=sp).status_code == 403
    run_id = client.get(f"/pipeline/sites/{other}/latest", headers=login(client, "scoper1")).json()["RUN_ID"]
    assert client.get(f"/pipeline/runs/{run_id}", headers=sp).status_code == 403
    assert client.post(f"/pipeline/sites/{other}/start", headers=sp).status_code == 403


def test_background_run_reports_progress(client):
    h = login(client, "scoper1")
    started = client.post("/pipeline/sites/TXDA1024/start", headers=h).json()
    assert started["status"] == "RUNNING" and started["run_id"].startswith("RUN-")
    first = client.get(f"/pipeline/runs/{started['run_id']}", headers=h).json()
    assert first["STATUS"] in ("RUNNING", "SUCCEEDED", "SUCCEEDED_WITH_WARNINGS") and len(first["STEPS"]) == 9
    again = client.post("/pipeline/sites/TXDA1024/start", headers=h).json()          # one run per site at a time
    assert again["run_id"] == started["run_id"] or not again["already_running"]
    done = wait_done(client, h, started["run_id"])
    assert done["STATUS"].startswith("SUCCEEDED") and all(s["status"] == "DONE" for s in done["STEPS"])


def test_implement_only_approved_redlines(client):
    h, rv, ae = login(client, "scoper1"), login(client, "reviewer1"), login(client, "ae1")
    site = "TXCA0977"                                              # DXF drawing: a cable-route redline and a mount-reinforcement redline
    red = [r for r in client.get(f"/redlines?site_id={site}", headers=h).json() if r["DOC_TYPE"] == "CD"]
    assert len(red) >= 2 and all(r["STATUS"] == "DRAFT" for r in red)
    # nothing approved: the job runs but writes no drawing, and says so
    job = client.post(f"/pipeline/sites/{site}/apply", headers=rv).json()
    run = wait_done(client, rv, job["run_id"])
    assert run["STATUS"] == "SUCCEEDED_WITH_WARNINGS" and not (run["SUMMARY"] or {}).get("files")
    assert client.get(f"/pipeline/sites/{site}/revision", headers=h).json()["revision"] is None
    # INCORPORATE needs the revised drawing first
    first = red[0]["REDLINE_ID"]
    for a, who in (("APPROVE", rv), ("SEND", rv), ("ACKNOWLEDGE", ae)):
        assert client.post(f"/redlines/{first}/transition", json={"action": a}, headers=who).status_code == 200, a
    r = client.post(f"/redlines/{first}/transition", json={"action": "INCORPORATE", "reason_code": "RC-AE-REVISED"}, headers=ae)
    assert r.status_code == 400 and "Implement" in r.json()["error"]["message"]
    # approve one of the two redlines and implement
    job = client.post(f"/pipeline/sites/{site}/apply", headers=rv).json()
    run = wait_done(client, rv, job["run_id"])
    assert run["STATUS"] == "SUCCEEDED", run["WARNINGS"]
    assert [s["status"] for s in run["STEPS"]] == ["DONE", "DONE", "DONE"]
    changes = run["SUMMARY"]["changes"]
    applied = {c["redline_id"]: c["applied"] for c in changes}
    assert applied[first] is True and sum(applied.values()) == 1                      # the unapproved redline is listed, not applied
    assert any("approve it" in c["detail"] for c in changes if not c["applied"])
    rev = client.get(f"/pipeline/sites/{site}/revision", headers=h).json()["revision"]
    assert rev and rev["RUN_ID"] == run["RUN_ID"]
    pdf = client.get(f"/pipeline/runs/{run['RUN_ID']}/file/revised_cd_pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert client.get(f"/pipeline/runs/{run['RUN_ID']}/file/nope", headers=h).status_code == 404
    # incorporating issues the drawing as the site's next CD revision (once, however many redlines are incorporated)
    r = client.post(f"/redlines/{first}/transition", json={"action": "INCORPORATE", "reason_code": "RC-AE-REVISED"}, headers=ae)
    assert r.status_code == 200, r.text
    assert any(u["FILE_NAME"] == f"{site}_CD_REV2.dxf" for u in client.get(f"/sites/{site}/documents", headers=h).json()["uploads"])
