"""The Evidence object: the unit of trust in this app.

Every calculation returns an Evidence record holding the result, the formula used and
the CSV line numbers of the rows that went into it. The LLM only ever sees `result`;
the UI shows all of it under each answer so a reviewer can check any figure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Evidence:
    tool: str
    title: str
    args: dict
    result: dict                  # JSON-serialisable payload; this is what the LLM sees
    formula: str
    row_lines: list[int]          # CSV line numbers of the source rows
    summary: str                  # deterministic plain-English summary of the result
    table: pd.DataFrame | None = None   # optional display table for the UI
    id: str = ""                  # "E1", "E2", ... assigned per answer

    def llm_payload(self, max_chars: int = 8000) -> str:
        payload = {"evidence_id": self.id, **self.result, "source_row_count": len(self.row_lines)}
        text = json.dumps(payload, ensure_ascii=False, default=_json_default)
        if len(text) > max_chars:
            text = json.dumps({"evidence_id": self.id, "error": "result too large; narrow the question"})
        return text


@dataclass
class EvidenceRegistry:
    items: list[Evidence] = field(default_factory=list)

    def add(self, ev: Evidence) -> Evidence:
        ev.id = f"E{len(self.items) + 1}"
        self.items.append(ev)
        return ev


def _json_default(obj):
    if hasattr(obj, "item"):
        return obj.item()
    return str(obj)
