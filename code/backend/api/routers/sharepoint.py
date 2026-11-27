"""SharePoint: sites (one folder per site), the admin action that creates a site + its folder, and file upload into the selected
site's folder. The library behind it is chosen by `sharepoint.provider` (local folder or Microsoft Graph) - see
scopeiq/integrations/sharepoint.py."""
from __future__ import annotations

import base64
import csv
import hashlib
import json
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.deps import AE_FILE_TYPES, check_site_scope, current_user, repo, require, site_scope
from scopeiq.common.audit import AuditTrail
from scopeiq.common.errors import Conflict, NotFound, ValidationError
from scopeiq.config import get_settings
from scopeiq.db.repository import now_iso
from scopeiq.integrations.sharepoint import TYPE_FOLDERS, detect_doc_type, get_store, validate_site_id
from scopeiq.services.site_management import delete_site_cascade

router = APIRouter(tags=["sharepoint"])

STOP_WORDS = {"AND", "OF", "THE", "&"}


def extract_two_letter_code(name: str) -> str:
    """Extract a 2-letter uppercase code from a state or city name:
    - 2+ words: first letter of each of the first two words (e.g. 'Himachal Pradesh' -> 'HP', 'New York' -> 'NY')
    - 1 word: first two letters (e.g. 'Texas' -> 'TE', 'Dallas' -> 'DA')
    - Special user-specified example: 'Una' -> 'UA'
    - If already a 2-letter uppercase code (e.g. 'HP', 'TX'), preserves it.
    """
    if not name:
        return "XX"
    raw = name.strip()
    clean_upper = re.sub(r"[^A-Za-z0-9]", "", raw).upper()

    # User explicit example: Himachal Pradesh and Una -> HPUA0001
    if clean_upper == "UNA":
        return "UA"

    # Already a 2-letter uppercase code
    if len(clean_upper) == 2 and raw.isupper():
        return clean_upper

    parts = [re.sub(r"[^A-Za-z0-9]", "", w) for w in re.split(r"[\s\-_/]+", raw)]
    words = [w for w in parts if w]

    # Ignore stop words if 3 or more words (e.g. "Jammu and Kashmir" -> ["Jammu", "Kashmir"])
    if len(words) >= 3:
        meaningful = [w for w in words if w.upper() not in STOP_WORDS]
        if len(meaningful) >= 2:
            words = meaningful

    if not words:
        return "XX"

    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    else:
        w = words[0].upper()
        if len(w) >= 2:
            return w[:2]
        return (w + "X")[:2]


def generate_site_prefix(state: str, city: str) -> str:
    """Generate 4-letter prefix: 2 letters from state + 2 letters from city."""
    s = extract_two_letter_code(state)
    c = extract_two_letter_code(city)
    return (s + c).upper()


def get_next_site_id(state: str = "", city: str = "", prefix: str = "") -> dict:
    """Compute the 4-letter prefix and the next 4-digit sequence (e.g. 0001, 0002)."""
    pref = (prefix or "").strip().upper()
    if not pref and (state or city):
        pref = generate_site_prefix(state, city)

    if not pref or len(pref) != 4 or not pref.isalpha():
        return {"site_id": "", "prefix": pref, "sequence": 0}

    all_ids: set[str] = set()
    try:
        store = get_store()
        all_ids.update(store.list_site_ids())
    except Exception:
        pass

    try:
        r = repo()
        for row in r.select("CORE.SITE"):
            sid = row.get("SITE_ID")
            if sid:
                all_ids.add(str(sid).strip().upper())
    except Exception:
        pass

    pattern = re.compile(rf"^{re.escape(pref)}(\d{{4}})$")
    existing_seqs: list[int] = []
    for sid in all_ids:
        m = pattern.match(sid)
        if m:
            existing_seqs.append(int(m.group(1)))

    next_seq = max(existing_seqs, default=0) + 1
    next_site_id = f"{pref}{next_seq:04d}"
    return {
        "site_id": next_site_id,
        "prefix": pref,
        "sequence": next_seq,
    }




US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC",
}
STATE_NAME_TO_CODE = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA",
    "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE", "FLORIDA": "FL", "GEORGIA": "GA",
    "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA",
    "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO",
    "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH",
    "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT",
    "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
    "DISTRICT OF COLUMBIA": "DC",
}

_GEO_CACHE: dict[tuple[float, float], dict] = {}


