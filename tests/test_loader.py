import pandas as pd

from fin_analyst import config, loader
from tests.helpers import DATA, load_edge, load_text


def test_sample_loads_cleanly():
    res = loader.load_csv((DATA / "sample_financials.csv").read_bytes(), "sample_financials.csv")
    assert res.ok and res.errors == [] and res.warnings == [] and res.issues == []
    assert res.rows_read == res.rows_used == len(res.df) > 500
    assert list(res.df.columns) == loader.CANONICAL_COLUMNS
    assert set(res.df["type"]) == {"revenue", "expense"}


# --- file-level failures ------------------------------------------------------------
def test_empty_file():
    res = load_edge("empty.csv")
    assert not res.ok and "empty" in res.errors[0].lower()


def test_whitespace_only_file():
    res = load_text("   \n\n  ")
    assert not res.ok and "empty" in res.errors[0].lower()


def test_header_only():
    res = load_edge("header_only.csv")
    assert not res.ok and "no data rows" in res.errors[0]


def test_missing_amount_column_names_the_column():
    res = load_edge("missing_amount_column.csv")
    assert not res.ok
    msg = res.errors[0]
    assert "Missing required column(s): amount" in msg
    assert "Found columns: date, type, category, description" in msg


def test_wide_layout_missing_expenses_column():
    res = load_text("date,category,revenue\n2026-01-01,A,100\n")
    assert not res.ok and "expenses" in res.errors[0]


def test_binary_file_rejected():
    res = load_edge("not_really_a_csv.csv")
    assert not res.ok and "binary" in res.errors[0]


def test_wrong_extension_rejected():
    res = loader.load_csv(b"date,type,category,amount\n2026-01-01,revenue,A,1\n", "report.xlsx")
    assert not res.ok and "not a .csv" in res.errors[0]


def test_file_too_large_rejected():
    data = b"date,type,category,amount\n" + b"2026-01-01,revenue,A,1\n" * (config.MAX_FILE_BYTES // 20)
    res = loader.load_csv(data, "big.csv")
    assert not res.ok and "limit" in res.errors[0]


def test_all_rows_invalid():
    res = load_edge("all_invalid_dates.csv")
    assert not res.ok and "No usable rows" in res.errors[0]
    assert [i.line for i in res.issues] == [2, 3, 4]


def test_mostly_invalid_file_rejected():
    rows = "\n".join(["bad,revenue,A,1"] * 6 + ["2026-01-01,revenue,A,1"] * 4)
    res = load_text("date,type,category,amount\n" + rows + "\n")
    assert not res.ok and "6 of 10" in res.errors[0]


# --- row-level handling -----------------------------------------------------------------
def test_invalid_dates_skipped_with_line_numbers():
    res = load_edge("invalid_dates.csv")
    assert res.ok
    bad = {i.line: i.problem for i in res.issues}
    assert set(bad) == {4, 5, 6, 10}           # 2026-02-30, garbage, blank, month 13
    assert bad[6] == "date is blank"
    assert res.rows_used == 6
    # 05/02/2026 is read day-first -> 5 Feb 2026, and the user is told
    row = res.df[res.df["line"] == 7].iloc[0]
    assert row["date"] == pd.Timestamp("2026-02-05")
    assert any("day-first" in w for w in res.warnings)


def test_amount_parsing():
    res = load_edge("bad_amounts.csv")
    amounts = dict(zip(res.df["line"], res.df["amount"]))
    assert amounts[2] == 1200.50          # ₹1,200.50
    assert amounts[3] == 1234567.0        # Indian grouping 12,34,567
    assert amounts[4] == -500.0           # (500)
    assert amounts[7] == 1500.0           # 1.5e3
    assert {i.line for i in res.issues} == {5, 6, 9}   # abc, blank, inf
    assert any("reversal" in w for w in res.warnings)


def test_type_aliases_and_unknown_type():
    res = load_edge("unknown_type.csv")
    types = dict(zip(res.df["line"], res.df["type"]))
    assert types[2] == "revenue" and types[3] == "expense"
    assert [i.line for i in res.issues] == [4] and res.issues[0].column == "type"


def test_malformed_rows_reported():
    res = load_edge("malformed_rows.csv")
    assert res.ok and [i.line for i in res.issues] == [3, 4]
    assert "expected 5" in res.issues[0].problem


def test_wide_format_converted():
    res = load_edge("wide_format.csv")
    assert res.ok and res.source_format == "wide"
    df = res.df
    assert df.loc[df["type"] == "revenue", "amount"].sum() == 950000
    assert df.loc[df["type"] == "expense", "amount"].sum() == 775000


def test_semicolon_and_decimal_comma():
    res = load_edge("semicolon_delimited.csv")
    assert res.ok
    assert sorted(res.df["amount"]) == [300.0, 1250.5, 1300.0]


def test_line_numbers_survive_blank_lines():
    res = load_text("date,type,category,amount\n\n2026-01-01,revenue,A,10\n\n\n2026-01-02,revenue,A,bad\n")
    assert list(res.df["line"]) == [3]
    assert res.issues[0].line == 6


def test_missing_category_column_is_a_warning():
    res = load_text("date,type,amount\n2026-01-01,revenue,10\n2026-02-01,expense,4\n")
    assert res.ok and set(res.df["category"]) == {"Uncategorized"}
    assert any("No category column" in w for w in res.warnings)


def test_header_aliases():
    res = load_text("Transaction Date,Kind,Account,Value\n2026-01-01,Income,Sales,10\n")
    assert res.ok and res.df.iloc[0]["type"] == "revenue" and res.df.iloc[0]["amount"] == 10


def test_category_capitalisation_merged():
    res = load_text("date,type,category,amount\n2026-01-01,expense,Marketing,1\n2026-01-02,expense,marketing,2\n")
    assert set(res.df["category"]) == {"Marketing"}


def test_all_negative_expenses_flipped():
    res = load_text("date,type,category,amount\n2026-01-01,revenue,A,100\n2026-01-02,expense,X,-40\n")
    assert res.df.loc[res.df["type"] == "expense", "amount"].tolist() == [40.0]


def test_injected_category_is_truncated_data():
    res = load_edge("prompt_injection.csv")
    assert res.ok
    assert res.df["category"].str.len().max() <= config.MAX_CATEGORY_CHARS


def test_single_month_and_gap_warnings():
    assert any("single month" in w for w in load_edge("single_month.csv").warnings)
    res = load_text("date,type,category,amount\n2026-01-01,revenue,A,1\n2026-03-01,revenue,A,1\n")
    assert any("2026-02" in w for w in res.warnings)
