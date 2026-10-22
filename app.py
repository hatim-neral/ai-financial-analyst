"""Streamlit entry point: account (dataset) switcher → validate → pages → grounded Q&A.

All figures come from fin_analyst.metrics; layout lives in ui/. This file only handles
state, the sidebar and routing.
Run locally with:  streamlit run app.py
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import streamlit as st

from fin_analyst import llm, loader, metrics, samples
from fin_analyst import formatting as fmt
from ui import feedback, pages, plan, report, theme
from ui.components import countup_script, esc, safe_md

ROOT = Path(__file__).parent
TEMPLATE_PATH = ROOT / "data" / "template.csv"

FORMAT_HELP = """
**One row per transaction** (recommended):

| date | type | category | amount | description |
|---|---|---|---|---|
| 2026-01-15 | revenue | Subscriptions | 125000 | optional |
| 2026-01-20 | expense | Marketing | 18000 | optional |

- `date`: YYYY-MM-DD preferred; DD/MM/YYYY is read day-first
- `type`: revenue or expense (income / cost also accepted)
- `amount`: a number; ₹, commas and (brackets) for negatives are handled

**Also accepted:** `date, category, revenue, expenses` (one column each).
Max 5 MB / 50,000 rows.
"""

NAV = (("home", "Overview", "space_dashboard"), ("insights", "Insights", "insights"),
       ("activity", "Transactions", "receipt_long"), ("plan", "Plan", "savings"), ("ask", "Ask AI", "chat"))
PAGES = {"home": pages.home, "insights": pages.insights, "activity": pages.activity, "plan": pages.plan,
         "ask": pages.ask_ai}

st.set_page_config(page_title="AI Financial Analyst", page_icon=":material/receipt_long:", layout="wide")
if "_accent" not in st.session_state:
    theme.set_accent(*samples.ACCENTS[samples.DEFAULT.key])
theme.inject()


# ---------------------------------------------------------------------------------
# Cached resources
# ---------------------------------------------------------------------------------
@st.cache_data(show_spinner=False, max_entries=16)
def load_file(data: bytes, name: str) -> loader.LoadResult:
    return loader.load_csv(data, name)


def _secrets_source():
    """st.secrets if a secrets file exists; touching st.secrets without one can show an
    error banner. On Streamlit Cloud, root-level secrets are also set as env vars."""
    candidates = [ROOT / ".streamlit" / "secrets.toml", Path.home() / ".streamlit" / "secrets.toml"]
    try:
        if any(p.exists() for p in candidates) or st.secrets.load_if_toml_exists():
            return st.secrets
    except Exception:
        pass
    return {}


def _keys_fingerprint() -> str:
    """Which provider keys and model settings are set right now (hashed, never the keys themselves). The
    client cache is keyed on it, so adding or changing keys on a running app takes effect at once; a
    cache without this kept serving a client built before the keys existed."""
    source = _secrets_source()
    names = [v for name in llm.PROVIDERS for v in (llm.PROVIDERS[name][2], llm.PROVIDERS[name][3])] + ["LLM_PROVIDER"]
    parts = []
    for n in names:
        try:
            value = os.environ.get(n) or (source.get(n) if source else None)
        except Exception:
            value = None
        parts.append(f"{n}={value or ''}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


@st.cache_resource(show_spinner=False)
def _client_for(fingerprint: str) -> llm.ChatClient:
    return llm.ChatClient(llm.load_providers(os.environ, _secrets_source()))


def get_client() -> llm.ChatClient:
    return _client_for(_keys_fingerprint())


@st.cache_data(show_spinner=False)
def read_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


# ---------------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------------
def set_source(filename: str, data: bytes, key: tuple, sample_key: str | None = None, toast: str | None = None) -> None:
    """`filename` goes to the loader (it checks the .csv extension); `toast` is the name to announce."""
    if st.session_state.get("source_key") != key:
        st.session_state["source_key"] = key
        st.session_state["source"] = (filename, data, sample_key)
        st.session_state["history"] = []
        if toast:
            st.session_state["toast"] = toast


def use_sample(s: samples.Sample, toast: bool = True) -> None:
    theme.set_accent(*samples.ACCENTS.get(s.key, samples.UPLOAD_ACCENT))  # before the theme is drawn
    set_source(s.filename, read_bytes(str(s.path)), ("sample", s.key), s.key, s.name if toast else None)


st.session_state.setdefault("history", [])
st.session_state.setdefault("questions_asked", 0)
st.session_state.setdefault("page", "home")
st.session_state.setdefault("plans", {})  # account id -> budgets, cash balance, saved scenarios
if "source" not in st.session_state:
    use_sample(samples.DEFAULT, toast=False)
client = get_client()

# ---------------------------------------------------------------------------------
# Sidebar: product, account (the scope), navigation, utilities at the bottom
# ---------------------------------------------------------------------------------
UPLOAD = "__upload__"


def _switch_account() -> None:
    # Only a sample account switches the source. When a second file is uploaded, the upload entry's label
    # ("Your file: <name>") changes and Streamlit can hand back that label instead of a key: ignore it.
    key = st.session_state["account"]
    if key in samples.BY_KEY:
        use_sample(samples.BY_KEY[key])


with st.sidebar:
    st.html('<div class="brand"><div class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></div>'
            '<div class="brand-name">AI Financial Analyst</div></div>')
    current = st.session_state["source"][2]
    options = [s.key for s in samples.SAMPLES] + ([UPLOAD] if current is None else [])
    st.session_state["account"] = current or UPLOAD
    st.selectbox("Account", options, key="account", on_change=_switch_account,
                 format_func=lambda k: f"Your file: {st.session_state['source'][0]}" if k == UPLOAD
                 else f"{samples.BY_KEY[k].name} · {samples.BY_KEY[k].kind}")

    st.html('<div class="rail-label">Workspace</div>')
    with st.container(key="nav"):
        for key, label, icon in NAV:
            active = st.session_state["page"] == key
            if st.button(label, key=f"nav_{key}", icon=f":material/{icon}:", type="secondary" if active else "tertiary",
                         width="stretch"):
                st.session_state["page"] = key
                st.rerun()

    st.html('<div class="rail-label">Data</div>')
    with st.expander("Upload a CSV", icon=":material/upload_file:"):
        uploaded = st.file_uploader("Upload a CSV", type=["csv"], key="uploader", label_visibility="collapsed",
                                    help="Revenue and expense transactions. Data stays in memory for this session only.")
        st.download_button("Blank template", read_bytes(str(TEMPLATE_PATH)), "template.csv", "text/csv",
                           key="dl_template", icon=":material/download:", type="tertiary")
        st.markdown(FORMAT_HELP)
    report_slot = st.empty()  # filled once the account is loaded
    st.toggle("Sound and haptics", key="sound_on", value=False,
              help="A soft chime (and a tap on phones that support it) when an answer is verified or you hit a win.")

    on = bool(client.providers)
    st.html(f'<div class="ai-status{"" if on else " off"}"><i></i>'
            f'{esc("AI connected: " + client.label) if on else "AI not configured"}</div>')
    st.caption("Uploads stay in memory for this session. Only calculated results, never raw rows, are sent to the AI.")

if uploaded is not None:
    data = uploaded.getvalue()
    upload_key = ("upload", uploaded.name, len(data), hashlib.sha256(data).hexdigest()[:16])
    if st.session_state.get("last_upload_key") != upload_key:
        st.session_state["last_upload_key"] = upload_key
        theme.set_accent(*samples.UPLOAD_ACCENT)
        set_source(uploaded.name, data, upload_key, toast=uploaded.name)
        st.rerun()
elif st.session_state.get("last_upload_key") is not None:
    # The user removed their upload: go back to the default account.
    if st.session_state.get("source_key") == st.session_state["last_upload_key"]:
        use_sample(samples.DEFAULT)
    st.session_state["last_upload_key"] = None
    st.rerun()

# ---------------------------------------------------------------------------------
# Load the active account
# ---------------------------------------------------------------------------------
name, data, sample_key = st.session_state["source"]
sample = samples.BY_KEY.get(sample_key) if sample_key else None
result = load_file(data, name)

if not result.ok:
    st.html('<div class="title"><h1>This file can\'t be analysed</h1>'
            '<p>Fix the file and upload it again, download the blank template, or pick a sample account.</p></div>')
    st.error("\n".join(f"- {safe_md(e)}" for e in result.errors))
    if result.issues:
        st.dataframe(result.issues_frame(), hide_index=True)
    st.stop()

df = result.df
months = metrics.available_months(df)
if toast_name := st.session_state.pop("toast", None):
    st.toast(f"Opened {toast_name}: {len(df):,} transactions", icon=":material/task_alt:")

# ---------------------------------------------------------------------------------
# Title row: the page's h1 on the left; the period and the page's actions on the right
# ---------------------------------------------------------------------------------
page = st.session_state["page"]
title = sample.name if sample else name
left, right = st.columns([3, 2], vertical_alignment="center")
actions = right.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center")

presets = ["All"] + [p for p, n in (("12M", 12), ("6M", 6), ("3M", 3)) if len(months) > n]
presets += ["Custom"] if len(months) > 1 else []
start, end = months[0], months[-1]
custom = None
if page != "ask":
    with actions:
        choice = st.segmented_control("Period", presets, default="All", key="period_preset",
                                      label_visibility="collapsed") or "All"
    if choice in ("12M", "6M", "3M"):
        start = months[-int(choice[:-1])]
    elif choice == "Custom":
        custom = True

if custom:
    start, end = st.select_slider("Custom period", options=months, value=(months[0], months[-1]),
                                  format_func=fmt.month_label, key="period_custom")

if result.warnings or result.issues:
    skipped = result.rows_read - result.rows_used
    with st.expander(f"Data quality notes: {len(result.warnings)} notes, {skipped:,} rows skipped",
                     icon=":material/warning:", expanded=bool(result.issues)):
        for w in result.warnings:
            st.warning(w)
        if result.issues:
            st.dataframe(result.issues_frame(), hide_index=True)
            if result.issues_truncated:
                st.caption(f"…and {result.issues_truncated:,} more problems not listed.")

account_id = sample.key if sample else hashlib.md5(repr(st.session_state["source_key"]).encode()).hexdigest()[:10]
account_plan = st.session_state["plans"].setdefault(account_id, plan.new_plan())
ctx = pages.Ctx(df=df, result=result, name=title, sample=sample, months=months, start=start, end=end, client=client,
                account_id=account_id, plan=account_plan)
if celebration := st.session_state.pop("pending_celebration", None):
    feedback.celebrate(celebration)
PAGES[page](ctx, pages.Header(left=left, actions=actions))
countup_script()

with report_slot:
    st.download_button("Download report", report.build(ctx, st.session_state["history"]),
                       f"{title.lower().replace(' ', '-')}-report.html", "text/html", key="dl_report",
                       icon=":material/summarize:", width="stretch",
                       help="A printable summary of this account and period, including verified AI answers. "
                            "Open it and use Print, then Save as PDF.")

# Bottom tab bar (shown on phones only, via CSS)
with st.container(key="tabbar"):
    for col, (key, label, icon) in zip(st.columns(len(NAV)), NAV):
        if col.button(label, key=f"tab_{key}", icon=f":material/{icon}:",
                      type="secondary" if page == key else "tertiary"):
            st.session_state["page"] = key
            st.rerun()
