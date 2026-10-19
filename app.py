"""Streamlit interface: upload → validate → dashboard → grounded Q&A.

All figures come from fin_analyst.metrics. This file only handles layout and state.
Run locally with:  streamlit run app.py
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from fin_analyst import agent, config, llm, loader, metrics
from fin_analyst import formatting as fmt
from fin_analyst.evidence import Evidence

ROOT = Path(__file__).parent
SAMPLE_PATH = ROOT / "data" / "sample_financials.csv"
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

st.set_page_config(page_title="AI Financial Analyst", page_icon="📊", layout="wide")


# ---------------------------------------------------------------------------------
# Cached resources
# ---------------------------------------------------------------------------------
@st.cache_data(show_spinner=False, max_entries=8)
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


@st.cache_resource(show_spinner=False)
def get_client() -> llm.ChatClient:
    return llm.ChatClient(llm.load_providers(os.environ, _secrets_source()))


@st.cache_data(show_spinner=False)
def read_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


# ---------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------
def safe_md(text: str) -> str:
    """Markdown from the LLM or the uploaded file: drop images (no remote loads) and
    escape '$' so Streamlit doesn't render it as LaTeX."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text or "")
    return text.replace("$", "\\$")


def show_evidence(ev: Evidence, df: pd.DataFrame, label: str | None = None, show_table: bool = False) -> None:
    with st.expander(label or f"How this is calculated · {len(ev.row_lines):,} source rows"):
        st.markdown(f"**Calculation:** {safe_md(ev.formula)}")
        if show_table and ev.table is not None:
            st.dataframe(ev.table, hide_index=True)
        src = df[df["line"].isin(ev.row_lines)]
        st.markdown(f"**Source rows** ({len(src):,}) — `CSV line` is the line number in the uploaded file")
        view = src.assign(date=src["date"].dt.strftime("%Y-%m-%d"))[
            ["line", "date", "type", "category", "amount", "description"]
        ].rename(columns={"line": "CSV line"})
        if len(view) > 1000:
            st.caption("Showing the first 1,000 rows.")
            view = view.head(1000)
        st.dataframe(view, hide_index=True)


def reset_chat() -> None:
    st.session_state["history"] = []


def set_source(name: str, data: bytes, key: tuple) -> None:
    if st.session_state.get("source_key") != key:
        st.session_state["source_key"] = key
        st.session_state["source"] = (name, data)
        reset_chat()


# ---------------------------------------------------------------------------------
# Sidebar: data source and AI status
# ---------------------------------------------------------------------------------
st.session_state.setdefault("history", [])
st.session_state.setdefault("questions_asked", 0)
client = get_client()

with st.sidebar:
    st.header("Data")
    uploaded = st.file_uploader("Upload a CSV", type=["csv"], key="uploader",
                                help="Revenue and expense transactions. Data stays in memory for this session only.")
    use_sample = st.button("Use sample data", key="use_sample")
    st.download_button("Download sample CSV", read_bytes(str(SAMPLE_PATH)), "sample_financials.csv",
                       "text/csv", key="dl_sample")
    st.download_button("Download blank template", read_bytes(str(TEMPLATE_PATH)), "template.csv",
                       "text/csv", key="dl_template")
    with st.expander("Expected CSV format"):
        st.markdown(FORMAT_HELP)

    st.divider()
    st.subheader("AI analyst")
    if client.providers:
        st.success(f"Connected: {client.label}")
    else:
        st.info("No LLM API key configured. The dashboard works; questions are disabled. "
                "Set GROQ_API_KEY (or GEMINI_API_KEY) in Streamlit secrets.")
    st.caption("Uploaded data is processed in memory and never stored. "
               "Only calculated results (not raw rows) are sent to the LLM.")

if uploaded is not None:
    data = uploaded.getvalue()
    upload_key = ("upload", uploaded.name, len(data), hashlib.sha256(data).hexdigest()[:16])
    if st.session_state.get("last_upload_key") != upload_key:
        st.session_state["last_upload_key"] = upload_key
        set_source(uploaded.name, data, upload_key)
elif st.session_state.get("last_upload_key") is not None:
    # The user removed their upload.
    if st.session_state.get("source_key") == st.session_state["last_upload_key"]:
        st.session_state.pop("source", None)
        st.session_state.pop("source_key", None)
    st.session_state["last_upload_key"] = None

if use_sample:
    set_source("sample_financials.csv", read_bytes(str(SAMPLE_PATH)), ("sample",))

# ---------------------------------------------------------------------------------
# Header and load
# ---------------------------------------------------------------------------------
st.title("📊 AI Financial Analyst")
st.caption("Upload revenue and expense transactions, review the trends, and ask questions in plain English. "
           "Every figure is calculated in Python and traceable to the rows it came from.")

