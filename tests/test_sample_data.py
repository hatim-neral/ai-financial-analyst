"""The demo relies on stories planted in the synthetic data. These tests keep them true."""

import csv
import importlib.util

from fin_analyst import metrics
from tests.helpers import DATA, ROOT, sample_df


def _top_driver(month, metric):
    r = metrics.explain_change(sample_df(), month, metric).result
    return r, r["drivers_sorted_by_impact"][0]


def test_march_2026_revenue_decline_driven_by_enterprise_licenses():
    r, d = _top_driver("2026-03", "revenue")
    assert r["change_pct"] < -20
    assert d["category"] == "Enterprise Licenses" and d["transactions_current"] == 1
    assert metrics.largest_decline_month(sample_df()) == "2026-03"


def test_august_2025_revenue_decline_driven_by_services():
    r, d = _top_driver("2025-08", "revenue")
    assert r["change"] < 0 and d["category"] == "Professional Services"


def test_november_2025_expense_spike_driven_by_marketing():
    r, d = _top_driver("2025-11", "expenses")
    assert r["change_pct"] > 10 and d["category"] == "Marketing"


def test_generator_is_deterministic():
    spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "generate_sample_data.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    with open(DATA / "sample_financials.csv", newline="", encoding="utf-8") as f:
        on_disk = list(csv.DictReader(f))
    assert gen.generate_rows() == on_disk