def reverse_geocode(lat: float, lon: float) -> dict:
    key = (round(lat, 5), round(lon, 5))
    if key in _GEO_CACHE:
        return _GEO_CACHE[key]

    # 1. OpenStreetMap Nominatim
    try:
        import httpx
        resp = httpx.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"format": "jsonv2", "lat": lat, "lon": lon, "addressdetails": 1},
            headers={"User-Agent": "ScopeIQ/1.0 (telecom-scoping-app)"},
            timeout=4.0,
        )
        if resp.status_code == 200:
            d = resp.json()
            addr = d.get("address", {})
            city = (addr.get("city") or addr.get("town") or addr.get("village") or
                    addr.get("municipality") or addr.get("hamlet") or addr.get("suburb") or
                    addr.get("county") or "").strip()
            raw_state = (addr.get("state") or addr.get("province") or addr.get("region") or
                         addr.get("state_district") or "").strip()
            iso = addr.get("ISO3166-2-lvl4", "")
            state_code = ""
            if iso and "-" in iso:
                state_code = iso.split("-")[1].upper()
            elif raw_state.upper() in STATE_NAME_TO_CODE:
                state_code = STATE_NAME_TO_CODE[raw_state.upper()]
            elif len(raw_state) == 2:
                state_code = raw_state.upper()

            exact_state = raw_state or state_code

            res = {
                "city": city,
                "state": exact_state,
                "state_code": state_code,
                "state_name": exact_state,
                "country": addr.get("country", "").strip(),
                "zip": addr.get("postcode", "").strip(),
                "county": addr.get("county", "").strip(),
                "address": addr.get("road", "").strip(),
                "display_name": d.get("display_name", ""),
                "latitude": lat,
                "longitude": lon,
            }
            _GEO_CACHE[key] = res
            return res
    except Exception:
        pass

    # 2. BigDataCloud Fallback
    try:
        import httpx
        resp = httpx.get(
            "https://api.bigdatacloud.net/data/reverse-geocode-client",
            params={"latitude": lat, "longitude": lon, "localityLanguage": "en"},
            timeout=3.5,
        )
        if resp.status_code == 200:
            d = resp.json()
            city = (d.get("city") or d.get("locality") or "").strip()
            raw_state = (d.get("principalSubdivision") or "").strip()
            sub_code = (d.get("principalSubdivisionCode") or "").strip()
            state_code = ""
            if sub_code and "-" in sub_code:
                state_code = sub_code.split("-")[1].upper()
            elif sub_code:
                state_code = sub_code.upper()

            exact_state = raw_state or state_code

            res = {
                "city": city,
                "state": exact_state,
                "state_code": state_code,
                "state_name": exact_state,
                "country": d.get("countryName", "").strip(),
                "zip": d.get("postcode", "").strip(),
                "county": "",
                "display_name": f"{city}, {exact_state}".strip(", "),
                "latitude": lat,
                "longitude": lon,
            }
            _GEO_CACHE[key] = res
            return res
    except Exception:
        pass

    return {"city": "", "state": "", "state_name": "", "latitude": lat, "longitude": lon, "error": "Location could not be resolved from coordinates"}


