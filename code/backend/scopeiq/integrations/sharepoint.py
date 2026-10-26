"""SharePoint document library: one folder per site, files uploaded into that site's folder only.

The pipeline reads its inputs from site folders (rfds / cds / drone / ma_sa / bom). This module is the single place that
talks to the library, behind one interface with two providers chosen by `sharepoint.provider`:

* LocalSharePoint  - a folder on disk that stands in for the document library. Works offline; used for the demo and the tests.
* GraphSharePoint  - the real SharePoint through Microsoft Graph (client-credentials app registration). Needs a tenant; it has been
                     written against the Graph documentation and is covered by request-shape tests only, not yet run against a live tenant.

Library layout (same as the sample site folders the engine already reads):
    <library_root>/<SITE_ID>/rfds | cds | ma_sa | bom | drone | drone/imagery | drone/video
"""
from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from scopeiq.common.errors import AppError, NotFound, ValidationError
from scopeiq.common.logging import get_logger
from scopeiq.config import get_settings
from scopeiq.extract.registry import classify

log = get_logger(__name__)

SITE_ID_RE = re.compile(r"^[A-Z]{4}\d{4}$")          # same shape the registry expects, e.g. TXDA1024
# \b would not match before "_" (underscore is a word character), so use explicit look-arounds
OTHER_SITE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{4}\d{4})(?!\d)")
SITE_FOLDERS = ["rfds", "cds", "ma_sa", "bom", "drone", "drone/imagery", "drone/video"]
# document type -> folder, identical to the app's upload screen
TYPE_FOLDERS = {"RFDS": "rfds", "CD": "cds", "MA_SA": "ma_sa", "BOM_REV0": "bom", "DRONE_META": "drone", "DRONE_VENDOR": "drone",
                "DRONE_POINTCLOUD": "drone", "DRONE_IMAGE": "drone/imagery", "DRONE_VIDEO": "drone/video"}


class SharePointError(AppError):
    code, http_status, default_message = "SIQ-SP-502", 502, "SharePoint request failed"


def validate_site_id(site_id: str) -> str:
    site_id = (site_id or "").strip().upper()
    if not SITE_ID_RE.match(site_id):
        raise ValidationError("Site id must be 4 letters + 4 digits, for example TXDA1024", details={"site_id": site_id})
    return site_id


def detect_doc_type(file_name: str) -> str | None:
    """Document type from the file name (same naming convention the pipeline uses), or None if it cannot be told."""
    for typ, folder in TYPE_FOLDERS.items():
        if classify(f"{folder}/{file_name}") == typ:
            return typ
    return None


def safe_file_name(name: str) -> str:
    name = Path((name or "").replace("\\", "/")).name.strip()
    if not name or name in (".", "..") or any(ord(c) < 32 for c in name) or any(c in name for c in '<>:"|?*'):
        raise ValidationError("File name is missing or contains characters SharePoint does not allow")
    return name


def check_belongs_to_site(site_id: str, file_name: str) -> None:
    """A file named for another site must not land in this site's folder (same guard as the pipeline's registry)."""
    other = [s for s in OTHER_SITE_RE.findall(file_name) if s != site_id]
    if other:
        raise ValidationError(f"'{file_name}' is named for site {other[0]}, but {site_id} is selected",
                              details={"selected_site": site_id, "file_site": other[0]})


