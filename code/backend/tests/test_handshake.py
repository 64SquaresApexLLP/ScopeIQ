"""The workflow of the guide over the API: BOM revision locked -> service provider handshake (agree / request changes) -> final approval, and the
service provider's limited view. On a database of its own, so no sample data is needed."""
import pytest
from fastapi.testclient import TestClient

from tests.test_api import SP_COMPANIES, login


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


def _site(site, company, state, **extra):
    from scopeiq.db.repository import get_repository
    get_repository().insert("CORE.SITE", [{"SITE_ID": site, "SITE_NAME": f"Site {site}", "CX_SP": company, "WORKFLOW_STATE": state, **extra}])


def _revision(site, no, kind, status, locked):
    from scopeiq.db.repository import get_repository, now_iso
    get_repository().insert("CORE.BOM_REVISION", [{"BOM_REV_ID": f"{site}-REV{no}", "SITE_ID": site, "REV_NO": no, "REV_LABEL": f"REV {no}", "KIND": kind,
                                                   "STATUS": status, "LOCKED": locked, "CREATED_AT": now_iso()}])


def _rev(site, no):
    from scopeiq.db.repository import get_repository
    return get_repository().get("CORE.BOM_REVISION", BOM_REV_ID=f"{site}-REV{no}")


def test_the_bom_goes_to_the_provider_then_to_final_approval(client):
    """Reviewer sends the locked revision to the provider; the provider agrees or asks for changes (which make the next revision); only then does
    Admin / Ericsson give final approval, which locks the latest generated revision and never touches REV 0."""
    site = "TXFB0001"
    _site(site, SP_COMPANIES["sp_prairie"], "IN_REVIEW")
    _revision(site, 0, "TOOL_REV0", "RECEIVED", True)
    _revision(site, 1, "GENERATED", "DRAFT", False)
    scoper, reviewer, sp, other, admin = (login(client, w) for w in ("scoper1", "reviewer1", "sp_prairie", "sp_brazos", "admin"))
    step = lambda h, action, **kw: client.post(f"/workflow/SITE_SCOPING/{site}/transition", json={"action": action, **kw}, headers=h)
    inbox = lambda h: [n for n in client.get("/workflow/inbox", headers=h).json() if n["SITE_ID"] == site]
    words = "Move the Gamma RRU to position 2 - the platform has no room"

    assert step(scoper, "SUBMIT_TO_SP").status_code == 403 and step(sp, "SUBMIT_TO_SP").status_code == 403
    assert step(reviewer, "SUBMIT_TO_SP").status_code == 200                                 # the handshake starts
    assert _rev(site, 1)["STATUS"] == "SP_REVIEW" and _rev(site, 1)["LOCKED"]                # what the provider reviews cannot change under it
    assert inbox(sp) and not inbox(other)                                                    # its own provider is told, and only that one
    assert step(admin, "APPROVE_FBA").status_code == 409                                     # not before the provider has answered

    assert step(other, "REQUEST_CHANGES", reason_code="RC-SP-REQUEST", comment="x").status_code == 403
    assert step(sp, "REQUEST_CHANGES").status_code == 400                                    # a reason and its own words
    assert step(sp, "REQUEST_CHANGES", reason_code="RC-SP-REQUEST", comment=words).status_code == 200
    assert _rev(site, 1)["STATUS"] == "SP_CHANGES_REQUESTED"                                 # next revision required
    _revision(site, 2, "GENERATED", "DRAFT", False)                                          # the next run makes REV 2
    assert step(scoper, "SUBMIT_REVIEW").status_code == 200 and step(reviewer, "SUBMIT_TO_SP").status_code == 200

    assert step(sp, "AGREE").status_code == 200 and _rev(site, 2)["STATUS"] == "SP_AGREED"   # no reason needed to agree
    assert step(reviewer, "APPROVE_FBA").status_code == 403 and step(sp, "APPROVE_FBA").status_code == 403    # only Admin gives final approval
    assert step(admin, "REJECT_FBA").status_code == 400                                      # sending it back needs a reason and a comment
    assert step(admin, "APPROVE_FBA").status_code == 200
    assert _rev(site, 2)["STATUS"] == "FBA" and _rev(site, 2)["LOCKED"]
    assert _rev(site, 1)["STATUS"] == "SP_CHANGES_REQUESTED" and _rev(site, 0)["STATUS"] == "RECEIVED"       # earlier revisions are left as they were

    history = client.get(f"/sites/{site}/handshake", headers=admin).json()["workflow_history"]
    assert any(h["COMMENT"] == words and h["ACTOR_USER_ID"] == "sp_prairie" for h in history)    # the provider's words are kept as written
    assert any("approved" in n["MESSAGE"].lower() for n in inbox(sp))                                # final approval is told to the provider too


