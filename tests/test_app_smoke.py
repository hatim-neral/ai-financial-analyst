"""UI smoke tests using Streamlit's built-in test runner (no browser needed).
Skipped automatically if Streamlit isn't installed."""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from tests.helpers import ROOT  # noqa: E402

APP = str(ROOT / "app.py")


def test_first_visit_shows_instructions():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("Use sample data" in i.value for i in at.info)


def test_sample_data_renders_dashboard():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.button(key="use_sample").click().run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert labels[:4] == ["Total revenue", "Total expenses", "Net revenue", "Net margin"]
    assert at.metric[0].value == "₹39,092,584"
