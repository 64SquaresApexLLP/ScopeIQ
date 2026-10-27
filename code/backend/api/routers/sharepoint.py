"""SharePoint: sites (one folder per site), the admin action that creates a site + its folder, and file upload into the selected
site's folder. The library behind it is chosen by `sharepoint.provider` (local folder or Microsoft Graph) - see
scopeiq/integrations/sharepoint.py."""
from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from api.deps import check_site_scope, current_user, repo, require, site_scope
from scopeiq.common.audit import AuditTrail
from scopeiq.common.errors import Conflict, NotFound, ValidationError
from scopeiq.config import get_settings
from scopeiq.db.repository import now_iso
from scopeiq.integrations.sharepoint import TYPE_FOLDERS, detect_doc_type, get_store, validate_site_id

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


@router.get("/sharepoint/sites")
def list_sites(user: dict = Depends(require("ADMIN"))):
    """Every site that has a SharePoint folder, with its file count. Admin only."""
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
        if scope and sid not in rows:
            continue
        files = store.list_files(sid)
        s = rows.get(sid, {})
        out.append({"site_id": sid, "site_name": s.get("SITE_NAME") or "", "city": s.get("CITY") or "", "state": s.get("STATE") or "",
                    "stream": s.get("STREAM") or "", "files": len(files), "bytes": sum(f["size"] for f in files),
                    "in_database": sid in rows})
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


@router.get("/sharepoint/sites/{site_id}/files")
def site_files(site_id: str, user: dict = Depends(require("ADMIN"))):
    sid = validate_site_id(site_id)
    store = get_store()
    if not store.site_exists(sid):
        raise NotFound(f"Site {sid} has no folder in SharePoint")
    if repo().select("CORE.SITE", {"SITE_ID": sid}):
        check_site_scope(user, sid)
    files = store.list_files(sid)
    for f in files:
        f["doc_type"] = detect_doc_type(f["name"])
    return {"site_id": sid, "location": f"{store.location} / {sid}", "files": files}


from scopeiq.services.document_compare import inspect_file_against_site


@router.post("/sharepoint/sites/{site_id}/check-content")
async def check_content(site_id: str, file: UploadFile = File(...), doc_type: str | None = Form(default=None),
                        user: dict = Depends(require("ADMIN"))):
    """Pre-upload inspection for SharePoint: checks if file data is NEW, DUPLICATE, or UPDATED with additions."""
    sid = validate_site_id(site_id)
    store = get_store()
    if not store.site_exists(sid):
        raise NotFound(f"Site {sid} has no folder in SharePoint")
    data = await file.read()
    if not data:
        raise ValidationError("File is empty")
    inspection = inspect_file_against_site(sid, file.filename or "", data, doc_type=doc_type, repo=repo())
    return inspection.to_dict()


@router.post("/sharepoint/sites/{site_id}/upload")
async def upload(site_id: str, file: UploadFile = File(...), doc_type: str | None = Form(default=None),
                 replace_file: str | None = Form(default=None),
                 user: dict = Depends(require("ADMIN"))):
    """Upload one file into the selected site's folder. The site comes from the path, so a file can only go to that one site."""
    sid = validate_site_id(site_id)
    store = get_store()
    if not store.site_exists(sid):
        raise NotFound(f"Site {sid} has no folder in SharePoint")
    if repo().select("CORE.SITE", {"SITE_ID": sid}):
        check_site_scope(user, sid)
    if doc_type and doc_type not in TYPE_FOLDERS:
        raise ValidationError(f"Unknown document type {doc_type}", details={"allowed": list(TYPE_FOLDERS)})
    data = await file.read()
    saved = store.upload(sid, file.filename or "", data, doc_type or None, replace_file=replace_file)
    inspection = inspect_file_against_site(sid, file.filename or "", data, doc_type=doc_type, repo=repo(), exclude_filename=file.filename)
    AuditTrail.record(entity_type="SHAREPOINT_FILE", entity_id=f"{sid}/{saved['folder']}/{saved['name']}",
                      action="REPLACE_FILE" if (replace_file or saved.get("replaced")) else "UPLOAD",
                      after={"doc_type": saved["doc_type"], "size": saved["size"], "replaced": saved["replaced"],
                             "replace_file": replace_file}, site_id=sid, source="api")
    out = {"site_id": sid, **saved}
    if inspection.status == "UPDATED":
        out["is_updated"] = True
        out["updated_from"] = inspection.existing_file
        out["diff"] = inspection.to_dict()["diff"]
        out["message"] = f"Changes detected: Contains updates compared to '{inspection.existing_file}'."
    elif inspection.status == "DUPLICATE":
        out["is_duplicate"] = True
        out["already_exists"] = True
        out["duplicate_of"] = inspection.existing_file
        out["message"] = f"Already exists: Identical content matches '{inspection.existing_file}'."
    return out

