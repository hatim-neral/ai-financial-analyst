"""Altair charts and HTML bar lists, drawn to the app-screen chart rules.

One question, one series. Straight 2px lines, square-ish columns, 4-5 faint horizontal gridlines,
no y-axis line, no legend for a single series. The chart hue goes on the main data element (the
current period, the selected series); everything else is ink or grey; a loss is the negative colour.
Every chart takes figures already calculated by fin_analyst.metrics.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from fin_analyst import formatting as fmt

from .components import esc
from .theme import FONT, T

# Axis labels in lakh / crore, the way Indian finance teams read them.
# Ticks keep enough precision to stay distinct: crore, then lakh (one decimal under 10 L), then thousands.
RUPEE_AXIS = ("datum.value == 0 ? '0' : (datum.value < 0 ? '−' : '') + '₹' + ("
              "abs(datum.value) >= 10000000 ? format(abs(datum.value) / 10000000, '.1~f') + ' Cr'"
              " : abs(datum.value) >= 1000000 ? format(abs(datum.value) / 100000, '.0f') + ' L'"
              " : abs(datum.value) >= 100000 ? format(abs(datum.value) / 100000, '.1~f') + ' L'"
              " : abs(datum.value) >= 1000 ? format(abs(datum.value) / 1000, '.0f') + 'K'"
              " : format(abs(datum.value), '.0f'))")
METRIC_NAMES = {"revenue": "Revenue", "expenses": "Expenses", "net": "Net revenue"}


def _finish(chart, height: int, on_field: bool = False):
    grid, label, domain = (("rgba(255,255,255,0.18)", "rgba(255,255,255,0.86)", "rgba(255,255,255,0.4)") if on_field
                           else (T["grid"], T["muted"], T["control"]))
    return (chart.properties(height=height, background="transparent")
            .configure(font=FONT)
            .configure_view(strokeWidth=0)
            .configure_axis(gridColor=grid, domain=False, ticks=False, labelColor=label, labelFontSize=12,
                            labelPadding=6, titleColor=label)
            .configure_axisX(grid=False, domain=True, domainColor=domain)
            .configure_legend(labelColor=T["muted"], labelFontSize=12, symbolSize=60, orient="top", title=None))


def _y(field: str, title=None):
    return alt.Y(f"{field}:Q", title=title, axis=alt.Axis(labelExpr=RUPEE_AXIS, tickCount=4))


def _months(mt: pd.DataFrame) -> pd.DataFrame:
    d = mt.rename_axis("month").reset_index()
    d["Month"] = [fmt.month_label(m) for m in d["month"]]
    return d


def monthly_columns(mt: pd.DataFrame, metric: str = "net", highlight: str | None = None, height: int = 170,
                    on_field: bool = False):
    """Columns per month; the highlighted (current) month carries the hue, losses the negative colour.
    `on_field` draws for the account-coloured hero: white current month, translucent white others."""
    d = _months(mt)
    d["v"] = d[metric].astype(float)
    hl = highlight or d["month"].iloc[-1]
    d["kind"] = ["current" if m == hl else "loss" if v < 0 else "other" for m, v in zip(d["month"], d["v"])]
    hover = alt.selection_point(on="pointerover", clear="pointerout", fields=["Month"], nearest=False, empty=False)
    chart = alt.Chart(d).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        x=alt.X("Month:N", sort=list(d["Month"]), title=None,
                axis=alt.Axis(labelAngle=0, labelOverlap=True, labelExpr="split(datum.label, ' ')[0] + ' ' + slice(split(datum.label, ' ')[1], 2)")),
        y=_y("v"),
        color=alt.Color("kind:N", legend=None,
                        scale=alt.Scale(domain=["current", "other", "loss"], range=(["#ffffff", "rgba(255,255,255,0.42)", "#ffc9c9"] if on_field
                                      else [T["hue"], T["grey"], T["negative"]]))),
        opacity=alt.condition(hover, alt.value(0.75), alt.value(1)),
        tooltip=[alt.Tooltip("Month:N"), alt.Tooltip("v:Q", title=METRIC_NAMES[metric], format=",.0f")],
    ).add_params(hover)
    return _finish(chart, height, on_field)


def trend_line(mt: pd.DataFrame, metric: str = "revenue", height: int = 240):
    """One series in the hue, straight segments, a hover rule with the month's value."""
    d = _months(mt)
    d["v"] = d[metric].astype(float)
    x = alt.X("Month:N", sort=list(d["Month"]), title=None,
              axis=alt.Axis(labelAngle=0, labelOverlap=True, labelExpr="split(datum.label, ' ')[0] + ' ' + slice(split(datum.label, ' ')[1], 2)"))
    hover = alt.selection_point(nearest=True, on="pointerover", clear="pointerout", fields=["Month"], empty=False)
    line = alt.Chart(d).mark_line(strokeWidth=2, color=T["hue"]).encode(x=x, y=_y("v"))
    dots = alt.Chart(d).mark_point(filled=True, size=50, color=T["hue"]).encode(
        x=x, y=_y("v"), opacity=alt.condition(hover, alt.value(1), alt.value(0)))
    rule = alt.Chart(d).mark_rule(color=T["control"]).encode(
        x=x, opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("Month:N"), alt.Tooltip("v:Q", title=METRIC_NAMES[metric], format=",.0f")]).add_params(hover)
    layers = line + dots + rule
    if (d["v"] < 0).any():  # a series that crosses zero shows the zero line
        layers += alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=T["control"]).encode(y="y:Q")
    return _finish(layers, height)


