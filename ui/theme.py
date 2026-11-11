"""Look and feel for the ScopeIQ admin console: colours (same palette as the demo app) and the CSS that styles the page and the nav bar."""
import streamlit as st

PRIMARY = "#0F2A5F"
ACCENT = "#4F6BFF"
ACCENT2 = "#14B8A6"
BG = "#F4F6FB"
TEXT = "#0F172A"
MUTED = "#64748B"
BORDER = "#E3E8F2"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {{
  --primary: {PRIMARY}; --accent: {ACCENT}; --accent2: {ACCENT2};
  --bg: {BG}; --text: {TEXT}; --muted: {MUTED}; --border: {BORDER};
}}

/* ---------- page ---------- */
html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"] {{
  background: var(--bg) !important;
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
}}
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], footer {{ display: none !important; }}
.block-container {{ padding: 14px 28px 48px !important; max-width: 1320px !important; }}
h1, h2, h3, h4 {{ color: var(--text); letter-spacing: -0.02em; }}

/* ---------- top nav bar ---------- */
.st-key-topnav {{
  position: sticky; top: 12px; z-index: 1000;
  margin-bottom: 26px;
  padding: 10px 14px 10px 18px;
  border-radius: 20px;
  background:
    radial-gradient(120% 220% at 0% 0%, rgba(79,107,255,0.55) 0%, rgba(79,107,255,0) 55%),
    radial-gradient(90% 200% at 100% 100%, rgba(20,184,166,0.30) 0%, rgba(20,184,166,0) 60%),
    linear-gradient(120deg, #0B1F4A 0%, #0F2A5F 55%, #1B2F7A 100%);
  box-shadow: 0 1px 0 rgba(255,255,255,0.10) inset, 0 14px 34px rgba(15,42,95,0.30), 0 2px 6px rgba(15,23,42,0.18);
  border: 1px solid rgba(255,255,255,0.10);
}}
.st-key-topnav [data-testid="stHorizontalBlock"] {{ align-items: center; gap: 12px; }}
.st-key-topnav [data-testid="stColumn"] {{ min-width: 0; }}

/* brand */
.brand {{ display: flex; align-items: center; gap: 12px; white-space: nowrap; }}
.brand-mark {{
  width: 40px; height: 40px; border-radius: 12px; flex: none;
  display: grid; place-items: center;
  background: linear-gradient(135deg, #4F6BFF 0%, #14B8A6 100%);
  box-shadow: 0 6px 16px rgba(20,184,166,0.35), 0 0 0 1px rgba(255,255,255,0.25) inset;
  transition: transform .35s cubic-bezier(.3,1.6,.5,1), box-shadow .35s;
}}
.brand:hover .brand-mark {{ transform: rotate(-8deg) scale(1.08); box-shadow: 0 10px 22px rgba(20,184,166,0.5), 0 0 0 1px rgba(255,255,255,0.35) inset; }}
.brand-name {{ color: #fff; font-weight: 800; font-size: 19px; letter-spacing: -0.4px; line-height: 1.05; }}
.brand-sub {{ color: rgba(255,255,255,0.58); font-size: 10.5px; font-weight: 600; letter-spacing: 1.6px; text-transform: uppercase; margin-top: 2px; }}

/* tabs: a radio group dressed as a nav */
.st-key-topnav [data-testid="stRadio"] > label {{ display: none; }}
.st-key-topnav div[role="radiogroup"] {{
  display: flex; flex-wrap: nowrap; justify-content: center; gap: 2px;
  padding: 5px; border-radius: 16px;
  background: rgba(255,255,255,0.07);
  border: 1px solid rgba(255,255,255,0.08);
  backdrop-filter: blur(6px);
  overflow-x: auto; scrollbar-width: none;
}}
.st-key-topnav div[role="radiogroup"]::-webkit-scrollbar {{ display: none; }}
.st-key-topnav label[data-baseweb="radio"] {{
  position: relative; margin: 0 !important; padding: 0 !important; cursor: pointer;
  border-radius: 12px; overflow: hidden; isolation: isolate;
  transition: transform .22s cubic-bezier(.3,1.4,.5,1), background .22s, box-shadow .22s;
}}
.st-key-topnav label[data-baseweb="radio"] > div:first-child {{ display: none !important; }}   /* the radio dot */
.st-key-topnav label[data-baseweb="radio"] > div:last-child {{ padding: 9px 14px; margin: 0 !important; }}
.st-key-topnav label[data-baseweb="radio"] p {{
  margin: 0; color: rgba(255,255,255,0.70); font-size: 13.2px; font-weight: 600; letter-spacing: 0.1px; white-space: nowrap;
  display: flex; align-items: center; gap: 7px;
  transition: color .2s, letter-spacing .25s;
}}
.st-key-topnav label[data-baseweb="radio"] p span[data-testid="stIconMaterial"] {{
  font-size: 18px; transition: transform .35s cubic-bezier(.3,1.7,.5,1), color .2s;
}}

/* hover: the tab lifts, a light sweeps across it, the icon pops, an underline grows from the middle */
.st-key-topnav label[data-baseweb="radio"]::before {{
  content: ""; position: absolute; inset: 0; z-index: -1; border-radius: 12px;
  background: linear-gradient(110deg, transparent 20%, rgba(255,255,255,0.20) 50%, transparent 80%);
  transform: translateX(-120%); transition: transform .55s ease;
}}
.st-key-topnav label[data-baseweb="radio"]::after {{
  content: ""; position: absolute; left: 50%; bottom: 4px; height: 2.5px; width: 0; border-radius: 3px;
  background: linear-gradient(90deg, #4F6BFF, #14B8A6); transform: translateX(-50%);
  transition: width .3s cubic-bezier(.3,1.2,.5,1); box-shadow: 0 0 10px rgba(20,184,166,0.9);
}}
.st-key-topnav label[data-baseweb="radio"]:hover {{ transform: translateY(-2px); background: rgba(255,255,255,0.09); }}
.st-key-topnav label[data-baseweb="radio"]:hover::before {{ transform: translateX(120%); }}
.st-key-topnav label[data-baseweb="radio"]:hover::after {{ width: 58%; }}
.st-key-topnav label[data-baseweb="radio"]:hover p {{ color: #fff; }}
.st-key-topnav label[data-baseweb="radio"]:hover p span[data-testid="stIconMaterial"] {{ transform: scale(1.22) rotate(-6deg); color: #7DE9DB; }}
.st-key-topnav label[data-baseweb="radio"]:active {{ transform: translateY(0) scale(0.97); }}

/* selected tab */
.st-key-topnav label[data-baseweb="radio"]:has(input:checked) {{
  background: linear-gradient(135deg, #4F6BFF 0%, #3B82F6 55%, #14B8A6 130%);
  box-shadow: 0 6px 18px rgba(79,107,255,0.55), 0 0 0 1px rgba(255,255,255,0.28) inset;
}}
.st-key-topnav label[data-baseweb="radio"]:has(input:checked) p {{ color: #fff; font-weight: 700; }}
.st-key-topnav label[data-baseweb="radio"]:has(input:checked)::after {{ width: 0; }}
.st-key-topnav label[data-baseweb="radio"]:has(input:checked):hover {{ transform: translateY(-1px); }}

/* user chip */
.user {{ display: flex; align-items: center; justify-content: flex-end; gap: 10px; white-space: nowrap; }}
.user-text {{ text-align: right; line-height: 1.15; }}
.user-name {{ color: #fff; font-weight: 700; font-size: 13px; }}
.user-role {{ color: rgba(255,255,255,0.60); font-size: 11px; font-weight: 500; }}
.avatar {{
  width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; flex: none;
  color: #fff; font-weight: 800; font-size: 13px;
  background: linear-gradient(135deg, #14B8A6, #4F6BFF);
  box-shadow: 0 0 0 2px rgba(255,255,255,0.35), 0 4px 12px rgba(0,0,0,0.25);
  transition: transform .3s cubic-bezier(.3,1.6,.5,1);
}}
.user:hover .avatar {{ transform: scale(1.1) rotate(6deg); }}

/* ---------- content cards ---------- */
.hero {{
  position: relative; overflow: hidden; border-radius: 22px; padding: 30px 32px; color: #fff; margin-bottom: 22px;
  background: linear-gradient(120deg, #0F2A5F 0%, #4F46E5 100%);
  box-shadow: 0 12px 30px rgba(79,70,229,0.25);
}}
.hero::after {{ content: ""; position: absolute; right: -60px; top: -80px; width: 280px; height: 280px; border-radius: 50%;
  background: radial-gradient(circle, rgba(20,184,166,0.45), rgba(20,184,166,0) 70%); }}
.hero h1 {{ color: #fff; margin: 0 0 8px; padding: 0; font-size: 28px; line-height: 1.15; font-weight: 800; letter-spacing: -0.6px; }}
.hero .chip {{ margin-bottom: 10px; }}
.hero p {{ margin: 0; color: rgba(255,255,255,0.78); font-size: 14.5px; max-width: 640px; line-height: 1.5; }}
.hero a {{ color: #fff; font-weight: 700; text-decoration: none; border-bottom: 1px dashed rgba(255,255,255,0.6); }}
.chip {{ display: inline-flex; align-items: center; gap: 6px; margin-bottom: 12px; padding: 4px 11px; border-radius: 999px; font-size: 11.5px; font-weight: 700;
  background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.22); letter-spacing: .3px; }}
.card {{
  background: #fff; border: 1px solid var(--border); border-radius: 18px; padding: 20px 22px; min-height: 150px;
  box-shadow: 0 1px 2px rgba(15,23,42,0.04), 0 6px 20px rgba(15,23,42,0.05);
  transition: transform .25s, box-shadow .25s, border-color .25s;
}}
.card:hover {{ transform: translateY(-3px); border-color: #C9D3F5; box-shadow: 0 2px 4px rgba(15,23,42,0.06), 0 14px 30px rgba(79,107,255,0.14); }}
.card .k {{ color: var(--muted); font-size: 11.5px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; }}
.card .v {{ color: var(--text); font-size: 22px; font-weight: 800; letter-spacing: -0.4px; margin-top: 6px; }}
.card .d {{ color: var(--muted); font-size: 13px; margin-top: 6px; line-height: 1.45; }}
.pill {{ display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 700; }}
.pill.warn {{ background: #FFF4DD; color: #A15C07; }}
.pill.ok {{ background: #E5F7EC; color: #166534; }}
.tree {{ font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; font-size: 12.8px; color: #334155; line-height: 1.75; background: #F8FAFF; border: 1px solid var(--border); border-radius: 14px; padding: 14px 18px; }}
.soon {{ text-align: center; padding: 70px 20px; }}
.soon .big {{ font-size: 22px; font-weight: 800; color: var(--text); margin-top: 10px; }}
.soon .sub {{ color: var(--muted); margin-top: 6px; }}

@media (max-width: 1100px) {{
  .brand-sub, .user-text {{ display: none; }}
}}
</style>
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