def test_each_role_is_offered_only_its_own_steps_and_the_provider_is_kept_out_of_scoping_work(client):
    site = "TXRL0001"
    _site(site, SP_COMPANIES["sp_prairie"], "IN_SCOPING")
    _revision(site, 1, "GENERATED", "DRAFT", False)
    sp, scoper, reviewer, admin = (login(client, w) for w in ("sp_prairie", "scoper1", "reviewer1", "admin"))
    steps = lambda h: [a["action"] for a in client.get(f"/sites/{site}/handshake", headers=h).json()["workflow_actions"]]
    offered = lambda h: sorted(a["action"] for a in client.get(f"/workflow/SITE_SCOPING/{site}/actions", headers=h).json()["actions"])
    go = lambda h, action: client.post(f"/workflow/SITE_SCOPING/{site}/transition", json={"action": action}, headers=h).status_code

    assert steps(scoper) == ["SUBMIT_REVIEW"] and offered(sp) == []                          # nothing for the provider while it is being scoped
    assert go(scoper, "SUBMIT_REVIEW") == 200
    assert "SUBMIT_TO_SP" in steps(reviewer) and "SUBMIT_REVIEW" not in steps(reviewer) and offered(sp) == []
    assert go(reviewer, "SUBMIT_TO_SP") == 200
    assert offered(sp) == ["AGREE", "REQUEST_CHANGES"]                                       # the handshake: its two answers
    assert go(sp, "AGREE") == 200
    assert offered(sp) == [] and "APPROVE_FBA" in steps(admin)                               # then it is Admin's
    assert client.post(f"/sites/{site}/assign-sp", json={"cx_sp": "Brazos"}, headers=admin).status_code == 403      # fixed once it is out for the handshake

    for path in (f"/sites/{site}/handshake", f"/sites/{site}/delta", f"/sites/{site}/estimate", "/pipeline/runs", "/redlines", "/rfis", "/discrepancies",
                 "/sharepoint/sites", "/reference/rate_card", f"/workflow/SITE_SCOPING/{site}/history", f"/bom/sites/{site}/revisions"):
        assert client.get(path, headers=sp).status_code == 403, path
        assert client.get(path, headers=admin).status_code != 403, path


