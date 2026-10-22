"""UI smoke tests using Streamlit's built-in test runner (no browser needed).
Skipped automatically if Streamlit isn't installed. No test here asks the AI a question."""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from fin_analyst import samples  # noqa: E402
from tests.helpers import ROOT  # noqa: E402

APP = str(ROOT / "app.py")


def _app():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, at.exception
    return at


def test_opens_on_the_default_account_with_totals():
    at = _app()
    labels = [m.label for m in at.metric]
    assert labels[:4] == ["Revenue", "Expenses", "Net margin", "Transactions"]
    assert at.metric[0].value == "₹39,092,584" and at.metric[3].value == "711"


def test_switching_accounts_changes_the_numbers():
    at = _app()
    at.selectbox(key="account").select("masala").run()
    assert not at.exception
    assert at.metric[0].value != "₹39,092,584" and at.metric[3].value == "674"


@pytest.mark.parametrize("page", ["insights", "activity", "plan", "ask"])
@pytest.mark.parametrize("account", [s.key for s in samples.SAMPLES])
def test_every_page_renders_for_every_account(page, account):
    at = _app()
    at.selectbox(key="account").select(account).run()
    at.button(key=f"nav_{page}").click().run()
    assert not at.exception, at.exception


def test_period_presets_narrow_the_totals():
    at = _app()
    full = at.metric[0].value
    at.button_group(key="period_preset").set_value("6M").run()
    assert not at.exception and at.metric[0].value != full


def test_bad_upload_shows_an_error_not_a_crash():
    at = _app()
    at.session_state["source"] = ("empty.csv", b"", None)
    at.session_state["source_key"] = ("upload", "empty.csv")
    at.run()
    assert not at.exception and at.error


def test_plan_page_budgets_runway_and_scenarios():
    at = _app()
    at.button(key="nav_plan").click().run()
    at.button(key="budget_suggest").click().run()
    assert not at.exception
    plan = at.session_state["plans"]["cloudnine"]
    assert plan["budgets"] and all(v > 0 for v in plan["budgets"].values())
    at.number_input(key="cash_cloudnine").set_value(5_000_000).run()
    assert not at.exception and at.session_state["plans"]["cloudnine"]["cash_balance"] == 5_000_000
    at.text_input(key="scen_name").input("Grow 5%").run()
    at.button(key="scen_save").click().run()
    assert not at.exception
    assert [s["name"] for s in at.session_state["plans"]["cloudnine"]["scenarios"]] == ["Grow 5%"]


def test_report_download_is_offered():
    at = _app()
    assert not at.exception
    assert any(getattr(el, "proto", None) is not None and "Download report" in str(el.proto) for el in at.get("download_button"))


def test_keys_added_to_a_running_app_take_effect(monkeypatch):
    # Regression: the AI client was cached for the life of the server, so keys added after start-up
    # (as on Streamlit Cloud, where secrets are saved while the app runs) were never picked up.
    for var in ("GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY",
                "NVIDIA_API_KEY", "HF_TOKEN", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    at = AppTest.from_file(APP, default_timeout=60)
    at.secrets["GROQ_API_KEY"] = ""
    at.run()
    status = lambda: " ".join(e.body for e in at.get("html") if "ai-status" in e.body)
    assert "AI not configured" in status()
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_added_later")
    at.run()
    assert "AI connected" in status()
