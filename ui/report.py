"""One-click report: a self-contained, printable HTML file (open it and use Print → Save as PDF).

Everything in it comes from fin_analyst.metrics or from AI answers that passed the number
guard. All text is escaped; the AI's markdown is converted with a tiny, safe subset.
"""

from __future__ import annotations

import html
import re
from datetime import date

from fin_analyst import formatting as fmt
from fin_analyst import metrics


def _md(text: str) -> str:
    """Escape, then allow **bold**, *italic* and '-' / '•' bullet lists. Nothing else."""
    out, items = [], []

    def inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        return re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", s)

    def flush():
        if items:
            out.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
            items.clear()

    for line in (text or "").splitlines():
        stripped = line.strip()
        if re.match(r"^[-•*]\s+", stripped):
            items.append(inline(re.sub(r"^[-•*]\s+", "", stripped)))
        else:
            flush()
            if stripped:
                out.append(f"<p>{inline(stripped)}</p>")
    flush()
    return "".join(out)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build(ctx, history) -> str:
    df, s, e = ctx.df, ctx.start, ctx.end
    period = ctx.period
    summ = metrics.period_summary(df, s, e).result
    parts = [f"""
<header><div class="mark" aria-hidden="true"><i></i><i></i><i></i></div><div><h1>{html.escape(ctx.name)}</h1>
<p>{html.escape(ctx.sample.kind if ctx.sample else "Uploaded data")} · {html.escape(period)} · generated {date.today():%-d %b %Y}</p></div></header>
<section class="kpis">
  <div><span>Revenue</span><b>{fmt.money(summ['total_revenue'])}</b></div>
  <div><span>Expenses</span><b>{fmt.money(summ['total_expenses'])}</b></div>
  <div><span>Net revenue</span><b>{fmt.money(summ['net_revenue'])}</b></div>
  <div><span>Net margin</span><b>{fmt.pct(summ['net_margin_pct'], signed=False)}</b></div>
</section>"""]

    highlights = []
    for fn in (lambda: metrics.find_anomalies(df, "both", s, e), lambda: metrics.category_growth(df, "expenses", s, e),
               lambda: metrics.period_breakdown(df, "quarter", s, e)):
        try:
            highlights.append(fn().summary)
        except metrics.MetricError:
            pass
    if highlights:
        parts.append("<h2>Highlights</h2><ul>" + "".join(f"<li>{html.escape(h)}</li>" for h in highlights) + "</ul>")

    try:
        pb = metrics.period_breakdown(df, "quarter", s, e).result["periods"]
        parts.append("<h2>By quarter</h2>" + _table(
            ["Quarter", "Revenue", "Expenses", "Net revenue", "Margin"],
            [[p["period"] + (" (partial)" if p["partial"] else ""), fmt.money(p["revenue"]), fmt.money(p["expenses"]),
              fmt.money(p["net_revenue"]), fmt.pct(p["net_margin_pct"], signed=False)] for p in pb]))
    except metrics.MetricError:
        pass

    for metric in ("revenue", "expenses"):
        try:
            top = metrics.top_categories(df, metric, s, e, n=8).result
            parts.append(f"<h2>Top {'revenue' if metric == 'revenue' else 'expense'} categories</h2>" + _table(
                ["Category", "Total", "Share"],
                [[c["category"], fmt.money(c["total"]), fmt.pct(c["share_of_total_pct"], signed=False)] for c in top["categories"]]))
        except metrics.MetricError:
            pass

    plan = ctx.plan
    if plan.get("budgets"):
        b = metrics.budget_status(df, plan["budgets"], e).result
        parts.append(f"<h2>Budgets, {fmt.month_label(b['month'])}</h2>" + _table(
            ["Category", "Budget", "Actual", "Used", "Months over"],
            [[c["category"], fmt.money(c["monthly_budget"]), fmt.money(c["actual"]),
              fmt.pct(c["used_pct"], 0, signed=False), c["months_over_budget"]] for c in b["categories"]]))
    if plan.get("cash_balance"):
        rw = metrics.cash_runway(df, plan["cash_balance"])
        parts.append(f"<h2>Cash runway</h2><p>{html.escape(rw.summary)}</p><p class='note'>{html.escape(rw.result['note'])}</p>")
    if plan.get("scenarios"):
        from .plan import _tool_adj, describe
        rows = []
        for sc in plan["scenarios"]:
            try:
                r = metrics.what_if(df, [_tool_adj(a) for a in sc["adjustments"]], s, e).result
                rows.append([sc["name"], describe(sc["adjustments"]), fmt.money(r["scenario"]["net_revenue"]),
                             fmt.signed_money(r["net_revenue_change"]),
                             f"{fmt.pct(r['baseline']['net_margin_pct'], signed=False)} → {fmt.pct(r['scenario']['net_margin_pct'], signed=False)}"])
            except metrics.MetricError:
                continue
        if rows:
            parts.append("<h2>Saved scenarios</h2>" + _table(["Scenario", "Changes", "Net revenue", "Change", "Margin"], rows))

    answered = [h for h in history if h.status in ("verified", "no_figures", "fallback")]
    if answered:
        parts.append("<h2>Questions answered by the AI analyst</h2>")
        for h in answered:
            tag = "Verified" if h.status == "verified" else "Calculation shown" if h.status == "fallback" else "No figures"
            sources = "; ".join(f"[{ev.id}] {ev.title}" for ev in h.evidence)
            parts.append(f"<div class='qa'><div class='q'>{html.escape(h.question)}</div><span class='tag'>{tag}</span>"
                         f"{_md(h.text)}<p class='note'>Sources: {html.escape(sources) or 'none'}</p></div>")

    parts.append("<footer>Every figure was calculated in Python from the uploaded transactions. AI answers were "
                 "checked figure by figure against those calculations before being included.</footer>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(ctx.name)} report, {html.escape(period)}</title>
<style>
  body {{ font: 15px/1.55 Geist, Inter, -apple-system, system-ui, sans-serif; font-variant-numeric: tabular-nums; color: #14141F; margin: 0 auto; max-width: 860px; padding: 40px 24px; }}
  header {{ display: flex; gap: 14px; align-items: center; margin-bottom: 24px; }}
  .mark {{ display: grid; gap: 4px; width: 26px; }}
  .mark i {{ display: block; height: 4px; border-radius: 1px; background: #141414; }}
  .mark i:nth-child(2) {{ width: 70%; }} .mark i:nth-child(3) {{ width: 85%; background: #1d5fbf; }}
  h1 {{ margin: 0; font-size: 28px; letter-spacing: -0.02em; }} header p {{ margin: 2px 0 0; color: #62627A; }}
  h2 {{ font-size: 18px; margin: 30px 0 10px; letter-spacing: -0.01em; }}
  .kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
  .kpis div {{ border: 1px solid #E4E4EE; border-radius: 14px; padding: 12px 14px; }}
  .kpis span {{ display: block; color: #62627A; font-size: 12px; }} .kpis b {{ font-size: 19px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  th, td {{ text-align: left; padding: 7px 8px; border-bottom: 1px solid #ECECF4; }} th {{ color: #62627A; font-weight: 600; }}
  .qa {{ border: 1px solid #E4E4EE; border-radius: 14px; padding: 12px 16px; margin: 10px 0; break-inside: avoid; }}
  .q {{ font-weight: 700; }} .tag {{ font-size: 12px; color: #2e7d32; font-weight: 500; }}
  .note {{ color: #62627A; font-size: 12.5px; }}
  footer {{ margin-top: 36px; color: #62627A; font-size: 12px; border-top: 1px solid #ECECF4; padding-top: 12px; }}
  @media print {{ body {{ padding: 0; }} .kpis div, .qa {{ border-color: #ccc; }} }}
  @media (max-width: 600px) {{ .kpis {{ grid-template-columns: repeat(2, 1fr); }} }}
</style></head><body>{"".join(parts)}</body></html>"""
