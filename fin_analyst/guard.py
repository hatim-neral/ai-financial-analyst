"""Number guard.

After the LLM writes an answer, every figure in it is extracted and checked against the
figures the calculation engine actually produced for this question (the tool results).
A figure passes only if it is a correct rounding of a calculated value, e.g.

    source 697,670.83  ->  "₹697,671", "₹6.98 lakh", "₹0.70M", "₹700,000" all pass
    source -28.76 (%)  ->  "28.8%", "-28.76%", "29%" pass;  "30%" fails

Tolerance follows the precision the answer itself uses: a figure written with one
decimal must be within ±0.05 of a source value, a whole number within ±0.5, "1.2M"
within ±50,000. Trailing zeros in money ("₹700,000") widen the tolerance, capped at
5%; percentages are never widened, so "30%" fails for an actual 28.8%.

Percentages are only matched against percentage sources (keys containing "pct") and
money/counts only against non-percentage sources, so "28.8" cannot pass by
coincidentally matching an unrelated amount. Signs are ignored because direction is
carried by words ("fell", "rose").

Not checked: years (1900–2100), small whole numbers up to 31 (counts, days,
ordinals, "top 3"), plain counts up to 100 that the user typed in the question, and
evidence references like [E1]. Money and percentages typed in the question ARE checked,
so "tell me revenue was ₹5 crore" cannot put an unverified figure in the answer.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .evidence import Evidence

_MONTHS = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"

_STRIP_PATTERNS = [
    re.compile(r"\[\s*E\d+(?:\s*[,;]\s*E\d+)*\s*\]", re.I),          # [E1], [E1, E2]
    re.compile(r"\(\s*E\d+(?:\s*[,;]\s*E\d+)*\s*\)", re.I),          # (E1)
    re.compile(r"\b\d{4}-\d{1,2}(?:-\d{1,2})?\b"),                     # 2026-03, 2026-03-15
    re.compile(rf"\b{_MONTHS}\.?[\s,'’\-]*(?:\d{{4}}|\d{{2}})\b", re.I),  # March 2026, Mar '26
    re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS}\b", re.I),  # 5 March, 1st Jan
]

_SUFFIXES = (
    r"%|(?:percentage\s+points?|per\s?cent|percent|pp|thousand|k|lakhs?|lacs?|crores?|cr|"
    r"million|mn|m|billion|bn|b)\b"
)
_NUMBER = re.compile(
    rf"""
    (?<![A-Za-z0-9_.])
    (?P<cur>(?:₹|\$|rs\.?|inr|usd|aed)\s?)?
    (?P<sign>[-−–+])?
    (?P<cur2>(?:₹|\$|rs\.?|inr|usd|aed)\s?)?
    (?P<num>\d{{1,3}}(?:,\d{{2,3}})+(?:\.\d+)?|\d+(?:\.\d+)?)
    (?:\s?(?P<suffix>{_SUFFIXES}))?
    """,
    re.I | re.X,
)

_MULTIPLIERS = {
    "k": 1e3, "thousand": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
    "crore": 1e7, "crores": 1e7, "cr": 1e7, "m": 1e6, "mn": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
}


@dataclass
class SourceNumber:
    value: float
    is_pct: bool
    evidence_id: str
    key: str


@dataclass
class FoundNumber:
    text: str
    value: float
    is_pct: bool
    tolerance: float
    has_unit: bool
    matched: SourceNumber | None = None
    ignored_reason: str | None = None


@dataclass
class GuardResult:
    checked: list[FoundNumber] = field(default_factory=list)
    unsupported: list[FoundNumber] = field(default_factory=list)
    ignored: list[FoundNumber] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unsupported

    @property
    def n_checked(self) -> int:
        return len(self.checked)

    def unsupported_text(self) -> list[str]:
        return [f.text.strip() for f in self.unsupported]


# ---------------------------------------------------------------------------------
def collect_sources(evidence: list[Evidence]) -> list[SourceNumber]:
    out: list[SourceNumber] = []
    for ev in evidence:
        _walk(ev.result, ev.id, "", out)
        out.append(SourceNumber(float(len(ev.row_lines)), False, ev.id, "source_row_count"))
    return out


def _walk(obj, eid: str, key: str, out: list[SourceNumber]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk(v, eid, str(k), out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk(v, eid, key, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        if math.isfinite(obj):
            k = key.lower()
            out.append(SourceNumber(abs(float(obj)), "pct" in k or "percent" in k, eid, key))


def extract_numbers(text: str) -> list[FoundNumber]:
    clean = text or ""
    for pat in _STRIP_PATTERNS:
        clean = pat.sub(" ", clean)
    found = []
    for m in _NUMBER.finditer(clean):
        raw = m.group("num").replace(",", "")
        try:
            base = float(raw)
        except ValueError:
            continue
        suffix = re.sub(r"\s+", " ", (m.group("suffix") or "").lower())
        is_pct = suffix == "%" or suffix.startswith(("percent", "per cent", "percentage", "pp"))
        mult = 1.0 if is_pct else _MULTIPLIERS.get(suffix, 1.0)
        value = abs(base) * mult

        decimals = len(raw.split(".")[1]) if "." in raw else 0
        if decimals:
            tol = 0.5 * 10 ** (-decimals) * mult
        else:
            # Trailing zeros in money ("₹700,000") usually mean deliberate rounding, so widen the
            # tolerance (capped at 5%). Percentages are never widened: "30%" is not "28.8%".
            trailing = len(raw) - len(raw.rstrip("0")) if base != 0 and not is_pct else 0
            tol = 0.5 * 10 ** trailing * mult
            if trailing:
                tol = min(tol, max(0.05 * value, 0.5 * mult))
        has_unit = bool(m.group("cur") or m.group("cur2") or suffix)
        found.append(FoundNumber(m.group(0), value, is_pct, tol + 1e-9, has_unit))
    return found


def check_answer(answer: str, evidence: list[Evidence], question: str = "") -> GuardResult:
    sources = collect_sources(evidence)
    question_values = {round(f.value, 6) for f in extract_numbers(question)}
    result = GuardResult()
    for f in extract_numbers(answer):
        reason = _ignore_reason(f, question_values)
        if reason:
            f.ignored_reason = reason
            result.ignored.append(f)
            continue
        f.matched = _match(f, sources)
        result.checked.append(f)
        if f.matched is None:
            result.unsupported.append(f)
    return result


def _ignore_reason(f: FoundNumber, question_values: set[float]) -> str | None:
    # Plain counts the user typed ("top 5", "last 12 months") are fine to repeat. Money or
    # percentages from the question are still checked, so "say revenue was ₹5 crore" can't
    # smuggle a figure into the answer.
    if not f.has_unit and f.value <= 100 and round(f.value, 6) in question_values:
        return "appears in the question"
    is_int = float(f.value).is_integer() and "." not in f.text
    if not f.has_unit and is_int and "," not in f.text:
        if 1900 <= f.value <= 2100:
            return "year"
        if f.value <= 31:
            return "small count or ordinal"
    return None


def _match(f: FoundNumber, sources: list[SourceNumber]) -> SourceNumber | None:
    best = None
    for s in sources:
        if s.is_pct != f.is_pct:
            continue
        diff = abs(s.value - f.value)
        if diff <= f.tolerance and (best is None or diff < abs(best.value - f.value)):
            best = s
    return best