def test_a_provider_is_given_final_drawings_and_from_the_handshake_the_scope_and_bom(client):
    """Drawings, scope of work and the BOM are given from the handshake onward (SP_HANDSHAKE through FBA_APPROVED), only after a finished
    pipeline run generated the BOM and no redline is open (including INCORPORATED redlines), and go back out of sight when changes are requested."""
    from scopeiq.db.repository import get_repository, now_iso
    r, site = get_repository(), "TXPV0001"
    sp, other, admin = login(client, "sp_prairie"), login(client, "sp_brazos"), login(client, "admin")
    _site(site, SP_COMPANIES["sp_prairie"], "IN_REVIEW", LAST_RUN_ID="RUN-PV")
    doc = lambda i, doc_type, status, rev: {"DOC_ID": f"DOC-{site}-{i}", "SITE_ID": site, "DOC_TYPE": doc_type, "FILE_NAME": f"{site}_{i}.pdf", "REL_PATH": f"sites/{site}/{i}.pdf",
                                            "FILE_FORMAT": "PDF", "REVISION": f"REV {rev}", "REVISION_RANK": rev, "STATUS": status}
    r.insert("CORE.DOCUMENT", [doc("cd2", "CD", "CURRENT", 2), doc("cd1", "CD", "SUPERSEDED", 1), doc("cdd", "CD", "DUPLICATE", 2), doc("rfds", "RFDS", "CURRENT", 3)])
    r.insert("CORE.BOM_OUTPUT_LINE", [{"LINE_ID": "L1", "RUN_ID": "RUN-PV", "SITE_ID": site, "SECTOR": "A", "CATEGORY": "Antenna", "MODEL": "ANT-1", "DESCRIPTION": "Panel antenna",
                                       "UOM": "EA", "TOTAL_QTY": 2, "ACTION": "Install", "SUPPLY": "CFM", "UNIT_COST_USD": 100.0, "TOTAL_COST_USD": 200.0, "RULE_ID": "KIT-1"}])
    r.insert("CORE.EQUIPMENT_DELTA", [{"SITE_ID": site, "RUN_ID": "RUN-PV", "SEQ": 0, "SECTOR": "A", "POSITION": "2", "KIND": "ANTENNA", "CATALOG_KEY": "ANT-1", "ACTION": "NEW", "BASIS": "RFDS rev 3"}])
    view = lambda h: client.get(f"/sites/{site}/provider", headers=h).json()
    names = lambda v: sorted(d["FILE_NAME"] for d in v["drawings"])
    state = lambda s: r.update("CORE.SITE", {"WORKFLOW_STATE": s}, {"SITE_ID": site})

    assert names(view(sp)) == []                                                            # no run has finished and still in IN_REVIEW: nothing shown yet
    r.insert("CORE.PIPELINE_RUN", [{"RUN_ID": "RUN-PV", "SITE_ID": site, "STARTED_AT": now_iso(), "STATUS": "SUCCEEDED"}])
    r.insert("CORE.REDLINE", [{"REDLINE_ID": "RL-PV", "SITE_ID": site, "STATUS": "WORK_QUEUE"}])
    assert names(view(sp)) == []                                                            # still in IN_REVIEW with an open redline
    r.update("CORE.REDLINE", {"STATUS": "COMPLETED"}, {"REDLINE_ID": "RL-PV"})
    v = view(sp)
    assert names(v) == [] and v["phase"] == "PENDING" and v["scope"] == {"released": False, "items": []} and v["bom"]["released"] is False   # still in IN_REVIEW (Option B: wait for SP_HANDSHAKE)
    assert client.get(f"/sites/{site}/provider", headers=other).status_code == 403          # nor to another provider

    state("SP_HANDSHAKE")                                                                   # sent for the handshake: drawings, scope of work and BOM are given
    v = view(sp)
    assert names(v) == [f"{site}_cd2.pdf"]                                                  # the current drawing only: no superseded or duplicate, no RFDS
    assert v["phase"] == "REVIEW" and v["scope"]["released"] and [x["CATALOG_KEY"] for x in v["scope"]["items"]] == ["ANT-1"]
    assert v["bom"]["released"] and not v["bom"]["approved"] and len(v["bom"]["lines"]) == 1 and v["bom"]["lines"][0]["MODEL"] == "ANT-1"
    assert not {"UNIT_COST_USD", "TOTAL_COST_USD", "RULE_ID", "TRACE"} & set(v["bom"]["lines"][0])    # what to build, not what it costs or how it was derived
    assert not {"BASIS", "SOURCE_REF", "RUN_ID"} & set(v["scope"]["items"][0])

    # An incorporated redline counts as resolved and still reveals the corrected CD once BOM is generated
    r.update("CORE.REDLINE", {"STATUS": "INCORPORATED"}, {"REDLINE_ID": "RL-PV"})
    assert names(view(sp)) == [f"{site}_cd2.pdf"]

    # An open redline blocks drawings even in SP_HANDSHAKE; restoring INCORPORATED unblocks it
    r.update("CORE.REDLINE", {"STATUS": "WORK_QUEUE"}, {"REDLINE_ID": "RL-PV"})
    assert names(view(sp)) == []
    r.update("CORE.REDLINE", {"STATUS": "INCORPORATED"}, {"REDLINE_ID": "RL-PV"})

    # A pipeline run that skipped the BOM stage (e.g. stopped at Stage 4) does not release drawings
    r.update("CORE.PIPELINE_RUN", {"STEPS": [{"key": "BOM", "status": "SKIPPED"}]}, {"RUN_ID": "RUN-PV"})
    assert names(view(sp)) == []
    r.update("CORE.PIPELINE_RUN", {"STEPS": [{"key": "BOM", "status": "DONE"}]}, {"RUN_ID": "RUN-PV"})
    assert names(view(sp)) == [f"{site}_cd2.pdf"]

    state("SUBMITTED_FBA")
    assert view(sp)["phase"] == "AGREED" and view(sp)["bom"]["released"] and names(view(sp)) == [f"{site}_cd2.pdf"]
    state("FBA_APPROVED")
    assert view(sp)["phase"] == "APPROVED" and view(sp)["bom"]["approved"] and names(view(sp)) == [f"{site}_cd2.pdf"]
    state("IN_SCOPING")                                                                     # changes requested: drawings, scope & BOM go back out of sight until the next revision
    v = view(sp)
    assert names(v) == [] and v["phase"] == "PENDING" and not v["bom"]["released"] and v["bom"]["lines"] == [] and v["scope"]["items"] == []

    mine = {s["SITE_ID"]: s for s in client.get("/sites", headers=sp).json()}               # all of its own company's sites, and no one else's
    assert site in mine and all(s["CX_SP"] == SP_COMPANIES["sp_prairie"] for s in mine.values())
    assert not mine[site]["DRAWINGS_READY"] and mine[site]["PHASE"] == "PENDING"
    assert not {"WORKFLOW_STATE", "STREAM", "OPEN_DISCREPANCIES", "DOC_COUNT", "ACTIONS", "LAST_RUN_ID"} & set(mine[site])

    state("SP_HANDSHAKE")
    mine = {s["SITE_ID"]: s for s in client.get("/sites", headers=sp).json()}
    assert mine[site]["DRAWINGS_READY"] and mine[site]["PHASE"] == "REVIEW"

    detail = client.get(f"/sites/{site}", headers=sp).json()
    assert detail["documents"] == [] and detail["revision_check"] is None and detail["last_run"] == [] and "WORKFLOW_STATE" not in detail["site"]
    assert len(client.get(f"/sites/{site}", headers=admin).json()["documents"]) == 4        # the scoping team still sees every file

    ok = lambda doc_id, path, h: client.get(f"/documents/{doc_id}/{path}", headers=h).status_code
    for path in ("preview", "download"):
        assert ok(f"DOC-{site}-cd1", path, sp) == 403 and ok(f"DOC-{site}-cdd", path, sp) == 403 and ok(f"DOC-{site}-rfds", path, sp) == 403
        assert ok(f"DOC-{site}-cd2", path, other) == 403                                    # another provider's site
        assert ok(f"DOC-{site}-cd2", path, sp) != 403                                       # the drawing it was given
    assert names({"drawings": client.get(f"/sites/{site}/documents", headers=sp).json()["documents"]}) == [f"{site}_cd2.pdf"]


