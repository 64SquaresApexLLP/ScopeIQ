"""SharePoint tab (first version: the page shell, connection state and folder layout; document handling comes next)."""
import streamlit as st

SITE_URL = "https://64squaresllc.sharepoint.com/sites/ScopeIQ"
LIBRARY = "Documents"
ROOT = "Sites"
DOC_FOLDERS = ["CD", "DRONE", "RFDS", "MA_SA"]


def render() -> None:
    st.markdown(
        '<div class="hero"><div class="chip">SharePoint</div>'
        '<h1>SharePoint documents</h1>'
        f'<p>Every site gets its own folder in the ScopeIQ SharePoint site. Documents are stored there and read from there when the pipeline runs. '
        f'<a href="{SITE_URL}" target="_blank" rel="noopener">Open the SharePoint site</a></p></div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3, gap="medium")
    c1.markdown(
        '<div class="card"><div class="k">Connection</div><div class="v">Not connected yet</div>'
        '<div class="d"><span class="pill warn">Waiting for access</span><br>The app needs permission to read and write the SharePoint site.</div></div>',
        unsafe_allow_html=True,
    )
    c2.markdown(
        f'<div class="card"><div class="k">SharePoint site</div><div class="v">ScopeIQ</div>'
        f'<div class="d">Library: {LIBRARY}<br>Root folder: {ROOT}</div></div>',
        unsafe_allow_html=True,
    )
    c3.markdown(
        '<div class="card"><div class="k">Sites</div><div class="v">&ndash;</div>'
        '<div class="d">The list of site folders appears here once the connection is made.</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:22px'></div>", unsafe_allow_html=True)
    left, right = st.columns([1.1, 1], gap="medium")
    with left:
        sp = "&nbsp;"
        tree = [f"{LIBRARY}/", f"└─ {ROOT}/", f"{sp * 3}└─ &lt;SITE_ID&gt;/"]
        tree += [f"{sp * 6}{'└─' if i == len(DOC_FOLDERS) - 1 else '├─'} {f}/" for i, f in enumerate(DOC_FOLDERS)]
        st.markdown(
            '<div class="card"><div class="k">Folder layout for each site</div>'
            f'<div class="tree" style="margin-top:12px">{"<br>".join(tree)}</div></div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            '<div class="card"><div class="k">What this tab will do</div>'
            '<div class="d" style="font-size:14px;color:#334155">'
            '&bull; create a folder for a new site<br>&bull; upload CD drawings, drone data and RFDS files<br>'
            '&bull; list and download the documents of a site<br>&bull; replace or remove a file<br>'
            '&bull; flag files that are duplicates or updated versions</div></div>',
            unsafe_allow_html=True,
        )
