"""Tool definitions exposed to the LLM (OpenAI-compatible function calling).

The LLM decides *which* calculation answers a question; Python does the calculation.
Arguments from the model are treated as untrusted input: unknown tools and unknown
arguments are rejected or dropped, and every value is validated by `metrics`.
"""

from __future__ import annotations

import json

import pandas as pd

from . import metrics
from .evidence import Evidence

# Nullable: some models (e.g. gpt-oss) send null for omitted optional args; run_tool drops nulls.
_MONTH = {"type": ["string", "null"], "description": "Month in YYYY-MM format, e.g. 2026-03."}

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "get_period_summary",
            "description": (
                "Total revenue, total expenses, net revenue (revenue minus expenses) and net margin for a period. "
                "Use for questions about totals, net revenue, profit or margin. For a single month set "
                "start_month and end_month to the same month. Omit both for the whole dataset."
            ),
            "parameters": {
                "type": "object",
                "properties": {"start_month": _MONTH, "end_month": _MONTH},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_monthly_trend",
            "description": (
                "Revenue, expenses and net revenue for every month in a range, with month-over-month % changes. "
                "Use for trend questions or to find which month rose or fell the most."
            ),
            "parameters": {
                "type": "object",
                "properties": {"start_month": _MONTH, "end_month": _MONTH},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_month_change",
            "description": (
                "Explains why revenue, expenses or net revenue changed in a month compared with the previous month: "
                "totals for both months, the change, and each category's change, share of the total change and "
                "transaction counts, sorted by impact. Use for 'why did X decline/increase in <month>' questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "month": _MONTH,
                    "metric": {"type": ["string", "null"], "enum": ["revenue", "expenses", "net", None],
                               "description": "Which measure to explain. Default revenue."},
                },
                "required": ["month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_categories",
            "description": (
                "The largest revenue or expense categories in a period, with totals, share of the total and "
                "transaction counts. Use for 'top drivers', 'biggest expenses' or 'main revenue sources' questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": ["revenue", "expenses"]},
                    "start_month": _MONTH,
                    "end_month": _MONTH,
                    "n": {"type": ["integer", "null"], "description": "How many categories (1-15). Default 5."},
                },
                "required": ["metric"],
            },
        },
    },
]


def _fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required or []}}}


_RANGE = {"start_month": _MONTH, "end_month": _MONTH}
_NULLABLE_STR = ["string", "null"]

TOOL_SPECS += [
    _fn("compare_periods",
        "Compare two date ranges side by side: totals, monthly averages, margin change and the categories that "
        "moved most. Use for H1 vs H2, quarter vs quarter, year over year, before/after questions. "
        "Period A is the baseline, B the comparison.",
        {"period_a_start": _MONTH, "period_a_end": _MONTH, "period_b_start": _MONTH, "period_b_end": _MONTH},
        ["period_a_start", "period_a_end", "period_b_start", "period_b_end"]),
    _fn("category_growth",
        "Rank revenue or expense categories by growth: average of the first N months vs the last N months of a "
        "period. Use for 'fastest growing costs', 'which revenue lines are shrinking'.",
        {"metric": {"type": "string", "enum": ["revenue", "expenses"]}, **_RANGE,
         "window_months": {"type": ["integer", "null"], "description": "N, default 3."}}, ["metric"]),
    _fn("category_trend",
        "Month-by-month history of ONE category: totals, share of all revenue/expenses, highest and lowest month, "
        "first-to-last change. Use for 'how has X evolved', 'when did X peak'.",
        {"category": {"type": "string"}, **_RANGE}, ["category"]),
    _fn("find_anomalies",
        "Find unusual spikes or drops: category-months far from that category's typical month, and months whose "
        "total is unusual. Use for 'anything unusual', 'one-offs', 'red flags'.",
        {"metric": {"type": _NULLABLE_STR, "enum": ["revenue", "expenses", "both", None]}, **_RANGE}),
    _fn("period_breakdown",
        "Totals, net revenue and margin per calendar quarter or year, with change vs the previous one and the "
        "best/worst period. Use for quarterly or annual questions.",
        {"grain": {"type": "string", "enum": ["quarter", "year"]}, **_RANGE}, ["grain"]),
    _fn("expense_ratios",
        "Each expense category as a % of revenue and of total expenses, plus the overall expense ratio. Use for "
        "'what share of revenue goes to X', cost structure, efficiency questions.", dict(_RANGE)),
    _fn("what_if",
        "Hypothetical scenario: apply % changes to categories (or 'all revenue' / 'all expenses') over a period "
        "and get baseline vs scenario net revenue and margin. Use for 'what if we cut X by 20%'.",
        {"adjustments": {"type": "array", "items": {"type": "object", "properties": {
            "category": {"type": "string", "description": "Category name, 'all revenue' or 'all expenses'."},
            "change_pct": {"type": "number", "description": "-20 means a 20% cut."}},
            "required": ["category", "change_pct"]}}, **_RANGE}, ["adjustments"]),
    _fn("project_trend",
        "Straight-line projection of revenue, expenses or net revenue for the next months, from the recent trend. "
        "Use for 'if this continues', 'where are we heading'. Always say it is a projection, not a forecast.",
        {"metric": {"type": "string", "enum": ["revenue", "expenses", "net"]},
         "months_ahead": {"type": ["integer", "null"], "description": "1-12, default 3."},
         "basis_months": {"type": ["integer", "null"], "description": "Recent months to fit, default 6."}},
        ["metric"]),
    _fn("get_budget_status",
        "The user's monthly budgets vs actual spend per expense category for one month (default: latest), with "
        "how many months each category went over. Use for 'am I over budget', 'which budgets are at risk'.",
        {"month": {"type": _NULLABLE_STR, "description": "YYYY-MM; omit for the latest month."}}),
    _fn("get_cash_runway",
        "How many months the user's cash lasts at the recent average monthly net revenue, and when it runs out. "
        "Uses the cash balance the user entered. Use for runway, burn rate and 'how long can we last'.",
        {"basis_months": {"type": ["integer", "null"], "description": "Recent months to average, default 3."}}),
]

