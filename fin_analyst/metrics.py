"""Deterministic financial calculations.

Every public function takes the clean DataFrame from `loader.load_csv` and returns an
`Evidence` record. The LLM layer calls these as tools; the dashboard calls them
directly. No figure shown anywhere in the app is computed outside this module.

Definitions used throughout:
  revenue       = sum of rows with type == "revenue"
  expenses      = sum of rows with type == "expense"
  net revenue   = revenue − expenses   (the brief's "net revenue"; i.e. net income)
  MoM change %  = (this month − previous calendar month) ÷ |previous month| × 100,
                  left blank when the previous month has no data or is zero
"""

from __future__ import annotations

import calendar
import math
import re

import pandas as pd

from . import formatting as fmt
from .evidence import Evidence

METRICS = ("revenue", "expenses", "net")
MAX_TREND_MONTHS = 36
MAX_DRIVERS = 10


class MetricError(ValueError):
    """Invalid request (unknown month, bad metric...). The message is safe to show to
    users and to pass back to the LLM so it can correct itself."""


# ---------------------------------------------------------------------------------
# Month helpers
# ---------------------------------------------------------------------------------
_MONTH_NAMES = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTH_NAMES.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
_MONTH_NAMES["sept"] = 9


def available_months(df: pd.DataFrame) -> list[str]:
    return sorted(df["month"].unique().tolist())


def previous_month(month: str) -> str:
    return str(pd.Period(month, "M") - 1)


def _parse_month(value, months: list[str]) -> str:
    """Parse a month reference into 'YYYY-MM' (presence in the data not checked)."""
    v = str(value).strip().lower().replace(",", " ")
    v = re.sub(r"\s+", " ", v)
    if not v:
        raise MetricError("A month is required, in YYYY-MM format.")

    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})", v)
    if m:
        year, mon = int(m.group(1)), int(m.group(2))
        if 1 <= mon <= 12:
            return f"{year:04d}-{mon:02d}"
        raise MetricError(f"'{value}' is not a valid month.")

    if v in _MONTH_NAMES:  # month name without a year
        candidates = [x for x in months if int(x[5:]) == _MONTH_NAMES[v]]
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise MetricError(f"There is no {value.strip().title()} in the data ({months[0]} to {months[-1]}).")
        raise MetricError(f"'{value}' matches several months in the data ({', '.join(candidates)}). "
                          f"Ask the user which year they mean.")

    m = re.fullmatch(r"([a-z]+)[ '\-/]*(\d{2}|\d{4})", v)
    if m and m.group(1) in _MONTH_NAMES:
        year = int(m.group(2))
        year = year + 2000 if year < 100 else year
        return f"{year:04d}-{_MONTH_NAMES[m.group(1)]:02d}"

    m = re.fullmatch(r"(\d{1,2})[-/.](\d{4})", v)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(2)):04d}-{int(m.group(1)):02d}"

    raise MetricError(f"Could not understand the month '{value}'. Use YYYY-MM, e.g. {months[-1]}.")


def resolve_month(df: pd.DataFrame, value) -> str:
    months = available_months(df)
    month = _parse_month(value, months)
    if month not in months:
        raise MetricError(f"No data for {month}. The data covers {months[0]} to {months[-1]}.")
    return month


def resolve_period(df: pd.DataFrame, start=None, end=None) -> tuple[str, str, bool]:
    """Returns (start, end, clamped). Missing bounds default to the full data range."""
    months = available_months(df)
    s = _parse_month(start, months) if start not in (None, "") else months[0]
    e = _parse_month(end, months) if end not in (None, "") else months[-1]
    if s > e:
        s, e = e, s
    clamped = s < months[0] or e > months[-1]
    s, e = max(s, months[0]), min(e, months[-1])
    if s > e or not any(s <= m <= e for m in months):
        raise MetricError(f"No data between {start} and {end}. The data covers {months[0]} to {months[-1]}.")
    return s, e, clamped


# ---------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------
def _r(x, d: int = 2):
    if x is None:
        return None
    x = float(x)
    if math.isnan(x) or math.isinf(x):
        return None
    return round(x, d)


