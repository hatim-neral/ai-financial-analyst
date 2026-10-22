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
# Advanced tools: comparisons, growth, anomalies, ratios, scenarios, projections
# ---------------------------------------------------------------------------------
MAX_LIST = 15
MAX_PROJECTION_MONTHS = 12


def _period_label(s: str, e: str) -> str:
    return fmt.month_label(s) if s == e else f"{fmt.month_label(s)} to {fmt.month_label(e)}"


def _months_between(df: pd.DataFrame, s: str, e: str) -> list[str]:
    return [m for m in available_months(df) if s <= m <= e]


def _totals(sel: pd.DataFrame) -> tuple[float, float, float, float | None]:
    revenue = float(sel.loc[sel["type"] == "revenue", "amount"].sum())
    expenses = float(sel.loc[sel["type"] == "expense", "amount"].sum())
    net = revenue - expenses
    return revenue, expenses, net, (net / revenue * 100 if revenue else None)


def _resolve_category(df: pd.DataFrame, value) -> str:
    cats = sorted(df["category"].unique().tolist())
    v = str(value or "").strip().lower()
    if not v:
        raise MetricError("A category name is required.")
    exact = [c for c in cats if c.lower() == v]
    if exact:
        return exact[0]
    partial = [c for c in cats if v in c.lower()]
    if len(partial) == 1:
        return partial[0]
    hint = ", ".join(partial or cats[:25])
    raise MetricError(f"Unknown or ambiguous category '{value}'. Choose one of: {hint}.")


def compare_periods(df: pd.DataFrame, period_a_start, period_a_end, period_b_start, period_b_end) -> Evidence:
    a_s, a_e, _ = resolve_period(df, period_a_start, period_a_end)
    b_s, b_e, _ = resolve_period(df, period_b_start, period_b_end)
    A, B = _in_period(df, a_s, a_e), _in_period(df, b_s, b_e)
    na, nb = int(A["month"].nunique()), int(B["month"].nunique())

    def block(sel, s, e, n):
        rev, exp, net, margin = _totals(sel)
        return {"period_start": s, "period_end": e, "months_with_data": n,
                "total_revenue": _r(rev), "total_expenses": _r(exp), "net_revenue": _r(net),
                "net_margin_pct": _r(margin), "avg_monthly_revenue": _r(rev / n),
                "avg_monthly_expenses": _r(exp / n), "avg_monthly_net_revenue": _r(net / n)}

    a, b = block(A, a_s, a_e, na), block(B, b_s, b_e, nb)
    changes = {}
    for key in ("total_revenue", "total_expenses", "net_revenue"):
        changes[f"{key}_change"] = _r(b[key] - a[key])
        changes[f"{key}_change_pct"] = _r(pct_change(b[key], a[key]))
    for key in ("avg_monthly_revenue", "avg_monthly_expenses", "avg_monthly_net_revenue"):
        changes[f"{key}_change_pct"] = _r(pct_change(b[key], a[key]))
    if a["net_margin_pct"] is not None and b["net_margin_pct"] is not None:
        changes["net_margin_change_pct_points"] = _r(b["net_margin_pct"] - a["net_margin_pct"])

    ga = A.groupby(["type", "category"])["amount"].sum()
    gb = B.groupby(["type", "category"])["amount"].sum()
    j = pd.concat([ga.rename("a"), gb.rename("b")], axis=1).fillna(0.0)
    j["change"] = j["b"] - j["a"]
    j = j.reindex(j["change"].abs().sort_values(ascending=False).index)
    movers = [{"category": c, "type": t, "period_a": _r(r["a"]), "period_b": _r(r["b"]),
               "change": _r(r["change"]), "change_pct": _r(pct_change(r["b"], r["a"]))}
              for (t, c), r in j.head(8).iterrows()]

    result = {"period_a": a, "period_b": b, **changes, "biggest_category_moves": movers}
    if na != nb:
        result["note"] = (f"Periods have different lengths ({na} vs {nb} months); "
                          "compare the avg_monthly figures for a like-for-like view.")
    la, lb = _period_label(a_s, a_e), _period_label(b_s, b_e)
    summary = (f"{la} vs {lb}: revenue {fmt.money(a['total_revenue'])} → {fmt.money(b['total_revenue'])} "
               f"({fmt.pct(changes['total_revenue_change_pct'])}), expenses {fmt.money(a['total_expenses'])} → "
               f"{fmt.money(b['total_expenses'])} ({fmt.pct(changes['total_expenses_change_pct'])}), net revenue "
               f"{fmt.money(a['net_revenue'])} → {fmt.money(b['net_revenue'])}.")
    if movers:
        m0 = movers[0]
        summary += f" Biggest move: {m0['category']} ({m0['type']}) {fmt.signed_money(m0['change'])}."
    table = pd.DataFrame({
        "Category": [f"{m['category']} ({m['type']})" for m in movers],
        la: [fmt.money(m["period_a"]) for m in movers],
        lb: [fmt.money(m["period_b"]) for m in movers],
        "Change": [fmt.signed_money(m["change"]) for m in movers],
        "Change %": [fmt.pct(m["change_pct"]) for m in movers],
    })
    return Evidence(
        tool="compare_periods", title=f"{la} vs {lb}",
        args={"period_a_start": a_s, "period_a_end": a_e, "period_b_start": b_s, "period_b_end": b_e},
        result=result,
        formula=("Totals per period = Σ amount by type within each date range; change = period B − period A; "
                 "change % = change ÷ |period A| × 100; monthly average = period total ÷ months with data."),
        row_lines=_lines(pd.concat([A, B])), summary=summary, table=table)


