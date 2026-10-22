"""Tests for the advanced tools (comparisons, growth, anomalies, ratios, scenarios, projections).

Hand-checked values use SMALL_CSV (see tests/helpers.py):
    Jan 2026: revenue A 1000 + B 500 = 1500, expenses X 300
    Feb 2026: revenue A 400 + B 700  = 1100, expenses X 350 + Y 50 = 400
    Apr 2026: revenue A 800, expenses X 200
The sample-data tests check that the stories planted by scripts/generate_sample_data.py are found.
"""

import pytest

from fin_analyst import guard, metrics, tools
from tests.helpers import load_text, sample_df, small_df


def test_compare_periods_hand_checked():
    r = metrics.compare_periods(small_df(), "2026-01", "2026-01", "2026-02", "2026-02").result
    assert r["period_a"]["total_revenue"] == 1500 and r["period_b"]["total_revenue"] == 1100
    assert r["total_revenue_change"] == -400 and r["total_revenue_change_pct"] == pytest.approx(-26.67, abs=0.01)
    assert r["net_revenue_change"] == (1100 - 400) - (1500 - 300)
    assert r["net_margin_change_pct_points"] == pytest.approx(63.64 - 80.0, abs=0.01)
    top = r["biggest_category_moves"][0]
    assert (top["category"], top["change"]) == ("A", -600)


def test_compare_periods_flags_unequal_lengths():
    r = metrics.compare_periods(small_df(), "2026-01", "2026-02", "2026-04", "2026-04").result
    assert "different lengths" in r["note"] and r["period_a"]["avg_monthly_revenue"] == 1300


def test_category_growth_ranks_cloud_first_in_sample():
    r = metrics.category_growth(sample_df(), "expenses").result
    assert r["categories_fastest_growth_first"][0]["category"] == "Cloud Infrastructure"
    assert r["window_months"] == 3 and len(r["first_window"]) == 3


def test_category_growth_window_is_capped_by_period_length():
    r = metrics.category_growth(small_df(), "revenue", window_months=10).result
    assert r["window_months"] == 1  # 3 months of data -> at most half
    a = next(c for c in r["categories_fastest_growth_first"] if c["category"] == "A")
    assert a["growth_pct"] == pytest.approx(-20.0)  # 1000 -> 800


def test_category_trend_resolves_partial_names_and_finds_peak():
    r = metrics.category_trend(sample_df(), "marketing").result
    assert r["category"] == "Marketing" and r["type"] == "expense"
    assert r["highest_month"] == "2025-11"  # planted year-end campaign


def test_category_trend_rejects_unknown_category():
    with pytest.raises(metrics.MetricError, match="Unknown or ambiguous"):
        metrics.category_trend(sample_df(), "Yachts")


def test_find_anomalies_finds_planted_stories():
    r = metrics.find_anomalies(sample_df()).result
    hits = {(x["month"], x["category"]) for x in r["unusual_category_months"]}
    assert {("2026-03", "Enterprise Licenses"), ("2025-11", "Marketing"), ("2025-08", "Professional Services")} <= hits


def test_find_anomalies_needs_four_months():
    with pytest.raises(metrics.MetricError, match="four months"):
        metrics.find_anomalies(small_df())


def test_period_breakdown_quarters_add_up():
    df = sample_df()
    r = metrics.period_breakdown(df, "quarter").result
    total = metrics.period_summary(df).result["total_revenue"]
    assert sum(p["revenue"] for p in r["periods"]) == pytest.approx(total, abs=0.05)
    assert len(r["periods"]) == 6 and not any(p["partial"] for p in r["periods"])
    assert r["worst_by_net_revenue"] == "2026-Q1"  # contains the March 2026 collapse


def test_period_breakdown_marks_partial_years():
    r = metrics.period_breakdown(sample_df(), "year").result
    assert [p["period"] for p in r["periods"]] == ["2025", "2026"] and r["periods"][1]["partial"]


def test_expense_ratios_hand_checked():
    r = metrics.expense_ratios(small_df()).result
    assert r["total_expense_ratio_pct"] == pytest.approx(900 / 3400 * 100, abs=0.01)
    x = r["expense_categories"][0]
    assert x["category"] == "X" and x["ratio_to_revenue_pct"] == pytest.approx(850 / 3400 * 100, abs=0.01)


def test_what_if_applies_category_and_side_changes():
    r = metrics.what_if(small_df(), [{"category": "X", "change_pct": -50},
                                     {"category": "all revenue", "change_pct": 10}]).result
    assert r["scenario"]["total_expenses"] == 900 - 425
    assert r["scenario"]["total_revenue"] == pytest.approx(3740)
    assert r["net_revenue_change"] == pytest.approx(425 + 340)


def test_what_if_validates_input():
    with pytest.raises(metrics.MetricError):
        metrics.what_if(small_df(), [])
    with pytest.raises(metrics.MetricError, match="between"):
        metrics.what_if(small_df(), [{"category": "X", "change_pct": -150}])


def test_project_trend_is_exact_on_a_straight_line():
    rows = "\n".join(f"2026-{m:02d}-05,revenue,A,{1000 + 100 * m}," for m in range(1, 7))
    df = load_text("date,type,category,amount,description\n" + rows + "\n").df
    r = metrics.project_trend(df, "revenue", months_ahead=2, basis_months=6).result
    assert r["slope_per_month"] == pytest.approx(100) and r["r_squared"] == pytest.approx(1.0)
    assert [p["month"] for p in r["projections"]] == ["2026-07", "2026-08"]
    assert [p["projected_value"] for p in r["projections"]] == [pytest.approx(1700), pytest.approx(1800)]


@pytest.mark.parametrize("name,args", [
    ("compare_periods", {"period_a_start": "2025-01", "period_a_end": "2025-06",
                         "period_b_start": "2026-01", "period_b_end": "2026-06"}),
    ("category_growth", {"metric": "expenses"}),
    ("category_trend", {"category": "Salaries", "start_month": None}),
    ("find_anomalies", {"metric": None}),
    ("period_breakdown", {"grain": "quarter"}),
    ("expense_ratios", {}),
    ("what_if", {"adjustments": [{"category": "Marketing", "change_pct": -20}]}),
    ("project_trend", {"metric": "net", "months_ahead": None}),
])
def test_every_new_tool_runs_through_the_tool_runner(name, args):
    ev = tools.run_tool(name, args, sample_df())
    assert ev.row_lines and ev.summary and len(ev.llm_payload()) < 8000


def test_guard_accepts_percentage_points_from_compare_periods():
    ev = metrics.compare_periods(sample_df(), "2025-01", "2025-06", "2026-01", "2026-06")
    ev.id = "E1"
    pts = abs(ev.result["net_margin_change_pct_points"])
    assert guard.check_answer(f"Margin moved {pts:.1f} percentage points [E1].", [ev]).ok