def pct_change(current: float, previous: float | None):
    if previous is None or previous == 0 or pd.isna(previous):
        return None
    return (current - previous) / abs(previous) * 100


def _lines(frame: pd.DataFrame) -> list[int]:
    return sorted(int(x) for x in frame["line"].unique())


def _in_period(df: pd.DataFrame, s: str, e: str) -> pd.DataFrame:
    return df[(df["month"] >= s) & (df["month"] <= e)]


def _type_for(metric: str) -> str:
    return "revenue" if metric == "revenue" else "expense"


def _check_metric(metric: str, allowed=METRICS) -> str:
    metric = str(metric or "").strip().lower()
    aliases = {"expense": "expenses", "cost": "expenses", "costs": "expenses",
               "net_revenue": "net", "net revenue": "net", "profit": "net", "net income": "net"}
    metric = aliases.get(metric, metric)
    if metric not in allowed:
        raise MetricError(f"Unknown metric '{metric}'. Use one of: {', '.join(allowed)}.")
    return metric


# ---------------------------------------------------------------------------------
# Monthly table (used by several tools and the dashboard)
# ---------------------------------------------------------------------------------
def monthly_table(df: pd.DataFrame) -> pd.DataFrame:
    months = available_months(df)
    rev = df[df["type"] == "revenue"].groupby("month")["amount"].sum().reindex(months, fill_value=0.0)
    exp = df[df["type"] == "expense"].groupby("month")["amount"].sum().reindex(months, fill_value=0.0)
    table = pd.DataFrame({"revenue": rev, "expenses": exp})
    table["net"] = table["revenue"] - table["expenses"]
    present = set(months)
    prev = [previous_month(m) if previous_month(m) in present else None for m in months]
    table["previous_month"] = pd.Series(prev, index=months, dtype=object)
    for col in ("revenue", "expenses", "net"):
        prev_vals = [table.at[p, col] if p else None for p in prev]
        table[f"{col}_mom_pct"] = [pct_change(c, p) for c, p in zip(table[col], prev_vals)]
        table[f"{col}_mom_change"] = [None if p is None else c - p for c, p in zip(table[col], prev_vals)]
    table.index.name = "month"
    return table


# ---------------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------------
def period_summary(df: pd.DataFrame, start_month=None, end_month=None) -> Evidence:
    s, e, clamped = resolve_period(df, start_month, end_month)
    sel = _in_period(df, s, e)
    rev_rows, exp_rows = sel[sel["type"] == "revenue"], sel[sel["type"] == "expense"]
    revenue, expenses = float(rev_rows["amount"].sum()), float(exp_rows["amount"].sum())
    net = revenue - expenses
    margin = net / revenue * 100 if revenue else None

    result = {
        "period_start": s,
        "period_end": e,
        "months_with_data": int(sel["month"].nunique()),
        "total_revenue": _r(revenue),
        "total_expenses": _r(expenses),
        "net_revenue": _r(net),
        "net_margin_pct": _r(margin),
        "revenue_transactions": int(len(rev_rows)),
        "expense_transactions": int(len(exp_rows)),
    }
    if clamped:
        result["note"] = "Requested period extends beyond the data; totals cover only the months available."

    period = fmt.month_label(s) if s == e else f"{fmt.month_label(s)} to {fmt.month_label(e)}"
    summary = (f"{period}: total revenue {fmt.money(revenue)}, total expenses {fmt.money(expenses)}, "
               f"net revenue (revenue − expenses) {fmt.money(net)}"
               + (f", a net margin of {fmt.pct(margin, signed=False)}." if margin is not None else "."))
    table = pd.DataFrame({
        "Measure": ["Total revenue", "Total expenses", "Net revenue (revenue − expenses)", "Net margin"],
        "Value": [fmt.money(revenue, 2), fmt.money(expenses, 2), fmt.money(net, 2), fmt.pct(margin, 2, signed=False)],
        "Rows used": [len(rev_rows), len(exp_rows), len(rev_rows) + len(exp_rows), ""],
    })
    return Evidence(
        tool="get_period_summary",
        title=f"Totals for {period}",
        args={"start_month": s, "end_month": e},
        result=result,
        formula=(f"Total revenue = Σ amount of revenue rows; total expenses = Σ amount of expense rows "
                 f"(dates {s} to {e}); net revenue = revenue − expenses; net margin = net ÷ revenue × 100."),
        row_lines=_lines(sel),
        summary=summary,
        table=table,
    )


