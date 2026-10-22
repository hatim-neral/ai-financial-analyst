"""Budgets, cash runway, context tools, agent progress events, follow-ups, report and theme."""

import json
import re

import pytest

from fin_analyst import agent, loader, metrics, samples, tools
from fin_analyst.llm import ChatResponse, ToolCall
from tests.helpers import load_text, sample_df, small_df


# --- budgets -------------------------------------------------------------------------
def test_budget_status_hand_checked():
    # Apr 2026 in SMALL_CSV: expense X 200
    r = metrics.budget_status(small_df(), {"X": 150, "Y": 100}).result
    x = next(c for c in r["categories"] if c["category"] == "X")
    y = next(c for c in r["categories"] if c["category"] == "Y")
    assert r["month"] == "2026-04" and x["actual"] == 200 and x["status"] == "over" and x["used_pct"] == pytest.approx(133.33, abs=0.01)
    assert y["actual"] == 0 and y["status"] == "under"
    assert x["months_over_budget"] == 3  # 300, 350, 200 all exceed 150
    assert r["over_budget_count"] == 1


def test_budget_status_needs_budgets():
    with pytest.raises(metrics.MetricError, match="No budgets"):
        metrics.budget_status(small_df(), {})


# --- runway --------------------------------------------------------------------------
def _burning_df():
    rows = "\n".join(f"2026-{m:02d}-05,revenue,A,1000,\n2026-{m:02d}-06,expense,X,1500," for m in range(1, 7))
    return load_text("date,type,category,amount,description\n" + rows + "\n").df


def test_cash_runway_months_and_run_out_month():
    r = metrics.cash_runway(_burning_df(), 2000, basis_months=3).result
    assert r["monthly_burn"] == 500 and r["runway_months"] == 4.0
    assert r["cash_runs_out_month"] == "2026-11" and not r["cash_flow_positive"]


def test_cash_runway_positive_cash_flow_has_no_end():
    r = metrics.cash_runway(sample_df(), 1_000_000).result
    assert r["cash_flow_positive"] and r["runway_months"] is None and r["cash_runs_out_month"] is None


def test_cash_runway_rejects_missing_balance():
    with pytest.raises(metrics.MetricError):
        metrics.cash_runway(small_df(), None)


# --- tools with context ---------------------------------------------------------------
def test_context_tools_read_user_inputs():
    ev = tools.run_tool("get_budget_status", {}, small_df(), {"budgets": {"X": 150}})
    assert ev.result["over_budget_count"] == 1
    ev = tools.run_tool("get_cash_runway", {"basis_months": 3}, _burning_df(), {"cash_balance": 2000})
    assert ev.result["runway_months"] == 4.0
    with pytest.raises(tools.ToolError, match="No budgets"):
        tools.run_tool("get_budget_status", {}, small_df(), {})


def test_every_tool_has_a_progress_label():
    names = {t["function"]["name"] for t in tools.TOOL_SPECS}
    assert names <= set(tools.TOOL_LABELS) and len(names) == 14


def test_system_prompt_names_planning_inputs_without_values():
    prompt = agent.build_system_prompt(small_df(), {"budgets": {"X": 987654}, "cash_balance": 555555})
    assert '"budgets_set_for": ["X"]' in prompt and '"cash_balance_set": true' in prompt
    assert "987654" not in prompt and "555555" not in prompt


# --- agent progress events -------------------------------------------------------------
class FakeClient:
    providers = [object()]

    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, messages, tools_):
        return self.responses.pop(0)


def test_agent_reports_progress_and_keeps_a_step_log():
    call = ToolCall("c1", "get_budget_status", "{}")
    client = FakeClient([ChatResponse(None, [call], {}, "fake", "m"),
                         ChatResponse("X is over budget at 133.3% of its budget [E1].", [], {}, "fake", "m")])
    events = []
    res = agent.answer_question("Am I over budget?", small_df(), client, context={"budgets": {"X": 150}},
                                on_event=lambda kind, msg: events.append(kind))
    assert res.status == "verified"
    assert events[:2] == ["think", "tool"] and "check" in events
    assert any("Checking budgets" in s for s in res.steps)


