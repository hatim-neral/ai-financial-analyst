"""Plan: budgets, cash runway and saved what-if scenarios, laid out as settings rows.

Each section is one row: a label column (title, description and a summary of the current
values) beside the panel that holds the work. What the user types lives in session state per
account (`ctx.plan`); every figure is calculated by fin_analyst.metrics, and the AI reads the
same inputs through the get_budget_status / get_cash_runway tools.
"""

from __future__ import annotations

import math

import altair as alt
import pandas as pd
import streamlit as st

from fin_analyst import formatting as fmt
from fin_analyst import metrics

from . import feedback
from .answer_charts import chart_for
from .charts import RUPEE_AXIS, _finish
from .components import esc, show_evidence, signed_class, title
from .theme import T

ALL_REVENUE, ALL_EXPENSES = "All revenue", "All expenses"


def new_plan() -> dict:
    return {"budgets": {}, "cash_balance": None, "scenarios": []}


def page(ctx, head, ask) -> None:
    with head.left:
        title("Plan", f"Budgets, cash runway and what-if scenarios for {esc(ctx.name)}. "
                      "The AI can read what you set here.")
    for i, (name, render) in enumerate((("Budgets", _budgets), ("Cash runway", _runway), ("Scenarios", _scenarios))):
        if i:
            st.divider()
        render(ctx, ask)


def _label(name: str, description: str, summary: str | None = None) -> None:
    st.html(f'<div class="card-title">{esc(name)}</div><div class="card-sub">{description}</div>'
            + (f'<div class="card-sub" style="margin-top:12px">{summary}</div>' if summary else ""))


# ---------------------------------------------------------------------------------
def _recent_average(df: pd.DataFrame, end: str, months: list[str], n: int = 3) -> pd.Series:
    upto = [m for m in months if m <= end][-n:]
    exp = df[(df["type"] == "expense") & (df["month"].isin(upto))]
    return exp.groupby("category")["amount"].sum() / max(len(upto), 1)


def _budgets(ctx, ask) -> None:
    plan, df = ctx.plan, ctx.df
    status = metrics.budget_status(df, plan["budgets"], ctx.end) if plan["budgets"] else None
    left, right = st.columns([2, 3], gap="large")
    with left:
        summary = None
        if status:
            r = status.result
            over = r["over_budget_count"]
            summary = (f'{fmt.month_label(r["month"])}: <span class="num">{fmt.money(r["total_actual"])}</span> of '
                       f'<span class="num">{fmt.money(r["total_budget"])}</span> used, '
                       + (f'<span class="neg">{over} over budget</span>.' if over else "everything within budget."))
        _label("Budgets", f"A monthly limit per expense category, compared with {fmt.month_label(ctx.end)}.", summary)
        b1, b2 = st.columns(2)
        if b1.button("Suggest budgets", key="budget_suggest", icon=":material/auto_fix_high:",
                     help="Last 3 months' average plus 2%, rounded up to the next ₹5,000"):
            avg = _recent_average(df, ctx.end, ctx.months)
            plan["budgets"] = {c: float(math.ceil(v * 1.02 / 5000) * 5000) for c, v in avg.items() if v > 0}
            st.session_state.pop(f"budget_editor_{ctx.account_id}", None)
            st.rerun()
        if b2.button("Clear", key="budget_clear", type="tertiary", icon=":material/backspace:", disabled=not plan["budgets"]):
            plan["budgets"] = {}
            st.session_state.pop(f"budget_editor_{ctx.account_id}", None)
            st.rerun()
        avg = _recent_average(df, ctx.end, ctx.months).sort_values(ascending=False)
        table = pd.DataFrame({"Category": avg.index, "Avg / month, last 3 (₹)": avg.round(0).values,
                              "Budget / month (₹)": [plan["budgets"].get(c) for c in avg.index]})
        edited = st.data_editor(
            table, key=f"budget_editor_{ctx.account_id}", hide_index=True, width="stretch",
            disabled=["Category", "Avg / month, last 3 (₹)"],
            column_config={"Avg / month, last 3 (₹)": st.column_config.NumberColumn(format="localized"),
                           "Budget / month (₹)": st.column_config.NumberColumn(format="localized", min_value=0, step=1000)})
        plan["budgets"] = {r["Category"]: float(r["Budget / month (₹)"]) for _, r in edited.iterrows()
                           if pd.notna(r["Budget / month (₹)"]) and r["Budget / month (₹)"] > 0}
        if st.button("Ask AI which budgets are at risk", key="ask_budgets", type="tertiary", icon=":material/chat:",
                     disabled=not ctx.client.providers or not plan["budgets"]):
            ask("Which budgets are at risk or broken most often, and which cut would help the margin most?")
    with right, st.container(key=f"card_budgets_{ctx.account_id}"):
        if not plan["budgets"]:
            st.html('<div class="empty">Set a budget on the left, or press Suggest budgets, to see this month against it.</div>')
        else:
            r = metrics.budget_status(df, plan["budgets"], ctx.end).result
            rows = []
            for c in r["categories"]:
                fill = min(c["used_pct"], 100)
                tone = {"over": "neg", "near": "warn"}.get(c["status"], "")
                rows.append(
                    f'<div class="row fixed"><div><div class="row-name">{esc(c["category"])}</div>'
                    f'<div class="track"><i class="{c["status"]}" style="width:{fill:.1f}%"></i></div>'
                    f'<div class="row-sub">Over in {c["months_over_budget"]} of {r["months_in_data"]} months</div></div>'
                    f'<div class="row-fig"><span class="{tone}">{fmt.money(c["actual"])}</span> / {fmt.money(c["monthly_budget"])}'
                    f'<small>{fmt.pct(c["used_pct"], 0, signed=False)} used</small></div></div>')
            st.html(f'<div class="rows">{"".join(rows)}</div>')
            if r["over_budget_count"] == 0:
                feedback.celebrate(f"budgets-{ctx.account_id}-{r['month']}-{sorted(plan['budgets'].items())}")
            show_evidence(metrics.budget_status(df, plan["budgets"], ctx.end), df, show_table=True)