def test_a_provider_requests_changes_in_the_handshake_and_after_final_approval(client):
    """In the handshake a request goes back to scoping and the locked revision gives way to the next one. After final approval the approved revision is
    never touched: the site is reopened for rework and the next revision is approved again. Never at any other time, and only by the site's own provider."""
    site = "TXRQ0001"
    _site(site, SP_COMPANIES["sp_prairie"], "IN_REVIEW")
    _revision(site, 1, "GENERATED", "DRAFT", False)
    sp, other, scoper, reviewer, admin = (login(client, w) for w in ("sp_prairie", "sp_brazos", "scoper1", "reviewer1", "admin"))
    step = lambda h, action, **kw: client.post(f"/workflow/SITE_SCOPING/{site}/transition", json={"action": action, **kw}, headers=h)
    ask = lambda **kw: step(sp, "REQUEST_CHANGES", **kw)
    state = lambda: client.get(f"/sites/{site}", headers=admin).json()["site"]["WORKFLOW_STATE"]
    words = ["The drawing shows the mount on the wrong leg", "Ground-level cabinet moved to the east pad"]

    assert ask(reason_code="RC-SP-REQUEST", comment="x").status_code == 409                   # not while it is being reviewed: the handshake has not begun
    assert step(reviewer, "SUBMIT_TO_SP").status_code == 200
    assert step(other, "REQUEST_CHANGES", reason_code="RC-SP-REQUEST", comment="x").status_code == 403 and step(scoper, "REQUEST_CHANGES", reason_code="RC-SP-REQUEST", comment="x").status_code == 403
    assert ask().status_code == 400 and ask(reason_code="RC-SP-REQUEST").status_code == 400    # a reason and its own words
    assert ask(reason_code="RC-SP-REQUEST", comment=words[0]).status_code == 200
    assert state() == "IN_SCOPING" and _rev(site, 1)["STATUS"] == "SP_CHANGES_REQUESTED" and _rev(site, 1)["LOCKED"]

    _revision(site, 2, "GENERATED", "DRAFT", False)
    assert step(scoper, "SUBMIT_REVIEW").status_code == 200 and step(reviewer, "SUBMIT_TO_SP").status_code == 200
    assert step(sp, "AGREE").status_code == 200
    assert ask(reason_code="RC-SP-REQUEST", comment="x").status_code == 409                   # it has agreed; the next answer is Admin's
    assert step(admin, "APPROVE_FBA").status_code == 200 and _rev(site, 2)["STATUS"] == "FBA"
    assert ask(reason_code="RC-SP-REQUEST", comment=words[1]).status_code == 200              # after approval
    assert state() == "REWORK" and _rev(site, 2)["STATUS"] == "FBA" and _rev(site, 2)["LOCKED"]     # the final revision is never touched

    mine = client.get(f"/sites/{site}/provider", headers=sp).json()["requests"]               # newest first, in its own words, with the reason as text
    assert [r["comment"] for r in mine] == words[::-1] and {r["reason"] for r in mine} == {"Change requested by the service provider"}
    assert any("asked for changes" in n["MESSAGE"] for n in client.get("/workflow/inbox", headers=admin).json() if n["SITE_ID"] == site)   # the scoping team is told