# --- follow-ups ------------------------------------------------------------------------
def test_followups_use_the_answer_context_and_skip_asked_questions():
    from ui import followups
    ev = metrics.explain_change(sample_df(), "2026-03", "revenue")
    res = agent.AnswerResult("Why did revenue fall in March 2026?", "…", "verified", evidence=[ev])
    months = metrics.available_months(sample_df())
    ideas = followups.suggest(res, months, set())
    assert any("expenses" in q and "March 2026" in q for q in ideas)
    assert any("March 2025" in q for q in ideas)  # same month a year earlier exists
    again = followups.suggest(res, months, {ideas[0]})
    assert ideas[0] not in again


# --- report ----------------------------------------------------------------------------
def test_report_escapes_text_and_keeps_safe_markdown():
    from ui import report
    out = report._md("**Revenue** fell <script>x</script>\n- first *point*\n- second")
    assert "<strong>Revenue</strong>" in out and "&lt;script&gt;" in out and "<script>" not in out
    assert out.count("<li>") == 2 and "<em>point</em>" in out


def test_report_builds_for_an_account_with_plan_and_answers():
    from ui import pages, plan, report
    df = sample_df()
    months = metrics.available_months(df)
    p = plan.new_plan()
    p.update(budgets={"Marketing": 150000}, cash_balance=5_000_000,
             scenarios=[{"name": "Lean", "adjustments": [{"category": "Marketing", "change_pct": -20}]}])
    ctx = pages.Ctx(df=df, result=None, name="Cloudnine <Software>", sample=None, months=months,
                    start=months[0], end=months[-1], client=None, plan=p)
    ans = agent.AnswerResult("Q <b>?", "**Bold** answer", "verified")
    html = report.build(ctx, [ans])
    assert html.startswith("<!doctype html>") and "Cloudnine &lt;Software&gt;" in html and "Q &lt;b&gt;?" in html
    for heading in ("Budgets", "Cash runway", "Saved scenarios", "Questions answered", "By quarter"):
        assert heading in html


# --- theme -----------------------------------------------------------------------------
@pytest.mark.parametrize("palette", ["DARK", "LIGHT"])
def test_theme_css_is_safe_for_both_palettes(palette):
    from ui import theme
    css = theme._css(getattr(theme, palette))
    body = css[css.index("<style>") + 7: css.rindex("</style>")]
    assert not re.search(r"<[a-zA-Z/!]", body)
    assert getattr(theme, palette)["ground"] in css


def test_gpt_oss_citation_styles_are_normalised():
    assert agent.normalise_citations("up 9.8%【E1】 and [E2†ratio_to_revenue_pct][E3†x]") == "up 9.8%[E1] and [E2][E3]"
    assert agent.normalise_citations("₹3,646,686 [\u200bE1\u200b]") == "₹3,646,686 [E1]"


# --- money river and bridge -------------------------------------------------------------
@pytest.mark.parametrize("key", [s.key for s in samples.SAMPLES])
def test_money_river_balances_on_every_account(key):
    from ui import river
    s = samples.BY_KEY[key]
    df = loader.load_csv(s.path.read_bytes(), s.filename).df
    months = metrics.available_months(df)
    d = river.flows(df, months[0], months[-1])
    assert abs(sum(n["value"] for n in d["left"]) - sum(n["value"] for n in d["right"])) < 1
    assert len([n for n in d["left"] if n["kind"] == "in"]) <= river.TOP + 1


def test_money_river_adds_a_shortfall_source_for_a_loss():
    from ui import river
    s = samples.BY_KEY["pixelpine"]
    df = loader.load_csv(s.path.read_bytes(), s.filename).df
    d = river.flows(df, "2025-10", "2025-12")
    assert d["net"] < 0 and d["left"][-1]["name"] == "Shortfall" and d["left"][-1]["value"] == pytest.approx(-d["net"])


def test_odometer_and_bridge_markup():
    from ui.components import bridge, odometer
    html_ = odometer(9366371)
    assert html_.count('class="odo"') == 7 and 'aria-label="₹9,366,371"' in html_
    b = bridge("May 2026", 100, [("Sales", "Revenue", 50), ("Rent", "Expense", -20)], "Jun 2026", 130)
    assert b.count("bridge-step") == 2 and 'class="down"' in b and "₹130" in b
