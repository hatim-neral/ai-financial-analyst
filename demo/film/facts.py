"""Check every figure the film says or shows against the app's own metrics. Run before building:
    .venv/bin/python demo/film/facts.py
Writes demo/film/build/facts.json, which the compositor reads for its on-screen figures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fin_analyst import formatting as fmt, loader, metrics, samples  # noqa: E402

s = samples.BY_KEY["masala"]
df = loader.load_csv(s.path.read_bytes(), s.filename).df
months = metrics.available_months(df)
total = metrics.period_summary(df, months[0], months[-1]).result
mt = metrics.monthly_table(df)
first, last = months[:3], months[-3:]
rev_growth = (mt.loc[last, "revenue"].mean() / mt.loc[first, "revenue"].mean() - 1) * 100
growth = metrics.category_growth(df, "expenses", months[0], months[-1]).result
commission = next(c for c in growth["categories_fastest_growth_first"] if c["category"] == "Delivery commissions")
by_month = df[df.category.isin(["Delivery commissions", "Delivery apps"])].groupby(["month", "category"]).amount.sum().unstack()
share = by_month["Delivery commissions"] / by_month["Delivery apps"] * 100
before = share[share.index < "2025-07"].mean()
after = share[share.index >= "2025-07"].mean()

scenario = metrics.what_if(df, [{"category": "Delivery apps", "change_pct": -20}, {"category": "Dine-in", "change_pct": 20}],
                           months[0], months[-1]).result

facts = {
    "margin_before": round(scenario["baseline"]["net_margin_pct"], 1),
    "margin_after": round(scenario["scenario"]["net_margin_pct"], 1),
    "transactions": len(df),
    "net_words": fmt.money_words(total["net_revenue"]),
    "revenue_growth_pct": round(rev_growth, 1),
    "commission_growth_pct": round(commission["growth_pct"], 1),
    "keep_per_100_before": round(before, 1),
    "keep_per_100_after": round(after, 1),
    "outlets": 2,
}
said = {"transactions": 674, "net_words": "₹1.58 crore", "revenue_growth_pct": (90, 100), "commission_growth_pct": (130.5, 131.5),
        "keep_per_100_before": (21.5, 22.5), "keep_per_100_after": (27.5, 28.5),
        "margin_before": (22.35, 22.45), "margin_after": (27.55, 27.65)}   # the Plan card in the footage shows 22.4% -> 27.6%
for k, want in said.items():
    got = facts[k]
    ok = (want[0] <= got <= want[1]) if isinstance(want, tuple) else got == want
    print(f"{'ok ' if ok else 'BAD'} {k}: {got} (script says {want})")
    if not ok:
        raise SystemExit("the script says something the data does not")
out = Path(__file__).parent / "build"
out.mkdir(exist_ok=True)
(out / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1))
