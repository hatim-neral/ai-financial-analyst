"""The screens: Home, Insights, Transactions, Plan and Ask AI.

Each screen answers one question first (see .taste-skill/app/notes.md). Pages only lay out
results; every figure comes from fin_analyst.metrics or the agent.
"""

from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

from fin_analyst import agent, config, metrics
from fin_analyst import formatting as fmt
from fin_analyst.llm import ChatClient
from fin_analyst.loader import LoadResult
from fin_analyst.samples import Sample

from . import charts, feedback, followups, plan as plan_page, river
from .answer_charts import chart_for
from .components import (badge, bridge, card_head, countup, esc, ledger_table, odometer, safe_md, show_evidence,
                         signed_class, title, tx_rows)

DEEP_DIVES = (
    "Compare the first half of the period with the second half: what changed in revenue, costs and margin, and which categories drove it?",
    "Which costs are growing faster than revenue, and what share of revenue does each of them take now?",
    "Were there any unusual months? Separate the one-offs from lasting changes and explain the biggest ones.",
    "Break the period down by quarter. Which quarter was best and which was worst for net revenue, and why?",
    "What if our largest expense were 10% lower and revenue 5% higher? Show net revenue and margin before and after.",
    "If the last six months' trend continues, what will net revenue look like over the next quarter? How reliable is that?",
)


@dataclass
class Ctx:
    df: pd.DataFrame
    result: LoadResult
    name: str
    sample: Sample | None
    months: list[str]
    start: str
    end: str
    client: ChatClient
    account_id: str = "default"
    plan: dict = field(default_factory=plan_page.new_plan)

    @property
    def context(self) -> dict:
        """User inputs the planning tools need (budgets, cash balance)."""
        return {"budgets": self.plan.get("budgets") or {}, "cash_balance": self.plan.get("cash_balance")}

    @property
    def key(self) -> str:
        """Changes with the account and period, so keyed blocks reset their own state."""
        return hashlib.md5(f"{self.name}|{self.start}|{self.end}".encode()).hexdigest()[:8]

    @property
    def period(self) -> str:
        s, e = fmt.month_label(self.start), fmt.month_label(self.end)
        return s if self.start == self.end else f"{s} – {e}"

    @property
    def window(self) -> pd.DataFrame:
        return self.df[(self.df["month"] >= self.start) & (self.df["month"] <= self.end)]


@dataclass
class Header:
    """The title row: the h1 on the left, actions on the right (the period control is already there)."""
    left: object
    actions: object


def go(page: str) -> None:
    st.session_state["page"] = page
    st.rerun()


def ask(question: str) -> None:
    st.session_state["pending_question"] = question
    go("ask")


def _num(x) -> str:
    return f'<span class="num">{x}</span>'