def category_growth(df: pd.DataFrame, metric: str = "expenses", start_month=None, end_month=None,
                    window_months: int = 3) -> Evidence:
    metric = _check_metric(metric, allowed=("revenue", "expenses"))
    s, e, _ = resolve_period(df, start_month, end_month)
    months = _months_between(df, s, e)
    if len(months) < 2:
        raise MetricError("Growth needs at least two months of data in the period.")
    try:
        w = int(window_months)
    except (TypeError, ValueError):
        w = 3
    w = max(1, min(w, len(months) // 2))
    first, last = months[:w], months[-w:]
    typ = _type_for(metric)
    sel = _in_period(df, s, e)
    sel = sel[sel["type"] == typ]
    if sel.empty:
        raise MetricError(f"There are no {metric} rows between {s} and {e}.")
    pivot = sel.pivot_table(index="category", columns="month", values="amount", aggfunc="sum").reindex(
        columns=months, fill_value=0.0).fillna(0.0)
    first_avg, last_avg = pivot[first].mean(axis=1), pivot[last].mean(axis=1)
    rows = []
    for cat in pivot.index:
        rows.append({"category": cat, "first_window_monthly_avg": _r(first_avg[cat]),
                     "last_window_monthly_avg": _r(last_avg[cat]),
                     "monthly_avg_change": _r(last_avg[cat] - first_avg[cat]),
                     "growth_pct": _r(pct_change(last_avg[cat], first_avg[cat])),
                     "period_total": _r(pivot.loc[cat].sum())})
    rows.sort(key=lambda r: (r["growth_pct"] is None, -(r["growth_pct"] or 0)))
    total_first, total_last = float(pivot[first].sum().mean()), float(pivot[last].sum().mean())
    result = {"metric": metric, "period_start": s, "period_end": e, "window_months": w,
              "first_window": first, "last_window": last,
              f"total_{metric}_first_window_monthly_avg": _r(total_first),
              f"total_{metric}_last_window_monthly_avg": _r(total_last),
              f"total_{metric}_growth_pct": _r(pct_change(total_last, total_first)),
              "categories_fastest_growth_first": rows[:MAX_LIST]}
    ranked = [r for r in rows if r["growth_pct"] is not None]
    summary = f"{metric.title()} by category, average of the first {w} vs last {w} months of {_period_label(s, e)}."
    if ranked:
        summary += (f" Fastest growing: {ranked[0]['category']} ({fmt.pct(ranked[0]['growth_pct'])})."
                    f" Weakest: {ranked[-1]['category']} ({fmt.pct(ranked[-1]['growth_pct'])}).")
    table = pd.DataFrame({
        "Category": [r["category"] for r in rows],
        f"Avg/month, first {w}": [fmt.money(r["first_window_monthly_avg"]) for r in rows],
        f"Avg/month, last {w}": [fmt.money(r["last_window_monthly_avg"]) for r in rows],
        "Growth": [fmt.pct(r["growth_pct"]) for r in rows],
    })
    return Evidence(
        tool="category_growth", title=f"Fastest-changing {'expense' if metric == 'expenses' else 'revenue'} categories, {_period_label(s, e)}",
        args={"metric": metric, "start_month": s, "end_month": e, "window_months": w}, result=result,
        formula=(f"For each category: average monthly {metric} over the first {w} months vs the last {w} months "
                 "of the period (months without rows count as 0); growth % = (last avg − first avg) ÷ first avg × 100."),
        row_lines=_lines(sel), summary=summary, table=table)


def category_trend(df: pd.DataFrame, category, start_month=None, end_month=None) -> Evidence:
    cat = _resolve_category(df, category)
    s, e, _ = resolve_period(df, start_month, end_month)
    months = _months_between(df, s, e)[-MAX_TREND_MONTHS:]
    s = months[0]
    sel = _in_period(df, s, e)
    rows = sel[sel["category"] == cat]
    if rows.empty:
        raise MetricError(f"No {cat} rows between {s} and {e}.")
    typ = rows.groupby("type")["amount"].sum().idxmax()
    rows = rows[rows["type"] == typ]
    monthly = rows.groupby("month")["amount"].sum().reindex(months, fill_value=0.0)
    type_totals = sel[sel["type"] == typ].groupby("month")["amount"].sum().reindex(months, fill_value=0.0)
    series, prev = [], None
    for m in months:
        v = float(monthly[m])
        series.append({"month": m, "amount": _r(v),
                       "share_of_monthly_total_pct": _r(v / type_totals[m] * 100) if type_totals[m] else None,
                       "mom_pct": _r(pct_change(v, prev)) if prev is not None else None})
        prev = v
    total = float(monthly.sum())
    first_v, last_v = float(monthly.iloc[0]), float(monthly.iloc[-1])
    result = {"category": cat, "type": typ, "period_start": s, "period_end": e,
              "period_total": _r(total), "monthly_avg": _r(total / len(months)),
              "share_of_period_total_pct": _r(total / float(type_totals.sum()) * 100) if type_totals.sum() else None,
              "highest_month": monthly.idxmax(), "highest_amount": _r(monthly.max()),
              "lowest_month": monthly.idxmin(), "lowest_amount": _r(monthly.min()),
              "first_month_amount": _r(first_v), "last_month_amount": _r(last_v),
              "change_first_to_last": _r(last_v - first_v),
              "change_first_to_last_pct": _r(pct_change(last_v, first_v)),
              "transactions": int(len(rows)), "months": series}
    summary = (f"{cat} ({typ}), {_period_label(s, e)}: {fmt.money(total)} in total, {fmt.money(total / len(months))} "
               f"a month on average; highest {fmt.month_label(result['highest_month'])} ({fmt.money(result['highest_amount'])}), "
               f"lowest {fmt.month_label(result['lowest_month'])} ({fmt.money(result['lowest_amount'])}).")
    table = pd.DataFrame({"Month": [fmt.month_label(x["month"]) for x in series],
                          "Amount": [fmt.money(x["amount"]) for x in series],
                          "MoM": [fmt.pct(x["mom_pct"]) for x in series],
                          f"Share of {typ}s": [fmt.pct(x["share_of_monthly_total_pct"], signed=False) for x in series]})
    return Evidence(
        tool="category_trend", title=f"{cat}: month by month", args={"category": cat, "start_month": s, "end_month": e},
        result=result,
        formula=(f"Monthly total = Σ amount of {typ} rows in category '{cat}' per month; share = category ÷ all {typ} "
                 "rows that month × 100; MoM % = (month − previous month) ÷ |previous month| × 100."),
        row_lines=_lines(rows), summary=summary, table=table)


def find_anomalies(df: pd.DataFrame, metric: str = "both", start_month=None, end_month=None) -> Evidence:
    metric = str(metric or "both").strip().lower()
    metric = {"expense": "expenses", "all": "both", "costs": "expenses"}.get(metric, metric)
    if metric not in ("revenue", "expenses", "both"):
        raise MetricError("metric must be revenue, expenses or both.")
    s, e, _ = resolve_period(df, start_month, end_month)
    months = _months_between(df, s, e)
    if len(months) < 4:
        raise MetricError("Spotting unusual months needs at least four months of data.")
    sel = _in_period(df, s, e)
    types = ["revenue", "expense"] if metric == "both" else [_type_for(metric)]
    flagged, totals_flagged = [], []
    for typ in types:
        part = sel[sel["type"] == typ]
        if part.empty:
            continue
        pivot = part.pivot_table(index="category", columns="month", values="amount", aggfunc="sum").reindex(
            columns=months, fill_value=0.0).fillna(0.0)
        monthly_total = pivot.sum()
        typical_total = float(monthly_total.median())
        floor = 0.05 * typical_total  # ignore wobbles smaller than 5% of a typical month
        for cat, row in pivot.iterrows():
            typical = float(row.median())
            for m, v in row.items():
                dev = float(v) - typical
                dev_pct = pct_change(float(v), typical)
                big = abs(dev) >= floor and (dev_pct is None or abs(dev_pct) >= 40)
                if big:
                    flagged.append({"month": m, "category": cat, "type": typ, "amount": _r(v),
                                    "typical_monthly_amount": _r(typical), "deviation": _r(dev),
                                    "deviation_pct": _r(dev_pct)})
        for m, v in monthly_total.items():
            dev_pct = pct_change(float(v), typical_total)
            if dev_pct is not None and abs(dev_pct) >= 15:
                totals_flagged.append({"month": m, "type": typ, "total": _r(v), "typical_monthly_total": _r(typical_total),
                                       "deviation_pct": _r(dev_pct)})
    flagged.sort(key=lambda r: -abs(r["deviation"]))
    totals_flagged.sort(key=lambda r: -abs(r["deviation_pct"]))
    result = {"metric": metric, "period_start": s, "period_end": e,
              "unusual_category_months": flagged[:10], "unusual_total_months": totals_flagged[:8],
              "rule": ("A category-month is unusual when it differs from that category's median month by at least "
                       "40% and by at least 5% of a typical month's total; a whole month is unusual when its total "
                       "differs from the median month by at least 15%.")}
    if not flagged and not totals_flagged:
        result["note"] = "Nothing unusual found under these rules."
    summary = f"Unusual months, {_period_label(s, e)}: "
    summary += ("; ".join(f"{fmt.month_label(x['month'])} {x['category']} {fmt.money(x['amount'])} vs a typical "
                          f"{fmt.money(x['typical_monthly_amount'])}" for x in flagged[:3]) or "none found") + "."
    table = pd.DataFrame({"Month": [fmt.month_label(x["month"]) for x in flagged[:10]],
                          "Category": [f"{x['category']} ({x['type']})" for x in flagged[:10]],
                          "Amount": [fmt.money(x["amount"]) for x in flagged[:10]],
                          "Typical month": [fmt.money(x["typical_monthly_amount"]) for x in flagged[:10]],
                          "Deviation": [fmt.pct(x["deviation_pct"]) for x in flagged[:10]]})
    src = sel[sel["type"].isin(types)]
    keys = {(x["month"], x["category"]) for x in flagged[:10]}
    hit = src[[(m, c) in keys for m, c in zip(src["month"], src["category"])]] if keys else src.iloc[0:0]
    return Evidence(
        tool="find_anomalies", title=f"Unusual months, {_period_label(s, e)}",
        args={"metric": metric, "start_month": s, "end_month": e}, result=result,
        formula=result["rule"] + " Median = middle value of the category's monthly totals in the period.",
        row_lines=_lines(hit if not hit.empty else src), summary=summary, table=table)


def period_breakdown(df: pd.DataFrame, grain: str = "quarter", start_month=None, end_month=None) -> Evidence:
    grain = str(grain or "quarter").strip().lower()
    grain = {"q": "quarter", "quarterly": "quarter", "quarters": "quarter", "y": "year", "yearly": "year",
             "annual": "year", "years": "year", "fy": "year"}.get(grain, grain)
    if grain not in ("quarter", "year"):
        raise MetricError("grain must be 'quarter' or 'year'.")
    s, e, _ = resolve_period(df, start_month, end_month)
    sel = _in_period(df, s, e).copy()
    p = pd.PeriodIndex(sel["month"], freq="M")
    sel["bucket"] = [f"{x.year}-Q{x.quarter}" for x in p] if grain == "quarter" else [str(x.year) for x in p]
    full = 3 if grain == "quarter" else 12
    out, prev = [], None
    for bucket, part in sel.groupby("bucket", sort=True):
        rev, exp, net, margin = _totals(part)
        n = int(part["month"].nunique())
        out.append({"period": bucket, "months_with_data": n, "partial": n < full,
                    "revenue": _r(rev), "expenses": _r(exp), "net_revenue": _r(net), "net_margin_pct": _r(margin),
                    "revenue_change_pct_vs_previous": _r(pct_change(rev, prev["revenue"])) if prev else None,
                    "net_revenue_change_vs_previous": _r(net - prev["net_revenue"]) if prev else None})
        prev = out[-1]
    out = out[-16:]
    best = max(out, key=lambda r: r["net_revenue"])
    worst = min(out, key=lambda r: r["net_revenue"])
    margins = [r for r in out if r["net_margin_pct"] is not None]
    result = {"grain": grain, "period_start": s, "period_end": e, "periods": out,
              "best_by_net_revenue": best["period"], "worst_by_net_revenue": worst["period"]}
    if margins:
        result["best_by_net_margin"] = max(margins, key=lambda r: r["net_margin_pct"])["period"]
        result["worst_by_net_margin"] = min(margins, key=lambda r: r["net_margin_pct"])["period"]
    if any(r["partial"] for r in out):
        result["note"] = "Periods marked partial have fewer months of data than a full " + grain + "."
    summary = (f"By {grain}, {_period_label(s, e)}: best net revenue {best['period']} ({fmt.money(best['net_revenue'])}), "
               f"weakest {worst['period']} ({fmt.money(worst['net_revenue'])}).")
    table = pd.DataFrame({grain.title(): [r["period"] + (" (partial)" if r["partial"] else "") for r in out],
                          "Revenue": [fmt.money(r["revenue"]) for r in out],
                          "Expenses": [fmt.money(r["expenses"]) for r in out],
                          "Net revenue": [fmt.money(r["net_revenue"]) for r in out],
                          "Margin": [fmt.pct(r["net_margin_pct"], signed=False) for r in out]})
    return Evidence(
        tool="period_breakdown", title=f"{grain.title()}ly totals, {_period_label(s, e)}",
        args={"grain": grain, "start_month": s, "end_month": e}, result=result,
        formula=(f"Totals per calendar {grain} = Σ amount by type; net = revenue − expenses; margin = net ÷ revenue × 100; "
                 f"change vs previous {grain} = this − previous."),
        row_lines=_lines(sel), summary=summary, table=table)


def expense_ratios(df: pd.DataFrame, start_month=None, end_month=None) -> Evidence:
    s, e, _ = resolve_period(df, start_month, end_month)
    sel = _in_period(df, s, e)
    rev, exp, net, margin = _totals(sel)
    if not rev:
        raise MetricError(f"There is no revenue between {s} and {e}, so ratios to revenue can't be calculated.")
    grp = sel[sel["type"] == "expense"].groupby("category")["amount"].sum().sort_values(ascending=False)
    cats = [{"category": c, "total": _r(v), "ratio_to_revenue_pct": _r(v / rev * 100),
             "share_of_expenses_pct": _r(v / exp * 100) if exp else None} for c, v in grp.head(MAX_LIST).items()]
    result = {"period_start": s, "period_end": e, "total_revenue": _r(rev), "total_expenses": _r(exp),
              "total_expense_ratio_pct": _r(exp / rev * 100), "net_margin_pct": _r(margin),
              "expense_categories": cats}
    summary = (f"{_period_label(s, e)}: expenses were {fmt.pct(exp / rev * 100, signed=False)} of revenue. "
               + "; ".join(f"{c['category']} {fmt.pct(c['ratio_to_revenue_pct'], signed=False)}" for c in cats[:4]) + ".")
    table = pd.DataFrame({"Category": [c["category"] for c in cats],
                          "Total": [fmt.money(c["total"]) for c in cats],
                          "% of revenue": [fmt.pct(c["ratio_to_revenue_pct"], signed=False) for c in cats],
                          "% of expenses": [fmt.pct(c["share_of_expenses_pct"], signed=False) for c in cats]})
    return Evidence(
        tool="expense_ratios", title=f"Costs as a share of revenue, {_period_label(s, e)}",
        args={"start_month": s, "end_month": e}, result=result,
        formula="Ratio to revenue = category expenses ÷ total revenue × 100; share of expenses = category ÷ total expenses × 100.",
        row_lines=_lines(sel), summary=summary, table=table)


def what_if(df: pd.DataFrame, adjustments=None, start_month=None, end_month=None) -> Evidence:
    s, e, _ = resolve_period(df, start_month, end_month)
    sel = _in_period(df, s, e)
    if isinstance(adjustments, dict):
        adjustments = [adjustments]
    if not adjustments or not isinstance(adjustments, list):
        raise MetricError("Give at least one adjustment: {category, change_pct}, e.g. Marketing -20. "
                          "Use category 'all revenue' or 'all expenses' to change a whole side.")
    rev, exp, net, margin = _totals(sel)
    new_rev, new_exp, applied = rev, exp, []
    for adj in adjustments[:8]:
        if not isinstance(adj, dict):
            raise MetricError("Each adjustment must be an object with category and change_pct.")
        try:
            pct = float(adj.get("change_pct"))
        except (TypeError, ValueError):
            raise MetricError("change_pct must be a number, e.g. -20 for a 20% cut.")
        if not -100 <= pct <= 1000:
            raise MetricError("change_pct must be between -100 and 1000.")
        name = str(adj.get("category", "")).strip().lower()
        if name in ("all revenue", "revenue", "all_revenue"):
            base, typ, label = rev, "revenue", "All revenue"
        elif name in ("all expenses", "expenses", "all_expenses", "all costs"):
            base, typ, label = exp, "expense", "All expenses"
        else:
            label = _resolve_category(df, adj.get("category"))
            rows = sel[sel["category"] == label]
            typ = rows.groupby("type")["amount"].sum().idxmax() if not rows.empty else "expense"
            base = float(rows.loc[rows["type"] == typ, "amount"].sum())
        delta = base * pct / 100
        if typ == "revenue":
            new_rev += delta
        else:
            new_exp += delta
        applied.append({"category": label, "type": typ, "change_pct": _r(pct), "baseline_amount": _r(base),
                        "amount_change": _r(delta)})
    new_net = new_rev - new_exp
    new_margin = new_net / new_rev * 100 if new_rev else None
    result = {"period_start": s, "period_end": e, "adjustments": applied,
              "baseline": {"total_revenue": _r(rev), "total_expenses": _r(exp), "net_revenue": _r(net),
                           "net_margin_pct": _r(margin)},
              "scenario": {"total_revenue": _r(new_rev), "total_expenses": _r(new_exp), "net_revenue": _r(new_net),
                           "net_margin_pct": _r(new_margin)},
              "net_revenue_change": _r(new_net - net),
              "net_revenue_change_pct": _r(pct_change(new_net, net)),
              "note": "Hypothetical: applies each change to the period's actual totals; nothing else moves."}
    if margin is not None and new_margin is not None:
        result["net_margin_change_pct_points"] = _r(new_margin - margin)
    summary = (f"Scenario for {_period_label(s, e)}: net revenue {fmt.money(net)} → {fmt.money(new_net)} "
               f"({fmt.signed_money(new_net - net)}); margin {fmt.pct(margin, signed=False)} → {fmt.pct(new_margin, signed=False)}.")
    table = pd.DataFrame({"Change": [f"{a['category']} {fmt.pct(a['change_pct'], 0)}" for a in applied],
                          "Baseline": [fmt.money(a["baseline_amount"]) for a in applied],
                          "Effect": [fmt.signed_money(a["amount_change"]) for a in applied]})
    return Evidence(
        tool="what_if", title=f"What-if scenario, {_period_label(s, e)}",
        args={"adjustments": applied, "start_month": s, "end_month": e}, result=result,
        formula=("Scenario amount = baseline amount × (1 + change % ÷ 100) for each adjusted category; "
                 "scenario net = scenario revenue − scenario expenses."),
        row_lines=_lines(sel), summary=summary, table=table)


def project_trend(df: pd.DataFrame, metric: str = "net", months_ahead: int = 3, basis_months: int = 6) -> Evidence:
    metric = _check_metric(metric)
    try:
        ahead = max(1, min(int(months_ahead), MAX_PROJECTION_MONTHS))
    except (TypeError, ValueError):
        ahead = 3
    table = monthly_table(df)
    try:
        n = max(3, min(int(basis_months), len(table)))
    except (TypeError, ValueError):
        n = min(6, len(table))
    if len(table) < 3:
        raise MetricError("A projection needs at least three months of data.")
    basis = table.iloc[-n:]
    y = basis[metric].astype(float).tolist()
    xs = list(range(n))
    x_mean, y_mean = sum(xs) / n, sum(y) / n
    sxx = sum((x - x_mean) ** 2 for x in xs)
    slope = sum((x - x_mean) * (v - y_mean) for x, v in zip(xs, y)) / sxx if sxx else 0.0
    intercept = y_mean - slope * x_mean
    ss_tot = sum((v - y_mean) ** 2 for v in y)
    ss_res = sum((v - (intercept + slope * x)) ** 2 for x, v in zip(xs, y))
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    last = pd.Period(basis.index[-1], "M")
    proj = [{"month": str(last + k), "projected_value": _r(intercept + slope * (n - 1 + k))} for k in range(1, ahead + 1)]
    name = {"revenue": "revenue", "expenses": "expenses", "net": "net revenue"}[metric]
    result = {"metric": "net_revenue" if metric == "net" else metric, "method": "straight-line (least squares) trend",
              "basis_start": basis.index[0], "basis_end": basis.index[-1], "basis_months": n,
              "slope_per_month": _r(slope), "r_squared": _r(r2, 3), "last_actual": _r(y[-1]),
              "projections": proj, "projected_total": _r(sum(p["projected_value"] for p in proj)),
              "note": "A projection of the recent trend, not a forecast: it ignores seasonality, one-off deals and plans."}
    if r2 < 0.5:
        result["fit_warning"] = "The trend fits the recent months poorly (r_squared below 0.5); treat the projection as rough."
    summary = (f"Projected {name} from the last {n} months' trend ({fmt.signed_money(slope)} a month): "
               + "; ".join(f"{fmt.month_label(p['month'])} {fmt.money(p['projected_value'])}" for p in proj) + ".")
    tbl = pd.DataFrame({"Month": [fmt.month_label(p["month"]) for p in proj],
                        f"Projected {name}": [fmt.money(p["projected_value"]) for p in proj]})
    return Evidence(
        tool="project_trend", title=f"Projected {name}, next {ahead} months",
        args={"metric": metric, "months_ahead": ahead, "basis_months": n}, result=result,
        formula=(f"Least-squares straight line through monthly {name} for {basis.index[0]} to {basis.index[-1]}, "
                 "extended forward; r² measures how well the line fits those months (1 = perfect)."),
        row_lines=_lines(df[df["month"].isin(basis.index)]), summary=summary, table=tbl)


# ---------------------------------------------------------------------------------
# Planning tools: budgets and cash runway (use inputs the user typed on the Plan page)
# ---------------------------------------------------------------------------------
MAX_RUNWAY_PROJECTION = 24


def budget_status(df: pd.DataFrame, budgets: dict | None, month=None) -> Evidence:
    """Actual spend vs the user's monthly budget per expense category, for one month."""
    budgets = {str(k): float(v) for k, v in (budgets or {}).items() if v not in (None, "") and float(v) > 0}
    if not budgets:
        raise MetricError("No budgets are set. The user can add monthly budgets on the Plan page.")
    months = available_months(df)
    m = resolve_month(df, month) if month not in (None, "") else months[-1]
    exp = df[(df["type"] == "expense") & (df["month"] == m)]
    actual = exp.groupby("category")["amount"].sum()
    rows, over = [], []
    for cat, budget in sorted(budgets.items(), key=lambda kv: -kv[1]):
        spent = float(actual.get(cat, 0.0))
        used = spent / budget * 100
        status = "over" if used > 100 else "near" if used >= 90 else "under"
        rows.append({"category": cat, "monthly_budget": _r(budget), "actual": _r(spent),
                     "remaining": _r(budget - spent), "used_pct": _r(used), "status": status})
        if status == "over":
            over.append(rows[-1])
    # How often each category broke its budget across the whole dataset
    by_month = df[df["type"] == "expense"].groupby(["category", "month"])["amount"].sum()
    for r in rows:
        vals = by_month.get(r["category"])
        r["months_over_budget"] = int((vals > r["monthly_budget"]).sum()) if vals is not None else 0
    total_budget, total_actual = sum(budgets.values()), float(sum(r["actual"] for r in rows))
    result = {"month": m, "categories": rows, "total_budget": _r(total_budget), "total_actual": _r(total_actual),
              "total_used_pct": _r(total_actual / total_budget * 100), "over_budget_count": len(over),
              "months_in_data": len(months)}
    summary = (f"{fmt.month_label(m)}: {fmt.money(total_actual)} spent against budgets of {fmt.money(total_budget)} "
               f"({fmt.pct(total_actual / total_budget * 100, signed=False)}). "
               + ("Over budget: " + ", ".join(f"{o['category']} by {fmt.money(-o['remaining'])}" for o in over) + "."
                  if over else "Every budgeted category is within budget."))
    table = pd.DataFrame({"Category": [r["category"] for r in rows],
                          "Budget": [fmt.money(r["monthly_budget"]) for r in rows],
                          "Actual": [fmt.money(r["actual"]) for r in rows],
                          "Used": [fmt.pct(r["used_pct"], 0, signed=False) for r in rows],
                          "Months over": [r["months_over_budget"] for r in rows]})
    return Evidence(
        tool="get_budget_status", title=f"Budgets vs actual, {fmt.month_label(m)}", args={"month": m}, result=result,
        formula="Used % = actual expense rows in the category that month ÷ the monthly budget the user set × 100; "
                "over = above 100%, near = 90–100%. Months over = months in the data where actual exceeded the budget.",
        row_lines=_lines(exp[exp["category"].isin(budgets)]), summary=summary, table=table)


def cash_runway(df: pd.DataFrame, cash_balance, basis_months: int = 3) -> Evidence:
    """How long the user's cash lasts at the recent average monthly net revenue."""
    try:
        balance = float(cash_balance)
    except (TypeError, ValueError):
        raise MetricError("No cash balance is set. The user can enter it on the Plan page.")
    if not math.isfinite(balance) or balance < 0:
        raise MetricError("The cash balance must be zero or more.")
    table = monthly_table(df)
    try:
        n = max(1, min(int(basis_months), len(table)))
    except (TypeError, ValueError):
        n = min(3, len(table))
    basis = table.iloc[-n:]
    avg_net = float(basis["net"].mean())
    last = pd.Period(basis.index[-1], "M")
    path, bal, zero_month = [], balance, None
    for k in range(1, MAX_RUNWAY_PROJECTION + 1):
        bal += avg_net
        path.append({"month": str(last + k), "projected_balance": _r(bal)})
        if zero_month is None and bal < 0:
            zero_month = str(last + k)
    runway = balance / -avg_net if avg_net < 0 else None
    result = {"cash_balance": _r(balance), "as_of_month": str(last), "basis_start": basis.index[0],
              "basis_end": basis.index[-1], "basis_months": n, "avg_monthly_net_revenue": _r(avg_net),
              "monthly_burn": _r(-avg_net) if avg_net < 0 else 0.0,
              "runway_months": _r(runway, 1), "cash_runs_out_month": zero_month,
              "cash_flow_positive": avg_net >= 0, "balance_projection": path[:12],
              "note": "Assumes every future month looks like the average of the basis months; ignores timing, "
                      "loans, tax and one-offs. Net revenue is used as a proxy for cash flow."}
    if avg_net >= 0:
        summary = (f"Cash-flow positive: the last {n} months averaged {fmt.signed_money(avg_net)} net revenue a month, "
                   f"so {fmt.money(balance)} grows rather than runs down.")
    else:
        summary = (f"At the last {n} months' average burn of {fmt.money(-avg_net)} a month, {fmt.money(balance)} lasts "
                   f"about {runway:.1f} months" + (f" (runs out in {fmt.month_label(zero_month)})." if zero_month else "."))
    tbl = pd.DataFrame({"Month": [fmt.month_label(p["month"]) for p in path[:12]],
                        "Projected balance": [fmt.money(p["projected_balance"]) for p in path[:12]]})
    return Evidence(
        tool="get_cash_runway", title="Cash runway", args={"basis_months": n}, result=result,
        formula=(f"Average monthly net revenue over {basis.index[0]} to {basis.index[-1]}; runway = cash balance ÷ "
                 "average monthly burn (only when net revenue is negative); projected balance = balance + k × average."),
        row_lines=_lines(df[df["month"].isin(basis.index)]), summary=summary, table=tbl)


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