def period_columns(periods: list[dict], height: int = 200):
    """Net revenue per quarter or year; the latest period in the hue, losses negative, others grey."""
    d = pd.DataFrame(periods)
    d["label"] = d["period"] + d["partial"].map({True: "*", False: ""})
    last = d["label"].iloc[-1]
    d["kind"] = ["current" if lab == last else "loss" if v < 0 else "other" for lab, v in zip(d["label"], d["net_revenue"])]
    chart = alt.Chart(d).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2, size=28).encode(
        x=alt.X("label:N", sort=list(d["label"]), title=None, axis=alt.Axis(labelAngle=0)),
        y=_y("net_revenue"),
        color=alt.Color("kind:N", legend=None,
                        scale=alt.Scale(domain=["current", "other", "loss"], range=[T["hue"], T["grey"], T["negative"]])),
        tooltip=[alt.Tooltip("label:N", title="Period"), alt.Tooltip("net_revenue:Q", title="Net revenue", format=",.0f"),
                 alt.Tooltip("net_margin_pct:Q", title="Margin %", format=".1f")])
    return _finish(chart, height)


def growth_bars(rows: list[dict], bad_when_up: bool):
    """Signed growth per category in grey; only the changes that hurt carry the negative colour."""
    d = pd.DataFrame([r for r in rows if r.get("growth_pct") is not None])
    if d.empty:
        return None
    d = d.sort_values("growth_pct", ascending=False)
    d["kind"] = ["bad" if (g > 0) == bad_when_up and g != 0 else "fine" for g in d["growth_pct"]]
    d["label"] = [f"{g:+.0f}%" for g in d["growth_pct"]]
    base = alt.Chart(d).encode(y=alt.Y("category:N", sort=list(d["category"]), title=None, axis=alt.Axis(labelLimit=170)))
    bars = base.mark_bar(height=12, cornerRadiusEnd=2).encode(
        x=alt.X("growth_pct:Q", title=None, axis=alt.Axis(labelExpr="(datum.value > 0 ? '+' : '') + datum.value + '%'", tickCount=4)),
        color=alt.Color("kind:N", legend=None, scale=alt.Scale(domain=["bad", "fine"], range=[T["negative"], T["grey"]])),
        tooltip=[alt.Tooltip("category:N", title="Category"), alt.Tooltip("growth_pct:Q", title="Growth %", format="+.1f"),
                 alt.Tooltip("first_window_monthly_avg:Q", title="Avg / month before", format=",.0f"),
                 alt.Tooltip("last_window_monthly_avg:Q", title="Avg / month now", format=",.0f")])
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=T["control"]).encode(x="x:Q")
    return _finish(bars + zero, max(140, 28 * len(d)))


def bar_list(categories: list[dict], limit: int = 6) -> str:
    """A ranked money list: label and value on one line, a 2px proportional bar under it (top in ink)."""
    items = categories[:limit]
    top = max((c["total"] for c in items), default=0) or 1
    rows = []
    for c in items:
        width = 88 * c["total"] / top
        rows.append(
            f'<div class="row"><div><div class="row-name">{esc(c["category"])}</div>'
            f'<div class="row-bar"><i style="width:{width:.1f}%"></i></div></div>'
            f'<div class="row-fig">{fmt.money(c["total"])}<small>{fmt.pct(c["share_of_total_pct"], signed=False)}</small></div></div>')
    return f'<div class="rows">{"".join(rows)}</div>'
