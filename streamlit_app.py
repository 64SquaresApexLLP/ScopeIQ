"""ScopeIQ - admin console on Snowflake (Streamlit). Nav bar on top; one view per tab."""
import streamlit as st

from ui import navbar, theme
from views import coming_soon, sharepoint

st.set_page_config(page_title="ScopeIQ", page_icon=":material/cell_tower:", layout="wide", initial_sidebar_state="collapsed")


def signed_in_user() -> tuple[str, str]:
    """User and role of the viewer. Falls back to a placeholder when the app runs outside Snowflake."""
    if "who" not in st.session_state:
        try:
            from snowflake.snowpark.context import get_active_session
            row = get_active_session().sql("SELECT CURRENT_USER(), CURRENT_ROLE()").collect()[0]
            st.session_state["who"] = (str(row[0]), str(row[1]))
        except Exception:
            st.session_state["who"] = ("Local preview", "Not in Snowflake")
    return st.session_state["who"]


theme.apply()
name, role = signed_in_user()
tab = navbar.render(name.title() if name.isupper() else name, role.replace("_", " ").title())

if tab == "SharePoint":
    sharepoint.render()
else:
    coming_soon.render(tab)