source = st.session_state.get("source")
if source is None:
    st.info("Upload a CSV in the sidebar, or click **Use sample data** to try the app with a synthetic dataset.")
    with st.expander("Expected CSV format", expanded=True):
        st.markdown(FORMAT_HELP)
    st.stop()

name, data = source
result = load_file(data, name)

if not result.ok:
    st.error("**This file can't be analysed.**\n\n" + "\n".join(f"- {safe_md(e)}" for e in result.errors))
    if result.issues:
        st.markdown("**Row-level problems**")
        st.dataframe(result.issues_frame(), hide_index=True)
    st.caption("Fix the file and upload it again, or download the template from the sidebar.")
    st.stop()

df = result.df
months = metrics.available_months(df)
is_sample = st.session_state.get("source_key") == ("sample",)
st.markdown(f"**{safe_md(name)}**{' (synthetic sample data)' if is_sample else ''} · {result.rows_used:,} of {result.rows_read:,} rows used · "
            f"{fmt.month_label(months[0])} – {fmt.month_label(months[-1])} · {result.source_format} format")

notes = len(result.warnings) + (1 if result.issues else 0)
if notes:
    skipped = result.rows_read - result.rows_used
    title = f"⚠️ Data quality notes ({len(result.warnings)} notes, {skipped:,} rows skipped)"
    with st.expander(title, expanded=bool(result.issues)):
        for w in result.warnings:
            st.warning(w)
        if result.issues:
            st.markdown("**Rows with problems** (line = line number in your file)")
            st.dataframe(result.issues_frame(), hide_index=True)
            if result.issues_truncated:
                st.caption(f"…and {result.issues_truncated:,} more problems not listed.")

tab_dash, tab_ask, tab_data = st.tabs(["📈 Dashboard", "💬 Ask the analyst", "🧾 Data"])

# ---------------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------------
with tab_dash:
    if len(months) > 1:
        start, end = st.select_slider("Period", options=months, value=(months[0], months[-1]),
                                      format_func=fmt.month_label, key="period")
    else:
        start = end = months[0]

    summary = metrics.period_summary(df, start, end)
    mt = metrics.monthly_table(df)
    r = summary.result
    end_row = mt.loc[end]
    prev = end_row["previous_month"]

    def delta_pct(col: str):
        v = end_row[f"{col}_mom_pct"]
        return None if fmt.is_missing(prev) or fmt.is_missing(v) else f"{fmt.pct(v)} MoM"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total revenue", fmt.money(r["total_revenue"]), delta=delta_pct("revenue"))
    c2.metric("Total expenses", fmt.money(r["total_expenses"]), delta=delta_pct("expenses"), delta_color="inverse")
    net_delta = end_row["net_mom_change"]
    c3.metric("Net revenue", fmt.money(r["net_revenue"]),
              delta=None if fmt.is_missing(prev) or fmt.is_missing(net_delta) else f"{fmt.signed_money(net_delta)} MoM",
              help="Net revenue = revenue − expenses")
    c4.metric("Net margin", fmt.pct(r["net_margin_pct"], signed=False), help="Net revenue ÷ revenue")
    if not fmt.is_missing(prev):
        st.caption(f"Totals cover {fmt.month_label(start)} – {fmt.month_label(end)}. "
                   f"Arrows compare {fmt.month_label(end)} with {fmt.month_label(prev)}.")
    show_evidence(summary, df)

    st.subheader("Monthly trend")
    chart = mt.loc[(mt.index >= start) & (mt.index <= end), ["revenue", "expenses", "net"]]
    chart = chart.rename(columns={"revenue": "Revenue", "expenses": "Expenses", "net": "Net revenue"})
    st.line_chart(chart)
    trend = metrics.monthly_trend(df, start, end)
    st.dataframe(trend.table, hide_index=True)
    show_evidence(trend, df)

    st.subheader("Top drivers")
    col_rev, col_exp = st.columns(2)
    for col, metric in ((col_rev, "revenue"), (col_exp, "expenses")):
        with col:
            try:
                ev = metrics.top_categories(df, metric, start, end, n=6)
            except metrics.MetricError as exc:
                st.info(str(exc))
                continue
            st.markdown(f"**{ev.title}**")
            bars = pd.DataFrame({"Total": [c["total"] for c in ev.result["categories"]]},
                                index=[c["category"] for c in ev.result["categories"]])
            st.bar_chart(bars)
            st.dataframe(ev.table, hide_index=True)
            show_evidence(ev, df)

    st.subheader("What changed in a month?")
    eligible = [m for m in months if metrics.previous_month(m) in months]
    if not eligible:
        st.info("This needs at least two consecutive months of data.")
    else:
        default = metrics.largest_decline_month(df, "revenue")
        default = default if default in eligible else eligible[-1]
        cm, cx = st.columns([1, 2])
        month = cm.selectbox("Month", eligible, index=eligible.index(default),
                             format_func=fmt.month_label, key="change_month")
        measure = cx.radio("Measure", ["revenue", "expenses", "net"], horizontal=True, key="change_metric",
                           format_func=lambda m: {"revenue": "Revenue", "expenses": "Expenses", "net": "Net revenue"}[m])
        ev = metrics.explain_change(df, month, measure)
        st.markdown(safe_md(ev.summary))
        st.dataframe(ev.table, hide_index=True)
        show_evidence(ev, df)