# ---------------------------------------------------------------------------------
def _runway(ctx, ask) -> None:
    plan, df = ctx.plan, ctx.df
    last = ctx.months[-1]
    left, right = st.columns([2, 3], gap="large")
    with left:
        _label("Cash runway", f"How long your bank balance lasts at the recent average net revenue. "
                              f"Uses the last months of the data, up to {fmt.month_label(last)}.")
        bal = st.number_input(f"Cash in the bank at the end of {fmt.month_label(last)} (₹)", min_value=0.0,
                              value=float(plan["cash_balance"] or 0.0), step=100_000.0, format="%.0f",
                              key=f"cash_{ctx.account_id}")
        plan["cash_balance"] = bal if bal > 0 else None
        basis = st.segmented_control("Average over", [3, 6, 12], default=3, key="runway_basis",
                                     format_func=lambda n: f"{n} months") or 3
        if st.button("Ask AI how to extend the runway", key="ask_runway", type="tertiary", icon=":material/chat:",
                     disabled=not ctx.client.providers or not plan["cash_balance"]):
            ask("How long will our cash last, and which costs are growing fastest and shortening the runway?")
    with right, st.container(key=f"card_runway_{ctx.account_id}"):
        if not plan["cash_balance"]:
            st.html('<div class="empty">Enter your current bank balance to see how many months it lasts.</div>')
            return
        ev = metrics.cash_runway(df, plan["cash_balance"], basis)
        r = ev.result
        if r["cash_flow_positive"]:
            value, tone = "Cash-flow positive", "pos"
            sub = (f"Net revenue averaged {fmt.signed_money(r['avg_monthly_net_revenue'])} a month over the last "
                   f"{r['basis_months']} months, so the balance grows.")
        else:
            months_left = r["runway_months"]
            value, tone = f"{months_left:.1f} months", "" if months_left >= 18 else "warn" if months_left >= 6 else "neg"
            sub = (f"Burning {fmt.money(r['monthly_burn'])} a month (average of the last {r['basis_months']} months). "
                   + (f"Cash runs out in {fmt.month_label(r['cash_runs_out_month'])}." if r["cash_runs_out_month"]
                      else "Cash lasts beyond the next two years."))
        st.html(f'<div class="answer-label">Runway from {fmt.money(r["cash_balance"])}</div>'
                f'<div class="answer-value {tone}">{esc(value)}</div><div class="card-sub">{esc(sub)}</div>')
        chart = chart_for(ev)
        if chart is not None:
            st.altair_chart(chart, width="stretch")
        st.caption(r["note"])
        show_evidence(ev, df, show_table=True)


# ---------------------------------------------------------------------------------
def describe(adjustments: list[dict]) -> str:
    return ", ".join(f"{a['category']} {fmt.pct(a['change_pct'], 0)}" for a in adjustments)


def save_scenario(plan: dict, name: str, adjustments: list[dict], improves: bool = False, account_id: str = "") -> None:
    plan["scenarios"] = [s for s in plan["scenarios"] if s["name"] != name] + [{"name": name, "adjustments": adjustments}]
    st.toast(f"Saved “{name}” to Plan", icon=":material/bookmark_added:")
    if improves:  # a plan that lifts the margin is worth a moment (shown after the rerun)
        st.session_state["pending_celebration"] = f"scenario-{account_id}-{name}"


def _tool_adj(a: dict) -> dict:
    """UI labels -> what_if() category names."""
    cat = {ALL_REVENUE: "all revenue", ALL_EXPENSES: "all expenses"}.get(a["category"], a["category"])
    return {"category": cat, "change_pct": a["change_pct"]}


