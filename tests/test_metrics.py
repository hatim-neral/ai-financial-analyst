"""Calculation tests. Expected values were worked out by hand from SMALL_CSV:

    Jan 2026: revenue A 1000 + B 500 = 1500, expenses X 300
    Feb 2026: revenue A 400 + B 700  = 1100, expenses X 350 + Y 50 = 400
    Mar 2026: (no data)
    Apr 2026: revenue A 800, expenses X 200
"""

import pandas as pd
import pytest

from fin_analyst import metrics
from tests.helpers import DATA, sample_df, small_df


def test_period_summary_totals():
    r = metrics.period_summary(small_df()).result
    assert r["total_revenue"] == 3400 and r["total_expenses"] == 900 and r["net_revenue"] == 2500
    assert r["net_margin_pct"] == pytest.approx(73.53, abs=0.01)
    assert r["months_with_data"] == 3 and r["period_start"] == "2026-01" and r["period_end"] == "2026-04"


def test_period_summary_single_month_and_rows():
    ev = metrics.period_summary(small_df(), "2026-02", "2026-02")
    assert ev.result["total_revenue"] == 1100 and ev.result["net_revenue"] == 700
    assert ev.row_lines == [5, 6, 7, 8]


def test_period_clamped_to_data():
    ev = metrics.period_summary(small_df(), "2025-01", "2030-12")
    assert ev.result["total_revenue"] == 3400 and "note" in ev.result


def test_monthly_trend_mom_and_gap():
    months = {m["month"]: m for m in metrics.monthly_trend(small_df()).result["months"]}
    assert months["2026-02"]["revenue_mom_pct"] == pytest.approx(-26.67, abs=0.01)
    assert months["2026-02"]["expenses_mom_pct"] == pytest.approx(33.33, abs=0.01)
    assert months["2026-01"]["revenue_mom_pct"] is None      # no previous month
    assert months["2026-04"]["revenue_mom_pct"] is None      # March missing: no comparison


def test_explain_revenue_change_by_category():
    r = metrics.explain_change(small_df(), "2026-02", "revenue").result
    assert r["previous_total"] == 1500 and r["current_total"] == 1100
    assert r["change"] == -400 and r["change_pct"] == pytest.approx(-26.67, abs=0.01)
    a, b = r["drivers_sorted_by_impact"]
    assert (a["category"], a["change"], a["share_of_total_change_pct"]) == ("A", -600, 150.0)
    assert (b["category"], b["change"], b["share_of_total_change_pct"]) == ("B", 200, -50.0)


def test_explain_net_change_signs():
    r = metrics.explain_change(small_df(), "February 2026", "net").result
    assert r["change"] == -500 and r["revenue_change"] == -400 and r["expenses_change"] == 100
    shares = {d["category"]: d["share_of_total_change_pct"] for d in r["drivers_sorted_by_impact"]}
    assert shares == {"A (revenue)": 120.0, "X (expense)": 10.0, "Y (expense)": 10.0, "B (revenue)": -40.0}


def test_explain_change_requires_previous_month():
    with pytest.raises(metrics.MetricError, match="2026-03"):
        metrics.explain_change(small_df(), "2026-04")


def test_top_categories():
    r = metrics.top_categories(small_df(), "revenue").result
    assert [(c["category"], c["total"]) for c in r["categories"]] == [("A", 2200), ("B", 1200)]
    assert r["categories"][0]["share_of_total_pct"] == pytest.approx(64.71, abs=0.01)


@pytest.mark.parametrize("value,expected", [
    ("2026-02", "2026-02"), ("2026/2", "2026-02"), ("Feb 2026", "2026-02"), ("February 2026", "2026-02"),
    ("feb-26", "2026-02"), ("02/2026", "2026-02"), ("February", "2026-02"),
])
def test_resolve_month_formats(value, expected):
    assert metrics.resolve_month(small_df(), value) == expected


@pytest.mark.parametrize("value,fragment", [
    ("2026-13", "not a valid month"), ("2030-01", "No data for 2030-01"), ("hello", "Could not understand"),
    ("March", "no March"),
])
def test_resolve_month_errors(value, fragment):
    with pytest.raises(metrics.MetricError, match=fragment):
        metrics.resolve_month(small_df(), value)


def test_ambiguous_month_name_on_sample():
    with pytest.raises(metrics.MetricError, match="several months"):
        metrics.resolve_month(sample_df(), "March")


def test_bad_metric_rejected():
    with pytest.raises(metrics.MetricError, match="Unknown metric"):
        metrics.explain_change(small_df(), "2026-02", "ebitda")


# --- invariants on the full sample dataset -------------------------------------------
def test_driver_changes_sum_to_total_change_every_month():
    df = sample_df()
    months = metrics.available_months(df)
    for m in months[1:]:
        for metric in ("revenue", "expenses", "net"):
            r = metrics.explain_change(df, m, metric).result
            impact = sum(d["change"] * (-1 if "(expense)" in d["category"] else 1)
                         for d in r["drivers_sorted_by_impact"])
            assert impact == pytest.approx(r["change"], abs=0.05), (m, metric)


def test_totals_match_an_independent_calculation():
    raw = pd.read_csv(DATA / "sample_financials.csv")
    r = metrics.period_summary(sample_df()).result
    assert r["total_revenue"] == pytest.approx(raw.loc[raw["type"] == "revenue", "amount"].sum(), abs=0.01)
    assert r["total_expenses"] == pytest.approx(raw.loc[raw["type"] == "expense", "amount"].sum(), abs=0.01)


def test_source_rows_reproduce_the_figure():
    df = sample_df()
    ev = metrics.top_categories(df, "expenses", "2025-11", "2025-11", n=1)
    rows = df[df["line"].isin(ev.row_lines)]
    assert rows["amount"].sum() == pytest.approx(ev.result["categories"][0]["total"], abs=0.01)
