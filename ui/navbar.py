"""Command bar: brand and breadcrumb, environment status and the signed-in user, then a rail with every tab of the admin console."""
import streamlit as st

from ui.theme import icon

# Same tabs, in the same order, as the demo app's admin console.
TABS = [
    ("Dashboard", "dashboard"),
    ("Sites", "location_on"),
    ("Work queue", "checklist"),
    ("Redlines & RFIs", "edit_note"),
    ("Inbox", "inbox"),
    ("SharePoint", "cloud_upload"),
    ("Admin", "admin_panel_settings"),
    ("More", "apps"),
]
DEFAULT_TAB = "SharePoint"

_LABELS = {name: f":material/{ic}: {name}" for name, ic in TABS}
_BY_LABEL = {label: name for name, label in _LABELS.items()}
_ICON = dict(TABS)


def _initials(name: str) -> str:
    parts = [p for p in name.replace("_", " ").replace(".", " ").split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


def render(user_name: str, role: str, env: dict) -> str:
    """Draws the bar and returns the name of the selected tab. env = {"live": bool, "warehouse": str}."""
    current = _BY_LABEL.get(st.session_state.get("nav_tab", ""), DEFAULT_TAB)
    status = (
        f'<span class="env" title="Running in Snowflake"><span class="dot"></span><span class="label">Snowflake</span>'
        f'<span class="mono">{env.get("warehouse") or "-"}</span></span>'
        if env.get("live")
        else '<span class="env" title="Running on this computer, not in Snowflake"><span class="dot amber"></span>'
             '<span class="label">Local preview</span></span>'
    )
    with st.container(key="topnav"):
        left, right = st.columns([3, 2], vertical_alignment="center")
        left.markdown(
            '<div class="brand">'
            f'<div class="logo">{icon("cell_tower")}</div>'
            '<div><div class="brand-name">ScopeIQ</div><div class="brand-sub">Admin console</div></div>'
            f'<div class="crumbs">{icon(_ICON[current])}<span>Console</span>{icon("chevron_right")}<b>{current}</b></div>'
            '</div>',
            unsafe_allow_html=True,
        )
        right.markdown(
            f'<div class="right">{status}'
            f'<div class="user" title="{user_name} ({role})"><div class="user-text"><div class="user-name">{user_name}</div>'
            f'<div class="user-role">{role}</div></div><div class="avatar">{_initials(user_name)}</div></div></div>',
            unsafe_allow_html=True,
        )
        choice = st.radio(
            "Navigation",
            list(_LABELS.values()),
            index=[n for n, _ in TABS].index(DEFAULT_TAB),
            horizontal=True,
            label_visibility="collapsed",
            key="nav_tab",
        )
    return _BY_LABEL[choice]