def monthly_trend(df: pd.DataFrame, start_month=None, end_month=None) -> Evidence:
    s, e, _ = resolve_period(df, start_month, end_month)
    table = monthly_table(df)
    table = table[(table.index >= s) & (table.index <= e)]
    truncated = len(table) > MAX_TREND_MONTHS
    if truncated:
        table = table.iloc[-MAX_TREND_MONTHS:]
        s = table.index[0]

    rows = []
    for month, r in table.iterrows():
        rows.append({
            "month": month,
            "revenue": _r(r["revenue"]),
            "expenses": _r(r["expenses"]),
            "net_revenue": _r(r["net"]),
            "revenue_mom_pct": _r(r["revenue_mom_pct"]),
            "expenses_mom_pct": _r(r["expenses_mom_pct"]),
            "net_revenue_mom_change": _r(r["net_mom_change"]),
        })
    result = {"period_start": s, "period_end": e, "months": rows}
    if truncated:
        result["note"] = f"Only the last {MAX_TREND_MONTHS} months are included."

    parts = [f"{len(rows)} months from {fmt.month_label(s)} to {fmt.month_label(e)}."]
    mom = table["revenue_mom_pct"].dropna()
    if not mom.empty:
        worst, best = mom.idxmin(), mom.idxmax()
        if mom[worst] < 0:
            parts.append(f"Largest revenue decline: {fmt.month_label(worst)} ({fmt.pct(mom[worst])}).")
        if mom[best] > 0:
            parts.append(f"Largest revenue increase: {fmt.month_label(best)} ({fmt.pct(mom[best])}).")
    exp_mom = table["expenses_mom_pct"].dropna()
    if not exp_mom.empty and exp_mom.max() > 0:
        parts.append(f"Largest expense increase: {fmt.month_label(exp_mom.idxmax())} ({fmt.pct(exp_mom.max())}).")

    display = pd.DataFrame({
        "Month": [fmt.month_label(m) for m in table.index],
        "Revenue": [fmt.money(x) for x in table["revenue"]],
        "Revenue MoM": [fmt.pct(x) for x in table["revenue_mom_pct"]],
        "Expenses": [fmt.money(x) for x in table["expenses"]],
        "Expenses MoM": [fmt.pct(x) for x in table["expenses_mom_pct"]],
        "Net revenue": [fmt.money(x) for x in table["net"]],
    })
    return Evidence(
        tool="get_monthly_trend",
        title=f"Monthly trend {fmt.month_label(s)} – {fmt.month_label(e)}",
        args={"start_month": s, "end_month": e},
        result=result,
        formula=("Monthly totals = Σ amount per calendar month and type; MoM % = (month − previous calendar month) "
                 "÷ |previous month| × 100, blank when the previous month has no data or is zero."),
        row_lines=_lines(_in_period(df, s, e)),
        summary=" ".join(parts),
        table=display,
    )


