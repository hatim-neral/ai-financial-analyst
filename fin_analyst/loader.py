"""CSV parsing and validation.

Turns an uploaded file (raw bytes) into one clean, canonical DataFrame with one row
per transaction:

    line | date | month | type | category | amount | description

`line` is the row's line number in the original CSV (the header is line 1), so every
figure the app shows can be traced back to the exact rows a user can find in their file.

Two input layouts are accepted:
  * long  : date, type (revenue/expense), category, amount[, description]
  * wide  : date, category, revenue, expenses[, description]

Nothing here raises on bad input. Problems are returned as:
  * errors   – the file cannot be used at all (empty, missing columns, ...)
  * warnings – the file is usable but something was adjusted
  * issues   – row-level problems, each with its CSV line number
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config

CANONICAL_COLUMNS = ["line", "date", "month", "type", "category", "amount", "description"]

ALIASES: dict[str, list[str]] = {
    "date": ["date", "txn_date", "transaction_date", "posting_date", "value_date", "period", "month"],
    "type": ["type", "kind", "flow", "transaction_type", "entry_type", "txn_type"],
    "category": ["category", "cat", "account", "line_item", "segment", "category_name"],
    "amount": ["amount", "value", "amt", "net_amount", "amount_inr"],
    "revenue": ["revenue", "revenues", "income", "sales"],
    "expenses": ["expenses", "expense", "cost", "costs", "spend"],
    "description": ["description", "desc", "memo", "note", "notes", "narration", "details"],
}
_ALIAS_LOOKUP = {alias: canon for canon, aliases in ALIASES.items() for alias in aliases}

TYPE_VALUES = {
    "revenue": "revenue", "revenues": "revenue", "income": "revenue", "sales": "revenue",
    "inflow": "revenue", "rev": "revenue",
    "expense": "expense", "expenses": "expense", "cost": "expense", "costs": "expense",
    "outflow": "expense", "spend": "expense", "exp": "expense",
}

LONG_FORMAT_HELP = "date, type, category, amount (one row per transaction; type is revenue or expense)"
WIDE_FORMAT_HELP = "date, category, revenue, expenses"

_MAX_ISSUES_KEPT = 1000
_ISO_LIKE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}")
_CURRENCY_RE = re.compile(r"(?i)(rs\.?|inr|usd|aed|eur|gbp|[₹$€£])")
# Decimal comma, e.g. "1.250,50" or "300,00". Never ambiguous with digit grouping,
# because a grouped number always ends with a 3-digit group ("1,200", "12,34,567").
_EURO_NUMBER = re.compile(r"^-?(\d{1,3}(\.\d{3})+|\d+),\d{1,2}$")


@dataclass
class RowIssue:
    line: int
    column: str
    value: str
    problem: str
    action: str = "row skipped"


@dataclass
class LoadResult:
    df: pd.DataFrame | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)
    issues_truncated: int = 0
    rows_read: int = 0
    source_format: str | None = None

    @property
    def ok(self) -> bool:
        return self.df is not None and not self.errors

    @property
    def rows_used(self) -> int:
        return 0 if self.df is None else int(self.df["line"].nunique())

    def issues_frame(self) -> pd.DataFrame:
        if not self.issues:
            return pd.DataFrame(columns=["line", "column", "value", "problem", "action"])
        return pd.DataFrame([i.__dict__ for i in self.issues]).sort_values("line", kind="stable")


# ---------------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------------
def load_csv(data: bytes, filename: str | None = None) -> LoadResult:
    result = LoadResult()

    # 1. File-level checks --------------------------------------------------------
    if data is None or len(data) == 0:
        return _fail(result, "The file is empty (0 bytes). Upload a CSV with a header row and at least one data row.")
    if len(data) > config.MAX_FILE_BYTES:
        mb = config.MAX_FILE_BYTES / (1024 * 1024)
        return _fail(result, f"The file is {len(data) / (1024 * 1024):.1f} MB; the limit is {mb:.0f} MB.")
    if filename and not filename.lower().endswith((".csv", ".txt")):
        return _fail(result, f"'{_short(filename)}' is not a .csv file.")
    if b"\x00" in data[:4096]:
        return _fail(result, "This doesn't look like a text CSV file (it contains binary data). "
                             "Export the sheet as CSV (UTF-8) and try again.")

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
        result.warnings.append("The file is not UTF-8; it was read as Latin-1. Check that category names look right.")

    if not text.strip():
        return _fail(result, "The file is empty (it contains only whitespace).")

    # 2. Split into records, keeping original line numbers ---------------------------
    delimiter = _sniff_delimiter(text)
    if delimiter != ",":
        result.warnings.append(f"Detected '{delimiter}' as the column separator.")

    try:
        header, records, lines = _read_records(text, delimiter, result)
    except csv.Error as exc:
        return _fail(result, f"The file could not be parsed as CSV ({exc}).")
    except _TooManyRows:
        return _fail(result, f"The file has more than {config.MAX_ROWS:,} data rows; the limit is {config.MAX_ROWS:,}.")

    if header is None:
        return _fail(result, "The file is empty (no header row found).")
    if not records:
        if result.rows_read:
            return _fail(result, "None of the data rows could be read (every row has the wrong number of fields).")
        return _fail(result, "The file has a header row but no data rows.")

    # 3. Map columns ---------------------------------------------------------------
    mapping = _map_columns(header, result)
    fmt = _detect_format(mapping)
    if fmt is None:
        return _fail(result, _missing_columns_message(header, mapping))
    result.source_format = fmt

    raw = pd.DataFrame({canon: [rec[idx] for rec in records] for canon, idx in mapping.items()})
    raw = raw.astype(str)
    for col in raw.columns:
        raw[col] = raw[col].str.strip()
    raw["line"] = lines

    if "category" not in raw.columns:
        raw["category"] = ""
        result.warnings.append("No category column found; all rows are grouped as 'Uncategorized', so driver analysis is limited.")
    if "description" not in raw.columns:
        raw["description"] = ""

    # 4. Parse values ---------------------------------------------------------------
    if fmt == "long":
        df = _build_long(raw, result)
    else:
        df = _build_wide(raw, result)

    if df.empty:
        return _fail(result, f"No usable rows: all {result.rows_read:,} data rows had problems (see the row details).")

    bad_lines = result.rows_read - df["line"].nunique()
    if result.rows_read and bad_lines / result.rows_read > config.MAX_INVALID_SHARE:
        return _fail(
            result,
            f"{bad_lines:,} of {result.rows_read:,} data rows failed validation, so the file probably "
            f"doesn't match the expected format. Expected columns: {LONG_FORMAT_HELP}.",
        )

    # 5. Dataset-level adjustments and notes ---------------------------------------
    df = _normalise_signs(df, result)
    df = _merge_category_spellings(df, result)
    _dataset_warnings(df, result)

    df = df.sort_values(["date", "line"], kind="stable").reset_index(drop=True)
    result.df = df[CANONICAL_COLUMNS]
    return result


# ---------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------
class _TooManyRows(Exception):
    pass


def _sniff_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _read_records(text: str, delimiter: str, result: LoadResult):
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = None
    for rec in reader:
        if rec and any(c.strip() for c in rec):
            header = rec
            break
    if header is None:
        return None, [], []
    # Drop trailing empty header cells produced by trailing commas.
    while header and not header[-1].strip():
        header = header[:-1]

    records, lines = [], []
    for rec in reader:
        if not rec or all(not c.strip() for c in rec):
            continue
        result.rows_read += 1
        if result.rows_read > config.MAX_ROWS:
            raise _TooManyRows()
        # Tolerate trailing empty cells (common from spreadsheet exports).
        while len(rec) > len(header) and not rec[-1].strip():
            rec = rec[:-1]
        if len(rec) != len(header):
            _add_issue(result, RowIssue(reader.line_num, "(whole row)", _short(delimiter.join(rec), 60),
                                        f"has {len(rec)} fields, expected {len(header)}"))
            continue
        records.append(rec)
        lines.append(reader.line_num)
    return header, records, lines


def _normalise_header(h: str) -> str:
    h = unicodedata.normalize("NFKC", h).replace("﻿", "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", h).strip("_")


def _map_columns(header: list[str], result: LoadResult) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, h in enumerate(header):
        canon = _ALIAS_LOOKUP.get(_normalise_header(h))
        if canon is None:
            continue
        if canon in mapping:
            result.warnings.append(
                f"Columns '{_short(header[mapping[canon]])}' and '{_short(h)}' both look like '{canon}'; "
                f"using '{_short(header[mapping[canon]])}'."
            )
            continue
        mapping[canon] = idx
    return mapping


def _detect_format(mapping: dict[str, int]) -> str | None:
    if all(c in mapping for c in ("date", "type", "amount")):
        return "long"
    if all(c in mapping for c in ("date", "revenue", "expenses")):
        return "wide"
    return None


def _missing_columns_message(header: list[str], mapping: dict[str, int]) -> str:
    wide_like = ("revenue" in mapping or "expenses" in mapping) and "amount" not in mapping
    required = ("date", "revenue", "expenses") if wide_like else ("date", "type", "amount")
    missing = [c for c in required if c not in mapping]
    found = ", ".join(_short(h) for h in header[:15] if h.strip()) or "(none)"
    if len(header) > 15:
        found += ", ..."
    return (
        f"Missing required column(s): {', '.join(missing)}. Found columns: {found}. "
        f"Expected: {LONG_FORMAT_HELP} — or the layout {WIDE_FORMAT_HELP}."
    )


# ---------------------------------------------------------------------------------
# Value parsing
# ---------------------------------------------------------------------------------
def _parse_dates(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Returns (parsed dates, mask of values that were not ISO and were read day-first)."""
    s = s.str.strip()
    parsed = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    # Anything that looks like ISO but failed strict parsing (e.g. 2026-02-30, 2026-13-01)
    # is invalid; it must not fall through to a lenient parser that could reinterpret it.
    needs_lenient = parsed.isna() & s.ne("") & ~s.str.match(_ISO_LIKE)
    if needs_lenient.any():
        try:
            alt = pd.to_datetime(s[needs_lenient], format="mixed", dayfirst=True, errors="coerce")
            if getattr(alt.dt, "tz", None) is not None:
                alt = alt.dt.tz_localize(None)
        except (ValueError, TypeError):
            alt = s[needs_lenient].map(_parse_one_date)
            alt = pd.to_datetime(alt, errors="coerce")
        parsed = parsed.astype("datetime64[ns]")
        parsed.loc[needs_lenient] = alt.astype("datetime64[ns]")
    else:
        parsed = parsed.astype("datetime64[ns]")

    out_of_range = parsed.notna() & ((parsed.dt.year < 1900) | (parsed.dt.year > 2100))
    parsed = parsed.mask(out_of_range)
    non_iso = needs_lenient & parsed.notna()
    return parsed.dt.normalize(), non_iso


