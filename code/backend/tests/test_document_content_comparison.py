"""Comprehensive tests for document content inspection, duplicate data detection with different filenames,
and updated data detection (old data with new additions) with replacement flow.
"""
import io
import openpyxl
import pytest
from fastapi.testclient import TestClient
from api.main import app
from scopeiq.common.context import bind
from scopeiq.db.repository import SqliteRepository, get_repository, set_repository, now_iso
from scopeiq.services.seed import load_reference_tables
from tests.test_api import login


@pytest.fixture
def compare_setup(ref):
    prev = get_repository()
    r = SqliteRepository(":memory:")
    r.init_schema()
    load_reference_tables(r)
    set_repository(r)

    # Insert test site
    with bind(user_id="system", role="SYSTEM"):
        r.insert("CORE.SITE", [{
            "SITE_ID": "TXTS1000", "SITE_NAME": "Test Comparison Site", "MARKET": "North Texas",
            "CUSTOMER": "Verizon", "WORKFLOW_STATE": "ASSIGNED", "UPDATED_AT": now_iso(),
            "UPDATED_BY": "system"
        }])

    with TestClient(app) as c:
        yield c, "TXTS1000"

    set_repository(prev)


def make_excel(rows: list[list], sheet_title: str = "BOM") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_content_duplicate_and_update_detection_flow(compare_setup):
    client, sid = compare_setup
    h = login(client, "scoper1")

    # Base BOM data
    base_rows = [
        ["Site ID", "Sector", "Equipment", "Quantity"],
        [sid, "Alpha", "AIR 6419 B41", 3],
        [sid, "Beta", "AIR 6419 B41", 3],
    ]
    base_bytes = make_excel(base_rows)

    # 1. First upload: Brand new data -> should succeed
    r_up1 = client.post(
        f"/sites/{sid}/documents/upload",
        data={"doc_type": "BOM_REV0"},
        files={"file": (f"{sid}_BOM_REV0.xlsx", base_bytes)},
        headers=h,
    )
    assert r_up1.status_code == 200
    assert r_up1.json()["STATUS"] == "RECEIVED"
    assert r_up1.json()["is_duplicate"] is False

    # 2. Check duplicate with DIFFERENT filename
    # Even though filename is different, data inside is identical!
    diff_filename = f"{sid}_BOM_Copy_Different_Name.xlsx"
    r_check_dup = client.post(
        f"/sites/{sid}/documents/check-content",
        data={"doc_type": "BOM_REV0"},
        files={"file": (diff_filename, base_bytes)},
        headers=h,
    )
    assert r_check_dup.status_code == 200
    dup_res = r_check_dup.json()
    assert dup_res["status"] == "DUPLICATE"
    assert dup_res["is_duplicate"] is True
    assert dup_res["duplicate_of"] == f"{sid}_BOM_REV0.xlsx"
    assert "already exists" in dup_res["message"].lower()

    # 3. Upload duplicate without confirmation -> 409 Conflict
    r_dup_blocked = client.post(
        f"/sites/{sid}/documents/upload",
        data={"doc_type": "BOM_REV0"},
        files={"file": (diff_filename, base_bytes)},
        headers=h,
    )
    assert r_dup_blocked.status_code == 409
    err = r_dup_blocked.json()["error"]["details"]
    assert err["is_duplicate"] is True
    assert err["duplicate_of"] == f"{sid}_BOM_REV0.xlsx"
    assert "already exists" in err["message"].lower()

    # 4. Same file uploaded with same data -> Already exists message
    r_same_same = client.post(
        f"/sites/{sid}/documents/check-content",
        data={"doc_type": "BOM_REV0"},
        files={"file": (f"{sid}_BOM_REV0.xlsx", base_bytes)},
        headers=h,
    )
    assert r_same_same.status_code == 200
    assert r_same_same.json()["status"] == "DUPLICATE"
    assert r_same_same.json()["already_exists"] is True
    assert "already exists" in r_same_same.json()["message"].lower()

    # 5. Updated file: contains old data PLUS new additions
    updated_rows = [
        ["Site ID", "Sector", "Equipment", "Quantity"],
        [sid, "Alpha", "AIR 6419 B41", 3],
        [sid, "Beta", "AIR 6419 B41", 3],
        [sid, "Gamma", "Radio 4480 B71", 2],  # Addition 1
        [sid, "Site", "OVP Box Type 6", 1],    # Addition 2
    ]
    updated_bytes = make_excel(updated_rows)

    # Pre-check content inspection for updated data -> Gives replace file option
    r_check_upd = client.post(
        f"/sites/{sid}/documents/check-content",
        data={"doc_type": "BOM_REV0"},
        files={"file": (f"{sid}_BOM_REV1.xlsx", updated_bytes)},
        headers=h,
    )
    assert r_check_upd.status_code == 200
    upd_res = r_check_upd.json()
    assert upd_res["status"] == "UPDATED"
    assert upd_res["is_updated"] is True
    assert upd_res["can_replace"] is True
    assert "replace" in upd_res["message"].lower()
    assert upd_res["diff"] is not None
    assert upd_res["diff"]["added_count"] == 2
    # Verify additions show what is new in the file
    additions_text = " ".join(upd_res["diff"]["additions"])
    assert "Radio 4480" in additions_text
    assert "OVP Box" in additions_text

    # 6. Upload updated file without confirmation -> 409 Conflict with diff details
    r_upd_blocked = client.post(
        f"/sites/{sid}/documents/upload",
        data={"doc_type": "BOM_REV0"},
        files={"file": (f"{sid}_BOM_REV1.xlsx", updated_bytes)},
        headers=h,
    )
    assert r_upd_blocked.status_code == 409
    upd_err = r_upd_blocked.json()["error"]["details"]
    assert upd_err["is_updated"] is True
    assert upd_err["diff"]["added_count"] == 2

    # 7. Upload with replace_file -> Successfully replaces old data with updated data!
    r_upd_replace = client.post(
        f"/sites/{sid}/documents/upload",
        data={"doc_type": "BOM_REV0", "replace_file": f"{sid}_BOM_REV0.xlsx"},
        files={"file": (f"{sid}_BOM_REV1.xlsx", updated_bytes)},
        headers=h,
    )
    assert r_upd_replace.status_code == 200
    rep_res = r_upd_replace.json()
    assert rep_res["replaced"] is True
    assert rep_res["replaced_file"] == f"{sid}_BOM_REV0.xlsx"
    assert "Replaced" in rep_res["MESSAGE"]

    # 8. Same file uploaded with some changes (same filename, modified data) -> shows replace file option
    modified_rows = [
        ["Site ID", "Sector", "Equipment", "Quantity"],
        [sid, "Alpha", "AIR 6419 B41", 6],  # Quantity changed from 3 to 6
        [sid, "Beta", "AIR 6419 B41", 3],
    ]
    modified_bytes = make_excel(modified_rows)
    r_same_mod = client.post(
        f"/sites/{sid}/documents/check-content",
        data={"doc_type": "BOM_REV0"},
        files={"file": (f"{sid}_BOM_REV1.xlsx", modified_bytes)},
        headers=h,
    )
    assert r_same_mod.status_code == 200
    mod_res = r_same_mod.json()
    assert mod_res["status"] == "UPDATED"
    assert mod_res["is_updated"] is True
    assert mod_res["can_replace"] is True
    assert "replace" in mod_res["message"].lower()
