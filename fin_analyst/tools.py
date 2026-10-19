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

_MONTH = {"type": "string", "description": "Month in YYYY-MM format, e.g. 2026-03."}

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
                    "metric": {"type": "string", "enum": ["revenue", "expenses", "net"],
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
                    "n": {"type": "integer", "description": "How many categories (1-15). Default 5."},
                },
                "required": ["metric"],
            },
        },
    },
]

_FUNCS = {
    "get_period_summary": (metrics.period_summary, {"start_month", "end_month"}),
    "get_monthly_trend": (metrics.monthly_trend, {"start_month", "end_month"}),
    "explain_month_change": (metrics.explain_change, {"month", "metric"}),
    "get_top_categories": (metrics.top_categories, {"metric", "start_month", "end_month", "n"}),
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


def run_tool(name: str, raw_args, df: pd.DataFrame) -> Evidence:
    if name not in _FUNCS:
        raise ToolError(f"Unknown tool '{name}'. Available: {', '.join(_FUNCS)}.")
    func, allowed = _FUNCS[name]
    args = parse_arguments(raw_args)
    clean = {k: v for k, v in args.items()
             if k in allowed and v is not None and str(v).strip().lower() not in ("", "null", "none")}
    try:
        return func(df, **clean)
    except metrics.MetricError as exc:
        raise ToolError(str(exc)) from exc
    except TypeError as exc:  # e.g. required argument missing
        raise ToolError(f"Invalid arguments for {name}: {exc}") from exc