# Short present-tense labels for live progress in the UI.
TOOL_LABELS = {
    "get_period_summary": "Adding up totals", "get_monthly_trend": "Reading the monthly trend",
    "explain_month_change": "Explaining the month's change", "get_top_categories": "Ranking categories",
    "compare_periods": "Comparing periods", "category_growth": "Measuring category growth",
    "category_trend": "Tracing a category", "find_anomalies": "Looking for unusual months",
    "period_breakdown": "Splitting into quarters or years", "expense_ratios": "Working out cost ratios",
    "what_if": "Running the scenario", "project_trend": "Projecting the trend",
    "get_budget_status": "Checking budgets", "get_cash_runway": "Calculating cash runway",
}

_FUNCS = {
    "get_period_summary": (metrics.period_summary, {"start_month", "end_month"}),
    "get_monthly_trend": (metrics.monthly_trend, {"start_month", "end_month"}),
    "explain_month_change": (metrics.explain_change, {"month", "metric"}),
    "get_top_categories": (metrics.top_categories, {"metric", "start_month", "end_month", "n"}),
    "compare_periods": (metrics.compare_periods, {"period_a_start", "period_a_end", "period_b_start", "period_b_end"}),
    "category_growth": (metrics.category_growth, {"metric", "start_month", "end_month", "window_months"}),
    "category_trend": (metrics.category_trend, {"category", "start_month", "end_month"}),
    "find_anomalies": (metrics.find_anomalies, {"metric", "start_month", "end_month"}),
    "period_breakdown": (metrics.period_breakdown, {"grain", "start_month", "end_month"}),
    "expense_ratios": (metrics.expense_ratios, {"start_month", "end_month"}),
    "what_if": (metrics.what_if, {"adjustments", "start_month", "end_month"}),
    "project_trend": (metrics.project_trend, {"metric", "months_ahead", "basis_months"}),
}
# Tools that need inputs the user typed in the app (passed in as `context`), not just the data.
_CONTEXT_FUNCS = {
    "get_budget_status": (lambda df, ctx, **kw: metrics.budget_status(df, ctx.get("budgets"), **kw), {"month"}),
    "get_cash_runway": (lambda df, ctx, **kw: metrics.cash_runway(df, ctx.get("cash_balance"), **kw), {"basis_months"}),
}


class ToolError(ValueError):
    """Message is passed back to the LLM so it can correct the call."""


def parse_arguments(raw) -> dict:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        args = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise ToolError("Tool arguments were not valid JSON.")
    if not isinstance(args, dict):
        raise ToolError("Tool arguments must be a JSON object.")
    return args


def run_tool(name: str, raw_args, df: pd.DataFrame, context: dict | None = None) -> Evidence:
    if name not in _FUNCS and name not in _CONTEXT_FUNCS:
        raise ToolError(f"Unknown tool '{name}'. Available: {', '.join([*_FUNCS, *_CONTEXT_FUNCS])}.")
    func, allowed = _FUNCS.get(name) or _CONTEXT_FUNCS[name]
    args = parse_arguments(raw_args)
    clean = {k: v for k, v in args.items()
             if k in allowed and v is not None and str(v).strip().lower() not in ("", "null", "none")}
    try:
        if name in _CONTEXT_FUNCS:
            return func(df, context or {}, **clean)
        return func(df, **clean)
    except metrics.MetricError as exc:
        raise ToolError(str(exc)) from exc
    except TypeError as exc:  # e.g. required argument missing
        raise ToolError(f"Invalid arguments for {name}: {exc}") from exc
