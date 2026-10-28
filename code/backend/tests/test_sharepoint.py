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
    # the store also mirrors sites into paths.sites_dir (the pipeline's input folder): keep that in the throw-away folder too
    import os

    from scopeiq.config import reset_settings_cache
    old_sites = os.environ.get("SCOPEIQ__PATHS__SITES_DIR")
    os.environ["SCOPEIQ__PATHS__SITES_DIR"] = str(tmp_path_factory.mktemp("sites_dir"))
    reset_settings_cache()
    store = sp.LocalSharePoint(root, "Ericsson-Scoping/Sites")
    sp.set_store(store)
    yield {"root": root, "store": store, "repo": r}
    sp.set_store(None)
    set_repository(previous)
    if old_sites is None:
        os.environ.pop("SCOPEIQ__PATHS__SITES_DIR", None)
    else:
        os.environ["SCOPEIQ__PATHS__SITES_DIR"] = old_sites
    reset_settings_cache()


@pytest.fixture(scope="module")
def client(env):
    from api.main import app
    with TestClient(app) as c:
        yield c


TEST_PASSWORD = "test-password-1"
PASSWORD_USERS = {"scoper": "SCOPER", "ae": "AE_ENGINEER"}      # demo user id prefix -> role that signs in with a password


def login(client, user_id):
    """Demo accounts sign in directly; SCOPER and AE_ENGINEER sign in with a username + password, which the admin creates first."""
    role = next((r for prefix, r in PASSWORD_USERS.items() if user_id.startswith(prefix)), None)
    if role:
        admin = login(client, "admin")
        client.post("/admin/logins", json={"username": user_id, "display_name": user_id, "password": TEST_PASSWORD, "role": role}, headers=admin)
        r = client.post("/auth/login", json={"username": user_id, "password": TEST_PASSWORD})
    else:
        r = client.post("/auth/login", json={"user_id": user_id, "password": "demo"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


SITE = {"site_id": "TXZZ0001", "site_name": "Test Hill", "city": "Dallas", "state": "TX", "stream": "BOM", "structure_type": "Monopole", "height_ft": 120}


def test_scopers_cannot_access_sharepoint(client):
    s = login(client, "scoper1")
    assert client.post("/admin/sites", json=SITE, headers=s).status_code == 403
    assert client.get("/sharepoint/status", headers=s).status_code == 403
    assert client.get("/sharepoint/sites", headers=s).status_code == 403
    assert client.get("/sharepoint/sites/TXZZ0001/files", headers=s).status_code == 403
    assert client.post("/sharepoint/sites/TXZZ0001/check-content", files={"file": ("a.pdf", b"test")}, headers=s).status_code == 403
    assert client.post("/sharepoint/sites/TXZZ0001/upload", files={"file": ("a.pdf", b"test")}, headers=s).status_code == 403
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
    # the new site is offered for uploads to admin
    sites = client.get("/sharepoint/sites", headers=h).json()["sites"]
    assert [s["site_id"] for s in sites] == ["TXZZ0001"] and sites[0]["files"] == 0


def test_create_site_rejects_bad_or_duplicate_ids(client):
    h = login(client, "admin")
    assert client.post("/admin/sites", json={**SITE, "site_id": "bad id"}, headers=h).status_code == 400
    assert client.post("/admin/sites", json={**SITE, "site_id": "TX12"}, headers=h).status_code == 400
    assert client.post("/admin/sites", json={**SITE, "site_id": "TXDA9998", "state": ""}, headers=h).status_code in (400, 422)
    # Full state names (like Himachal Pradesh or Texas) are accepted
    assert client.post("/admin/sites", json={**SITE, "site_id": "TXDA9998", "state": "Himachal Pradesh"}, headers=h).status_code == 200
    assert client.post("/admin/sites", json=SITE, headers=h).status_code == 409


def test_create_site_with_coordinates_and_geocoding(client, env):
    h = login(client, "admin")
    r = client.post("/admin/sites", json={**SITE, "site_id": "TXDA9997", "latitude": 32.8341, "longitude": -96.7512}, headers=h)
    assert r.status_code == 200, r.text
    site_row = env["repo"].select("CORE.SITE", {"SITE_ID": "TXDA9997"})[0]
    assert site_row["LATITUDE"] == 32.8341
    assert site_row["LONGITUDE"] == -96.7512

    geo = client.get("/admin/geocode/reverse?lat=32.8341&lon=-96.7512", headers=h)
    assert geo.status_code == 200, geo.text
    assert "city" in geo.json()
    assert "state" in geo.json()


def test_upload_goes_to_the_selected_site_only(client, env):
    h = login(client, "admin")
    client.post("/admin/sites", json={**SITE, "site_id": "TXZZ0002", "site_name": "Other Hill"}, headers=h)
    s = h
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
    s = login(client, "admin")
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
    s = login(client, "admin")
    a = client.post("/sharepoint/sites/TXZZ0002/upload", files={"file": ("TXZZ0002_RFDS_R3.xlsx", b"same-bytes")}, headers=s).json()
    b = client.post("/sharepoint/sites/TXZZ0002/upload", files={"file": ("TXZZ0002_RFDS_R3_copy.xlsx", b"same-bytes")}, headers=s).json()
    assert a["duplicate_of"] is None and b["duplicate_of"] == "TXZZ0002_RFDS_R3.xlsx"


def test_non_admin_cannot_access_sharepoint_sites(client):
    assert client.get("/sharepoint/sites", headers=login(client, "sp_prairie")).status_code == 403


def test_path_traversal_is_refused(client, env):
    s = login(client, "admin")
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


def test_site_prefix_and_auto_id_generation(client, env):
    from api.routers.sharepoint import extract_two_letter_code, generate_site_prefix, get_next_site_id

    # Two or more words in state -> first letters of first two words
    assert extract_two_letter_code("Himachal Pradesh") == "HP"
    assert extract_two_letter_code("New York") == "NY"
    assert extract_two_letter_code("Jammu and Kashmir") == "JK"

    # Single word in state -> first two letters
    assert extract_two_letter_code("Texas") == "TE"
    assert extract_two_letter_code("California") == "CA"

    # Special user requirement: Una -> UA
    assert extract_two_letter_code("Una") == "UA"
    assert extract_two_letter_code("Dallas") == "DA"
    assert extract_two_letter_code("Fort Worth") == "FW"

    # Prefix generation
    assert generate_site_prefix("Himachal pradesh", "Una") == "HPUA"
    assert generate_site_prefix("Texas", "Dallas") == "TEDA"

    # Sequence generation starting at 0001
    res1 = get_next_site_id(state="Himachal Pradesh", city="Una")
    assert res1["site_id"] == "HPUA0001"
    assert res1["sequence"] == 1

    # Via API endpoint
    h = login(client, "admin")
    api_res = client.get("/admin/sites/next-id?state=Himachal+Pradesh&city=Una", headers=h)
    assert api_res.status_code == 200
    assert api_res.json()["site_id"] == "HPUA0001"

    # Create site with auto-generated Site ID
    create_res = client.post("/admin/sites", json={
        "site_name": "Una Tower",
        "city": "Una",
        "state": "Himachal Pradesh",
        "stream": "BOM",
        "structure_type": "Monopole",
    }, headers=h)
    assert create_res.status_code == 200, create_res.text
    created_id = create_res.json()["site"]["SITE_ID"]
    assert created_id == "HPUA0001"

    # Next site with same state and city should increment to 0002
    res2 = get_next_site_id(state="Himachal Pradesh", city="Una")
    assert res2["site_id"] == "HPUA0002"
    assert res2["sequence"] == 2

