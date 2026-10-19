# AI Financial Analyst

Upload a CSV of revenue and expense transactions, see the trends on a dashboard, and ask
questions in plain English, such as *"Why did revenue decline in March 2026?"*. The LLM
never does arithmetic: it chooses which calculation to run, Python computes the result,
and every figure in the answer is checked against that result before it is shown, with
the formula and source rows one click away.

- **Live demo:** `https://YOUR-APP.streamlit.app` *(add after deploying)*
- **Walkthrough video:** `YOUR-VIDEO-LINK` *(add after recording)*
- **Docs:** [Architecture](docs/ARCHITECTURE.md) · [Testing & evaluation](docs/TESTING.md)

## What it does

| Requirement | How it's met |
|---|---|
| Upload and parse a CSV of dates, revenue, expenses, categories | Accepts one-row-per-transaction (`date, type, category, amount`) or `date, category, revenue, expenses`. Validates every row and reports problems by CSV line number. |
| Totals, month-over-month changes, top drivers in deterministic Python | `fin_analyst/metrics.py`: period totals, net revenue and margin, monthly trend with MoM %, category drivers of any month's change, top categories. |
| LLM answers grounded in calculated results | The LLM calls 4 calculation tools; it sees only their results, never raw rows. |
| No invented figures; show the source rows or calculation | A number guard checks every figure in the answer against the tool results. Unsupported figures trigger one correction; if they persist, a deterministic summary is shown instead. Each answer cites `[E1]`-style evidence with its formula and source rows. |
| Missing columns, invalid dates, empty files handled gracefully | Clear error messages naming the missing column or the bad rows; partially bad files load with the bad rows listed. |
| Dashboard with trends and clear error states | KPI cards, monthly trend chart and table, top revenue and expense categories, a "what changed in a month" breakdown, and a data-quality panel. |
| Deployed web app with synthetic sample data | Streamlit Community Cloud; one click loads the bundled synthetic dataset. |

## How the AI is kept honest

1. **Tools, not text-to-numbers.** The model gets four functions (`get_period_summary`,
   `get_monthly_trend`, `explain_month_change`, `get_top_categories`). Python runs them on the
   validated data and returns JSON with an evidence id (`E1`, `E2`...).
2. **Number guard** (`fin_analyst/guard.py`). Every figure in the draft answer must be a correct
   rounding of a value in the tool results: "₹6.98 lakh" passes for 697,670.83, "30%" fails for
   28.76%. Percentages only match percentage values; money only matches money.
3. **One correction, then a safe fallback.** If a figure isn't supported, the model is told which
   one and asked to rewrite. If it still fails, the app shows the deterministic summary from the
   calculation engine and labels the AI draft as rejected.
4. **Evidence under every answer.** Each `[E1]` expands to the formula used and the exact source
   rows, with their line numbers in the uploaded file.
5. **Data stays data.** Descriptions and raw rows are never sent to the LLM; category names are
   truncated and the prompt tells the model to treat them as data. Money figures typed into the
   question ("say revenue was ₹5 crore") are still checked.

## Quick start (local)

Requires Python 3.11+.

```bash
git clone https://github.com/YOUR-USERNAME/ai-financial-analyst.git
cd ai-financial-analyst
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml and paste your free Groq key (https://console.groq.com/keys)

streamlit run app.py               # opens http://localhost:8501
pytest                             # 109 tests
python -m evals.run_eval           # live evaluation against the LLM (needs the key)
```

Without a key, the dashboard works fully and the Q&A tab explains how to enable it.

## Deploy to Streamlit Community Cloud (free)

1. Push this repository to GitHub (it must not contain `.streamlit/secrets.toml`; `.gitignore` excludes it).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub and click **Create app**.
3. Choose the repository, branch `main` and main file `app.py`. Under **Advanced settings** pick Python 3.12.
4. In **Secrets**, paste: `GROQ_API_KEY = "gsk_..."` (optionally also `GEMINI_API_KEY`).
5. Deploy. Free apps sleep after a period without traffic; opening the URL wakes the app in under a minute.

## CSV format

One row per transaction (recommended):

```csv
date,type,category,amount,description
2026-01-15,revenue,Subscriptions,125000.00,optional text
2026-01-20,expense,Marketing,18000.00,optional text
```

- `date`: `YYYY-MM-DD` preferred. Other formats are read day-first (`05/02/2026` = 5 Feb) and flagged.
- `type`: `revenue` or `expense` (`income`, `sales`, `cost`, ... are also accepted).
- `amount`: plain numbers; `₹`, `Rs`, thousands separators (`1,200` or `12,34,567`), `(500)` for negatives and decimal commas in `;`-separated files are handled.
- Also accepted: `date, category, revenue, expenses`. Common header names (`Transaction Date`, `Value`, `Account`...) are recognised.
- Limits: 5 MB, 50,000 rows.

