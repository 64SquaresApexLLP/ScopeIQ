"""Top navigation bar: brand on the left, every tab of the admin console in the middle, signed-in user on the right."""
import streamlit as st

# Same tabs, in the same order, as the demo app's admin console. Only the SharePoint tab is built so far.
TABS = [
    ("Dashboard", "dashboard"),
    ("Sites", "location_on"),
    ("Work queue", "checklist"),
    ("Redlines & RFIs", "edit_note"),
    ("Inbox", "inbox"),
    ("SharePoint", "cloud_upload"),
    ("Admin", "settings"),
    ("More", "more_horiz"),
]
BUILT = {"SharePoint"}
DEFAULT_TAB = "SharePoint"

_LABELS = {name: f":material/{icon}: {name}" for name, icon in TABS}
_BY_LABEL = {label: name for name, label in _LABELS.items()}

_MARK = (
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M4 20 12 4l8 16"/><path d="M7.5 14h9"/><circle cx="12" cy="4" r="1.6" fill="#fff"/></svg>'
)


def _initials(name: str) -> str:
    parts = [p for p in name.replace("_", " ").replace(".", " ").split() if p]
    return ("".join(p[0] for p in parts[:2]) or name[:2] or "?").upper()


def render(user_name: str, role: str) -> str:
    """Draws the bar and returns the name of the selected tab."""
    with st.container(key="topnav"):
        left, mid, right = st.columns([1.55, 7.2, 1.9], vertical_alignment="center")
        with left:
            st.markdown(
                f'<div class="brand"><div class="brand-mark">{_MARK}</div>'
                '<div><div class="brand-name">ScopeIQ</div><div class="brand-sub">Admin console</div></div></div>',
                unsafe_allow_html=True,
            )
        with mid:
            choice = st.radio(
                "Navigation",
                list(_LABELS.values()),
                index=[n for n, _ in TABS].index(DEFAULT_TAB),
                horizontal=True,
                label_visibility="collapsed",
                key="nav_tab",
            )
        with right:
            st.markdown(
                f'<div class="user"><div class="user-text"><div class="user-name">{user_name}</div>'
                f'<div class="user-role">{role}</div></div><div class="avatar">{_initials(user_name)}</div></div>',
                unsafe_allow_html=True,
            )
    return _BY_LABEL[choice]