def explain_change(df: pd.DataFrame, month, metric: str = "revenue") -> Evidence:
    metric = _check_metric(metric)
    m = resolve_month(df, month)
    prev = previous_month(m)
    if prev not in available_months(df):
        raise MetricError(f"No data for {prev} (the month before {m}), so the change can't be calculated.")

    pieces = []
    types = ("revenue", "expense") if metric == "net" else (_type_for(metric),)
    for typ in types:
        cur = df[(df["month"] == m) & (df["type"] == typ)].groupby("category")["amount"].agg(["sum", "count"])
        prv = df[(df["month"] == prev) & (df["type"] == typ)].groupby("category")["amount"].agg(["sum", "count"])
        j = cur.join(prv, how="outer", lsuffix="_cur", rsuffix="_prev").fillna(0.0)
        j["delta"] = j["sum_cur"] - j["sum_prev"]
        # Impact on the chosen metric: expenses reduce net revenue.
        j["impact"] = -j["delta"] if (metric == "net" and typ == "expense") else j["delta"]
        j["label"] = [f"{c} ({typ})" if metric == "net" else c for c in j.index]
        j["typ"] = typ
        pieces.append(j)
    cats = pd.concat(pieces)

    def total(month_, typ):
        return float(df[(df["month"] == month_) & (df["type"] == typ)]["amount"].sum())

    if metric == "net":
        cur_total = total(m, "revenue") - total(m, "expense")
        prev_total = total(prev, "revenue") - total(prev, "expense")
    else:
        cur_total, prev_total = total(m, types[0]), total(prev, types[0])
    change = cur_total - prev_total
    change_pct = pct_change(cur_total, prev_total)
    direction = "decreased" if change < 0 else "increased" if change > 0 else "unchanged"

    cats = cats.sort_values("impact", ascending=change < 0, kind="stable")
    drivers = []
    for _, r in cats.head(MAX_DRIVERS).iterrows():
        drivers.append({
            "category": r["label"],
            "previous": _r(r["sum_prev"]),
            "current": _r(r["sum_cur"]),
            "change": _r(r["delta"]),
            "change_pct": _r(pct_change(r["sum_cur"], r["sum_prev"])),
            "share_of_total_change_pct": _r(r["impact"] / change * 100) if change else None,
            "transactions_previous": int(r["count_prev"]),
            "transactions_current": int(r["count_cur"]),
        })

    result = {
        "metric": "net_revenue" if metric == "net" else metric,
        "month": m,
        "previous_month": prev,
        "current_total": _r(cur_total),
        "previous_total": _r(prev_total),
        "change": _r(change),
        "change_pct": _r(change_pct),
        "direction": direction,
        "drivers_sorted_by_impact": drivers,
        "note": "share_of_total_change_pct can exceed 100 when other categories moved the opposite way.",
    }
    if metric == "net":
        result["revenue_change"] = _r(total(m, "revenue") - total(prev, "revenue"))
        result["expenses_change"] = _r(total(m, "expense") - total(prev, "expense"))

    name = {"revenue": "Revenue", "expenses": "Expenses", "net": "Net revenue"}[metric]
    summary = (f"{name} {direction} from {fmt.money(prev_total)} in {fmt.month_label(prev)} to "
               f"{fmt.money(cur_total)} in {fmt.month_label(m)} ({fmt.signed_money(change)}, {fmt.pct(change_pct)}).")
    if drivers and change:
        d = drivers[0]
        summary += (f" The biggest driver was {d['category']}: {fmt.signed_money(d['change'])} "
                    f"({fmt.pct(d['share_of_total_change_pct'], 0, signed=False)} of the change; "
                    f"{d['transactions_previous']} → {d['transactions_current']} transactions).")
        if len(drivers) > 1 and (drivers[1]["share_of_total_change_pct"] or 0) >= 15:
            d2 = drivers[1]
            summary += f" Next: {d2['category']} ({fmt.signed_money(d2['change'])})."
        offsets = [x for x in drivers if (x["share_of_total_change_pct"] or 0) < 0]
        if offsets:
            o = max(offsets, key=lambda x: abs(x["change"] or 0))
            summary += f" Partly offset by {o['category']} ({fmt.signed_money(o['change'])})."

    table = pd.DataFrame({
        "Category": [d["category"] for d in drivers],
        fmt.month_label(prev): [fmt.money(d["previous"]) for d in drivers],
        fmt.month_label(m): [fmt.money(d["current"]) for d in drivers],
        "Change": [fmt.signed_money(d["change"]) for d in drivers],
        "Change %": [fmt.pct(d["change_pct"]) for d in drivers],
        "Share of total change": [fmt.pct(d["share_of_total_change_pct"], 1, signed=False) for d in drivers],
        "Transactions": [f"{d['transactions_previous']} → {d['transactions_current']}" for d in drivers],
    })
    src = df[df["month"].isin([m, prev]) & df["type"].isin(types)]
    return Evidence(
        tool="explain_month_change",
        title=f"{name}: {fmt.month_label(m)} vs {fmt.month_label(prev)}, by category",
        args={"month": m, "metric": metric},
        result=result,
        formula=(f"Change = {name.lower()} in {m} − {name.lower()} in {prev}, split by category; "
                 f"share of change = category impact ÷ total change × 100"
                 + ("; expense increases count as negative impact on net revenue." if metric == "net" else ".")),
        row_lines=_lines(src),
        summary=summary,
        table=table,
    )