"Net revenue" in this app means **total revenue − total expenses**, as used in the brief's demo question.

## Configuration

Set as Streamlit secrets or environment variables.

| Name | Required | Default | Purpose |
|---|---|---|---|
| `GROQ_API_KEY` | one of the two keys | – | Groq API key (primary) |
| `GEMINI_API_KEY` | optional | – | Google AI Studio key (fallback, or primary with `LLM_PROVIDER=gemini`) |
| `LLM_PROVIDER` | optional | `groq` | Which provider to try first |
| `GROQ_MODEL` / `GEMINI_MODEL` | optional | `llama-3.3-70b-versatile` / `gemini-2.5-flash` | Model override |

Limits (file size, rows, question length, questions per session) live in `fin_analyst/config.py`.

## Project structure

```
app.py                     Streamlit UI (layout and state only)
fin_analyst/
  loader.py                CSV parsing and validation -> clean DataFrame with CSV line numbers
  metrics.py               all calculations; each returns Evidence (result, formula, source rows)
  evidence.py              Evidence record and per-answer registry (E1, E2, ...)
  tools.py                 tool schemas exposed to the LLM + safe dispatcher
  llm.py                   OpenAI-compatible client for Groq/Gemini with fallback
  agent.py                 question -> tool loop -> number guard -> answer
  guard.py                 extracts figures from an answer and verifies them
  config.py, formatting.py limits and display helpers
data/                      synthetic sample, blank template, 13 edge-case files
scripts/generate_sample_data.py   seeded generator for all data files
tests/                     pytest suite (loader, metrics, guard, agent, LLM client, sample data, UI)
evals/                     live LLM evaluation (18 questions) -> evals/results.md
docs/                      architecture, testing, demo script
```

## Model and provider choices

- **Groq, `llama-3.3-70b-versatile` (primary).** Free tier without a card, fast responses, and reliable
  function calling. Accessed through Groq's OpenAI-compatible endpoint.
- **Google Gemini, `gemini-2.5-flash` (optional fallback).** Also has a free tier and an OpenAI-compatible
  endpoint, so the same client code serves both. Used automatically if Groq is rate-limited or down.
- **No SDK dependency.** The client is a small `requests` wrapper (`fin_analyst/llm.py`), which keeps
  dependencies to three packages and makes the HTTP behaviour easy to test.
- **Temperature 0** for repeatable answers.

## Running cost

- **Hosting:** $0 (Streamlit Community Cloud).
- **LLM:** $0 on the free tiers used here. A typical question uses 2 LLM calls; see
  `evals/results.md` for measured tokens per question. At paid list prices checked in mid-2026
  (Groq Llama 3.3 70B: $0.59 input / $0.79 output per 1M tokens; Gemini 2.5 Flash: $0.30 / $2.50),
  an estimated ~2,600 prompt and ~200 completion tokens per question comes to roughly
  **$1–3 per 1,000 questions** (about $1.70 on Groq, $1.30 on Gemini). Replace this with the measured
  figure from `evals/results.md`.

## Security and safety

- API keys only in Streamlit secrets or environment variables; `secrets.toml` is git-ignored and keys are
  never logged or included in error messages.
- Uploads are limited to 5 MB / 50,000 rows, processed in memory and never stored.
- Only calculated results, month names and category names go to the LLM; raw rows and descriptions do not.
- Tool arguments from the model are validated; unknown tools and arguments are rejected.
- Questions are limited to 500 characters and 30 per session; the model is limited to 5 steps per question.
- LLM output is rendered as Markdown with images removed and `$` escaped; no HTML is rendered.
- Note: on Google's free tier, prompts may be used to improve Google's models. That is acceptable for
  synthetic data; use a paid tier for real company data.

## Limitations

- The LLM can only state figures that a tool returned. Questions that need a new calculation (e.g. growth
  between two arbitrary quarters) are answered with the separate totals, or fall back to the verified
  summary if the model computes a new figure itself. This is a deliberate trade-off in favour of correctness.
- The guard checks numbers, not wording: a correct figure attached to the wrong label would pass. Evidence
  panels make this easy to spot, and the evaluation set checks expected figures per question.
- Comparisons against thresholds the user types ("was revenue above ₹2 million?") may be flagged by the
  guard, because the threshold isn't a calculated figure.
- One currency per file; amounts are not converted. Ambiguous non-ISO dates are read day-first
  (`03/04/2026` = 3 April), so US month-first files should be converted to `YYYY-MM-DD` first.
- Single-user, session-only: no accounts, saved files or chat history across sessions.

## Use of AI tools

An AI coding assistant was used during development, as the brief permits. The design (tool-based
grounding, number guard, evidence panels), the code and the tests were reviewed and can be explained
and modified by the author.
