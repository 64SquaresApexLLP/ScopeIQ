"""SharePoint tab: connection status, site folders (create / choose), upload documents, browse a site's documents."""
import re
from urllib.parse import urlparse

import streamlit as st

import settings
from services import graph
from ui.theme import icon

ROOT = "Sites"
SITE_RE = re.compile(r"^[A-Z]{4}\d{4}$")                       # same Site ID format as the demo app, e.g. TXAD0405
FOLDERS = [("CD", "Construction drawings"), ("DRONE", "Video, photos, point cloud, vendor CSV"),
           ("RFDS", "Radio frequency data sheets"), ("MA_SA", "Mount and structural analysis")]
FOLDER_NAMES = [f for f, _ in FOLDERS]


def _html(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def classify(name: str) -> str | None:
    """Folder a file belongs in, from its name (same rules as the demo app). None when it cannot tell."""
    if re.search(r"RFDS", name, re.I):
        return "RFDS"
    if re.search(r"(?:^|[-_\s])(?:CD|PCD)(?:[-_\s.]|$)", name, re.I):
        return "CD"
    if re.search(r"(?:^|[-_\s])(?:SAMA|MA_SA|SA_MA|MA|SA)(?:[-_\s.]|$)", name, re.I):
        return "MA_SA"
    if re.search(r"capture_metadata\.json$|vendor_measurements\.csv$|\.la[sz]$|\.(jpe?g|png|tif|mp4|mov|avi)$", name, re.I):
        return "DRONE"
    return None


def kb(n) -> str:
    n = n or 0
    return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{max(1, round(n / 1024))} KB" if n else "0 KB"


# ---------------------------------------------------------------- connection (cached for the life of the token)
@st.cache_resource(ttl=3000, show_spinner=False)
def _connect() -> graph.SharePoint:
    m = settings.microsoft()
    token, expires = graph.get_token(m["tenant_id"], m["client_id"], m["client_secret"])
    return graph.SharePoint(token, expires, settings.sharepoint_site_url()).connect()


def _explain(e: graph.GraphError) -> str:
    if e.code == "not_configured":
        return "The Microsoft credentials or the SharePoint address are not set for this app."
    if e.status == 0:
        return "This app cannot reach Microsoft from here (network access is not enabled for it)."
    if e.status in (401, 403):
        return "Microsoft accepted the app but did not allow it to use this SharePoint site. The site access grant is missing or was given to a different app."
    if e.status == 404:
        return "The SharePoint site or its Documents library was not found. Check the site address."
    return f"SharePoint returned an error ({e.status}{' ' + e.code if e.code else ''})."


def _sp():
    """(client, error text). One retry with a fresh token if the cached one was refused."""
    try:
        return _connect(), None
    except graph.GraphError as e:
        return None, _explain(e)


@st.cache_data(ttl=20, show_spinner=False)
def _site_folders(_ver: int) -> list[dict]:
    sp, _ = _sp()
    return [i for i in sp.list(ROOT) if "folder" in i] if sp else []


@st.cache_data(ttl=20, show_spinner=False)
def _site_files(site: str, _ver: int) -> dict[str, list[dict]]:
    sp, _ = _sp()
    out: dict[str, list[dict]] = {}
    if not sp:
        return out
    for sub in sp.list(f"{ROOT}/{site}"):
        if "folder" in sub:
            files = [i for i in sp.list(f"{ROOT}/{site}/{sub['name']}") if "file" in i]
            out[sub["name"]] = files
    return out


def _changed() -> None:
    st.session_state["sp_ver"] = st.session_state.get("sp_ver", 0) + 1


def _kpi(tile: str, ic: str, k: str, v: str, d: str) -> str:
    return (f'<div class="card lift"><div class="kpi"><div class="tile {tile}">{icon(ic)}</div>'
            f'<div><div class="k">{k}</div><div class="v">{v}</div><div class="d">{d}</div></div></div></div>')


def render() -> None:
    site_url = settings.sharepoint_site_url()
    ver = st.session_state.get("sp_ver", 0)
    sp, error = _sp()
    sites = _site_folders(ver) if sp else []
    host = urlparse(site_url).netloc or "not set"

    _html(
        '<div class="page-head"><div>'
        f'<div class="eyebrow">{icon("folder_managed")}Documents</div>'
        '<div class="page-title">SharePoint</div>'
        '<div class="page-sub">Every site has its own folder in the ScopeIQ SharePoint site. Documents are uploaded there, '
        'and the pipeline reads them from there.</div></div>'
        + (f'<a class="btn ghost" href="{site_url}" target="_blank" rel="noopener">{icon("open_in_new")}Open in SharePoint</a>' if site_url else "")
        + '</div>'
    )

    if sp:
        conn = ("teal", "link", "Connection", "Connected", '<span class="badge green"><span class="dot"></span>Live</span>')
    else:
        conn = ("amber", "link_off", "Connection", "Not connected", '<span class="badge amber"><span class="dot amber"></span>Needs attention</span>')
    cards = [conn,
             ("blue", "hub", "SharePoint site", (sp.site_name if sp else "ScopeIQ") or "ScopeIQ", host),
             ("violet", "folder_open", "Library", f"{sp.library if sp else 'Documents'} / {ROOT}", "One folder per site"),
             ("teal", "location_on", "Site folders", str(len(sites)) if sp else "&ndash;", "Sites with a folder" if sp else "Shown once connected")]
    _html('<div class="grid g4">' + "".join(_kpi(*c) for c in cards) + "</div>")

    if not sp:
        _html(f'<div class="card"><div class="card-title">{icon("report")}Cannot use SharePoint yet</div>'
              f'<div class="card-sub" style="font-size:14px;color:#334155;margin-top:8px">{error}</div></div>')
        if st.button("Try again", key="sp_retry"):
            _connect.clear()
            st.rerun()
        return

    # ------------------------------------------------------------ sites: choose or create
    _html('<div class="section-label">Sites</div>')
    left, right = st.columns([1, 1], gap="medium")
    with left:
        with st.container(border=True, key="sp_choose"):
            st.markdown("**Choose a site**")
            names = sorted(i["name"] for i in sites)
            site = st.selectbox("Site", names, index=None, placeholder="Select a site to add or view documents" if names else "No sites yet - create one",
                                label_visibility="collapsed", key="sp_site") if names else None
            if not names:
                st.caption("No site folders yet. Create the first one on the right.")
    with right:
        with st.container(border=True, key="sp_create"):
            st.markdown("**Create a site**")
            new_id = st.text_input("Site ID", max_chars=8, placeholder="TXAD0405", label_visibility="collapsed", key="sp_new_id").strip().upper()
            ok = bool(SITE_RE.match(new_id))
            if new_id and not ok:
                st.caption("Use 4 letters then 4 digits, for example TXAD0405.")
            if new_id and ok and new_id in {i["name"] for i in sites}:
                st.caption("This site already has a folder.")
            if st.button(f"Create folder{(' for ' + new_id) if ok else ''}", disabled=not ok, key="sp_create_btn", use_container_width=True):
                try:
                    for f in FOLDER_NAMES:
                        sp.ensure_folder(f"{ROOT}/{new_id}/{f}")
                    _changed()
                    st.session_state["sp_notice"] = f"Folder for {new_id} is ready: {ROOT}/{new_id}/ with {', '.join(FOLDER_NAMES)}."
                    st.rerun()
                except graph.GraphError as e:
                    st.error(_explain(e))
    if st.session_state.get("sp_notice"):
        st.success(st.session_state.pop("sp_notice"))

    if not site:
        _html('<div class="gap"></div>')
        _html(f'<div class="card"><div class="empty" style="padding:38px 20px"><div class="halo">{icon("touch_app")}</div>'
              '<h2>Select a site</h2><p>Choose a site above to upload its documents and see what is already there.</p></div></div>')
        return

    # ------------------------------------------------------------ upload
    files = _site_files(site, ver)
    _html(f'<div class="section-label">Add documents to {site}</div>')
    with st.container(border=True, key="sp_upload"):
        picked = st.file_uploader("Drag and drop files here, or browse", accept_multiple_files=True, key=f"sp_files_{site}_{st.session_state.get('sp_up', 0)}")
        plan = []
        for f in picked or []:
            guess = classify(f.name)
            c1, c2, c3 = st.columns([3, 2, 2], vertical_alignment="center")
            c1.markdown(f"**{f.name}**  \n<span style='color:#64748B;font-size:12px'>{kb(f.size)}</span>", unsafe_allow_html=True)
            folder = c2.selectbox("Folder", FOLDER_NAMES, index=FOLDER_NAMES.index(guess) if guess else None, placeholder="Choose folder",
                                  label_visibility="collapsed", key=f"sp_folder_{site}_{f.name}_{f.size}")
            dup = bool(folder) and any(x["name"] == f.name for x in files.get(folder, []))
            replace = c3.checkbox("Replace existing", key=f"sp_rep_{site}_{f.name}_{f.size}") if dup else False
            if dup and not replace:
                c3.caption("Already there: will be skipped")
            plan.append((f, folder, dup, replace))
        todo = [p for p in plan if p[1] and (not p[2] or p[3])]
        if st.button(f"Upload {len(todo)} file{'s' if len(todo) != 1 else ''} to {site}" if todo else "Upload", disabled=not todo, key="sp_upload_btn", type="primary"):
            bar, results = st.progress(0.0), []
            for n, (f, folder, dup, replace) in enumerate(todo, 1):
                try:
                    sp.ensure_folder(f"{ROOT}/{site}/{folder}")
                    sp.upload(f"{ROOT}/{site}/{folder}/{f.name}", f.getvalue(), replace=replace)
                    results.append((f.name, True, f"Saved in {folder}" + (" (replaced)" if replace else "")))
                except graph.GraphError as e:
                    results.append((f.name, False, "A file with this name already exists" if e.status == 409 else _explain(e)))
                bar.progress(n / len(todo))
            _changed()
            st.session_state["sp_up"] = st.session_state.get("sp_up", 0) + 1          # clears the picker
            st.session_state["sp_results"] = results
            st.rerun()
    for name, good, msg in st.session_state.pop("sp_results", []):
        (st.success if good else st.error)(f"{name}: {msg}")

    # ------------------------------------------------------------ documents
    total = sum(len(v) for v in files.values())
    _html(f'<div class="section-label">Documents in {site} &middot; {total} file{"s" if total != 1 else ""}</div>')
    if not total:
        _html(f'<div class="card"><div class="empty" style="padding:34px 20px"><div class="halo">{icon("folder_open")}</div>'
              '<h2>Nothing uploaded yet</h2><p>Files you add above appear here, grouped by folder.</p></div></div>')
    for folder in FOLDER_NAMES + [f for f in files if f not in FOLDER_NAMES]:
        items = sorted(files.get(folder, []), key=lambda i: i["name"].lower())
        if not items:
            continue
        with st.container(border=True, key=f"sp_docs_{folder}"):
            st.markdown(f"**{folder}** &nbsp;<span style='color:#64748B;font-size:12px'>{len(items)} file{'s' if len(items) != 1 else ''}</span>", unsafe_allow_html=True)
            for it in items:
                a, b, c, d = st.columns([5, 1.4, 1.8, 1.2], vertical_alignment="center")
                a.markdown(it["name"])
                b.caption(kb(it.get("size")))
                c.caption((it.get("lastModifiedDateTime") or "")[:10])
                url = it.get("@microsoft.graph.downloadUrl") or it.get("webUrl")
                if url:
                    d.link_button("Download", url)
