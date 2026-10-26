"""SharePoint: admin creates a site (folder + record), users upload only into the selected site's folder.
Runs against a throw-away database and a throw-away library folder; needs no sample data."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    from scopeiq.db import repository as repomod
    from scopeiq.db.repository import SqliteRepository, set_repository
    from scopeiq.integrations import sharepoint as sp
    from scopeiq.services.seed import load_reference_tables
    previous = repomod._repo          # do not call get_repository(): it would open (and write to) the tracked local database
    r = SqliteRepository(":memory:")
    r.init_schema()
    load_reference_tables(r)
    set_repository(r)
    root = tmp_path_factory.mktemp("sharepoint")
    store = sp.LocalSharePoint(root, "Ericsson-Scoping/Sites")
    sp.set_store(store)
    yield {"root": root, "store": store, "repo": r}
    sp.set_store(None)
    set_repository(previous)


@pytest.fixture(scope="module")
def client(env):
    from api.main import app
    with TestClient(app) as c:
        yield c


def login(client, user_id):
    r = client.post("/auth/login", json={"user_id": user_id, "password": "demo"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


SITE = {"site_id": "TXZZ0001", "site_name": "Test Hill", "city": "Dallas", "state": "TX", "stream": "BOM", "structure_type": "Monopole", "height_ft": 120}


def test_only_admin_creates_a_site(client):
    assert client.post("/admin/sites", json=SITE, headers=login(client, "scoper1")).status_code == 403
    assert client.post("/admin/sites", json=SITE).status_code == 401


def test_admin_creates_site_and_folder(client, env):
    h = login(client, "admin")
    r = client.post("/admin/sites", json=SITE, headers=h)
    assert r.status_code == 200, r.text
    base = env["root"] / "Ericsson-Scoping/Sites/TXZZ0001"
    for f in ("rfds", "cds", "ma_sa", "bom", "drone", "drone/imagery", "drone/video"):
        assert (base / f).is_dir(), f
    assert env["repo"].select("CORE.SITE", {"SITE_ID": "TXZZ0001"})[0]["WORKFLOW_STATE"] == "ASSIGNED"
    assert env["repo"].select("AUDIT.AUDIT_LOG", {"ENTITY_ID": "TXZZ0001", "ACTION": "CREATE"})
    # the new site is offered for uploads
    sites = client.get("/sharepoint/sites", headers=login(client, "scoper1")).json()["sites"]
    assert [s["site_id"] for s in sites] == ["TXZZ0001"] and sites[0]["files"] == 0


def test_create_site_rejects_bad_or_duplicate_ids(client):
    h = login(client, "admin")
    assert client.post("/admin/sites", json={**SITE, "site_id": "bad id"}, headers=h).status_code == 400
    assert client.post("/admin/sites", json={**SITE, "site_id": "TX12"}, headers=h).status_code == 400
    assert client.post("/admin/sites", json=SITE, headers=h).status_code == 409


def test_upload_goes_to_the_selected_site_only(client, env):
    h = login(client, "admin")
    client.post("/admin/sites", json={**SITE, "site_id": "TXZZ0002", "site_name": "Other Hill"}, headers=h)
    s = login(client, "scoper1")
    r = client.post("/sharepoint/sites/TXZZ0001/upload", files={"file": ("TXZZ0001_CD_REV2.pdf", b"%PDF-1.4 drawing")}, headers=s)
    assert r.status_code == 200, r.text
    assert r.json()["folder"] == "cds" and r.json()["doc_type"] == "CD"
    base = env["root"] / "Ericsson-Scoping/Sites"
    assert (base / "TXZZ0001/cds/TXZZ0001_CD_REV2.pdf").read_bytes() == b"%PDF-1.4 drawing"
    assert not any((base / "TXZZ0002").rglob("*.pdf")), "a file leaked into another site's folder"
    # type is detected from the name for each kind of document
    for name, folder in (("TXZZ0001_RFDS_R4.xlsx", "rfds"), ("TXZZ0001_MA_SA_R0.pdf", "ma_sa"), ("TXZZ0001_BOM_REV0_preliminary.xlsx", "bom"),
                         ("TXZZ0001_pointcloud.laz", "drone"), ("TXZZ0001_sector_alpha.jpg", "drone/imagery")):
        assert client.post("/sharepoint/sites/TXZZ0001/upload", files={"file": (name, b"x" * 10)}, headers=s).json()["folder"] == folder
    files = client.get("/sharepoint/sites/TXZZ0001/files", headers=s).json()["files"]
    assert len(files) == 6 and {f["folder"] for f in files} >= {"cds", "rfds", "drone/imagery"}


def test_upload_validation(client):
    s = login(client, "scoper1")
    up = lambda site, name, data=b"abc", **kw: client.post(f"/sharepoint/sites/{site}/upload", files={"file": (name, data)}, headers=s, **kw)  # noqa: E731
    assert up("TXZZ0001", "TXZZ0002_CD_REV1.pdf").status_code == 400            # named for another site
    assert up("TXZZ0001", "holiday_notes.docx").status_code == 400                # type cannot be told
    assert up("TXZZ0001", "TXZZ0001_CD_REV3.pdf", b"").status_code == 400       # empty
    assert up("TXZZ9999", "TXZZ9999_CD_REV1.pdf").status_code == 404            # site has no folder
    assert up("nope", "x.pdf").status_code == 400                                # bad site id
    r = client.post("/sharepoint/sites/TXZZ0001/upload", files={"file": ("notes.bin", b"abc")}, data={"doc_type": "DRONE_VENDOR"}, headers=s)
    assert r.status_code == 200 and r.json()["folder"] == "drone"                # the user can choose the type
    assert client.post("/sharepoint/sites/TXZZ0001/upload", files={"file": ("a.pdf", b"a")}, data={"doc_type": "WRONG"}, headers=s).status_code == 400


def test_duplicate_content_is_flagged_not_blocked(client):
    s = login(client, "scoper1")
    a = client.post("/sharepoint/sites/TXZZ0002/upload", files={"file": ("TXZZ0002_RFDS_R3.xlsx", b"same-bytes")}, headers=s).json()
    b = client.post("/sharepoint/sites/TXZZ0002/upload", files={"file": ("TXZZ0002_RFDS_R3_copy.xlsx", b"same-bytes")}, headers=s).json()
    assert a["duplicate_of"] is None and b["duplicate_of"] == "TXZZ0002_RFDS_R3.xlsx"


def test_cx_sp_cannot_see_unassigned_sites(client):
    assert client.get("/sharepoint/sites", headers=login(client, "sp_prairie")).json()["sites"] == []


def test_path_traversal_is_refused(client, env):
    s = login(client, "scoper1")
    r = client.post("/sharepoint/sites/TXZZ0001/upload", files={"file": ("../../evil_CD_REV1.pdf", b"x")}, headers=s)
    assert r.status_code in (200, 400)
    assert not list(env["root"].rglob("evil_CD_REV1.pdf")) or all(env["root"] in p.parents for p in env["root"].rglob("evil_CD_REV1.pdf"))
    assert not (env["root"].parent / "evil_CD_REV1.pdf").exists()


def test_graph_provider_request_shapes():
    """Graph calls are built correctly (checked with a mock transport; not run against a live tenant)."""
    from scopeiq.integrations.sharepoint import GraphSharePoint, SharePointError
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.method, str(req.url).split("v1.0")[-1] if "graph" in str(req.url) else "token"))
        u = str(req.url)
        if "oauth2" in u:
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        if u.endswith("/sites/contoso.sharepoint.com:/sites/ScopeIQ"):
            return httpx.Response(200, json={"id": "SITEID"})
        if u.endswith("/sites/SITEID/drives"):
            return httpx.Response(200, json={"value": [{"id": "DRV", "name": "Documents"}]})
        if req.method == "POST" and u.endswith("/children"):
            return httpx.Response(201, json={})
        if req.method == "PUT":
            return httpx.Response(201, json={})
        return httpx.Response(404, json={})

    cfg = {"tenant_id": "tn", "client_id": "cid", "client_secret": "sec", "site_hostname": "contoso.sharepoint.com", "site_path": "/sites/ScopeIQ", "drive_name": "Documents"}
    g = GraphSharePoint(cfg, "Ericsson-Scoping/Sites", transport=httpx.MockTransport(handler))
    g.create_site_folder("TXZZ0003")
    folders = [p for m, p in seen if m == "POST" and p.endswith("/children")]
    assert len(folders) >= 7 + 2, "creates the library root path and the 7 site sub-folders"
    out = g.save_file("TXZZ0003", "cds", "TXZZ0003_CD_REV1.pdf", b"pdf")
    assert out["path"] == "Ericsson-Scoping/Sites/TXZZ0003/cds/TXZZ0003_CD_REV1.pdf"
    assert any(m == "PUT" and p.endswith("TXZZ0003_CD_REV1.pdf:/content") for m, p in seen)
    with pytest.raises(SharePointError):
        GraphSharePoint({"tenant_id": "x"}, "root")
    assert json.dumps(seen)  # keeps the recorded calls for debugging