class SharePointStore(ABC):
    name = "base"

    @property
    @abstractmethod
    def location(self) -> str:
        """Human-readable library location, shown in the UI."""

    @abstractmethod
    def site_exists(self, site_id: str) -> bool: ...

    @abstractmethod
    def create_site_folder(self, site_id: str) -> dict: ...

    @abstractmethod
    def list_site_ids(self) -> list[str]: ...

    @abstractmethod
    def list_files(self, site_id: str) -> list[dict]: ...

    @abstractmethod
    def save_file(self, site_id: str, folder: str, file_name: str, data: bytes) -> dict: ...

    # shared behaviour -----------------------------------------------------------------------------------------------
    def upload(self, site_id: str, file_name: str, data: bytes, doc_type: str | None = None) -> dict:
        """Validate and store one file in the selected site's folder (and nowhere else)."""
        site_id = validate_site_id(site_id)
        if not self.site_exists(site_id):
            raise NotFound(f"Site {site_id} has no folder in SharePoint - ask an admin to create the site first")
        file_name = safe_file_name(file_name)
        check_belongs_to_site(site_id, file_name)
        if not data:
            raise ValidationError(f"'{file_name}' is empty")
        limit = int(get_settings().get("sharepoint.max_upload_mb", 400)) * 1024 * 1024
        if len(data) > limit:
            raise ValidationError(f"'{file_name}' is larger than {limit // (1024 * 1024)} MB")
        doc_type = doc_type or detect_doc_type(file_name)
        if doc_type not in TYPE_FOLDERS:
            raise ValidationError(f"Cannot tell the document type of '{file_name}'. Rename it with the site convention "
                                  f"(e.g. {site_id}_CD_REV2.pdf, {site_id}_RFDS_R4.xlsx) or choose the type.",
                                  details={"allowed_types": list(TYPE_FOLDERS)})
        folder = TYPE_FOLDERS[doc_type]
        digest = hashlib.sha256(data).hexdigest()
        same = [f for f in self.list_files(site_id) if f.get("hash") == digest and f["name"] != file_name]
        saved = self.save_file(site_id, folder, file_name, data)
        saved.update({"doc_type": doc_type, "hash": digest, "duplicate_of": same[0]["name"] if same else None})
        log.info("uploaded %s (%s) to %s/%s", file_name, doc_type, site_id, folder, extra={"site_id": site_id})
        return saved


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================================================== local
class LocalSharePoint(SharePointStore):
    name = "local"

    def __init__(self, root: Path, library_root: str):
        self.base = Path(root) / library_root
        self.library_root = library_root
        self.base.mkdir(parents=True, exist_ok=True)

    @property
    def location(self) -> str:
        return f"SharePoint (local library) / {self.library_root}"

    def _site_dir(self, site_id: str) -> Path:
        site_id = validate_site_id(site_id)
        d = (self.base / site_id).resolve()
        if self.base.resolve() not in d.parents:
            raise ValidationError("Invalid site folder")
        return d

    def site_exists(self, site_id: str) -> bool:
        return self._site_dir(site_id).is_dir()

    def create_site_folder(self, site_id: str) -> dict:
        d = self._site_dir(site_id)
        for f in SITE_FOLDERS:
            (d / f).mkdir(parents=True, exist_ok=True)
        return {"site_id": validate_site_id(site_id), "path": f"{self.library_root}/{site_id}", "folders": SITE_FOLDERS}

    def list_site_ids(self) -> list[str]:
        return sorted(p.name for p in self.base.iterdir() if p.is_dir() and SITE_ID_RE.match(p.name))

    def list_files(self, site_id: str) -> list[dict]:
        d = self._site_dir(site_id)
        if not d.is_dir():
            return []
        out = []
        for p in sorted(x for x in d.rglob("*") if x.is_file()):
            st = p.stat()
            out.append({"name": p.name, "folder": p.parent.relative_to(d).as_posix(), "size": st.st_size,
                        "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                        "hash": hashlib.sha256(p.read_bytes()).hexdigest() if st.st_size <= 64 * 1024 * 1024 else None})
        return out

    def save_file(self, site_id: str, folder: str, file_name: str, data: bytes) -> dict:
        if folder not in SITE_FOLDERS:
            raise ValidationError(f"Unknown folder {folder}")
        d = self._site_dir(site_id)
        dest = (d / folder / file_name).resolve()
        if d.resolve() not in dest.parents:
            raise ValidationError("Invalid target path")
        dest.parent.mkdir(parents=True, exist_ok=True)
        replaced = dest.exists()
        dest.write_bytes(data)
        return {"name": file_name, "folder": folder, "size": len(data), "modified": _now(), "replaced": replaced,
                "path": f"{self.library_root}/{site_id}/{folder}/{file_name}"}


# =============================================================================================================== graph
class GraphSharePoint(SharePointStore):
    """Microsoft Graph provider. App registration needs the application permission Sites.Selected (preferred, granted on the one
    site) or Sites.ReadWrite.All, with admin consent. Configure sharepoint.graph.* (secret via environment variable)."""
    name = "graph"
    GRAPH = "https://graph.microsoft.com/v1.0"
    SIMPLE_LIMIT = 4 * 1024 * 1024                  # Graph's simple upload limit
    CHUNK = 320 * 1024 * 10                         # upload-session chunks must be multiples of 320 KiB

    def __init__(self, cfg: dict, library_root: str, transport=None):
        import httpx
        missing = [k for k in ("tenant_id", "client_id", "client_secret", "site_hostname", "site_path") if not cfg.get(k)]
        if missing:
            raise SharePointError("SharePoint (Graph) is not configured", details={"missing": missing})
        self.cfg, self.library_root = cfg, library_root.strip("/")
        self.http = httpx.Client(timeout=60, transport=transport)
        self._token: tuple[str, float] | None = None
        self._drive: str | None = None

    @property
    def location(self) -> str:
        return f"SharePoint ({self.cfg['site_hostname']}{self.cfg['site_path']}) / {self.cfg.get('drive_name', 'Documents')} / {self.library_root}"

    def _auth(self) -> dict:
        import time
        if not self._token or self._token[1] < time.time() + 60:
            r = self.http.post(f"https://login.microsoftonline.com/{self.cfg['tenant_id']}/oauth2/v2.0/token",
                               data={"client_id": self.cfg["client_id"], "client_secret": self.cfg["client_secret"],
                                     "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"})
            if r.status_code != 200:
                raise SharePointError("Could not sign in to Microsoft Graph", details={"status": r.status_code})
            j = r.json()
            self._token = (j["access_token"], time.time() + int(j.get("expires_in", 3600)))
        return {"Authorization": f"Bearer {self._token[0]}"}

    def _call(self, method: str, url: str, ok=(200, 201, 202, 204), **kw):
        r = self.http.request(method, url if url.startswith("http") else self.GRAPH + url, headers={**self._auth(), **kw.pop("headers", {})}, **kw)
        if r.status_code not in ok:
            raise SharePointError(f"SharePoint returned {r.status_code}", details={"url": url.split("?")[0], "body": r.text[:300]})
        return r

    def _drive_id(self) -> str:
        if not self._drive:
            site = self._call("GET", f"/sites/{self.cfg['site_hostname']}:{self.cfg['site_path']}").json()["id"]
            drives = self._call("GET", f"/sites/{site}/drives").json().get("value", [])
            want = self.cfg.get("drive_name") or "Documents"
            d = next((x for x in drives if x["name"] == want), None)
            if not d:
                raise SharePointError(f"Document library '{want}' not found", details={"available": [x["name"] for x in drives]})
            self._drive = d["id"]
        return self._drive

    def _item(self, path: str) -> str:
        from urllib.parse import quote
        return f"/drives/{self._drive_id()}/root:/{quote(path.strip('/'))}"

    def _mkdir(self, parent: str, name: str) -> None:
        from urllib.parse import quote
        url = f"/drives/{self._drive_id()}/root/children" if not parent else f"/drives/{self._drive_id()}/root:/{quote(parent)}:/children"
        r = self.http.post(self.GRAPH + url, headers=self._auth(),
                           json={"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"})
        if r.status_code not in (200, 201, 409):            # 409 = already there
            raise SharePointError(f"Could not create folder {name}", details={"status": r.status_code, "body": r.text[:300]})

    def _ensure_path(self, path: str) -> None:
        acc = ""
        for part in [p for p in path.split("/") if p]:
            self._mkdir(acc, part)
            acc = f"{acc}/{part}".strip("/")

    def site_exists(self, site_id: str) -> bool:
        r = self.http.get(self.GRAPH + self._item(f"{self.library_root}/{validate_site_id(site_id)}"), headers=self._auth())
        return r.status_code == 200

    def create_site_folder(self, site_id: str) -> dict:
        site_id = validate_site_id(site_id)
        for f in SITE_FOLDERS:
            self._ensure_path(f"{self.library_root}/{site_id}/{f}")
        return {"site_id": site_id, "path": f"{self.library_root}/{site_id}", "folders": SITE_FOLDERS}

    def list_site_ids(self) -> list[str]:
        r = self.http.get(self.GRAPH + self._item(self.library_root) + ":/children", headers=self._auth())
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            raise SharePointError("Could not list the sites folder", details={"status": r.status_code})
        return sorted(i["name"] for i in r.json().get("value", []) if "folder" in i and SITE_ID_RE.match(i["name"]))

    def list_files(self, site_id: str) -> list[dict]:
        site_id = validate_site_id(site_id)
        out: list[dict] = []

        def walk(rel: str):
            url = self._item(f"{self.library_root}/{site_id}/{rel}".strip("/")) + ":/children"
            while url:
                j = self._call("GET", url).json()
                for i in j.get("value", []):
                    if "folder" in i:
                        walk(f"{rel}/{i['name']}".strip("/"))
                    else:
                        h = (i.get("file", {}).get("hashes") or {}).get("sha256Hash")
                        out.append({"name": i["name"], "folder": rel, "size": i.get("size", 0), "modified": i.get("lastModifiedDateTime"),
                                    "hash": h.lower() if h else None})
                url = j.get("@odata.nextLink")
        walk("")
        return sorted(out, key=lambda f: (f["folder"], f["name"]))

    def save_file(self, site_id: str, folder: str, file_name: str, data: bytes) -> dict:
        path = f"{self.library_root}/{site_id}/{folder}/{file_name}"
        existed = self.http.get(self.GRAPH + self._item(path), headers=self._auth()).status_code == 200
        if len(data) <= self.SIMPLE_LIMIT:
            self._call("PUT", self._item(path) + ":/content", content=data, headers={"Content-Type": "application/octet-stream"})
        else:
            sess = self._call("POST", self._item(path) + ":/createUploadSession",
                              json={"item": {"@microsoft.graph.conflictBehavior": "replace"}}).json()["uploadUrl"]
            for start in range(0, len(data), self.CHUNK):
                chunk = data[start:start + self.CHUNK]
                r = self.http.put(sess, content=chunk, headers={"Content-Length": str(len(chunk)),
                                  "Content-Range": f"bytes {start}-{start + len(chunk) - 1}/{len(data)}"})
                if r.status_code not in (200, 201, 202):
                    raise SharePointError("Upload to SharePoint failed", details={"status": r.status_code, "body": r.text[:300]})
        return {"name": file_name, "folder": folder, "size": len(data), "modified": _now(), "replaced": existed, "path": path}


# =============================================================================================================== factory
_store: SharePointStore | None = None


def get_store() -> SharePointStore:
    global _store
    if _store is None:
        st = get_settings()
        provider = str(st.get("sharepoint.provider", "local")).lower()
        lib = str(st.get("sharepoint.library_root", "Ericsson-Scoping/Sites"))
        if provider == "graph":
            _store = GraphSharePoint(st.section("sharepoint").get("graph", {}), lib)
        else:
            _store = LocalSharePoint(st.path("sharepoint.local_root"), lib)
    return _store


def set_store(store: SharePointStore | None) -> None:
    global _store
    _store = store
