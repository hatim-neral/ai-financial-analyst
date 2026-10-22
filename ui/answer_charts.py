"""A small chart for each kind of tool result, shown inside the AI's answer.

Charts only re-draw numbers already in the Evidence result, so they carry the same guarantee as
the answer text. Ledger rules: grey for context, the chart hue on the main element (the comparison
period, the scenario, the projection), the negative colour only on what hurts, dashed lines only
for projections and reference lines.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from fin_analyst import formatting as fmt
from fin_analyst.evidence import Evidence

from . import charts
from .charts import RUPEE_AXIS, _finish
from .theme import T


def _hbars(d: pd.DataFrame, label: str, value: str, kind: str | None = None, pct: bool = False, reference: float | None = None):
    axis = (alt.Axis(labelExpr="datum.value + '%'", tickCount=4) if pct
            else alt.Axis(labelExpr=RUPEE_AXIS, tickCount=4))
    color = (alt.Color(f"{kind}:N", legend=None, scale=alt.Scale(domain=["bad", "warn", "fine", "top"],
                                                                 range=[T["negative"], T["warning"], T["grey"], T["ink"]]))
             if kind else alt.value(T["grey"]))
    bars = alt.Chart(d).mark_bar(height=12, cornerRadiusEnd=2).encode(
        y=alt.Y(f"{label}:N", sort=list(d[label]), title=None, axis=alt.Axis(labelLimit=180)),
        x=alt.X(f"{value}:Q", title=None, axis=axis), color=color,
        tooltip=[alt.Tooltip(f"{label}:N"), alt.Tooltip(f"{value}:Q", format="+,.1f" if pct else "+,.0f")])
    layers = bars + alt.Chart(pd.DataFrame({"x": [reference or 0]})).mark_rule(
        color=T["control"], strokeDash=[3, 3] if reference else []).encode(x="x:Q")
    return _finish(layers, max(120, 28 * len(d)))


def _columns(d: pd.DataFrame, x: str, y: str, kind: str, height: int = 180):
    chart = alt.Chart(d).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2, size=36).encode(
        x=alt.X(f"{x}:N", sort=list(d[x]), title=None, axis=alt.Axis(labelAngle=0, labelLimit=140)),
        y=alt.Y(f"{y}:Q", title=None, axis=alt.Axis(labelExpr=RUPEE_AXIS, tickCount=4)),
        color=alt.Color(f"{kind}:N", legend=None, scale=alt.Scale(domain=["base", "main"], range=[T["grey"], T["hue"]])),
        tooltip=[alt.Tooltip(f"{x}:N"), alt.Tooltip(f"{y}:Q", title="Amount", format=",.0f")])
    return _finish(chart, height)


def chart_for(ev: Evidence):
    """Return an Altair chart for this evidence, or None when a chart wouldn't add anything."""
    r, tool = ev.result, ev.tool
    try:
        if tool == "compare_periods":
            a, b = r["period_a"], r["period_b"]
            la = f"{fmt.month_label(a['period_start'])} – {fmt.month_label(a['period_end'])}"
            lb = f"{fmt.month_label(b['period_start'])} – {fmt.month_label(b['period_end'])}"
            rows = [{"Measure": m, "Period": p, "v": blk[k]} for m, k in
                    (("Revenue", "total_revenue"), ("Expenses", "total_expenses"), ("Net revenue", "net_revenue"))
                    for p, blk in ((la, a), (lb, b))]
            d = pd.DataFrame(rows)
            chart = alt.Chart(d).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
                x=alt.X("Measure:N", sort=["Revenue", "Expenses", "Net revenue"], title=None, axis=alt.Axis(labelAngle=0)),
                xOffset=alt.XOffset("Period:N", sort=[la, lb]),
                y=alt.Y("v:Q", title=None, axis=alt.Axis(labelExpr=RUPEE_AXIS, tickCount=4)),
                color=alt.Color("Period:N", sort=[la, lb], title=None, scale=alt.Scale(domain=[la, lb], range=[T["grey"], T["hue"]])),
                tooltip=["Measure:N", "Period:N", alt.Tooltip("v:Q", title="Amount", format=",.0f")])
            return _finish(chart, 200)
        if tool == "explain_month_change":
            rows = []
            for d in r["drivers_sorted_by_impact"][:8]:
                change = d["change"] or 0
                # An expense going up hurts; revenue going down hurts.
                is_expense = r["metric"] == "expenses" or (r["metric"] == "net_revenue" and "(expense)" in d["category"])
                hurts = change > 0 if is_expense else change < 0
                rows.append({"category": d["category"], "change": change, "kind": "bad" if hurts else "fine"})
            return _hbars(pd.DataFrame(rows), "category", "change", "kind")
        if tool == "get_top_categories":
            d = pd.DataFrame(r["categories"])
            d["kind"] = ["top" if i == 0 else "fine" for i in range(len(d))]
            return _hbars(d, "category", "total", "kind")
        if tool == "period_breakdown":
            return charts.period_columns(r["periods"], height=200)
        if tool == "category_growth":
            return charts.growth_bars(r["categories_fastest_growth_first"], bad_when_up=(r["metric"] == "expenses"))
        if tool == "category_trend":
            d = pd.DataFrame(r["months"]).set_index("month").rename(columns={"amount": "revenue"})
            return charts.trend_line(d[["revenue"]], "revenue", height=180)
        if tool == "get_monthly_trend":
            d = pd.DataFrame(r["months"]).set_index("month").rename(columns={"net_revenue": "net"})
            return charts.monthly_columns(d[["net"]], "net", height=180)
        if tool == "find_anomalies":
            items = r["unusual_category_months"][:8]
            if not items:
                return None
            d = pd.DataFrame([{"label": f"{x['category']}, {fmt.month_label(x['month'])}", "dev": x["deviation"]} for x in items])
            return _hbars(d, "label", "dev")
        if tool == "expense_ratios":
            d = pd.DataFrame(r["expense_categories"][:8])
            d["kind"] = ["top" if i == 0 else "fine" for i in range(len(d))]
            return _hbars(d, "category", "ratio_to_revenue_pct", "kind", pct=True)
        if tool == "what_if":
            d = pd.DataFrame([{"Case": "Actual", "v": r["baseline"]["net_revenue"], "kind": "base"},
                              {"Case": "Scenario", "v": r["scenario"]["net_revenue"], "kind": "main"}])
            return _columns(d, "Case", "v", "kind")
        if tool == "project_trend":
            d = pd.DataFrame([{"Month": fmt.month_label(r["basis_end"]), "v": r["last_actual"], "kind": "Actual"}]
                             + [{"Month": fmt.month_label(p["month"]), "v": p["projected_value"], "kind": "Projected"}
                                for p in r["projections"]])
            base = alt.Chart(d).encode(x=alt.X("Month:N", sort=list(d["Month"]), title=None, axis=alt.Axis(labelAngle=0)),
                                       y=alt.Y("v:Q", title=None, axis=alt.Axis(labelExpr=RUPEE_AXIS, tickCount=4),
                                               scale=alt.Scale(zero=False)))
            line = base.mark_line(strokeDash=[5, 4], strokeWidth=2, color=T["hue"])
            dots = base.mark_point(filled=True, size=50).encode(
                color=alt.Color("kind:N", title=None, scale=alt.Scale(domain=["Actual", "Projected"], range=[T["ink"], T["hue"]])),
                tooltip=["Month:N", "kind:N", alt.Tooltip("v:Q", format=",.0f")])
            return _finish(line + dots, 180)
        if tool == "get_cash_runway":
            d = pd.DataFrame(r["balance_projection"])
            d["Month"] = [fmt.month_label(m) for m in d["month"]]
            x = alt.X("Month:N", sort=list(d["Month"]), title=None,
                      axis=alt.Axis(labelAngle=0, labelOverlap=True,
                                    labelExpr="split(datum.label, ' ')[0] + ' ' + slice(split(datum.label, ' ')[1], 2)"))
            line = alt.Chart(d).mark_line(strokeDash=[5, 4], strokeWidth=2, color=T["hue"]).encode(
                x=x, y=alt.Y("projected_balance:Q", title=None, axis=alt.Axis(labelExpr=RUPEE_AXIS, tickCount=4)),
                tooltip=["Month:N", alt.Tooltip("projected_balance:Q", title="Projected balance", format=",.0f")])
            zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=T["negative"], strokeDash=[3, 3]).encode(y="y:Q")
            return _finish(line + zero, 180)
        if tool == "get_budget_status":
            d = pd.DataFrame(r["categories"])
            d["kind"] = d["status"].map({"over": "bad", "near": "warn", "under": "fine"})
            return _hbars(d, "category", "used_pct", "kind", pct=True, reference=100)
    except (KeyError, ValueError, TypeError):
        return None
    return None