class SiteIn(BaseModel):
    site_id: str = Field(default="", description="4 letters + 4 digits, e.g. TXDA1024. If empty or AUTO, auto-generated from State and City.")
    site_name: str = Field(min_length=2, max_length=120)
    city: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=120, description="Exact state or province name")
    stream: Literal["BOM", "DESIGN", "DEPLOYMENT"] = "BOM"
    structure_type: Literal["Monopole", "Self-support tower", "Guyed tower", "Rooftop"] = "Monopole"
    height_ft: float | None = Field(default=None, ge=0, le=2000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    address: str = ""
    market: str = ""
    zip: str = ""


@router.get("/admin/geocode/reverse")
def reverse_geocode_api(lat: float, lon: float, user: dict = Depends(require("ADMIN"))):
    """Reverse geocode coordinates into suggested city, exact state name, postal code, and formatted location."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValidationError("Latitude must be between -90 and 90, Longitude between -180 and 180.")
    geo = reverse_geocode(lat, lon)
    out = dict(geo)
    exact_state = out.get("state_name") or out.get("state") or ""
    exact_city = out.get("city") or ""
    if exact_state or exact_city:
        next_info = get_next_site_id(state=exact_state, city=exact_city)
        out["suggested_site_id"] = next_info["site_id"]
        out["site_id_prefix"] = next_info["prefix"]
    return out


@router.get("/admin/sites/next-id")
def next_site_id_endpoint(state: str = "", city: str = "", prefix: str = "", user: dict = Depends(require("ADMIN"))):
    """Generates the next sequential Site ID based on state and city (e.g. 'Himachal Pradesh' + 'Una' -> 'HPUA0001')."""
    return get_next_site_id(state=state, city=city, prefix=prefix)


@router.get("/sharepoint/status")
def status(user: dict = Depends(require("ADMIN"))):
    s = get_store()
    return {"provider": s.name, "location": s.location, "document_types": TYPE_FOLDERS,
            "max_upload_mb": int(get_settings().get("sharepoint.max_upload_mb", 400))}


# AE_ENGINEER_ALLOWED_TYPES: document types A&E Engineers are permitted to upload
AE_ENGINEER_ALLOWED_TYPES = {"CD", "MA_SA"}


@router.get("/sharepoint/sites")
def list_sites(user: dict = Depends(require("ADMIN", "AE_ENGINEER"))):
    """Every site that has a SharePoint folder and exists in the database. Admin only."""
    store, r = get_store(), repo()
    scope = site_scope(user)
    rows = {s["SITE_ID"]: s for s in r.select("CORE.SITE", scope or None, order_by="SITE_ID")}
    # Auto-provision folder for database sites if not present
    if hasattr(store, "site_exists") and hasattr(store, "create_site_folder"):
        for sid in rows:
            if not store.site_exists(sid):
                store.create_site_folder(sid)
    out = []
    for sid in store.list_site_ids():
        if sid not in rows:
            continue
        files = store.list_files(sid)
        s = rows.get(sid, {})
        out.append({"site_id": sid, "site_name": s.get("SITE_NAME") or "", "city": s.get("CITY") or "", "state": s.get("STATE") or "",
                    "stream": s.get("STREAM") or "", "files": len(files), "bytes": sum(f["size"] for f in files),
                    "in_database": True})
    return {"location": store.location, "provider": store.name, "sites": out}


@router.post("/admin/sites")
def create_site(body: SiteIn, user: dict = Depends(require("ADMIN"))):
    """Admin: create a site. This creates its folder tree in SharePoint and the site record, so the site shows up for uploads."""
    st = body.state.strip()
    if not st:
        raise ValidationError("State is required.")
    raw_sid = (body.site_id or "").strip()
    if not raw_sid or raw_sid.upper() == "AUTO":
        next_info = get_next_site_id(state=st, city=body.city)
        raw_sid = next_info["site_id"]
        if not raw_sid:
            raise ValidationError("Site ID could not be auto-generated. Please provide a 4-letter + 4-digit Site ID.")
    sid = validate_site_id(raw_sid)
    store, r = get_store(), repo()
    if r.select("CORE.SITE", {"SITE_ID": sid}):
        raise Conflict(f"Site {sid} already exists")
    if hasattr(store, "site_exists") and store.site_exists(sid):
        lib_root = getattr(store, "library_root", "Ericsson-Scoping/Sites")
        folder = {"path": f"{lib_root}/{sid}"}
    else:
        folder = store.create_site_folder(sid)                      # SharePoint first: if it fails, no database row is left behind
    row = {"SITE_ID": sid, "SITE_NAME": body.site_name.strip(), "MARKET": body.market or get_settings().get("app.market", ""),
           "CUSTOMER": get_settings().get("app.carrier", ""), "ADDRESS": body.address, "CITY": body.city.strip(), "STATE": st,
           "ZIP": body.zip, "LATITUDE": body.latitude, "LONGITUDE": body.longitude,
           "STRUCTURE_TYPE": body.structure_type, "HEIGHT_FT": body.height_ft, "SITE_STATUS": "New", "STREAM": body.stream,
           "WORKFLOW_STATE": "ASSIGNED", "ASSIGNED_DATE": now_iso()[:10], "UPDATED_AT": now_iso(), "UPDATED_BY": user["sub"]}
    r.insert("CORE.SITE", [row])
    AuditTrail.record(entity_type="SITE", entity_id=sid, action="CREATE",
                      after={"site_name": row["SITE_NAME"], "city": row["CITY"], "state": row["STATE"], "sharepoint_path": folder["path"]},
                      site_id=sid, source="api")
    return {"site": row, "sharepoint": folder}


class SiteUpdate(BaseModel):
    site_name: str | None = None
    city: str | None = None
    state: str | None = None
    address: str | None = None
    structure_type: Literal["Monopole", "Self-support tower", "Guyed tower", "Rooftop"] | None = None
    height_ft: float | None = None
    stream: Literal["BOM", "DESIGN", "DEPLOYMENT"] | None = None


@router.patch("/admin/sites/{site_id}")
def update_site(site_id: str, body: SiteUpdate, user: dict = Depends(require("ADMIN"))):
    """Admin: update site name, city, state, or other metadata."""
    sid = validate_site_id(site_id)
    r = repo()
    existing = r.select("CORE.SITE", {"SITE_ID": sid})
    if not existing:
        raise NotFound(f"Site {sid} not found")
    updates: dict = {}
    if body.site_name is not None and body.site_name.strip():
        updates["SITE_NAME"] = body.site_name.strip()
    if body.city is not None and body.city.strip():
        updates["CITY"] = body.city.strip()
    if body.state is not None and body.state.strip():
        updates["STATE"] = body.state.strip().upper()
    if body.address is not None:
        updates["ADDRESS"] = body.address.strip()
    if body.structure_type is not None:
        updates["STRUCTURE_TYPE"] = body.structure_type
    if body.height_ft is not None:
        updates["HEIGHT_FT"] = body.height_ft
    if body.stream is not None:
        updates["STREAM"] = body.stream
    if updates:
        updates["UPDATED_AT"] = now_iso()
        updates["UPDATED_BY"] = user["sub"]
        r.update("CORE.SITE", updates, {"SITE_ID": sid})
    return {"site": r.get("CORE.SITE", SITE_ID=sid)}


_SITE_CASCADE_TABLES = [
    "CORE.REDLINE_PROOF", "CORE.REDLINE", "CORE.RFI", "CORE.BOM_CHANGE", "CORE.BOM_LINE", "CORE.BOM_REVISION",
    "CORE.DISCREPANCY", "CORE.EHS_ALERT", "CORE.EQUIPMENT_DELTA", "CORE.DRIVER_LINE", "CORE.SITE_REQUIREMENT",
    "CORE.ESTIMATE", "CORE.EVIDENCE_FRAME", "CORE.FIELD_OBJECT", "CORE.REV0_LINE", "CORE.ANALYSIS_RESULT",
    "CORE.TRUNK_MEASURE", "CORE.SECTOR_INFO", "CORE.CONFIG_LINE", "CORE.EXTRACTED_COMPARISON_RECORD",
    "CORE.EXTRACTED_FIELD", "CORE.PIPELINE_RUN", "CORE.UPLOAD", "CORE.DOCUMENT", "CORE.MILESTONE", "CORE.SITE",
    "WF.COMMENT", "WF.NOTIFICATION", "WF.WORKFLOW_EVENT",
]


@router.delete("/admin/sites/{site_id}")
def delete_site(site_id: str, user: dict = Depends(require("ADMIN"))):
    """Admin: delete a site and all its associated records, run history, documents, and files."""
    sid = validate_site_id(site_id)
    r = repo()
    existing = r.select("CORE.SITE", {"SITE_ID": sid})
    if not existing:
        raise NotFound(f"Site {sid} not found")
    res = delete_site_cascade(r, sid, delete_files=True, deleted_by=user.get("sub", "admin"))
    return {"site_id": sid, **res}


@router.delete("/admin/sites")
def delete_all_sites(user: dict = Depends(require("ADMIN"))):
    """Admin: delete all sites and their associated pipeline data, run history, documents, and files."""
    r = repo()
    sites = [s["SITE_ID"] for s in r.select("CORE.SITE")]
    store = get_store()
    all_sids = sorted(set(sites) | set(store.list_site_ids()))
    results = {}
    for sid in all_sids:
        results[sid] = delete_site_cascade(r, sid, delete_files=True, deleted_by=user.get("sub", "admin"))
    AuditTrail.record(entity_type="SITE", entity_id="ALL", action="DELETE_ALL", after={"sites": list(results.keys())}, source="api")
    return {"status": "ok", "deleted_sites": results}


def sync_site_documents_to_db(site_id: str, r=None) -> list[dict]:
    """Sync disk/SharePoint documents for a site into CORE.DOCUMENT in the repository."""
    from dataclasses import asdict
    from scopeiq.db.repository import get_repository, now_iso
    from scopeiq.db.schema import tables
    from scopeiq.extract.registry import register_site_folder

    r = r or repo()
    st = get_settings()
    site_dir = st.path("paths.sites_dir") / site_id
    doc_paths: dict = {}
    upload_dir = Path(st.path("paths.upload_dir")) / site_id
    try:
        docs = register_site_folder(site_dir, site_id, upload_dir=upload_dir if upload_dir.is_dir() else None, paths=doc_paths)
        r.delete_where("CORE.DOCUMENT", {"SITE_ID": site_id})
        if docs:
            known = {c for t in tables() if t.fqn == "CORE.DOCUMENT" for c in t.column_names}
            rows = [
                dict(
                    {k.upper(): v for k, v in asdict(d).items() if k.upper() in known},
                    INSERTED_AT=now_iso(),
                    INSERTED_BY="sharepoint_sync",
                )
                for d in docs
            ]
            r.insert("CORE.DOCUMENT", rows)
        return [d.__dict__ for d in docs]
    except Exception as exc:
        return []


def _ae_folder_only(user: dict, folder: str) -> None:
    """An A&E engineer may open files in the CD and SA/MA folders only."""
    if user["role"] == "AE_ENGINEER" and folder not in {TYPE_FOLDERS[t] for t in AE_FILE_TYPES}:
        from scopeiq.common.errors import PermissionDenied
        raise PermissionDenied("An A&E engineer can open CD and SA/MA files only")


def _resolve_sharepoint_file_path(site_id: str, folder: str, file_name: str) -> Path | None:
    st = get_settings()
    sp_local = st.path("sharepoint.local_root")
    sp_lib = st.get("sharepoint.library_root", "Ericsson-Scoping/Sites")
    candidates = [
        Path(sp_local) / sp_lib / site_id / folder / file_name,
        Path(sp_local) / sp_lib / site_id / file_name,
        st.path("paths.sites_dir") / site_id / folder / file_name,
        st.path("paths.sites_dir") / site_id / file_name,
        Path(st.path("paths.upload_dir")) / site_id / folder / file_name,
        Path(st.path("paths.upload_dir")) / site_id / file_name,
    ]
    for p in candidates:
        if p.is_file():
            return p
    for root in [Path(sp_local) / sp_lib / site_id, st.path("paths.sites_dir") / site_id]:
        if root.is_dir():
            for p in root.rglob(file_name):
                if p.is_file():
                    return p
    return None


def _read_excel_sheets(path: Path) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheets = []
    try:
        for name in wb.sheetnames:
            ws = wb[name]
            all_rows = list(ws.iter_rows(values_only=True))
            if not all_rows:
                continue
            headers = [str(c) if c is not None else "" for c in all_rows[0]]
            while headers and headers[-1] == "":
                headers.pop()
            col_count = len(headers)
            data_rows = []
            for row in all_rows[1:1001]:
                vals = list(row[:col_count])
                if any(v is not None and str(v).strip() != "" for v in vals):
                    data_rows.append([v if isinstance(v, (int, float, bool, str)) or v is None else str(v) for v in vals])
            sheets.append({
                "name": name,
                "columns": headers,
                "rows": data_rows,
                "total_rows": max(0, len(all_rows) - 1),
            })
    finally:
        wb.close()
    return sheets


def _read_csv_sheets(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        all_rows = list(reader)
        headers = all_rows[0] if all_rows else []
        data_rows = all_rows[1:1001] if len(all_rows) > 1 else []
        return [{
            "name": path.stem,
            "columns": headers,
            "rows": data_rows,
            "total_rows": max(0, len(all_rows) - 1),
        }]


def _build_file_preview(
    path: Path,
    file_name: str,
    download_url: str,
    site_id: str | None = None,
    folder: str | None = None,
    doc_id: str | None = None,
) -> dict:
    ext = path.suffix.lower().lstrip(".")
    st_stat = path.stat()
    size = st_stat.st_size
    mod = datetime.fromtimestamp(st_stat.st_mtime, timezone.utc).isoformat()
    doc_type = detect_doc_type(file_name)

    base = {
        "file_name": file_name,
        "format": ext.upper(),
        "doc_type": doc_type,
        "size": size,
        "modified": mod,
        "download_url": download_url,
        "site_id": site_id,
        "folder": folder,
        "doc_id": doc_id,
    }

    if ext in ("xlsx", "xls"):
        try:
            sheets = _read_excel_sheets(path)
            return {
                **base,
                "type": "spreadsheet",
                "sheets": sheets,
                "summary": {
                    "total_sheets": len(sheets),
                    "total_rows": sum(s.get("total_rows", 0) for s in sheets),
                },
            }
        except Exception as exc:
            return {**base, "type": "binary", "error": f"Could not parse Excel preview: {exc}"}

    if ext == "csv":
        try:
            sheets = _read_csv_sheets(path)
            return {
                **base,
                "type": "spreadsheet",
                "sheets": sheets,
                "summary": {
                    "total_sheets": 1,
                    "total_rows": sheets[0].get("total_rows", 0) if sheets else 0,
                },
            }
        except Exception as exc:
            return {**base, "type": "text", "content": path.read_text(encoding="utf-8", errors="replace")[:100000]}

    inline_url = f"{download_url}{'&' if '?' in download_url else '?'}disposition=inline"

    if ext == "pdf":
        pdf_pages = []
        total_pages = 0
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz
            doc = fitz.open(str(path))
            total_pages = len(doc)
            # Render up to 50 pages for smooth scrollable preview
            max_render = min(total_pages, 50)
            for p_idx in range(max_render):
                page = doc[p_idx]
                pix = page.get_pixmap(dpi=130)
                img_bytes = pix.tobytes("jpeg", jpg_quality=82)
                b64 = base64.b64encode(img_bytes).decode("ascii")
                pdf_pages.append({
                    "page_number": p_idx + 1,
                    "width": pix.width,
                    "height": pix.height,
                    "image": f"data:image/jpeg;base64,{b64}",
                })
        except Exception as p_err:
            pass

        return {
            **base,
            "type": "pdf",
            "file_url": inline_url,
            "pages": pdf_pages,
            "total_pages": total_pages or (len(pdf_pages) if pdf_pages else None),
        }

    if ext in ("jpg", "jpeg", "png", "webp", "tif", "tiff", "gif", "svg"):
        return {**base, "type": "image", "file_url": inline_url}

    if ext in ("mp4", "mov", "webm", "avi", "m4v"):
        return {**base, "type": "video", "file_url": inline_url}

    if ext == "json":
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            parsed = json.loads(raw)
            return {**base, "type": "json", "content": parsed, "raw": raw}
        except Exception:
            return {**base, "type": "text", "content": path.read_text(encoding="utf-8", errors="replace")[:100000]}

    if ext in ("txt", "md", "yaml", "yml", "log", "xml", "ini", "cfg"):
        return {**base, "type": "text", "content": path.read_text(encoding="utf-8", errors="replace")[:100000]}

    if ext in ("dxf", "dwg"):
        cad_pages = []
        if ext == "dxf":
            try:
                import ezdxf
                import pymupdf
                from ezdxf.addons.drawing import Frontend, RenderContext, layout
                from ezdxf.addons.drawing import pymupdf as mupdf_backend
                from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
                from ezdxf.math import BoundingBox2d

                doc = ezdxf.readfile(str(path))
                msp = doc.modelspace()
                cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.COLOR)

                SHEETS = ["T-1", "A-2", "A-3", "A-4", "E-1"]
                GAP, W, H = 400, 340, 220

                def _ref_x(e):
                    try:
                        t = e.dxftype()
                        if t in ("TEXT", "MTEXT", "INSERT", "POINT"):
                            return float(e.dxf.insert[0])
                        elif t == "LINE":
                            return float(e.dxf.start[0])
                        elif t in ("LWPOLYLINE", "POLYLINE"):
                            return float(e.vertices()[0][0])
                    except Exception:
                        pass
                    return 0.0

                groups = {}
                for e in msp:
                    groups.setdefault(int(_ref_x(e) // GAP), []).append(e)

                matched_sheets = [s for i, s in enumerate(SHEETS) if groups.get(i)]
                if len(matched_sheets) >= 2:
                    for i, sheet_name in enumerate(SHEETS):
                        ents = groups.get(i, [])
                        if not ents:
                            continue
                        backend = mupdf_backend.PyMuPdfBackend()
                        fe = Frontend(RenderContext(doc), backend, config=cfg)
                        fe.set_background("#ffffff")
                        fe.draw_entities(ents)
                        page_layout = layout.Page(17, 11, layout.Units.inch)
                        data = backend.get_pdf_bytes(
                            page_layout,
                            settings=layout.Settings(fit_page=True),
                            render_box=BoundingBox2d([(i * GAP - 3, -3), (i * GAP + W + 3, H + 3)]),
                        )
                        with pymupdf.open("pdf", data) as pdoc:
                            pix = pdoc[0].get_pixmap(dpi=110)
                            img_bytes = pix.tobytes("jpeg", jpg_quality=80)
                            b64 = base64.b64encode(img_bytes).decode("ascii")
                            cad_pages.append({
                                "sheet_name": sheet_name,
                                "page_number": len(cad_pages) + 1,
                                "width": pix.width,
                                "height": pix.height,
                                "image": f"data:image/jpeg;base64,{b64}",
                            })
                else:
                    backend = mupdf_backend.PyMuPdfBackend()
                    fe = Frontend(RenderContext(doc), backend, config=cfg)
                    fe.set_background("#ffffff")
                    fe.draw_layout(msp)
                    page_layout = layout.Page(17, 11, layout.Units.inch)
                    data = backend.get_pdf_bytes(page_layout, settings=layout.Settings(fit_page=True))
                    with pymupdf.open("pdf", data) as pdoc:
                        pix = pdoc[0].get_pixmap(dpi=110)
                        img_bytes = pix.tobytes("jpeg", jpg_quality=80)
                        b64 = base64.b64encode(img_bytes).decode("ascii")
                        cad_pages.append({
                            "sheet_name": "Model",
                            "page_number": 1,
                            "width": pix.width,
                            "height": pix.height,
                            "image": f"data:image/jpeg;base64,{b64}",
                        })
            except Exception:
                pass

        return {
            **base,
            "type": "cad",
            "category": "CAD Drawing",
            "pages": cad_pages,
            "total_pages": len(cad_pages) if cad_pages else None,
            "note": "CAD drawings can be downloaded for viewing in AutoCAD / DWG TrueView or reviewed via rendered PDF revisions.",
        }

    if ext in ("laz", "las"):
        try:
            import laspy
            import numpy as np
            from scopeiq.extract.drone import read_pointcloud

            objs, meta = read_pointcloud(path, rooftop=False)
            obj_rows = [
                {
                    "object_id": o.object_id,
                    "object_type": o.object_type,
                    "sector": o.sector,
                    "bearing_deg": float(o.bearing_deg) if o.bearing_deg is not None else None,
                    "facing_az_deg": float(o.facing_az_deg) if o.facing_az_deg is not None else None,
                    "center_height_ft": float(o.center_height_ft) if o.center_height_ft is not None else None,
                    "dimensions_in": [round(float(x), 1) for x in o.dims_in] if o.dims_in else None,
                    "confidence": round(float(o.confidence) * 100, 1) if o.confidence else 0,
                    "method": o.method,
                }
                for o in objs
            ]

            las = laspy.read(str(path))
            xyz = np.c_[las.x, las.y, las.z].astype(float)
            cls = np.asarray(las.classification)

            mask_eq = np.isin(cls, [64, 65, 66, 68])
            center = xyz[mask_eq].mean(axis=0) if mask_eq.any() else xyz.mean(axis=0)
            norm_xyz = xyz - center

            sample_indices = []
            targets = [(64, 1000), (65, 600), (66, 1000), (68, 400), (6, 800), (2, 200)]
            for c_val, limit in targets:
                idx = np.where(cls == c_val)[0]
                if len(idx) > limit:
                    idx = np.random.choice(idx, limit, replace=False)
                sample_indices.extend(idx)

            if not sample_indices:
                step = max(1, len(xyz) // 3500)
                sample_indices = list(range(0, len(xyz), step))

            sampled_pts = norm_xyz[sample_indices]
            sampled_cls = cls[sample_indices]
            points_payload = [
                [round(float(p[0]), 2), round(float(p[1]), 2), round(float(p[2]), 2), int(c)]
                for p, c in zip(sampled_pts, sampled_cls)
            ]

            return {
                **base,
                "type": "pointcloud",
                "category": "Drone LiDAR Point Cloud",
                "points": points_payload,
                "objects": obj_rows,
                "stats": {
                    "total_points": meta.get("points", len(xyz)),
                    "rendered_points": len(points_payload),
                    "equipment_objects": len(obj_rows),
                    "roof_z_m": meta.get("roof_z_m", 0.0),
                    "class_counts": {int(k): int(v) for k, v in meta.get("classes", {}).items()},
                },
            }
        except Exception as exc:
            return {
                **base,
                "type": "pointcloud",
                "category": "Drone LiDAR Point Cloud",
                "note": f"Point cloud preview: {exc}",
                "error": str(exc),
            }

    return {**base, "type": "binary", "note": f"Binary file ({ext.upper()})"}


@router.get("/sharepoint/sites/{site_id}/files/download")
def download_sharepoint_file(
    site_id: str,
    folder: str,
    file_name: str,
    disposition: str = "inline",
    user: dict = Depends(current_user),
):
    """Download or stream inline a file from the site's SharePoint / input folder."""
    import mimetypes

    sid = validate_site_id(site_id)
    if repo().select("CORE.SITE", {"SITE_ID": sid}):
        check_site_scope(user, sid)
    _ae_folder_only(user, folder)
    path = _resolve_sharepoint_file_path(sid, folder, file_name)
    if not path or not path.is_file():
        raise NotFound(f"File '{file_name}' not found for site {sid}")

    guessed, _ = mimetypes.guess_type(path.name)
    ext = path.suffix.lower()
    if ext == ".pdf":
        media_type = "application/pdf"
    elif ext in (".jpg", ".jpeg"):
        media_type = "image/jpeg"
    elif ext == ".png":
        media_type = "image/png"
    elif ext == ".mp4":
        media_type = "video/mp4"
    elif ext in (".laz", ".las"):
        media_type = "application/octet-stream"
    else:
        media_type = guessed or "application/octet-stream"

    disp_type = "attachment" if disposition.lower() == "attachment" else "inline"
    return FileResponse(
        path,
        filename=file_name,
        media_type=media_type,
        content_disposition_type=disp_type,
    )


@router.get("/sharepoint/sites/{site_id}/files/preview")
def preview_sharepoint_file(
    site_id: str,
    folder: str,
    file_name: str,
    user: dict = Depends(current_user),
):
    """Return an interactive preview payload (spreadsheet, pdf, image, video, json, text) for a site file."""
    sid = validate_site_id(site_id)
    if repo().select("CORE.SITE", {"SITE_ID": sid}):
        check_site_scope(user, sid)
    _ae_folder_only(user, folder)
    path = _resolve_sharepoint_file_path(sid, folder, file_name)
    if not path or not path.is_file():
        raise NotFound(f"File '{file_name}' not found for site {sid}")
    download_url = f"/sharepoint/sites/{sid}/files/download?folder={quote(folder)}&file_name={quote(file_name)}"
    return _build_file_preview(path, file_name, download_url, site_id=sid, folder=folder)


@router.get("/sharepoint/sites/{site_id}/files")
def site_files(site_id: str, user: dict = Depends(require("ADMIN", "AE_ENGINEER"))):
    sid = validate_site_id(site_id)
    store = get_store()
    if not store.site_exists(sid):
        raise NotFound(f"Site {sid} has no folder in SharePoint")
    if repo().select("CORE.SITE", {"SITE_ID": sid}):
        check_site_scope(user, sid)

    # In local mode, ensure files from paths.sites_dir are mirrored into local SharePoint if not already there
    if getattr(store, "name", "") == "local":
        try:
            import shutil
            st = get_settings()
            sites_dir = st.path("paths.sites_dir") / sid
            if sites_dir.is_dir():
                dest_dir = getattr(store, "_site_dir")(sid)
                for p in sites_dir.rglob("*"):
                    if p.is_file():
                        rel = p.relative_to(sites_dir)
                        target = dest_dir / rel
                        if not target.is_file():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(p, target)
        except Exception:
            pass

    files = store.list_files(sid)
    for f in files:
        f["doc_type"] = detect_doc_type(f["name"])
    if user["role"] == "AE_ENGINEER":                      # an A&E engineer sees the CD and SA/MA files, not the rest of the site's documents
        files = [f for f in files if f["doc_type"] in AE_FILE_TYPES]
    return {"site_id": sid, "location": f"{store.location} / {sid}", "files": files}


@router.delete("/sharepoint/sites/{site_id}/files")
def delete_file(
    site_id: str,
    folder: str,
    file_name: str,
    user: dict = Depends(require("ADMIN", "AE_ENGINEER")),
):
    """Delete a specific file from a site's SharePoint folder."""
    sid = validate_site_id(site_id)
    store = get_store()
    if not store.site_exists(sid):
        raise NotFound(f"Site {sid} has no folder in SharePoint")
    if repo().select("CORE.SITE", {"SITE_ID": sid}):
        check_site_scope(user, sid)

    deleted = store.delete_file(sid, folder, file_name)
    if not deleted:
        raise NotFound(f"File '{file_name}' not found in folder '{folder}' for site {sid}")

    try:
        r = repo()
        r.delete_where("CORE.DOCUMENT", {"SITE_ID": sid, "FILE_NAME": file_name})
        sync_site_documents_to_db(sid, r)
    except Exception:
        pass

    AuditTrail.record(
        entity_type="SHAREPOINT_FILE",
        entity_id=f"{sid}/{folder}/{file_name}",
        action="DELETE_FILE",
        site_id=sid,
        source="sharepoint",
        comment=f"Deleted file {file_name} from {folder} by {user.get('user_id')}",
    )
    return {"site_id": sid, "folder": folder, "file_name": file_name, "deleted": True}


from scopeiq.services.document_compare import inspect_file_against_site


@router.post("/sharepoint/sites/{site_id}/check-content")
async def check_content(site_id: str, file: UploadFile = File(...), doc_type: str | None = Form(default=None),
                        user: dict = Depends(require("ADMIN", "AE_ENGINEER"))):
    """Pre-upload inspection for SharePoint: checks if file data is NEW, DUPLICATE, or UPDATED with additions."""
    sid = validate_site_id(site_id)
    store = get_store()
    if not store.site_exists(sid):
        raise NotFound(f"Site {sid} has no folder in SharePoint")
    if user.get("role") == "AE_ENGINEER":
        from scopeiq.common.errors import PermissionDenied
        detected = detect_doc_type(file.filename or "")
        eff_type = doc_type if doc_type and doc_type != "AUTO" else detected
        if not eff_type or eff_type not in AE_ENGINEER_ALLOWED_TYPES or (detected and detected not in AE_ENGINEER_ALLOWED_TYPES):
            raise PermissionDenied(
                f"A&E Engineers can only upload CD and SA_MA documents. File '{file.filename}' is {f'a {detected}' if detected else 'not a CD or SA_MA'} document.",
                details={"allowed": sorted(AE_ENGINEER_ALLOWED_TYPES)},
            )
    data = await file.read()
    if not data:
        raise ValidationError("File is empty")
    inspection = inspect_file_against_site(sid, file.filename or "", data, doc_type=doc_type, repo=repo())
    return inspection.to_dict()


@router.post("/sharepoint/sites/{site_id}/upload")
async def upload(site_id: str, file: UploadFile = File(...), doc_type: str | None = Form(default=None),
                 replace_file: str | None = Form(default=None), confirm_duplicate: bool = Form(default=False),
                 user: dict = Depends(require("ADMIN", "AE_ENGINEER"))):
    """Upload one file into the selected site's folder. The site comes from the path, so a file can only go to that one site."""
    sid = validate_site_id(site_id)
    store = get_store()
    if not store.site_exists(sid):
        raise NotFound(f"Site {sid} has no folder in SharePoint")
    if repo().select("CORE.SITE", {"SITE_ID": sid}):
        check_site_scope(user, sid)
    # A&E Engineers may only upload CD and MA_SA (SA_MA) documents.
    # If doc_type is not provided or set to AUTO, detect it from the filename.
    # Disallowed document types (e.g. RFDS, BOM, Drone) or unclassifiable files are blocked.
    if user.get("role") == "AE_ENGINEER":
        from scopeiq.common.errors import PermissionDenied
        detected = detect_doc_type(file.filename or "")
        eff_type = doc_type if doc_type and doc_type != "AUTO" else detected
        if not eff_type or eff_type not in AE_ENGINEER_ALLOWED_TYPES:
            raise PermissionDenied(
                f"A&E Engineers can only upload CD and SA_MA documents. "
                f"File '{file.filename}' is {f'a {detected}' if detected else 'not a CD or SA_MA'} document.",
                details={"allowed": sorted(AE_ENGINEER_ALLOWED_TYPES)},
            )
        if detected and detected not in AE_ENGINEER_ALLOWED_TYPES:
            raise PermissionDenied(
                f"A&E Engineers can only upload CD and SA_MA documents. "
                f"File '{file.filename}' is a {detected} document.",
                details={"allowed": sorted(AE_ENGINEER_ALLOWED_TYPES)},
            )
        doc_type = eff_type
    if doc_type and doc_type not in TYPE_FOLDERS:
        raise ValidationError(f"Unknown document type {doc_type}", details={"allowed": list(TYPE_FOLDERS)})
    data = await file.read()
    # A file whose content is already on the site is refused here, whatever the screen did, unless it replaces that file or the caller confirms it.
    already = inspect_file_against_site(sid, file.filename or "", data, doc_type=doc_type, repo=repo()) if data else None
    if already and already.status == "DUPLICATE" and not (replace_file or confirm_duplicate):
        raise Conflict(f"Already exists! This file has identical content to '{already.existing_file}'. Upload is not required.",
                       details={"status": "DUPLICATE", "is_duplicate": True, "already_exists": True, "duplicate_of": already.existing_file,
                                "file_name": file.filename, "message": f"The content of this file is identical to '{already.existing_file}'."})
    saved = store.upload(sid, file.filename or "", data, doc_type or None, replace_file=replace_file)
    inspection = inspect_file_against_site(sid, file.filename or "", data, doc_type=doc_type, repo=repo(), exclude_filename=file.filename)
    AuditTrail.record(entity_type="SHAREPOINT_FILE", entity_id=f"{sid}/{saved['folder']}/{saved['name']}",
                      action="REPLACE_FILE" if (replace_file or saved.get("replaced")) else "UPLOAD",
                      after={"doc_type": saved["doc_type"], "size": saved["size"], "replaced": saved["replaced"],
                             "replace_file": replace_file}, site_id=sid, source="api")
    sync_site_documents_to_db(sid, repo())
    out = {"site_id": sid, **saved}
    if inspection.status == "UPDATED":
        out["is_updated"] = True
        out["is_duplicate"] = False
        out["already_exists"] = False
        out["duplicate_of"] = None
        out["updated_from"] = inspection.existing_file
        out["diff"] = inspection.to_dict()["diff"]
        out["message"] = f"Changes detected: Contains updates compared to '{inspection.existing_file}'."
    elif inspection.status == "DUPLICATE":
        out["is_duplicate"] = True
        out["already_exists"] = True
        out["is_updated"] = False
        out["updated_from"] = None
        out["diff"] = None
        out["duplicate_of"] = inspection.existing_file
        out["message"] = f"Already exists: Identical content matches '{inspection.existing_file}'."
    return out

