"""Microsoft Graph client for the ScopeIQ SharePoint site. Standard library only (no extra packages).
Credentials come from settings (Snowflake secrets, or a local .env); nothing is stored here and nothing secret is ever put in an error message."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

GRAPH = "https://graph.microsoft.com/v1.0"
SMALL_UPLOAD_LIMIT = 4 * 1024 * 1024            # larger files use an upload session
CHUNK = 320 * 1024 * 16                         # 5 MiB, a multiple of 320 KiB as Graph requires


class GraphError(Exception):
    """A failed Graph call. Carries only the HTTP status and Microsoft's error code, never request content or credentials."""

    def __init__(self, status: int, code: str = "", message: str = ""):
        self.status, self.code = status, code
        super().__init__(f"{status} {code} {message}".strip())


def _quote(path: str) -> str:
    return "/".join(urllib.parse.quote(p, safe="") for p in path.strip("/").split("/") if p)


def _request(url, data=None, headers=None, method=None, timeout=60, retries=3):
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                return r.status, (json.loads(body) if body else {}), r.headers
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                err = (json.loads(raw) or {}).get("error", {})
            except ValueError:
                err = {}
            if e.code in (429, 503) and attempt < retries:                  # Microsoft asks us to slow down
                time.sleep(min(int(e.headers.get("Retry-After", 2 ** attempt)), 20))
                continue
            code = err.get("code", "") if isinstance(err, dict) else ""
            raise GraphError(e.code, code, "")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise GraphError(0, "network", type(e).__name__)


def get_token(tenant_id: str, client_id: str, client_secret: str) -> tuple[str, float]:
    if not (tenant_id and client_id and client_secret):
        raise GraphError(0, "not_configured", "Microsoft credentials are not set")
    body = urllib.parse.urlencode({"client_id": client_id, "client_secret": client_secret, "scope": "https://graph.microsoft.com/.default",
                                   "grant_type": "client_credentials"}).encode()
    _s, tok, _h = _request(f"https://login.microsoftonline.com/{urllib.parse.quote(tenant_id)}/oauth2/v2.0/token", data=body, method="POST")
    return tok["access_token"], time.time() + int(tok.get("expires_in", 3600)) - 120


class SharePoint:
    """One document library of one site."""

    def __init__(self, token: str, expires_at: float, site_url: str, library: str = "Documents"):
        self._token, self.expires_at = token, expires_at
        self.site_url, self.library = site_url, library
        self.site_id = self.drive_id = None
        self.site_name = ""

    # -- plumbing
    def _h(self, extra=None):
        return {"Authorization": "Bearer " + self._token, **(extra or {})}

    def _json(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        _s, out, _h = _request(GRAPH + path, data=data, method=method, headers=self._h({"Content-Type": "application/json"} if data else {}))
        return out

    def connect(self) -> "SharePoint":
        u = urllib.parse.urlparse(self.site_url)
        if not u.netloc:
            raise GraphError(0, "not_configured", "SharePoint site address is not set")
        site = self._json("GET", f"/sites/{u.netloc}:{u.path.rstrip('/')}")
        self.site_id, self.site_name = site["id"], site.get("displayName", "")
        drives = self._json("GET", f"/sites/{self.site_id}/drives").get("value", [])
        drive = next((d for d in drives if d["name"] == self.library), None) or next((d for d in drives if d.get("driveType") == "documentLibrary"), None)
        if not drive:
            raise GraphError(404, "libraryNotFound", self.library)
        self.drive_id = drive["id"]
        return self

    def _item(self, path: str) -> str:
        return f"/drives/{self.drive_id}/root:/{_quote(path)}:" if path.strip("/") else f"/drives/{self.drive_id}/root"

    # -- folders and files
    def list(self, path: str = "") -> list[dict]:
        url, out = f"/drives/{self.drive_id}/root{':/' + _quote(path) + ':' if path.strip('/') else ''}/children?$top=200", []
        while url:
            try:
                page = self._json("GET", url) if url.startswith("/") else None
                if page is None:
                    _s, page, _h = _request(url, headers=self._h())
            except GraphError as e:
                if e.status == 404:
                    return []
                raise
            out += page.get("value", [])
            url = page.get("@odata.nextLink")
        return out

    def ensure_folder(self, path: str) -> None:
        """Creates every folder on the path that does not exist yet. Existing folders are left alone."""
        parts = [p for p in path.strip("/").split("/") if p]
        for i, name in enumerate(parts):
            parent = "/".join(parts[:i])
            endpoint = f"{self._item(parent)}/children" if parent else f"/drives/{self.drive_id}/root/children"
            try:
                self._json("POST", endpoint, {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"})
            except GraphError as e:
                if e.status != 409:                           # 409 = already there, fine
                    raise

    def exists(self, path: str) -> bool:
        try:
            self._json("GET", self._item(path))
            return True
        except GraphError as e:
            if e.status == 404:
                return False
            raise

    def upload(self, path: str, content: bytes, replace: bool = False) -> dict:
        """Uploads a file. Without replace=True an existing file of the same name is NOT overwritten (GraphError 409)."""
        behavior = "replace" if replace else "fail"
        if len(content) <= SMALL_UPLOAD_LIMIT:
            _s, out, _h = _request(f"{GRAPH}{self._item(path)}/content?@microsoft.graph.conflictBehavior={behavior}", data=content, method="PUT",
                                   headers=self._h({"Content-Type": "application/octet-stream"}), timeout=120)
            return out
        sess = self._json("POST", f"{self._item(path)}/createUploadSession", {"item": {"@microsoft.graph.conflictBehavior": behavior}})
        url, size, pos, out = sess["uploadUrl"], len(content), 0, {}
        while pos < size:
            chunk = content[pos:pos + CHUNK]
            _s, out, _h = _request(url, data=chunk, method="PUT", timeout=180,
                                   headers={"Content-Length": str(len(chunk)), "Content-Range": f"bytes {pos}-{pos + len(chunk) - 1}/{size}"})
            pos += len(chunk)
        return out

    def delete(self, path: str) -> None:
        _request(f"{GRAPH}{self._item(path)}", method="DELETE", headers=self._h())