def top_categories(df: pd.DataFrame, metric: str = "expenses", start_month=None, end_month=None, n: int = 5) -> Evidence:
    metric = _check_metric(metric, allowed=("revenue", "expenses"))
    try:
        n = max(1, min(int(n), 15))
    except (TypeError, ValueError):
        n = 5
    s, e, clamped = resolve_period(df, start_month, end_month)
    typ = _type_for(metric)
    sel = _in_period(df, s, e)
    sel = sel[sel["type"] == typ]
    if sel.empty:
        raise MetricError(f"There are no {metric} rows between {s} and {e}.")
    grp = sel.groupby("category")["amount"].agg(["sum", "count"]).sort_values("sum", ascending=False)
    total = float(grp["sum"].sum())
    top = grp.head(n)
    cats = [{
        "category": c,
        "total": _r(r["sum"]),
        "share_of_total_pct": _r(r["sum"] / total * 100) if total else None,
        "transactions": int(r["count"]),
    } for c, r in top.iterrows()]
    result = {"metric": metric, "period_start": s, "period_end": e, f"total_{metric}": _r(total),
              "categories": cats, "category_count": int(len(grp))}
    if clamped:
        result["note"] = "Requested period extends beyond the data; only available months are included."

    period = fmt.month_label(s) if s == e else f"{fmt.month_label(s)} to {fmt.month_label(e)}"
    noun = "expense" if metric == "expenses" else "revenue"
    summary = f"Top {noun} categories, {period}: " + "; ".join(
        f"{c['category']} {fmt.money(c['total'])} ({fmt.pct(c['share_of_total_pct'], signed=False)})" for c in cats) + "."
    table = pd.DataFrame({
        "Category": [c["category"] for c in cats],
        "Total": [fmt.money(c["total"]) for c in cats],
        "Share": [fmt.pct(c["share_of_total_pct"], signed=False) for c in cats],
        "Transactions": [c["transactions"] for c in cats],
    })
    return Evidence(
        tool="get_top_categories",
        title=f"Top {noun} categories, {period}",
        args={"metric": metric, "start_month": s, "end_month": e, "n": n},
        result=result,
        formula=f"Category total = Σ amount of {typ} rows per category ({s} to {e}); share = category total ÷ total {metric} × 100.",
        row_lines=_lines(sel[sel["category"].isin(top.index)]),
        summary=summary,
        table=table,
    )


# ---------------------------------------------------------------------------------
# Context for the LLM (no money figures, so the model cannot quote them untested)
# ---------------------------------------------------------------------------------
def dataset_profile(df: pd.DataFrame) -> dict:
    months = available_months(df)
    return {
        "first_month": months[0],
        "last_month": months[-1],
        "months": months if len(months) <= 60 else months[:3] + ["..."] + months[-3:],
        "revenue_categories": sorted(df.loc[df["type"] == "revenue", "category"].unique().tolist())[:40],
        "expense_categories": sorted(df.loc[df["type"] == "expense", "category"].unique().tolist())[:40],
    }


def largest_decline_month(df: pd.DataFrame, metric: str = "revenue") -> str | None:
    """Month with the biggest MoM percentage drop; used to suggest a demo question."""
    mom = monthly_table(df)[f"{metric}_mom_pct"].dropna()
    mom = mom[mom < 0]
    return None if mom.empty else str(mom.idxmin())
