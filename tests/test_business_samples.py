"""The five extra sample businesses load cleanly and keep the stories documented in
scripts/generate_business_samples.py (the suggested questions depend on them)."""

import csv
import importlib.util

import pytest

from fin_analyst import loader, metrics, samples
from tests.helpers import ROOT


def _df(key):
    s = samples.BY_KEY[key]
    res = loader.load_csv(s.path.read_bytes(), s.filename)
    assert res.ok and not res.issues, (res.errors, res.issues[:3])
    return res.df


def _cat(df, category, month):
    return float(df[(df["category"] == category) & (df["month"] == month)]["amount"].sum())


@pytest.mark.parametrize("sample", samples.SAMPLES, ids=lambda s: s.key)
def test_every_sample_loads_and_has_questions(sample):
    res = loader.load_csv(sample.path.read_bytes(), sample.filename)
    assert res.ok and not res.issues and res.rows_used == res.rows_read
    assert len(metrics.available_months(res.df)) >= 18 and len(sample.questions) >= 4


def test_sunrise_is_the_wide_format_example():
    s = samples.BY_KEY["sunrise"]
    assert loader.load_csv(s.path.read_bytes(), s.filename).source_format == "wide"


def test_masala_monsoon_festive_outlet_and_commission_stories():
    df = _df("masala")
    assert _cat(df, "Dine-in", "2024-07") < 0.9 * _cat(df, "Dine-in", "2024-06")
    assert _cat(df, "Delivery apps", "2024-07") > 1.1 * _cat(df, "Delivery apps", "2024-06")
    assert _cat(df, "Catering", "2024-10") > 3 * _cat(df, "Catering", "2024-09")
    assert _cat(df, "Rent", "2025-04") == pytest.approx(1.6 * _cat(df, "Rent", "2025-03"))
    before = _cat(df, "Delivery commissions", "2025-06") / _cat(df, "Delivery apps", "2025-06")
    after = _cat(df, "Delivery commissions", "2025-07") / _cat(df, "Delivery apps", "2025-07")
    assert before < 0.24 < 0.26 < after
    assert _cat(df, "Utilities", "2025-01") > 1.5 * _cat(df, "Utilities", "2024-12")


def test_threadline_september_losses_and_rising_returns():
    df = _df("threadline")
    mt = metrics.monthly_table(df)
    assert mt.loc["2024-09", "net"] < 0 and mt.loc["2025-09", "net"] < 0
    ratio = lambda m: _cat(df, "Returns & refunds", m) / _cat(df, "Website sales", m)
    assert ratio("2026-01") < 0.10 and ratio("2026-02") > 0.14
    assert _cat(df, "Wholesale", "2026-02") == 0 and _cat(df, "Wholesale", "2026-03") > 0


def test_pixel_and_pine_lost_client_and_one_offs():
    df = _df("pixelpine")
    assert _cat(df, "Retainers", "2025-10") < 0.65 * _cat(df, "Retainers", "2025-09")
    net = metrics.monthly_table(df)["net"]
    assert all(net[m] < 0 for m in ("2025-10", "2025-11", "2025-12")) and net["2026-02"] > 0
    hits = {(x["month"], x["category"]) for x in metrics.find_anomalies(df).result["unusual_category_months"]}
    assert {("2026-02", "Projects"), ("2026-01", "Equipment")} <= hits


def test_greenleaf_mri_flu_and_insurance_timing():
    df = _df("greenleaf")
    assert _cat(df, "Equipment lease", "2025-01") - _cat(df, "Equipment lease", "2024-12") == pytest.approx(420_000)
    assert _cat(df, "Diagnostics", "2025-06") > 1.4 * _cat(df, "Diagnostics", "2024-12")
    assert _cat(df, "Consultations", "2025-01") > 1.15 * _cat(df, "Consultations", "2024-11")
    assert _cat(df, "Insurance claims", "2025-09") == 0 and _cat(df, "Insurance claims", "2025-10") > 0
    assert len(metrics.available_months(df)) == 36


def test_sunrise_monsoon_losses_and_subsidy_catch_up():
    df = _df("sunrise")
    q = {p["period"]: p for p in metrics.period_breakdown(df, "quarter").result["periods"]}
    assert q["2024-Q3"]["net_revenue"] < 0 and q["2025-Q3"]["net_revenue"] < 0
    assert all(_cat(df, "Government subsidy receipts", f"2025-{m:02d}") == 0 for m in range(6, 13))
    assert _cat(df, "Government subsidy receipts", "2026-01") > 2_000_000
    panels = lambda m: _cat(df, "Panels & inverters", m) / (_cat(df, "Residential installs", m) + _cat(df, "Commercial projects", m))
    assert panels("2024-10") < 0.9 * panels("2024-09")


def test_business_generator_is_deterministic():
    spec = importlib.util.spec_from_file_location("gen2", ROOT / "scripts" / "generate_business_samples.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    for name, fn in gen.GENERATORS.items():
        with open(gen.OUT / name, newline="", encoding="utf-8") as f:
            assert fn() == list(csv.DictReader(f)), name
