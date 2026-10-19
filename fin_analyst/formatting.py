"""Display helpers shared by the UI and the deterministic summaries."""

from __future__ import annotations

import calendar
import math

from .config import CURRENCY


def is_missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def money(x, decimals: int = 0) -> str:
    if is_missing(x):
        return "—"
    sign = "-" if x < 0 else ""
    return f"{sign}{CURRENCY}{abs(x):,.{decimals}f}"


def signed_money(x, decimals: int = 0) -> str:
    if is_missing(x):
        return "—"
    sign = "+" if x > 0 else "-" if x < 0 else ""
    return f"{sign}{CURRENCY}{abs(x):,.{decimals}f}"


def pct(x, decimals: int = 1, signed: bool = True) -> str:
    if is_missing(x):
        return "—"
    if signed:
        return f"{x:+.{decimals}f}%"
    return f"{x:.{decimals}f}%"


def month_label_long(month: str) -> str:
    """'2026-03' -> 'March 2026'."""
    try:
        year, mon = month.split("-")
        return f"{calendar.month_name[int(mon)]} {year}"
    except (ValueError, IndexError, AttributeError):
        return str(month)


def month_label(month: str) -> str:
    """'2026-03' -> 'Mar 2026'."""
    try:
        year, mon = month.split("-")
        return f"{calendar.month_abbr[int(mon)]} {year}"
    except (ValueError, IndexError, AttributeError):
        return str(month)