# ---------------------------------------------------------------------------------
# Q&A
# ---------------------------------------------------------------------------------
with tab_ask:
    configured = bool(client.providers)
    if not configured:
        st.info("Add an LLM API key to enable questions: set `GROQ_API_KEY` (free at console.groq.com) "
                "in Streamlit secrets or as an environment variable, then restart the app.")
    st.caption("The AI chooses which calculation to run; Python does the maths; every figure in the answer is "
               "checked against the calculation results before it is shown, and cites its evidence, e.g. [E1].")

    history: list[agent.AnswerResult] = st.session_state["history"]
    for res in history:
        with st.chat_message("user"):
            st.markdown(safe_md(res.question))
        with st.chat_message("assistant"):
            if res.status == "verified":
                extra = " (after one correction)" if res.retried else ""
                st.success(f"✅ {res.guard.n_checked} figure(s) checked against the calculations{extra}")
                st.markdown(safe_md(res.text))
            elif res.status == "no_figures":
                st.info("ℹ️ No figures in this answer")
                st.markdown(safe_md(res.text))
            elif res.status == "fallback":
                st.warning(f"⚠️ {res.status_text}")
                st.markdown(safe_md(res.text))
            elif res.status == "llm_error":
                st.error(res.text)
            else:
                st.info(res.text)

            for ev in res.evidence:
                show_evidence(ev, df, label=f"[{ev.id}] {ev.title} · {len(ev.row_lines):,} source rows",
                              show_table=True)
            if res.rejected_draft:
                with st.expander("Rejected AI draft (not used as the answer)"):
                    if res.guard and res.guard.unsupported:
                        st.markdown("Figures not found in any calculation: "
                                    + ", ".join(f"`{t}`" for t in res.guard.unsupported_text()))
                    st.text(res.rejected_draft)
            if res.llm_calls:
                tokens = res.usage["prompt_tokens"] + res.usage["completion_tokens"]
                st.caption(f"{res.provider} · {res.latency_s:.1f}s · {tokens:,} tokens · "
                           f"{res.tool_calls} calculation(s)")

    limit_reached = st.session_state["questions_asked"] >= config.MAX_QUESTIONS_PER_SESSION
    if limit_reached:
        st.warning(f"This session has reached its limit of {config.MAX_QUESTIONS_PER_SESSION} questions. "
                   "Reload the page to start a new session.")

    suggestions = []
    decline = metrics.largest_decline_month(df, "revenue")
    if decline and metrics.previous_month(decline) in months:
        suggestions.append(f"Why did revenue decline in {fmt.month_label_long(decline)}?")
    suggestions.append("What were total expenses and net revenue for the period?")
    suggestions.append("What were the top 3 expense categories?")

    pending = None
    if not history:
        st.markdown("**Try one of these:**")
    cols = st.columns(len(suggestions))
    for i, (col, q) in enumerate(zip(cols, suggestions)):
        if col.button(q, key=f"suggest_{i}", disabled=not configured or limit_reached):
            pending = q

    typed = st.chat_input("Ask about revenue, expenses, months or categories…",
                          max_chars=config.MAX_QUESTION_CHARS, disabled=not configured or limit_reached,
                          key="chat_input")
    question = typed or pending
    if question and configured and not limit_reached:
        st.session_state["questions_asked"] += 1
        past = [(h.question, h.text) for h in history if h.status in ("verified", "no_figures")]
        with st.spinner("Calculating and checking the answer…"):
            res = agent.answer_question(question, df, client, history=past)
        history.append(res)
        st.rerun()

# ---------------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------------
with tab_data:
    st.markdown(f"**Cleaned data** — {len(df):,} transactions. `CSV line` is the line number in your file.")
    view = df.assign(date=df["date"].dt.strftime("%Y-%m-%d")).rename(columns={"line": "CSV line"})
    st.dataframe(view, hide_index=True)
    if result.issues:
        st.markdown("**Rows that were skipped or adjusted**")
        st.dataframe(result.issues_frame(), hide_index=True)