def _scenarios(ctx, ask) -> None:
    plan, df = ctx.plan, ctx.df
    cats = sorted(df["category"].unique())
    left, right = st.columns([2, 3], gap="large")
    with left:
        _label("Scenarios", f"Change categories by a percentage and see net revenue and margin for {esc(ctx.period)}. "
                            "You can also save one from any what-if answer in Ask AI.")
        name = st.text_input("Name", key="scen_name", placeholder="e.g. Lean marketing")
        rows = st.data_editor(
            pd.DataFrame({"Change": [ALL_REVENUE], "By %": [5.0]}), key=f"scen_editor_{ctx.account_id}", num_rows="dynamic",
            hide_index=True, width="stretch",
            column_config={"Change": st.column_config.SelectboxColumn(options=[ALL_REVENUE, ALL_EXPENSES, *cats], required=True),
                           "By %": st.column_config.NumberColumn(min_value=-100, max_value=1000, step=1, format="%+.0f%%")})
        adjustments = [{"category": r["Change"], "change_pct": float(r["By %"])} for _, r in rows.iterrows()
                       if isinstance(r["Change"], str) and pd.notna(r["By %"])]
        if adjustments:
            p = metrics.what_if(df, [_tool_adj(a) for a in adjustments], ctx.start, ctx.end).result
            st.html(f'<div class="card-sub">Net revenue <span class="num">{fmt.money(p["baseline"]["net_revenue"])}</span> → '
                    f'<span class="num">{fmt.money(p["scenario"]["net_revenue"])}</span>; margin '
                    f'{fmt.pct(p["baseline"]["net_margin_pct"], signed=False)} → {fmt.pct(p["scenario"]["net_margin_pct"], signed=False)}</div>')
        if st.button("Save scenario", key="scen_save", type="primary", icon=":material/bookmark_add:", disabled=not adjustments):
            save_scenario(plan, name.strip() or describe(adjustments), adjustments,
                          improves=(p.get("net_margin_change_pct_points") or 0) > 0, account_id=ctx.account_id)
            st.rerun()

    with right, st.container(key=f"card_scenarios_{ctx.account_id}"):
        if not plan["scenarios"]:
            st.html('<div class="empty">Saved scenarios appear here side by side.</div>')
            return
        results = []
        for s in plan["scenarios"]:
            try:
                results.append((s, metrics.what_if(df, [_tool_adj(a) for a in s["adjustments"]], ctx.start, ctx.end)))
            except metrics.MetricError as exc:
                st.warning(f"“{s['name']}” can't be applied to this data: {exc}")
        if not results:
            return
        base = results[0][1].result["baseline"]
        d = pd.DataFrame([{"Scenario": "Actual", "v": base["net_revenue"], "kind": "actual"}]
                         + [{"Scenario": s["name"], "v": ev.result["scenario"]["net_revenue"], "kind": "scenario"}
                            for s, ev in results])
        st.html(f'<div class="card-title">Net revenue by scenario</div><div class="card-sub">{esc(ctx.period)}</div>')
        chart = alt.Chart(d).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2, size=40).encode(
            x=alt.X("Scenario:N", sort=list(d["Scenario"]), title=None, axis=alt.Axis(labelAngle=0, labelLimit=140)),
            y=alt.Y("v:Q", title=None, axis=alt.Axis(labelExpr=RUPEE_AXIS, tickCount=4)),
            color=alt.Color("kind:N", legend=None, scale=alt.Scale(domain=["actual", "scenario"], range=[T["grey"], T["hue"]])),
            tooltip=["Scenario:N", alt.Tooltip("v:Q", title="Net revenue", format=",.0f")])
        st.altair_chart(_finish(chart, 200), width="stretch")
        for i, (s, ev) in enumerate(results):
            r = ev.result
            delta = r["net_revenue_change"]
            st.html(f'<div class="row"><div><div class="row-name">{esc(s["name"])}</div>'
                    f'<div class="row-sub">{esc(describe(s["adjustments"]))} · margin '
                    f'{fmt.pct(r["baseline"]["net_margin_pct"], signed=False)} → {fmt.pct(r["scenario"]["net_margin_pct"], signed=False)}</div></div>'
                    f'<div class="row-fig"><span class="{signed_class(delta, True)}">{fmt.signed_money(delta)}</span>'
                    f'<small>{fmt.money(r["scenario"]["net_revenue"])}</small></div></div>')
            b1, b2, _ = st.columns([1, 1, 2])
            if b1.button("Ask AI", key=f"scen_ask_{i}", type="tertiary", icon=":material/chat:", disabled=not ctx.client.providers):
                ask(f"What if {describe(s['adjustments'])}? Show net revenue and margin before and after, and say which change matters most.")
            if b2.button("Delete", key=f"scen_del_{i}", type="tertiary", icon=":material/delete:"):
                plan["scenarios"] = [x for x in plan["scenarios"] if x["name"] != s["name"]]
                st.rerun()
