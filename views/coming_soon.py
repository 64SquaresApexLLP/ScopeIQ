"""Placeholder for the tabs that are not built yet."""
import streamlit as st


def render(tab: str) -> None:
    st.markdown(
        '<div class="card"><div class="soon">'
        '<span class="pill warn">Coming next</span>'
        f'<div class="big">{tab}</div>'
        '<div class="sub">This tab is part of the admin console and will be built after SharePoint.</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )
