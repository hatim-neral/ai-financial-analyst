"""Next-question suggestions after an answer, built from what that answer calculated.

Deterministic (no extra LLM call): each rule looks at the tools the answer used and the
months or categories in their results.
"""

from __future__ import annotations

from fin_analyst import formatting as fmt
from fin_analyst.agent import AnswerResult
from fin_analyst.metrics import previous_month


def _year_before(month: str) -> str:
    return f"{int(month[:4]) - 1}{month[4:]}"


def suggest(res: AnswerResult, months: list[str], asked: set[str], limit: int = 3) -> list[str]:
    out: list[str] = []
    for ev in res.evidence:
        r, tool = ev.result, ev.tool
        if tool == "explain_month_change":
            m = r["month"]
            other = "expenses" if r["metric"] == "revenue" else "revenue"
            out.append(f"How did {other} move in {fmt.month_label_long(m)}, and which categories drove it?")
            if _year_before(m) in months:
                out.append(f"Compare {fmt.month_label_long(m)} with {fmt.month_label_long(_year_before(m))}.")
            out.append("Were there any other unusual months like this one?")
        elif tool == "compare_periods":
            out.append("Which categories grew fastest between those two periods?")
            moves = [x for x in r["biggest_category_moves"] if x["type"] == "expense"]
            if moves:
                out.append(f"What if {moves[0]['category']} had grown half as much? Show net revenue and margin.")
            out.append("Break both periods down by quarter.")
        elif tool == "category_growth":
            top = next((c for c in r["categories_fastest_growth_first"] if c["growth_pct"] is not None), None)
            if top:
                out.append(f"Show the month-by-month history of {top['category']}.")
                out.append(f"What share of revenue does {top['category']} take now?")
                out.append(f"What if {top['category']} were 15% lower over the whole period?")
        elif tool == "category_trend":
            cat = r["category"]
            out.append(f"Was {cat} unusual in any particular month?")
            out.append(f"What if {cat} were 20% lower? Show the effect on margin.")
            out.append("Which other categories are growing fastest?")
        elif tool == "find_anomalies":
            items = r["unusual_category_months"]
            if items:
                a = items[0]
                out.append(f"Why was {a['category']} so unusual in {fmt.month_label_long(a['month'])}?")
                if len(items) > 1:
                    b = items[1]
                    out.append(f"Explain {b['category']} in {fmt.month_label_long(b['month'])} too.")
            out.append("Leaving one-offs aside, what is the underlying trend in net revenue?")
        elif tool == "period_breakdown":
            best, worst = r.get("best_by_net_revenue"), r.get("worst_by_net_revenue")
            if best and worst and best != worst:
                out.append(f"Compare {best} with {worst} category by category.")
            out.append("Show the same view by year." if r["grain"] == "quarter" else "Show the same view by quarter.")
        elif tool == "expense_ratios":
            cats = r["expense_categories"]
            if cats:
                out.append(f"Is {cats[0]['category']} growing faster than revenue?")
            out.append("What if our three largest costs were each 10% lower?")
        elif tool == "what_if":
            out.append("Which single cost cut would improve the margin the most?")
            out.append("What if the same changes had applied only to the last six months?")
        elif tool == "project_trend":
            other = "expenses" if r["metric"] != "expenses" else "revenue"
            out.append(f"Project {other} for the same months.")
            out.append("Were there unusual months in the basis that could distort this projection?")
        elif tool == "get_budget_status":
            over = [c for c in r["categories"] if c["status"] == "over"]
            if over:
                out.append(f"How has {over[0]['category']} spending trended over the last six months?")
            out.append("Which budgets were broken most often, and by how much?")
        elif tool == "get_cash_runway":
            out.append("Which costs are growing fastest and shortening our runway?")
            out.append("How has monthly net revenue changed over the last six months?")
        elif tool == "get_top_categories":
            cats = r["categories"]
            if cats:
                out.append(f"How has {cats[0]['category']} changed month by month?")
            out.append("What share of revenue does each cost take?")
        elif tool == "get_period_summary":
            out.append("Compare the first half of this period with the second half.")
            out.append("Which quarter was the strongest, and why?")
        elif tool == "get_monthly_trend":
            if len(months) > 1 and previous_month(months[-1]) in months:
                out.append(f"Why did net revenue change in {fmt.month_label_long(months[-1])}?")
            out.append("If the recent trend continues, what will the next quarter look like?")
    if not out:
        out = ["Were there any unusual months?", "Which costs are growing faster than revenue?",
               "Compare the first half of the period with the second half."]
    seen, picked = {q.lower() for q in asked}, []
    for q in out:
        if q.lower() not in seen and q not in picked:
            picked.append(q)
    return picked[:limit]
