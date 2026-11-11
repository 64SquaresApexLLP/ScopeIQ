"""ScopeIQ - Snowflake Streamlit demo (first page).

Runs inside Snowflake (Streamlit in Snowflake). It only reads; it creates nothing.
"""
import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="ScopeIQ", page_icon=":satellite_antenna:", layout="wide")

st.title("ScopeIQ")
st.caption("Telecom scoping engine - Snowflake demo")

session = get_active_session()
info = session.sql(
    "SELECT CURRENT_USER() AS USER_NAME, CURRENT_ROLE() AS ROLE_NAME, "
    "CURRENT_WAREHOUSE() AS WAREHOUSE, CURRENT_DATABASE() AS DATABASE_NAME, "
    "CURRENT_SCHEMA() AS SCHEMA_NAME"
).to_pandas()

st.success("The app is running inside Snowflake.")
st.dataframe(info, hide_index=True, use_container_width=True)
