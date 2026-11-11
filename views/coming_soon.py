"""Placeholder for the tabs that are not built yet: says what the tab will do."""
import streamlit as st

from ui.theme import icon

ABOUT = {
    "Dashboard": ("dashboard", "Overview of all sites: pipeline runs, open redlines and RFIs, and what needs attention today."),
    "Sites": ("location_on", "Every site with its documents, pipeline stages and results."),
    "Work queue": ("checklist", "Findings waiting for a scoper's review, oldest first."),
    "Redlines & RFIs": ("edit_note", "Redlined drawings with drone evidence, and the RFIs sent to each team."),
    "Inbox": ("inbox", "Notifications and replies addressed to you."),
    "Admin": ("admin_panel_settings", "Create sites and manage user logins and roles."),
    "More": ("apps", "Reference data, rules and settings."),
}


def render(tab: str) -> None:
    ic, text = ABOUT.get(tab, ("construction", "This tab will be built next."))
    st.markdown(
        f'<div class="card"><div class="empty"><div class="halo">{icon(ic)}</div>'
        f'<h2>{tab}</h2><p>{text}</p>'
        '<span class="badge grey">Coming after SharePoint</span></div></div>',
        unsafe_allow_html=True,
    )
