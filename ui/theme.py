"""Look and feel of the ScopeIQ admin console: design tokens and the CSS for the page, the nav bar and the shared components."""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&display=swap');

:root {
  --ink: #0B1220; --text: #0F172A; --muted: #5B6B84; --faint: #94A3B8;
  --line: #E4E9F2; --line-strong: #CFD8E8; --surface: #FFFFFF; --bg: #F3F6FB;
  --brand: #4F6BFF; --brand-2: #14B8A6; --brand-3: #7C5CFF;
  --ok: #16A34A; --warn: #D97706; --bad: #DC2626;
  --nav-h: 46px;
  --radius: 16px;
  --ease-spring: cubic-bezier(.34,1.56,.64,1);
}

/* ---------- page ---------- */
html, body, [data-testid="stApp"] { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }
[data-testid="stApp"] {
  background:
    radial-gradient(900px 420px at 8% -8%, rgba(79,107,255,0.10), transparent 60%),
    radial-gradient(700px 380px at 96% -10%, rgba(20,184,166,0.10), transparent 60%),
    radial-gradient(circle at 1px 1px, rgba(15,23,42,0.055) 1px, transparent 0) 0 0 / 22px 22px,
    var(--bg) !important;
}
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], footer { display: none !important; }
.block-container { padding: 14px 28px 56px !important; max-width: 1360px !important; }
[data-testid="stMarkdownContainer"] p { margin-bottom: 0; }
.mi { font-family: 'Material Symbols Rounded'; font-weight: normal; font-style: normal; line-height: 1; letter-spacing: normal;
      text-transform: none; white-space: nowrap; word-wrap: normal; direction: ltr; font-feature-settings: 'liga'; -webkit-font-smoothing: antialiased;
      display: inline-block; vertical-align: middle; }

/* ======================================================================
   COMMAND BAR (top nav)
   ====================================================================== */
.st-key-topnav {
  position: sticky; top: 10px; z-index: 1000; gap: 10px !important;
  margin-bottom: 30px; padding: 12px 14px 12px; border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0) 40%),
    radial-gradient(110% 260% at 0% 0%, rgba(79,107,255,0.50), transparent 52%),
    radial-gradient(80% 240% at 100% 120%, rgba(20,184,166,0.32), transparent 58%),
    linear-gradient(115deg, #070F26 0%, #0C1D47 52%, #13215A 100%);
  border: 1px solid rgba(148,163,255,0.18);
  box-shadow: 0 1px 0 rgba(255,255,255,0.08) inset, 0 18px 40px -12px rgba(7,15,38,0.55), 0 2px 6px rgba(7,15,38,0.20);
}
.st-key-topnav::after {               /* thin animated light along the bottom edge */
  content: ""; position: absolute; left: 22px; right: 22px; bottom: -1px; height: 1px; pointer-events: none;
  background: linear-gradient(90deg, transparent, rgba(125,233,219,0.9), rgba(124,92,255,0.9), transparent);
  background-size: 200% 100%; animation: edge 6s linear infinite; opacity: .75;
}
@keyframes edge { from { background-position: 200% 0; } to { background-position: -200% 0; } }
.st-key-topnav { display: flex; flex-direction: column; gap: 0 !important; padding: 14px 16px 14px !important; }
.st-key-topnav [data-testid="stLayoutWrapper"] { margin: 0 0 16px !important; }      /* clear space between the top row and the tab rail */
.st-key-topnav [data-testid="stHorizontalBlock"] { align-items: center; gap: 14px; min-height: 44px; }
.st-key-topnav [data-testid="stColumn"], .st-key-topnav [data-testid="stColumn"] > [data-testid="stVerticalBlock"] { min-height: 44px; justify-content: center; }
.st-key-topnav [data-testid="stElementContainer"] { margin: 0 !important; }