def _parse_one_date(value: str):
    try:
        ts = pd.to_datetime(value, dayfirst=True)
        return ts.tz_localize(None) if ts.tzinfo is not None else ts
    except (ValueError, TypeError, OverflowError):
        return pd.NaT


def _parse_amounts(s: pd.Series) -> pd.Series:
    s = s.str.strip()
    euro = s.str.match(_EURO_NUMBER)
    s = s.mask(euro, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    negative_paren = s.str.match(r"^\(.*\)$")
    cleaned = s.str.replace(_CURRENCY_RE, "", regex=True).str.replace(r"[(),\s]", "", regex=True)
    num = pd.to_numeric(cleaned, errors="coerce").astype("float64")
    num = num.mask(negative_paren, -num.abs())
    invalid = num.isna() | ~np.isfinite(num) | (num.abs() > config.MAX_ABS_AMOUNT)
    return num.mask(invalid)


def _clean_text(s: pd.Series, max_len: int) -> pd.Series:
    s = s.str.replace(r"[\x00-\x1f\x7f]", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
    return s.str.slice(0, max_len)


def _build_long(raw: pd.DataFrame, result: LoadResult) -> pd.DataFrame:
    dates, non_iso = _parse_dates(raw["date"])
    types = raw["type"].str.lower().str.strip().map(TYPE_VALUES)
    amounts = _parse_amounts(raw["amount"])

    bad = dates.isna() | types.isna() | amounts.isna()
    for i in np.flatnonzero(bad.to_numpy()):
        line = int(raw["line"].iat[i])
        if pd.isna(dates.iat[i]):
            _add_issue(result, RowIssue(line, "date", _short(raw["date"].iat[i]), _date_problem(raw["date"].iat[i])))
        if pd.isna(types.iat[i]):
            _add_issue(result, RowIssue(line, "type", _short(raw["type"].iat[i]),
                                        "type must be 'revenue' or 'expense'"))
        if pd.isna(amounts.iat[i]):
            _add_issue(result, RowIssue(line, "amount", _short(raw["amount"].iat[i]), _amount_problem(raw["amount"].iat[i])))

    keep = ~bad
    _note_non_iso(non_iso & keep, result)
    df = pd.DataFrame({
        "line": raw["line"][keep].astype(int),
        "date": dates[keep],
        "type": types[keep],
        "category": raw["category"][keep],
        "amount": amounts[keep],
        "description": raw["description"][keep],
    })
    return _finish(df, result)


def _build_wide(raw: pd.DataFrame, result: LoadResult) -> pd.DataFrame:
    dates, non_iso = _parse_dates(raw["date"])
    parts = []
    any_value = pd.Series(False, index=raw.index)
    for col, typ in (("revenue", "revenue"), ("expenses", "expense")):
        cells = raw[col]
        present = cells.ne("")
        amounts = _parse_amounts(cells)
        bad_cell = present & amounts.isna()
        for i in np.flatnonzero((bad_cell & dates.notna()).to_numpy()):
            _add_issue(result, RowIssue(int(raw["line"].iat[i]), col, _short(cells.iat[i]),
                                        _amount_problem(cells.iat[i]), action="value skipped"))
        ok = present & amounts.notna() & dates.notna()
        any_value |= ok
        parts.append(pd.DataFrame({
            "line": raw["line"][ok].astype(int),
            "date": dates[ok],
            "type": typ,
            "category": raw["category"][ok],
            "amount": amounts[ok],
            "description": raw["description"][ok],
        }))

    for i in np.flatnonzero(dates.isna().to_numpy()):
        _add_issue(result, RowIssue(int(raw["line"].iat[i]), "date", _short(raw["date"].iat[i]),
                                    _date_problem(raw["date"].iat[i])))
    for i in np.flatnonzero((dates.notna() & ~any_value & raw["revenue"].eq("") & raw["expenses"].eq("")).to_numpy()):
        _add_issue(result, RowIssue(int(raw["line"].iat[i]), "revenue/expenses", "", "both revenue and expenses are blank"))

    _note_non_iso(non_iso & any_value, result)
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=CANONICAL_COLUMNS)
    return _finish(df, result)


def _finish(df: pd.DataFrame, result: LoadResult) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["category"] = _clean_text(df["category"].astype(str), config.MAX_CATEGORY_CHARS)
    blank = df["category"].eq("")
    if blank.any():
        df.loc[blank, "category"] = "Uncategorized"
        if result.source_format is not None and blank.sum() < len(df):
            result.warnings.append(f"{_plural(int(blank.sum()), 'row')} had no category; grouped as 'Uncategorized'.")
    df["description"] = _clean_text(df["description"].astype(str), config.MAX_DESCRIPTION_CHARS)
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.strftime("%Y-%m")
    df["amount"] = df["amount"].astype("float64")
    df["line"] = df["line"].astype(int)
    return df


def _normalise_signs(df: pd.DataFrame, result: LoadResult) -> pd.DataFrame:
    df = df.copy()
    for typ in ("revenue", "expense"):
        mask = df["type"].eq(typ)
        nonzero = df.loc[mask, "amount"].ne(0)
        if not nonzero.any():
            continue
        vals = df.loc[mask, "amount"][nonzero]
        if (vals < 0).all():
            df.loc[mask, "amount"] = df.loc[mask, "amount"].abs()
            result.warnings.append(f"All {typ} amounts were negative (a sign convention), so they were converted to positive values.")
        elif (vals < 0).any():
            n = int((vals < 0).sum())
            result.warnings.append(f"{_plural(n, f'negative {typ} amount')} {'was' if n == 1 else 'were'} kept as "
                                   f"a reversal/refund; {'it reduces' if n == 1 else 'they reduce'} {typ} totals.")
    return df


def _merge_category_spellings(df: pd.DataFrame, result: LoadResult) -> pd.DataFrame:
    df = df.copy()
    key = df["type"] + "|" + df["category"].str.casefold()
    canonical = df.groupby(key)["category"].transform("first")
    merged = int((canonical != df["category"]).sum())
    if merged:
        result.warnings.append(f"{_plural(merged, 'row')} had category names differing only in capitalisation; merged.")
    df["category"] = canonical
    return df


def _dataset_warnings(df: pd.DataFrame, result: LoadResult) -> None:
    months = sorted(df["month"].unique())
    if len(months) == 1:
        result.warnings.append("The data covers a single month, so month-over-month changes are not available.")
    else:
        full = pd.period_range(months[0], months[-1], freq="M").strftime("%Y-%m")
        gaps = [m for m in full if m not in set(months)]
        if gaps:
            shown = ", ".join(gaps[:6]) + (" ..." if len(gaps) > 6 else "")
            result.warnings.append(f"No rows for {len(gaps)} month(s) inside the date range ({shown}); "
                                   f"changes against those months are not calculated.")
    if not df["type"].eq("revenue").any():
        result.warnings.append("The file has no revenue rows.")
    if not df["type"].eq("expense").any():
        result.warnings.append("The file has no expense rows.")
    dupes = int(df.duplicated(subset=["date", "type", "category", "amount", "description"]).sum())
    if dupes:
        result.warnings.append(f"{_plural(dupes, 'row')} exactly duplicate another row. Kept; remove them if they were "
                               f"entered twice.")


# ---------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------
def _note_non_iso(mask: pd.Series, result: LoadResult) -> None:
    n = int(mask.sum())
    if n:
        result.warnings.append(f"{_plural(n, 'date')} {'was' if n == 1 else 'were'} not in YYYY-MM-DD format and "
                               f"{'was' if n == 1 else 'were'} read day-first (DD/MM/YYYY).")


def _date_problem(value: str) -> str:
    if not str(value).strip():
        return "date is blank"
    return "not a valid date (use YYYY-MM-DD)"


def _amount_problem(value: str) -> str:
    if not str(value).strip():
        return "amount is blank"
    return "not a valid number"


def _add_issue(result: LoadResult, issue: RowIssue) -> None:
    if len(result.issues) < _MAX_ISSUES_KEPT:
        result.issues.append(issue)
    else:
        result.issues_truncated += 1


def _plural(n: int, noun: str) -> str:
    return f"{n:,} {noun}" + ("" if n == 1 else "s")


def _short(value, n: int = 40) -> str:
    value = str(value)
    return value if len(value) <= n else value[: n - 1] + "…"


def _fail(result: LoadResult, message: str) -> LoadResult:
    result.errors.append(message)
    result.df = None
    return result