def test_service_providers_exist_only_as_companies_an_admin_created(client):
    """No provider comes from sample data: a name in the tracker with no account behind it reads as not assigned, a site can be assigned only to
    a company with a login, and one company keeps one spelling however its logins were typed."""
    from scopeiq.db.repository import get_repository
    r, admin = get_repository(), login(client, "admin")
    r.insert("CORE.SITE", [{"SITE_ID": "TXPR0001", "SITE_NAME": "Provider test", "CX_SP": "Acme Towers", "WORKFLOW_STATE": "ASSIGNED"}])
    site = lambda: client.get("/sites/TXPR0001", headers=admin).json()["site"]
    assign = lambda name: client.post("/sites/TXPR0001/assign-sp", json={"cx_sp": name}, headers=admin)
    new = lambda user, company: client.post("/admin/logins", headers=admin, json={"username": user, "display_name": user, "password": "a-long-password-1",
                                                                                  "role": "CX_SP", **({"service_provider": company} if company else {})})

    assert site()["CX_SP"] is None and assign("Acme Towers").status_code == 400          # named in the tracker, but nobody has an account
    assert new("acme.one", None).status_code == 400                                     # the company is required
    assert new("acme.one", "Acme Towers").json()["ORGANISATION"] == "Acme Towers"
    assert new("acme.two", "  acme TOWERS ").json()["ORGANISATION"] == "Acme Towers"   # the same company, the same spelling

    logins = client.get("/admin/logins", headers=admin).json()
    companies = sorted({x["ORGANISATION"] for x in logins if x["ROLE_CODE"] == "CX_SP"})
    assert [p["name"] for p in client.get("/sites/service-providers", headers=admin).json()] == companies and "Acme Towers" in companies
    assert assign("Acme Towers").status_code == 200 and site()["CX_SP"] == "Acme Towers"
    sp = {"Authorization": "Bearer " + client.post("/auth/login", json={"username": "acme.two", "password": "a-long-password-1", "role": "CX_SP"}).json()["token"]}
    assert [s["SITE_ID"] for s in client.get("/sites", headers=sp).json()] == ["TXPR0001"]      # its own company's sites, from either login

    cards = {u["role"]: u for u in client.get("/auth/users").json()}                     # the role is still offered, with no demo account
    assert cards["CX_SP"]["password_required"] and not cards["CX_SP"]["organisation"]


def test_a_run_never_replaces_a_bom_that_is_out_for_approval(client):
    """The workflow reference decides which states are closed to a run: with the provider, agreed and waiting for final approval, or approved."""
    from api.deps import pipeline
    from scopeiq.common.errors import WorkflowError
    from scopeiq.db.repository import get_repository
    r, svc = get_repository(), pipeline()
    closed = {s["STATE"] for s in svc.ref.rows("workflow_states") if s["ENTITY_TYPE"] == "SITE_SCOPING" and (s["IS_LOCKED"] == "Y" or s["OWNER_ROLE"] not in ("SCOPER", "REVIEWER"))}
    assert {"SP_HANDSHAKE", "SUBMITTED_FBA", "FBA_APPROVED"} <= closed and not closed & {"IN_SCOPING", "IN_REVIEW", "REWORK"}
    r.insert("CORE.SITE", [{"SITE_ID": "TXRUN001", "SITE_NAME": "Run guard", "WORKFLOW_STATE": "SP_HANDSHAKE"}])
    svc.sites_dir.mkdir(parents=True, exist_ok=True)
    (svc.sites_dir / "TXRUN001").mkdir(exist_ok=True)
    try:
        with pytest.raises(WorkflowError) as e:
            svc.begin_run("TXRUN001")
        assert e.value.details["state"] == "SP_HANDSHAKE"
        r.update("CORE.SITE", {"WORKFLOW_STATE": "REWORK"}, {"SITE_ID": "TXRUN001"})
        assert svc.begin_run("TXRUN001").startswith("RUN-TXRUN001")
    finally:
        import shutil
        shutil.rmtree(svc.sites_dir / "TXRUN001", ignore_errors=True)