/* brand */
.brand { display: flex; align-items: center; gap: 12px; white-space: nowrap; min-height: 44px; }
.logo { position: relative; width: 40px; height: 40px; flex: none; border-radius: 12px; display: grid; place-items: center;
  background: linear-gradient(140deg, #5B74FF, #14B8A6); box-shadow: 0 8px 20px -6px rgba(20,184,166,0.7), 0 0 0 1px rgba(255,255,255,0.25) inset; }
.logo::before { content: ""; position: absolute; inset: -3px; border-radius: 15px; padding: 1.5px; opacity: 0; transition: opacity .3s;
  background: conic-gradient(from 0deg, #7DE9DB, #7C5CFF, #4F6BFF, #7DE9DB);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude;
  animation: spin 3s linear infinite; }
.brand:hover .logo::before { opacity: 1; }
@keyframes spin { to { transform: rotate(360deg); } }
.logo .mi { color: #fff; font-size: 22px; }
.brand-name { color: #fff; font-weight: 800; font-size: 18px; letter-spacing: -0.4px; line-height: 1.1; }
.brand-sub { color: rgba(203,213,255,0.62); font-size: 10.5px; font-weight: 600; letter-spacing: 1.8px; text-transform: uppercase; }
.crumbs { display: flex; align-items: center; gap: 8px; margin-left: 10px; padding-left: 16px; border-left: 1px solid rgba(255,255,255,0.12);
  color: rgba(203,213,255,0.60); font-size: 13px; font-weight: 500; white-space: nowrap; }
.crumbs b { color: #fff; font-weight: 700; }
.crumbs .mi { font-size: 16px; opacity: .6; }

/* right side */
.right { display: flex; align-items: center; justify-content: flex-end; gap: 12px; white-space: nowrap; min-height: 44px; }
.env { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 999px; font-size: 12px; font-weight: 600;
  color: rgba(226,232,255,0.85); background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10); }
.env .mono { font-family: 'JetBrains Mono', ui-monospace, Consolas, monospace; font-size: 11.5px; color: #A5F3E7; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #34D399; box-shadow: 0 0 0 0 rgba(52,211,153,0.7); animation: pulse 2s infinite; flex: none; }
.dot.amber { background: #FBBF24; box-shadow: 0 0 0 0 rgba(251,191,36,0.7); animation-name: pulse-amber; }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(52,211,153,0.6); } 70% { box-shadow: 0 0 0 7px rgba(52,211,153,0); } 100% { box-shadow: 0 0 0 0 rgba(52,211,153,0); } }
@keyframes pulse-amber { 0% { box-shadow: 0 0 0 0 rgba(251,191,36,0.6); } 70% { box-shadow: 0 0 0 7px rgba(251,191,36,0); } 100% { box-shadow: 0 0 0 0 rgba(251,191,36,0); } }
.user { display: flex; align-items: center; gap: 10px; padding: 4px 4px 4px 12px; border-radius: 999px; transition: background .2s; }
.user:hover { background: rgba(255,255,255,0.07); }
.user-text { text-align: right; line-height: 1.2; }
.user-name { color: #fff; font-weight: 700; font-size: 13px; }
.user-role { color: rgba(203,213,255,0.62); font-size: 11px; font-weight: 500; }
.avatar { position: relative; width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; flex: none;
  color: #fff; font-weight: 800; font-size: 12.5px; background: linear-gradient(135deg, #14B8A6, #4F6BFF);
  box-shadow: 0 0 0 2px rgba(255,255,255,0.22); }
.avatar::after { content: ""; position: absolute; right: -1px; bottom: -1px; width: 10px; height: 10px; border-radius: 50%;
  background: #34D399; border: 2px solid #0C1D47; }

/* ---------- tab rail: equal-width tabs with a highlight that slides to the selected one ---------- */
.st-key-topnav [data-testid="stRadio"] > label { display: none; }
.st-key-topnav [data-testid="stElementContainer"]:has([data-testid="stRadio"]),
.st-key-topnav [data-testid="stRadio"], .st-key-topnav [data-testid="stRadio"] > div { width: 100% !important; max-width: none !important; }
.st-key-topnav div[role="radiogroup"] {
  --n: 8; --pad: 5px;
  position: relative; display: grid !important; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: 0 !important;
  width: 100%; padding: var(--pad); border-radius: 15px;
  background: rgba(2,6,23,0.35); border: 1px solid rgba(255,255,255,0.07);
  box-shadow: 0 1px 0 rgba(255,255,255,0.05), 0 2px 10px rgba(0,0,0,0.25) inset;
  overflow: hidden;                                         /* nothing can poke out of the rail */
}
.st-key-topnav div[role="radiogroup"]::before {   /* the sliding highlight */
  content: ""; position: absolute; z-index: 0; top: var(--pad); bottom: var(--pad);
  width: calc((100% - 2 * var(--pad)) / var(--n)); left: calc(var(--pad) + (100% - 2 * var(--pad)) / var(--n) * var(--i, 0));
  border-radius: 11px;
  background: linear-gradient(135deg, #5B74FF 0%, #4F6BFF 45%, #14B8A6 140%);
  box-shadow: 0 8px 22px -6px rgba(79,107,255,0.85), 0 0 0 1px rgba(255,255,255,0.22) inset, 0 1px 0 rgba(255,255,255,0.35) inset;
  transition: left .38s cubic-bezier(.22,1,.36,1);        /* smooth slide, no overshoot past the ends */
}
.st-key-topnav div[role="radiogroup"]:has(> label:nth-of-type(1) input:checked) { --i: 0; }
.st-key-topnav div[role="radiogroup"]:has(> label:nth-of-type(2) input:checked) { --i: 1; }
.st-key-topnav div[role="radiogroup"]:has(> label:nth-of-type(3) input:checked) { --i: 2; }
.st-key-topnav div[role="radiogroup"]:has(> label:nth-of-type(4) input:checked) { --i: 3; }
.st-key-topnav div[role="radiogroup"]:has(> label:nth-of-type(5) input:checked) { --i: 4; }
.st-key-topnav div[role="radiogroup"]:has(> label:nth-of-type(6) input:checked) { --i: 5; }
.st-key-topnav div[role="radiogroup"]:has(> label:nth-of-type(7) input:checked) { --i: 6; }
.st-key-topnav div[role="radiogroup"]:has(> label:nth-of-type(8) input:checked) { --i: 7; }

.st-key-topnav label[data-baseweb="radio"] {
  position: relative; z-index: 1; margin: 0 !important; padding: 0 !important; cursor: pointer; justify-content: center;
  height: var(--nav-h); border-radius: 11px; display: flex !important; align-items: center;
}
.st-key-topnav label[data-baseweb="radio"] > div:first-child { display: none !important; }   /* hide the radio dot */
.st-key-topnav label[data-baseweb="radio"] > div:last-child { padding: 0 8px; margin: 0 !important; }
.st-key-topnav label[data-baseweb="radio"] p {
  margin: 0; display: flex; align-items: center; gap: 8px; white-space: nowrap;
  color: rgba(203,213,255,0.66); font-size: 13.2px; font-weight: 600; letter-spacing: 0.1px;
  transition: color .2s ease;
}
.st-key-topnav label[data-baseweb="radio"] span[data-testid="stIconMaterial"] {
  font-size: 19px; transition: transform .4s var(--ease-spring), color .2s ease, filter .2s ease;
}
/* hover: soft glass plate, icon rises, label brightens, a scan line glints along the top */
.st-key-topnav label[data-baseweb="radio"]::before {
  content: ""; position: absolute; inset: 3px; border-radius: 9px; z-index: -1; opacity: 0;
  background: rgba(255,255,255,0.07); box-shadow: 0 0 0 1px rgba(255,255,255,0.08) inset; transition: opacity .2s ease;
}
.st-key-topnav label[data-baseweb="radio"]::after {
  content: ""; position: absolute; top: 3px; left: 50%; width: 0; height: 2px; border-radius: 2px; transform: translateX(-50%);
  background: linear-gradient(90deg, transparent, #7DE9DB, transparent); transition: width .35s ease; filter: drop-shadow(0 0 4px #7DE9DB);
}
.st-key-topnav label[data-baseweb="radio"]:hover::before { opacity: 1; }
.st-key-topnav label[data-baseweb="radio"]:hover::after { width: 54%; }
.st-key-topnav label[data-baseweb="radio"]:hover p { color: #fff; }
.st-key-topnav label[data-baseweb="radio"]:hover span[data-testid="stIconMaterial"] { transform: translateY(-2px) scale(1.15); color: #7DE9DB; filter: drop-shadow(0 0 6px rgba(125,233,219,0.6)); }
.st-key-topnav label[data-baseweb="radio"]:active span[data-testid="stIconMaterial"] { transform: scale(0.92); }
.st-key-topnav label[data-baseweb="radio"]:has(input:checked)::before,
.st-key-topnav label[data-baseweb="radio"]:has(input:checked)::after { opacity: 0; width: 0; }
.st-key-topnav label[data-baseweb="radio"]:has(input:checked) p { color: #fff; font-weight: 700; }
.st-key-topnav label[data-baseweb="radio"]:has(input:checked) span[data-testid="stIconMaterial"] { color: #fff; transform: none; filter: none; }
.st-key-topnav label[data-baseweb="radio"]:has(input:focus-visible) { outline: 2px solid #7DE9DB; outline-offset: -2px; }

/* narrow screens: the rail scrolls sideways and every tab sizes to its label */
@media (max-width: 1080px) {
  .crumbs, .user-text, .env .label { display: none; }
  .st-key-topnav { position: relative; top: 0; }
  .st-key-topnav div[role="radiogroup"] { display: flex !important; flex-wrap: nowrap !important; overflow-x: auto; scrollbar-width: none; }
  .st-key-topnav div[role="radiogroup"]::before { display: none; }
  .st-key-topnav label[data-baseweb="radio"] { flex: none; padding: 0 6px !important; }
  .st-key-topnav label[data-baseweb="radio"]:has(input:checked) { background: linear-gradient(135deg, #5B74FF, #14B8A6); }
}

/* ======================================================================
   CONTENT
   ====================================================================== */
/* card rows are CSS grids: equal heights, and they stack on narrow screens */
.grid { display: grid; gap: 16px; align-items: stretch; margin-bottom: 16px; }
.grid.g4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.grid.g2 { grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); }
.grid > .card { height: auto; }
@media (max-width: 1180px) { .grid.g4 { grid-template-columns: repeat(2, minmax(0, 1fr)); } .grid.g2 { grid-template-columns: 1fr; } }
@media (max-width: 620px) { .grid.g4 { grid-template-columns: 1fr; } }

.page-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin: 4px 2px 22px; flex-wrap: wrap; }
.eyebrow { display: inline-flex; align-items: center; gap: 6px; color: var(--brand); font-size: 12px; font-weight: 700; letter-spacing: 1.4px; text-transform: uppercase; }
.eyebrow .mi { font-size: 16px; }
.page-title { color: var(--ink); font-size: 30px; font-weight: 800; letter-spacing: -0.8px; line-height: 1.15; margin: 6px 0 6px; }
.page-sub { color: var(--muted); font-size: 14.5px; line-height: 1.55; max-width: 680px; }
.btn { display: inline-flex; align-items: center; gap: 8px; padding: 10px 16px; border-radius: 12px; font-weight: 700; font-size: 13.5px;
  text-decoration: none !important; transition: transform .2s var(--ease-spring), box-shadow .2s, background .2s; white-space: nowrap; }
.btn .mi { font-size: 18px; }
.btn.primary { color: #fff !important; background: linear-gradient(135deg, #4F6BFF, #3B5BFF 60%, #14B8A6 160%); box-shadow: 0 8px 20px -8px rgba(79,107,255,0.8); }
.btn.primary:hover { transform: translateY(-2px); box-shadow: 0 14px 26px -10px rgba(79,107,255,0.9); }
.btn.ghost { color: var(--text) !important; background: #fff; border: 1px solid var(--line); }
.btn.ghost:hover { transform: translateY(-2px); border-color: var(--line-strong); box-shadow: 0 10px 22px -12px rgba(15,23,42,0.25); }

.card {
  position: relative; background: rgba(255,255,255,0.86); backdrop-filter: blur(8px);
  border: 1px solid var(--line); border-radius: var(--radius); padding: 18px 20px; height: 100%; box-sizing: border-box;
  box-shadow: 0 1px 2px rgba(15,23,42,0.04), 0 8px 24px -12px rgba(15,23,42,0.10);
  transition: transform .25s var(--ease-spring), box-shadow .25s ease, border-color .25s ease;
}
.card.lift:hover { transform: translateY(-3px); border-color: #C7D2FE; box-shadow: 0 2px 4px rgba(15,23,42,0.05), 0 18px 34px -14px rgba(79,107,255,0.30); }
.card-title { display: flex; align-items: center; gap: 8px; color: var(--ink); font-size: 15px; font-weight: 750; letter-spacing: -0.2px; }
.card-title .mi { font-size: 19px; color: var(--brand); }
.card-sub { color: var(--muted); font-size: 13px; margin-top: 3px; }

.kpi { display: flex; gap: 14px; align-items: flex-start; }
.tile { width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center; flex: none; }
.tile .mi { font-size: 22px; }
.tile.blue { background: #EEF2FF; color: #4F6BFF; } .tile.teal { background: #E6FBF7; color: #0F9F8F; }
.tile.violet { background: #F1ECFF; color: #7C5CFF; } .tile.amber { background: #FFF5E1; color: #C27803; }
.kpi .k { color: var(--muted); font-size: 12px; font-weight: 600; }
.kpi .v { color: var(--ink); font-size: 19px; font-weight: 800; letter-spacing: -0.4px; margin-top: 2px; line-height: 1.25; }
.kpi .d { color: var(--faint); font-size: 12px; margin-top: 4px; }
.badge { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; flex: none; padding: 3px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 700; }
.badge.amber { background: #FFF5E1; color: #A15C07; } .badge.green { background: #E7F8EE; color: #166534; } .badge.grey { background: #F1F5F9; color: #475569; }

.steps { margin-top: 14px; display: flex; flex-direction: column; gap: 4px; }
.step { display: flex; gap: 14px; align-items: flex-start; padding: 12px; border-radius: 12px; transition: background .2s; }
.step:hover { background: #F6F8FF; }
.step .num { width: 28px; height: 28px; border-radius: 50%; flex: none; display: grid; place-items: center; font-size: 12.5px; font-weight: 800;
  color: #4F6BFF; background: #EEF2FF; box-shadow: 0 0 0 1px #DCE3FF inset; }
.step .t { color: var(--text); font-weight: 700; font-size: 13.8px; }
.step .s { color: var(--muted); font-size: 12.8px; margin-top: 2px; line-height: 1.45; }
.step .state { margin-left: auto; flex: none; padding-left: 8px; }
.step > div:nth-child(2) { min-width: 0; flex: 1; }
.kpi > div:last-child { min-width: 0; }
.kpi .v { overflow-wrap: anywhere; }
.node { flex-wrap: wrap; row-gap: 0; }

.tree { margin-top: 14px; padding: 14px 16px; border-radius: 12px; background: linear-gradient(180deg, #F8FAFF, #F3F6FD); border: 1px solid var(--line); }
.node { display: flex; align-items: center; gap: 8px; padding: 5px 0; color: var(--text); font-size: 13.5px; font-weight: 600; }
.node .mi { font-size: 19px; color: #F2B33D; }
.node.file .mi { color: #64748B; }
.node .hint { color: var(--faint); font-weight: 500; font-size: 12px; margin-left: 6px; }
.l1 { padding-left: 22px; } .l2 { padding-left: 44px; } .l3 { padding-left: 66px; }
.node.var { color: #4F6BFF; }

.caps { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; }
.cap { display: flex; gap: 12px; align-items: flex-start; }
.cap .t { color: var(--text); font-weight: 700; font-size: 13.8px; }
.cap .s { color: var(--muted); font-size: 12.6px; margin-top: 2px; line-height: 1.45; }

.section-label { color: var(--muted); font-size: 12px; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; margin: 26px 2px 12px; }
.gap { height: 16px; }

.empty { text-align: center; padding: 64px 24px 70px; }
.empty .halo { width: 76px; height: 76px; margin: 0 auto; border-radius: 22px; display: grid; place-items: center;
  background: linear-gradient(140deg, #EEF2FF, #E6FBF7); box-shadow: 0 0 0 8px rgba(79,107,255,0.06), 0 18px 34px -16px rgba(79,107,255,0.6); }
.empty .halo .mi { font-size: 36px; color: #4F6BFF; }
.empty h2 { color: var(--ink); font-size: 22px; font-weight: 800; margin: 20px 0 6px; padding: 0; letter-spacing: -0.4px; }
.empty p { color: var(--muted); max-width: 520px; margin: 0 auto; line-height: 1.55; font-size: 14px; }
.empty .badge { margin-top: 16px; }
</style>
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def icon(name: str) -> str:
    """A Material Symbols icon for use inside HTML."""
    return f'<span class="mi">{name}</span>'
