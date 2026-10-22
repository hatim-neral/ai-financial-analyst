"""Run the evaluation set against the real LLM and write evals/results.md + results.json.

    python -m evals.run_eval                 # all cases, provider from env/secrets
    python -m evals.run_eval --only demo-totals,margin
    python -m evals.run_eval --delay 4       # slower, for tight free-tier rate limits

API keys are read from environment variables or .streamlit/secrets.toml.
Pass criteria per case: the answer's status is allowed, every expected figure appears
(correctly rounded), every expected term appears, and no forbidden term appears.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from fin_analyst import agent, guard, llm, loader
from evals.cases import CASES

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = Path(__file__).resolve().parent

# Paid list prices in USD per 1M tokens (input, output), checked mid-2026. The free tiers
# cost nothing; these show what the same traffic would cost on a paid plan.
PRICES = {"groq": (0.59, 0.79), "gemini": (0.30, 2.50)}


def load_secrets() -> dict:
    path = ROOT / ".streamlit" / "secrets.toml"
    if path.exists():
        with path.open("rb") as f:
            return tomllib.load(f)
    return {}


def figures_present(text: str, expected: list[tuple[float, bool]]) -> list[str]:
    """Return expected figures that are missing from the answer."""
    found = guard.extract_numbers(text)
    missing = []
    for value, is_pct in expected:
        if not any(f.is_pct == is_pct and abs(f.value - abs(value)) <= f.tolerance for f in found):
            missing.append(f"{value}{'%' if is_pct else ''}")
    return missing


def evaluate(case, df, client) -> dict:
    res = agent.answer_question(case.question, df, client)
    text = res.text or ""
    reasons = []
    if res.status not in case.allowed_status:
        reasons.append(f"status {res.status} not in {sorted(case.allowed_status)}")
    if case.expect_numbers and res.status == "verified":
        missing = figures_present(text, case.expect_numbers(df))
        if missing:
            reasons.append("missing figures: " + ", ".join(missing))
    # Models often use narrow/no-break spaces ("January\u202f2026") and hyphens ("2026\u2011Q2").
    plain = re.sub(r"\s+", " ", re.sub(r"[\u2010-\u2015]", "-", text)).lower()  # and non-breaking hyphens
    for options in case.expect_any_terms:
        if not any(t.lower() in plain for t in options):
            reasons.append(f"missing term: {' / '.join(options)}")
    for t in case.forbid_terms:
        if t.lower() in plain:
            reasons.append(f"forbidden term present: {t}")
    first = res.first_draft_guard
    return {
        "id": case.id, "category": case.category, "question": case.question, "dataset": case.dataset,
        "passed": not reasons, "reasons": reasons, "status": res.status, "answer": text,
        "figures_checked": res.guard.n_checked if res.guard else 0,
        "unsupported_shown": (res.guard.unsupported_text()
                              if res.guard and res.status in ("verified", "no_figures") else []),
        "first_draft_unsupported": first.unsupported_text() if first else [],
        "retried": res.retried, "rejected_draft": res.rejected_draft,
        "tools": [f"{e.tool}({json.dumps(e.args)})" for e in res.evidence],
        "llm_calls": res.llm_calls, "latency_s": round(res.latency_s, 2),
        "prompt_tokens": res.usage["prompt_tokens"], "completion_tokens": res.usage["completion_tokens"],
        "provider": res.provider, "error": res.error,
    }


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    answered = [r for r in rows if r["status"] not in ("llm_error", "no_llm")]
    lat = sorted(r["latency_s"] for r in answered) or [0]
    pt = [r["prompt_tokens"] for r in answered] or [0]
    ct = [r["completion_tokens"] for r in answered] or [0]
    by_cat = {}
    for r in rows:
        c = by_cat.setdefault(r["category"], [0, 0])
        c[0] += r["passed"]
        c[1] += 1
    provider = (answered[0]["provider"] or "").split(" ·")[0] if answered else ""
    pin, pout = PRICES.get(provider, (0, 0))
    cost_per_q = statistics.mean(pt) / 1e6 * pin + statistics.mean(ct) / 1e6 * pout
    return {
        "cases": n,
        "passed": sum(r["passed"] for r in rows),
        "pass_rate": sum(r["passed"] for r in rows) / n if n else 0,
        "by_category": {k: f"{v[0]}/{v[1]}" for k, v in by_cat.items()},
        "verified": sum(r["status"] == "verified" for r in rows),
        "no_figures": sum(r["status"] == "no_figures" for r in rows),
        "fallback": sum(r["status"] == "fallback" for r in rows),
        "errors": sum(r["status"] == "llm_error" for r in rows),
        "first_drafts_with_unsupported_figures": sum(bool(r["first_draft_unsupported"]) for r in rows),
        "unsupported_figures_shown_to_user": sum(len(r["unsupported_shown"]) for r in rows),
        "figures_checked": sum(r["figures_checked"] for r in rows),
        "avg_latency_s": round(statistics.mean(lat), 2),
        "p95_latency_s": round(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 2),
        "avg_llm_calls": round(statistics.mean([r["llm_calls"] for r in answered] or [0]), 2),
        "avg_prompt_tokens": round(statistics.mean(pt)),
        "avg_completion_tokens": round(statistics.mean(ct)),
        "provider": provider,
        "est_cost_per_1000_questions_usd_paid_tier": round(cost_per_q * 1000, 2),
    }


def write_markdown(summary: dict, rows: list[dict], path: Path) -> None:
    s = summary
    lines = [
        "# Evaluation results",
        "",
        f"Run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · provider: {s['provider']}",
        "",
        "| Metric | Value |", "|---|---|",
        f"| Cases passed | **{s['passed']}/{s['cases']}** ({s['pass_rate']:.0%}) |",
        f"| By category | {', '.join(f'{k} {v}' for k, v in s['by_category'].items())} |",
        f"| Answers verified / no figures / fallback / error | {s['verified']} / {s['no_figures']} / {s['fallback']} / {s['errors']} |",
        f"| First drafts containing an unsupported figure (caught by the guard) | {s['first_drafts_with_unsupported_figures']} |",
        f"| Unsupported figures shown to the user | {s['unsupported_figures_shown_to_user']} |",
        f"| Figures checked by the guard | {s['figures_checked']} |",
        f"| Latency avg / p95 | {s['avg_latency_s']}s / {s['p95_latency_s']}s |",
        f"| LLM calls per question (avg) | {s['avg_llm_calls']} |",
        f"| Tokens per question (avg prompt / completion) | {s['avg_prompt_tokens']:,} / {s['avg_completion_tokens']:,} |",
        f"| Est. cost per 1,000 questions on the paid tier | ${s['est_cost_per_1000_questions_usd_paid_tier']} (free tier: $0) |",
        "",
        "| Case | Category | Status | Pass | Figures checked | First draft | Latency | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        first = "ok" if not r["first_draft_unsupported"] else "caught: " + ", ".join(r["first_draft_unsupported"])
        notes = "; ".join(r["reasons"]) or ""
        lines.append(f"| {r['id']} | {r['category']} | {r['status']} | {'✅' if r['passed'] else '❌'} | "
                     f"{r['figures_checked']} | {first} | {r['latency_s']}s | {notes} |")
    lines += ["", "## Answers", ""]
    for r in rows:
        lines += [f"### {r['id']} — {r['question']}", "",
                  f"*Status: {r['status']} · tools: {', '.join(r['tools']) or 'none'}*", "",
                  "> " + (r["answer"] or "").replace("\n", "\n> "), ""]
        if r["rejected_draft"]:
            lines += ["Rejected draft:", "", "> " + r["rejected_draft"].replace("\n", "\n> "), ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated case ids")
    parser.add_argument("--delay", type=float, default=3.0, help="seconds between questions (rate limits)")
    args = parser.parse_args()

    providers = llm.load_providers(os.environ, load_secrets())
    if not providers:
        print("No API key found. Set GROQ_API_KEY (or GEMINI_API_KEY) or add it to .streamlit/secrets.toml.")
        return 2
    client = llm.ChatClient(providers)
    print(f"Provider: {client.label}")

    cases = [c for c in CASES if not args.only or c.id in args.only.split(",")]
    frames = {}
    rows = []
    for i, case in enumerate(cases):
        if case.dataset not in frames:
            frames[case.dataset] = loader.load_csv((DATA / case.dataset).read_bytes(), case.dataset).df
        row = evaluate(case, frames[case.dataset], client)
        rows.append(row)
        mark = "PASS" if row["passed"] else "FAIL"
        print(f"[{i + 1}/{len(cases)}] {mark} {case.id}: {row['status']} {'; '.join(row['reasons'])}")
        if i < len(cases) - 1:
            time.sleep(args.delay)

    summary = summarise(rows)
    (OUT / "results.json").write_text(json.dumps({"summary": summary, "cases": rows}, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    write_markdown(summary, rows, OUT / "results.md")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {OUT / 'results.md'}")
    return 0 if summary["passed"] == summary["cases"] else 1


if __name__ == "__main__":
    sys.exit(main())
