"""Tests for SHA-256 duplicate document detection and warning flow."""
import hashlib
import pytest
from fastapi.testclient import TestClient
from api.main import app
from scopeiq.common.context import bind
from scopeiq.db.repository import SqliteRepository, get_repository, set_repository, now_iso
from scopeiq.services.seed import load_reference_tables
from tests.test_api import login


@pytest.fixture
def test_setup(ref):
    prev = get_repository()
    r = SqliteRepository(":memory:")
    r.init_schema()
    load_reference_tables(r)
    set_repository(r)

    # Insert test site
    with bind(user_id="system", role="SYSTEM"):
        r.insert("CORE.SITE", [{
            "SITE_ID": "TXZZ9999", "SITE_NAME": "Test Site", "MARKET": "North Texas",
            "CUSTOMER": "Verizon", "WORKFLOW_STATE": "ASSIGNED", "UPDATED_AT": now_iso(),
            "UPDATED_BY": "system"
        }])

    with TestClient(app) as c:
        yield c, "TXZZ9999"

    set_repository(prev)


def test_hash_pre_check_and_upload_warning(test_setup):
    client, sid = test_setup
    h = login(client, "scoper1")

    content = b"%PDF-1.4 unique test drawing content for hash verification"
    digest = hashlib.sha256(content).hexdigest()

    # 1. Pre-check before upload: does not exist
    r_check = client.get(f"/sites/{sid}/documents/check-hash?hash={digest}", headers=h)
    assert r_check.status_code == 200
    assert r_check.json()["exists"] is False

    # 2. Upload the file first time -> SUCCESS (RECEIVED)
    r_upload1 = client.post(
        f"/sites/{sid}/documents/upload",
        data={"doc_type": "CD"},
        files={"file": (f"{sid}_CD_REV2.pdf", content)},
        headers=h,
    )
    assert r_upload1.status_code == 200
    assert r_upload1.json()["FILE_HASH"] == digest
    assert r_upload1.json()["STATUS"] == "RECEIVED"

    # 3. Pre-check now detects the file via SHA-256
    r_check2 = client.get(f"/sites/{sid}/documents/check-hash?hash={digest}", headers=h)
    assert r_check2.status_code == 200
    assert r_check2.json()["exists"] is True
    assert r_check2.json()["duplicate_of"] == f"{sid}_CD_REV2.pdf"
    assert "Duplicate document detected" in r_check2.json()["warning"]

    # 4. Attempt to re-upload exact duplicate without confirmation -> 409 Conflict with warning details
    r_dup_blocked = client.post(
        f"/sites/{sid}/documents/upload",
        data={"doc_type": "CD"},
        files={"file": (f"{sid}_CD_REV3.pdf", content)},
        headers=h,
    )
    assert r_dup_blocked.status_code == 409
    details = r_dup_blocked.json()["error"]["details"]
    assert details["is_duplicate"] is True
    assert details["file_hash"] == digest
    assert details["duplicate_of"] == f"{sid}_CD_REV2.pdf"
    assert "Identical document content already exists" in details["warning"]

    # 5. Upload with confirm_duplicate=True -> Succeeds with DUPLICATE status & warning message
    r_dup_confirmed = client.post(
        f"/sites/{sid}/documents/upload",
        data={"doc_type": "CD", "confirm_duplicate": "true"},
        files={"file": (f"{sid}_CD_REV3.pdf", content)},
        headers=h,
    )
    assert r_dup_confirmed.status_code == 200
    assert r_dup_confirmed.json()["STATUS"] == "DUPLICATE"
    assert r_dup_confirmed.json()["is_duplicate"] is True
    assert r_dup_confirmed.json()["duplicate_of"] == f"{sid}_CD_REV2.pdf"
    assert "Warning: Document has identical content" in r_dup_confirmed.json()["warning"]