# ---------------------------------------------------------------------------------
# Home: "How is the business doing this period, and what moved last month?"
# ---------------------------------------------------------------------------------
def home(ctx: Ctx, head: Header) -> None:
    df, s, e = ctx.df, ctx.start, ctx.end
    summary = metrics.period_summary(df, s, e)
    r = summary.result
    mt = metrics.monthly_table(df)
    window = mt.loc[(mt.index >= s) & (mt.index <= e)]
    prev = mt.at[e, "previous_month"]
    move = metrics.explain_change(df, e, "net") if not fmt.is_missing(prev) else None

    finding = ""
    if move:
        mr = move.result
        lead = mr["drivers_sorted_by_impact"][0] if mr["drivers_sorted_by_impact"] and mr["change"] else None
        finding = (f" {fmt.month_label(e)} came in <b>{fmt.signed_money(mr['change'])}</b> against "
                   f"{fmt.month_label(prev)}" + (f", led by {esc(lead['category'].rsplit(' (', 1)[0])}." if lead else "."))
    with head.left:
        title(ctx.name, f"Net revenue <b>{fmt.money(r['net_revenue'])}</b> for {esc(ctx.period)} at a "
                        f"{fmt.pct(r['net_margin_pct'], signed=False)} margin.{finding}", avatar=ctx.name)
    with head.actions:
        if st.button("Ask AI", key="home_ask", type="primary", icon=":material/chat:", disabled=not ctx.client.providers,
                     help="Ask why a number moved, or what if you changed something"):
            go("ask")

    def mom(col: str):
        v = mt.at[e, f"{col}_mom_pct"]
        return None if fmt.is_missing(prev) or fmt.is_missing(v) else f"{fmt.pct(v)} vs {fmt.month_label(prev)}"

    with st.container(key="row_eq_top"):
        left, right = st.columns([2, 1])
        with left, st.container(key=f"card_net_{ctx.key}"):
            card_head("Net revenue", ctx.period)
            margin_line = f"{fmt.pct(r['net_margin_pct'], signed=False)} of revenue"
            # A real win, said plainly: the latest month is the best of the period (needs a few months to mean it).
            best = len(window) >= 3 and window["net"].iloc[-1] > 0 and window["net"].iloc[-1] >= window["net"].max()
            best_pill = f' <span class="pill pos">Best month in this period: {fmt.month_label(e)}</span>' if best else ""
            # The account colour floods this card; the figure rolls into place digit by digit.
            reading = fmt.money_words(r["net_revenue"]) if abs(r["net_revenue"]) >= 1e5 else ""
            st.html(odometer(r["net_revenue"])
                    + f'<div class="answer-delta">{f"≈ {esc(reading)} · " if reading else ""}{margin_line} · '
                      f'{r["months_with_data"]} months{best_pill}</div>')
            if best:
                feedback.celebrate(f"best-{ctx.account_id}-{s}-{e}")
            if len(window) > 1:
                st.altair_chart(charts.monthly_columns(window, "net", height=220, on_field=True), width="stretch")
            with st.container(key="strip"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Revenue", fmt.money(r["total_revenue"]), delta=mom("revenue"))
                c2.metric("Expenses", fmt.money(r["total_expenses"]), delta=mom("expenses"), delta_color="inverse")
                c3.metric("Net margin", fmt.pct(r["net_margin_pct"], signed=False))
                c4.metric("Transactions", f"{r['revenue_transactions'] + r['expense_transactions']:,}")
            show_evidence(summary, df)
        with right, st.container(key=f"card_moved_{ctx.key}"):
            _what_moved(ctx, move, prev)

    with st.container(key=f"card_river_{ctx.key}"):
        card_head("Where the money flows", ctx.period,
                  "Every rupee in, and where it went. Ribbon widths are the real amounts; hover one for its figure.")
        if not river.render(df, s, e):
            st.html('<div class="empty">No money moved in this period.</div>')
        else:
            try:
                show_evidence(metrics.top_categories(df, "expenses", s, e, n=15), df)
            except metrics.MetricError:
                pass

    with st.container(key="row_eq_mid"):
        b, c = st.columns(2)
        with b, st.container(key=f"card_recent_{ctx.key}"):
            card_head("Recent transactions", f"{len(ctx.window):,} in period")
            recent = ctx.window.sort_values(["date", "line"], ascending=False).head(5)
            st.html(tx_rows(recent))
            if st.button("View all transactions", key="see_all", type="tertiary", icon=":material/arrow_forward:"):
                go("activity")
        with c, st.container(key=f"card_attention_{ctx.key}"):
            items = (_budget_insight(ctx) + _insights(df, s, e))[:3]
            card_head("Needs a look", f"{len(items)} item{'s' if len(items) != 1 else ''}")
            if not items:
                st.html('<div class="empty">Nothing unusual in this period.</div>')
            for i, it in enumerate(items):
                st.html(f'<div class="row"><div><div class="row-name">{esc(it["title"])}</div>'
                        f'<div class="row-sub">{esc(it["body"])}</div></div>'
                        f'<div class="row-fig"><span class="pill {it["tone"]}">{esc(it["kind"])}</span></div></div>')
                if st.button("Ask AI about this", key=f"ask_insight_{i}", type="tertiary", icon=":material/subdirectory_arrow_right:",
                             disabled=not ctx.client.providers):
                    ask(it["question"])


def _what_moved(ctx: Ctx, move, prev) -> None:
    """The signature element: last month's net change split into each category's signed part."""
    e = ctx.end
    if move is None:
        card_head(f"What moved in {fmt.month_label(e)}")
        st.html(f'<div class="empty">There is no {fmt.month_label(metrics.previous_month(e))} in the data to compare with.</div>')
        return
    r = move.result
    card_head(f"What moved in {fmt.month_label(e)}", f"vs {fmt.month_label(prev)}",
              f'Net revenue <span class="{signed_class(r["change"], True)}">{fmt.signed_money(r["change"])}</span>'
              f' ({fmt.pct(r["change_pct"])})')
    parts = []
    for d in r["drivers_sorted_by_impact"]:
        name, kind = d["category"].rsplit(" (", 1) if " (" in d["category"] else (d["category"], "")
        is_expense = kind.startswith("expense")
        parts.append((name, "Expense" if is_expense else "Revenue", round(-(d["change"] or 0) if is_expense else (d["change"] or 0), 2)))
    # The five largest moves by size, then everything else, so the bridge lands exactly on this month.
    parts.sort(key=lambda x: -abs(x[2]))
    shown, rest = parts[:5], parts[5:]
    other = round(r["change"] - sum(p[2] for p in shown), 2)
    if rest or abs(other) >= 0.5:
        shown.append(("All other categories", f"{len(rest)} more", other))
    st.html(bridge(fmt.month_label(prev), r["previous_total"], shown, fmt.month_label(e), r["current_total"]))
    if st.button("Explain in Insights", key="moved_explain", type="tertiary", icon=":material/arrow_forward:"):
        st.session_state["change_month"] = e
        st.session_state["change_metric"] = "net"
        go("insights")
    show_evidence(move, ctx.df)


def _budget_insight(ctx: Ctx) -> list[dict]:
    if not ctx.plan.get("budgets"):
        return []
    r = metrics.budget_status(ctx.df, ctx.plan["budgets"], ctx.end).result
    over = [c for c in r["categories"] if c["status"] == "over"]
    if not over:
        return []
    o = over[0]
    return [{"kind": "Over budget", "tone": "neg", "title": f"{o['category']} over by {fmt.money(-o['remaining'])}",
             "body": f"{fmt.money(o['actual'])} spent in {fmt.month_label(r['month'])} against {fmt.money(o['monthly_budget'])}",
             "question": f"Why is {o['category']} over budget in {fmt.month_label_long(r['month'])}, and how often has it "
                         "broken the budget before?"}]


def _insights(df: pd.DataFrame, s: str, e: str) -> list[dict]:
    """Deterministic findings, each with a follow-up question for the AI."""
    out = []
    try:
        fa = metrics.find_anomalies(df, "both", s, e).result["unusual_category_months"]
        if fa:
            a = fa[0]
            high = (a["deviation"] or 0) > 0
            out.append({"kind": "Unusual", "tone": "warn", "title": f"{a['category']}, {fmt.month_label(a['month'])}",
                        "body": f"{fmt.money(a['amount'])} against a typical {fmt.money(a['typical_monthly_amount'])}",
                        "question": f"Why was {a['category']} so {'high' if high else 'low'} in "
                                    f"{fmt.month_label_long(a['month'])}, and what did it do to net revenue that month?"})
    except metrics.MetricError:
        pass
    try:
        rows = metrics.category_growth(df, "expenses", s, e).result["categories_fastest_growth_first"]
        g = next((x for x in rows if (x["growth_pct"] or 0) > 0), None)
        if g:
            out.append({"kind": "Rising cost", "tone": "neg", "title": f"{g['category']} {fmt.pct(g['growth_pct'], 0)}",
                        "body": f"{fmt.money(g['last_window_monthly_avg'])} a month now, from {fmt.money(g['first_window_monthly_avg'])}",
                        "question": f"Why are {g['category']} costs rising, and what share of revenue do they take now "
                                    "compared with the start of the period?"})
    except metrics.MetricError:
        pass
    try:
        pb = metrics.period_breakdown(df, "quarter", s, e).result
        if len(pb["periods"]) >= 2 and pb["best_by_net_revenue"] != pb["worst_by_net_revenue"]:
            best = next(p for p in pb["periods"] if p["period"] == pb["best_by_net_revenue"])
            worst = next(p for p in pb["periods"] if p["period"] == pb["worst_by_net_revenue"])
            out.append({"kind": "Best quarter", "tone": "neutral", "title": f"{best['period']} at {fmt.money(best['net_revenue'])}",
                        "body": f"Weakest was {worst['period']} at {fmt.money(worst['net_revenue'])}",
                        "question": f"Compare {best['period']} with {worst['period']}: what explains the difference in "
                                    "net revenue, category by category?"})
    except metrics.MetricError:
        pass
    return out


# ---------------------------------------------------------------------------------
# Insights: "Which way is each line moving, and why?"
# ---------------------------------------------------------------------------------
def insights(ctx: Ctx, head: Header) -> None:
    df, s, e = ctx.df, ctx.start, ctx.end
    mt = metrics.monthly_table(df)
    window = mt.loc[(mt.index >= s) & (mt.index <= e)]
    trend = metrics.monthly_trend(df, s, e)
    with head.left:
        title("Insights", f"{esc(ctx.name)} · {esc(ctx.period)}. {esc(trend.summary.split('. ', 1)[-1])}")

    with st.container(key="row_eq_trend"):
        left, right = st.columns([2, 1])
        with left, st.container(key=f"card_trend_{ctx.key}"):
            h1, h2 = st.columns([1, 1], vertical_alignment="center")
            with h1:
                st.html('<div class="card-title">Month by month</div>')
            with h2:
                metric = st.segmented_control("Series", ["revenue", "expenses", "net"], default="revenue", key="trend_metric",
                                              format_func=charts.METRIC_NAMES.get, label_visibility="collapsed") or "revenue"
            total = float(window[metric].sum())
            st.html(f'<div class="answer-label">{charts.METRIC_NAMES[metric]}, {esc(ctx.period)}</div>' + countup(total))
            if len(window) > 1:
                st.altair_chart(charts.trend_line(window, metric), width="stretch")
            with st.expander("Table of every month"):
                st.dataframe(trend.table, hide_index=True)
            show_evidence(trend, df)
        with right, st.container(key=f"card_moves_{ctx.key}"):
            card_head("Biggest monthly moves", ctx.period)
            moves = []
            for col, label, good_up in (("revenue_mom_pct", "Revenue", True), ("expenses_mom_pct", "Expenses", False),
                                        ("net_mom_change", "Net revenue", True)):
                series = window[col].dropna()
                if series.empty:
                    continue
                for m in dict.fromkeys([series.idxmin(), series.idxmax()]):
                    v = float(series[m])
                    shown = fmt.pct(v) if col.endswith("pct") else fmt.signed_money(v)
                    moves.append((abs(v) if col.endswith("pct") else 0, f'<div class="row"><div><div class="row-name">{label}</div>'
                                  f'<div class="row-sub">{fmt.month_label(m)} vs {fmt.month_label(metrics.previous_month(m))}</div></div>'
                                  f'<div class="row-fig"><span class="{signed_class(v, good_up)}">{shown}</span></div></div>'))
            if moves:
                st.html(f'<div class="rows">{"".join(html_row for _, html_row in moves[:6])}</div>')
            else:
                st.html('<div class="empty">Needs at least two consecutive months.</div>')

    with st.container(key="row_eq_drivers"):
        cols = st.columns(2)
        for col, metric in zip(cols, ("revenue", "expenses")):
            with col, st.container(key=f"card_top_{metric}_{ctx.key}"):
                try:
                    ev = metrics.top_categories(df, metric, s, e, n=8)
                except metrics.MetricError as exc:
                    card_head(f"Top {metric}")
                    st.html(f'<div class="empty">{esc(exc)}</div>')
                    continue
                card_head(f"Top {'revenue' if metric == 'revenue' else 'expense'} categories", ctx.period)
                st.html(charts.bar_list(ev.result["categories"], limit=6))
                show_evidence(ev, df)

    with st.container(key="row_eq_periods"):
        left, right = st.columns(2)
        with left, st.container(key=f"card_periods_{ctx.key}"):
            h1, h2 = st.columns([1, 1], vertical_alignment="center")
            with h1:
                st.html('<div class="card-title">Net revenue by period</div>')
            with h2:
                grain = st.segmented_control("Group by", ["quarter", "year"], default="quarter", key="grain",
                                             format_func=str.title, label_visibility="collapsed") or "quarter"
            try:
                pb = metrics.period_breakdown(df, grain, s, e)
                st.html(f'<div class="card-sub">Best {esc(pb.result["best_by_net_revenue"])}, weakest '
                        f'{esc(pb.result["worst_by_net_revenue"])}. * marks a partial {grain}.</div>')
                st.altair_chart(charts.period_columns(pb.result["periods"]), width="stretch")
                show_evidence(pb, df, show_table=True)
            except metrics.MetricError as exc:
                st.html(f'<div class="empty">{esc(exc)}</div>')
        with right, st.container(key=f"card_growth_{ctx.key}"):
            h1, h2 = st.columns([1, 1], vertical_alignment="center")
            with h1:
                st.html('<div class="card-title">Growing and shrinking</div>')
            with h2:
                gm = st.segmented_control("Measure", ["expenses", "revenue"], default="expenses", key="growth_metric",
                                          format_func=str.title, label_visibility="collapsed") or "expenses"
            try:
                cg = metrics.category_growth(df, gm, s, e)
                w = cg.result["window_months"]
                st.html(f'<div class="card-sub">Average month, first {w} vs last {w} months. '
                        f'{"Rising costs" if gm == "expenses" else "Falling revenue"} in red.</div>')
                chart = charts.growth_bars(cg.result["categories_fastest_growth_first"], bad_when_up=(gm == "expenses"))
                if chart is not None:
                    st.altair_chart(chart, width="stretch")
                show_evidence(cg, df, show_table=True)
            except metrics.MetricError as exc:
                st.html(f'<div class="empty">{esc(exc)}</div>')

    eligible = [m for m in ctx.months if metrics.previous_month(m) in ctx.months and s <= m <= e]
    with st.container(key=f"card_change_{ctx.key}"):
        card_head("Explain a month", "vs the month before")
        if not eligible:
            st.html('<div class="empty">This needs at least two consecutive months in the selected period.</div>')
            return
        default = st.session_state.get("change_month")
        if default not in eligible:
            default = metrics.largest_decline_month(df, "revenue")
            default = default if default in eligible else eligible[-1]
            st.session_state["change_month"] = default
        cm, cx = st.columns([1, 2], vertical_alignment="bottom")
        month = cm.selectbox("Month", eligible, format_func=fmt.month_label, key="change_month")
        measure = cx.segmented_control("Measure", ["revenue", "expenses", "net"], default="revenue", key="change_metric",
                                       format_func=charts.METRIC_NAMES.get) or "revenue"
        ev = metrics.explain_change(df, month, measure)
        st.markdown(safe_md(ev.summary))
        st.dataframe(ev.table, hide_index=True)
        show_evidence(ev, df)


# ---------------------------------------------------------------------------------
# Transactions: "Which rows make up these totals?"
# ---------------------------------------------------------------------------------
def activity(ctx: Ctx, head: Header) -> None:
    df = ctx.window
    is_rev = df["type"] == "revenue"
    money_in, money_out = df.loc[is_rev, "amount"].sum(), df.loc[~is_rev, "amount"].sum()
    with head.left:
        title("Transactions", f"{len(df):,} rows in {esc(ctx.period)}: <b>{fmt.money(money_in)}</b> in from "
                              f"{int(is_rev.sum()):,} revenue rows, <b>{fmt.money(money_out)}</b> out over "
                              f"{int((~is_rev).sum()):,} expense rows.")

    c_type, c_search = st.columns([1, 2], vertical_alignment="center")
    with c_type:
        show = st.segmented_control("Show", ["All", "Revenue", "Expenses"], default="All",
                                    key="data_filter", label_visibility="collapsed") or "All"
    with c_search:
        query = st.text_input("Search", key="data_search", placeholder="Search categories or descriptions",
                              label_visibility="collapsed", icon=":material/search:")
    rows = df if show == "All" else df[is_rev] if show == "Revenue" else df[~is_rev]
    cats = st.pills("Categories", sorted(rows["category"].unique()), selection_mode="multi",
                    key=f"data_cats_{show}", label_visibility="collapsed")
    if cats:
        rows = rows[rows["category"].isin(cats)]
    if query.strip():
        q = query.strip().lower()
        rows = rows[rows["category"].str.lower().str.contains(q, regex=False)
                    | rows["description"].fillna("").str.lower().str.contains(q, regex=False)]

    with st.container(key=f"card_table_{ctx.key}"):
        if rows.empty:
            card_head("No matching transactions")
            st.html('<div class="empty">No transactions match. Clear the search or pick other categories.</div>')
        else:
            notes = []
            for label, mask in (("Largest in", rows["type"] == "revenue"), ("largest out", rows["type"] != "revenue")):
                if mask.any():
                    top = rows[mask].loc[rows.loc[mask, "amount"].idxmax()]
                    notes.append(f"{label} {fmt.money(top['amount'])} ({esc(top['category'])}, "
                                 f"{top['date'].strftime('%-d %b %Y')}, CSV line {int(top['line'])})")
            card_head(f"{len(rows):,} of {len(ctx.df):,} transactions", "CSV line = line in your file", "; ".join(notes) + ".")
            view = rows.assign(date=rows["date"].dt.strftime("%Y-%m-%d")).rename(columns={"line": "CSV line"})
            ledger_table(view, height=min(36 + 35 * len(view), 560))
    if ctx.result.issues:
        with st.expander(f"Rows that were skipped or adjusted · {len(ctx.result.issues):,}"):
            st.dataframe(ctx.result.issues_frame(), hide_index=True)


# ---------------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------------
def plan(ctx: Ctx, head: Header) -> None:
    plan_page.page(ctx, head, ask)


# ---------------------------------------------------------------------------------
# Ask AI: "Answer my question with checked figures."
# ---------------------------------------------------------------------------------
def ask_ai(ctx: Ctx, head: Header) -> None:
    configured = bool(ctx.client.providers)
    history: list[agent.AnswerResult] = st.session_state["history"]
    limit_reached = st.session_state["questions_asked"] >= config.MAX_QUESTIONS_PER_SESSION
    pending = st.session_state.pop("pending_question", None)
    fresh = st.session_state.pop("fresh_answer", None)
    disabled = not configured or limit_reached

    with head.left:
        title("Ask AI", f"Questions about {esc(ctx.name)}. The AI picks the calculations, Python does the maths, and every "
                        "figure is checked against the results before you see it.")
    with head.actions:
        if history and st.button("Clear conversation", key="clear_chat", icon=":material/delete_sweep:"):
            st.session_state["history"] = []
            st.rerun()

    _, mid, _ = st.columns([1, 5, 1])
    with mid:
        if not configured:
            st.info("Questions need an LLM API key: set `GROQ_API_KEY` (free at console.groq.com) in Streamlit secrets "
                    "or as an environment variable, then restart the app.")
        for i, res in enumerate(history):
            _render_answer(ctx, res, i, fresh=(i == fresh))

        if history and not disabled and history[-1].status in ("verified", "no_figures", "fallback"):
            ideas = followups.suggest(history[-1], ctx.months, {h.question for h in history})
            if ideas:
                with st.container(key="followups"):
                    st.html('<div class="ideas-label">Keep digging</div>')
                    for j, q in enumerate(ideas):
                        with st.container(key=f"follow_{j}"):
                            if st.button(q, key=f"follow_{len(history)}_{j}", icon=":material/subdirectory_arrow_right:"):
                                pending = q

        if limit_reached:
            st.warning(f"This session has reached its limit of {config.MAX_QUESTIONS_PER_SESSION} questions. "
                       "Reload the page to start a new session.")

        groups = []
        if ctx.sample:
            groups.append((f"Built for {ctx.sample.name}", ctx.sample.questions))
        else:
            decline = metrics.largest_decline_month(ctx.df, "revenue")
            if decline and metrics.previous_month(decline) in ctx.months:
                groups.append(("Start here", (f"Why did revenue decline in {fmt.month_label_long(decline)}?",)))
        planning = []
        if ctx.plan.get("budgets"):
            planning.append("Which budgets are at risk this month, and which have been broken most often?")
        if ctx.plan.get("cash_balance"):
            planning.append("How long will our cash last at the current burn, and what is shortening the runway?")
        if planning:
            groups.append(("Your plan", tuple(planning)))
        groups.append(("Works on any data", DEEP_DIVES))

        def idea_list():
            with st.container(key="ideas"):
                for gi, (label, questions) in enumerate(groups):
                    st.html(f'<div class="ideas-label">{esc(label)}</div>')
                    for i, q in enumerate(questions):
                        if st.button(q, key=f"q_{gi}_{i}", disabled=disabled, icon=":material/arrow_forward:"):
                            return q
            return None

        if history:
            with st.expander("More questions to ask"):
                picked = idea_list()
        else:
            with st.container(key="card_ideas"):
                card_head("Questions to start with", "Hard ones welcome: comparisons, one-offs, what-ifs, runway")
                picked = idea_list()
        pending = picked or pending

        typed = st.chat_input("Ask about revenue, costs, budgets, runway, what-ifs…", max_chars=config.MAX_QUESTION_CHARS,
                              disabled=disabled, key="chat_input")
        question = typed or pending
        if question and configured and not limit_reached:
            st.session_state["questions_asked"] += 1
            past = [(h.question, h.text) for h in history if h.status in ("verified", "no_figures")]
            st.html(f'<div class="q-row"><div class="q">{html.escape(question)}</div></div>')
            with st.status("Reading your question…", expanded=True) as status:
                def on_event(kind: str, message: str) -> None:
                    status.update(label=f"{message}…" if kind in ("think", "tool") else message)
                    status.write(message)

                res = agent.answer_question(question, ctx.df, ctx.client, history=past, context=ctx.context,
                                            on_event=on_event)
                ok = res.status in ("verified", "no_figures")
                status.update(label=_status_label(res), state="complete" if ok else "error", expanded=False)
            history.append(res)
            st.session_state["fresh_answer"] = len(history) - 1
            st.rerun()


def _status_label(res: agent.AnswerResult) -> str:
    calcs = len(res.evidence)
    bits = [f"{calcs} calculation{'s' if calcs != 1 else ''}"]
    if res.guard is not None:
        bits.append(f"{res.guard.n_checked} figure{'s' if res.guard.n_checked != 1 else ''} checked")
    bits.append(f"{res.latency_s:.1f}s")
    lead = {"verified": "Verified", "no_figures": "Answered", "fallback": "Showing the verified calculation",
            "llm_error": "AI busy, try again shortly"}.get(res.status, "Done")
    return f"{lead} · " + " · ".join(bits)


def _render_answer(ctx: Ctx, res: agent.AnswerResult, index: int, fresh: bool = False) -> None:
    st.html(f'<div class="q-row"><div class="q">{html.escape(res.question)}</div></div>')
    with st.container(key=f"card_answer_{index}"):
        if res.status == "verified":
            n = res.guard.n_checked
            badge(f"Verified · {n} figure{'s' if n != 1 else ''} match the calculations"
                  + (", after one correction" if res.retried else ""), fresh=fresh)
            if fresh:
                feedback.chime("verified")
        elif res.status == "fallback":
            badge(res.status_text, warn=True, fresh=fresh)
        if res.status in ("verified", "no_figures", "fallback"):
            st.markdown(safe_md(res.text))
        elif res.status == "llm_error":
            st.info(res.text, icon=":material/hourglass_top:")
        else:
            st.info(res.text)

        shown = 0
        for ev in res.evidence:
            if shown >= 2:
                break
            chart = chart_for(ev)
            if chart is not None:
                st.html(f'<div class="card-sub">[{esc(ev.id)}] {esc(ev.title)}</div>')
                st.altair_chart(chart, width="stretch")
                shown += 1
        for ev in res.evidence:
            show_evidence(ev, ctx.df, label=f"[{ev.id}] {ev.title} · {len(ev.row_lines):,} CSV lines", show_table=True)
            if ev.tool == "what_if":
                adj = [{"category": a["category"], "change_pct": a["change_pct"]} for a in ev.result["adjustments"]]
                if st.button("Save this scenario to Plan", key=f"save_scen_{index}_{ev.id}", type="tertiary",
                             icon=":material/bookmark_add:"):
                    plan_page.save_scenario(ctx.plan, plan_page.describe(adj), adj,
                                            improves=(ev.result.get("net_margin_change_pct_points") or 0) > 0,
                                            account_id=ctx.account_id)
                    st.rerun()
        if res.rejected_draft:
            with st.expander("Rejected AI draft (not used as the answer)"):
                if res.guard and res.guard.unsupported:
                    st.markdown("Figures not found in any calculation: "
                                + ", ".join(f"`{t}`" for t in res.guard.unsupported_text()))
                st.text(res.rejected_draft)
        if res.steps or res.llm_calls:
            tokens = res.usage["prompt_tokens"] + res.usage["completion_tokens"]
            with st.expander(f"{_status_label(res)} · {res.provider or 'no AI call'}"):
                for step in res.steps:
                    st.write(step)
                st.caption(f"{tokens:,} tokens · {res.llm_calls} AI calls")
