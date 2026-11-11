"""ScopeIQ - admin console on Snowflake (Streamlit). Command bar on top; one view per tab."""
import streamlit as st

from ui import navbar, theme
from views import coming_soon, sharepoint

st.set_page_config(page_title="ScopeIQ", page_icon=":material/cell_tower:", layout="wide", initial_sidebar_state="collapsed")


def viewer() -> dict:
    """Who is viewing and where the app runs. Falls back to a local preview outside Snowflake."""
    if "viewer" not in st.session_state:
        try:
            from snowflake.snowpark.context import get_active_session
            row = get_active_session().sql("SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE()").collect()[0]
            st.session_state["viewer"] = {"user": str(row[0]), "role": str(row[1]), "warehouse": str(row[2] or ""), "live": True}
        except Exception:
            st.session_state["viewer"] = {"user": "Local user", "role": "Developer", "warehouse": "", "live": False}
    return st.session_state["viewer"]


theme.apply()
v = viewer()
name = v["user"].title() if v["user"].isupper() else v["user"]
tab = navbar.render(name, v["role"].replace("_", " ").title(), v)

if tab == "SharePoint":
    sharepoint.render()
else:
    coming_soon.render(tab)
