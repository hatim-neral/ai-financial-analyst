"""Shared test helpers (plain functions, no fixtures needed)."""

from __future__ import annotations

import json
from pathlib import Path

from fin_analyst import loader
from fin_analyst.llm import ChatResponse, ToolCall

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EDGE = DATA / "edge_cases"

# Small hand-checked dataset. March 2026 is deliberately missing (a gap month).
SMALL_CSV = """date,type,category,amount,description
2026-01-10,revenue,A,1000,
2026-01-15,revenue,B,500,
2026-01-20,expense,X,300,
2026-02-10,revenue,A,400,
2026-02-12,revenue,B,700,
2026-02-20,expense,X,350,
2026-02-21,expense,Y,50,
2026-04-05,revenue,A,800,
2026-04-06,expense,X,200,
"""


def load_text(text: str, name: str = "test.csv") -> loader.LoadResult:
    return loader.load_csv(text.encode("utf-8"), name)


def load_edge(name: str) -> loader.LoadResult:
    return loader.load_csv((EDGE / name).read_bytes(), name)


def small_df():
    res = load_text(SMALL_CSV)
    assert res.ok, res.errors
    return res.df


def sample_df():
    res = loader.load_csv((DATA / "sample_financials.csv").read_bytes(), "sample_financials.csv")
    assert res.ok, res.errors
    return res.df


class FakeClient:
    """Scripted stand-in for llm.ChatClient. Each script item is either a string (a final
    text answer), a list of (tool_name, args_dict) tuples (tool calls), or an Exception."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[list[dict]] = []
        self.providers = ["fake"]

    def complete(self, messages, tools=None):
        self.calls.append([dict(m) for m in messages])
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        usage = {"prompt_tokens": 1000, "completion_tokens": 50}
        if isinstance(item, list):
            calls = [ToolCall(f"call_{i}", name, json.dumps(args)) for i, (name, args) in enumerate(item)]
            return ChatResponse(None, calls, usage, "fake", "fake-model")
        return ChatResponse(item, [], usage, "fake", "fake-model")
