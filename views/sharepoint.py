"""SharePoint tab (first version: page shell, connection state, setup steps and folder layout; document handling comes next)."""
from urllib.parse import urlparse

import streamlit as st

import settings
from ui.theme import icon

SITE_URL = settings.sharepoint_site_url()
HOST = urlparse(SITE_URL).netloc or "not set"
SITE_NAME = (urlparse(SITE_URL).path.rstrip("/").split("/") or [""])[-1] or "ScopeIQ"
LIBRARY = "Documents"
ROOT = "Sites"
DOC_FOLDERS = [("CD", "Construction drawings"), ("DRONE", "Video, photos, point cloud, vendor CSV"),
               ("RFDS", "Radio frequency data sheets"), ("MA_SA", "Mount and structural analysis")]


def _html(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def _kpi(tile: str, ic: str, k: str, v: str, d: str) -> str:
    return (f'<div class="card lift"><div class="kpi"><div class="tile {tile}">{icon(ic)}</div>'
            f'<div><div class="k">{k}</div><div class="v">{v}</div><div class="d">{d}</div></div></div></div>')


def render() -> None:
    _html(
        '<div class="page-head"><div>'
        f'<div class="eyebrow">{icon("folder_managed")}Documents</div>'
        '<div class="page-title">SharePoint</div>'
        '<div class="page-sub">Every site has its own folder in the ScopeIQ SharePoint site. Documents are uploaded there, '
        'and the pipeline reads them from there.</div></div>'
        + (f'<a class="btn ghost" href="{SITE_URL}" target="_blank" rel="noopener">{icon("open_in_new")}Open in SharePoint</a>' if SITE_URL else "") +
        '</div>'
    )

    cards = [
        ("amber", "link_off", "Connection", "Not connected", '<span class="badge amber"><span class="dot amber"></span>Waiting for access</span>'),
        ("blue", "hub", "SharePoint site", SITE_NAME, HOST),
        ("violet", "folder_open", "Library", f"{LIBRARY} / {ROOT}", "One folder per site"),
        ("teal", "location_on", "Site folders", "&ndash;", "Shown once connected"),
    ]
    _html('<div class="grid g4">' + "".join(_kpi(*c) for c in cards) + "</div>")

    steps = [
        ("Register the app in Microsoft Entra ID", "Gives ScopeIQ its own identity in the 64squares Microsoft 365 tenant."),
        ("Grant access to the ScopeIQ SharePoint site only", "Permission Sites.Selected, limited to this one site."),
        ("Let Snowflake reach Microsoft Graph", "A network rule and the app's credentials stored as a Snowflake secret."),
    ]
    rows = "".join(
        f'<div class="step"><div class="num">{i}</div><div><div class="t">{t}</div><div class="s">{d}</div></div>'
        '<div class="state"><span class="badge grey">To do</span></div></div>'
        for i, (t, d) in enumerate(steps, 1)
    )
    connect = (f'<div class="card"><div class="card-title">{icon("checklist")}Connect SharePoint</div>'
               f'<div class="card-sub">Three one-time steps before files can be read and written from here.</div>'
               f'<div class="steps">{rows}</div></div>')
    nodes = [f'<div class="node">{icon("folder")}{LIBRARY}</div>',
             f'<div class="node l1">{icon("folder")}{ROOT}</div>',
             f'<div class="node l2 var">{icon("folder_special")}&lt;SITE_ID&gt;<span class="hint">e.g. TXAD0405</span></div>']
    nodes += [f'<div class="node l3">{icon("folder")}{f}<span class="hint">{h}</span></div>' for f, h in DOC_FOLDERS]
    layout = (f'<div class="card"><div class="card-title">{icon("account_tree")}Folder layout</div>'
              f'<div class="card-sub">Created automatically when a site is added.</div>'
              f'<div class="tree">{"".join(nodes)}</div></div>')
    _html(f'<div class="grid g2">{connect}{layout}</div>')

    _html('<div class="section-label">What you will be able to do here</div>')
    caps = [
        ("blue", "create_new_folder", "Create site folders", "A new site gets its folder and sub-folders in one step."),
        ("teal", "upload_file", "Upload documents", "Drag and drop CD drawings, drone data and RFDS files."),
        ("violet", "folder_open", "Browse and download", "See every document of a site, grouped by type."),
        ("amber", "difference", "Spot duplicates", "Identical files are blocked; changed versions are flagged."),
    ]
    _html('<div class="card"><div class="caps">' + "".join(
        f'<div class="cap"><div class="tile {t}">{icon(ic)}</div><div><div class="t">{a}</div><div class="s">{b}</div></div></div>'
        for t, ic, a, b in caps) + '</div></div>')
