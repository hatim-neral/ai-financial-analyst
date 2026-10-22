# AI Financial Analyst

Upload a CSV of revenue and expense transactions, see the trends on a dashboard, and ask
questions in plain English, such as *"Why did revenue decline in March 2026?"*. The LLM
never does arithmetic: it chooses which calculation to run, Python computes the result,
and every figure in the answer is checked against that result before it is shown, with
the formula and source rows one click away.

- **Live demo:** https://aifinancialanalysthatim.streamlit.app (free hosting sleeps when idle; opening the link wakes it in under a minute)
- **Walkthrough video (4:42):** https://drive.google.com/drive/folders/1rc5rAGixqtXcF_I5wF1t7-zUKgPrW-pn?usp=drive_link · [script](docs/DEMO_SCRIPT.md)
- **Docs:** [Architecture](docs/ARCHITECTURE.md) · [Testing & evaluation](docs/TESTING.md)

## What it does

| Requirement | How it's met |
|---|---|
| Upload and parse a CSV of dates, revenue, expenses, categories | Accepts one-row-per-transaction (`date, type, category, amount`) or `date, category, revenue, expenses`. Validates every row and reports problems by CSV line number. |
| Totals, month-over-month changes, top drivers in deterministic Python | `fin_analyst/metrics.py`: period totals, net revenue and margin, monthly trend with MoM %, category drivers of any month's change, top categories. |
| LLM answers grounded in calculated results | The LLM calls 14 calculation tools (totals, trends, comparisons, growth, anomalies, ratios, what-ifs, projections, budgets, runway); it sees only their results, never raw rows. Answers show live progress, a chart per calculation and suggested follow-ups. |
| No invented figures; show the source rows or calculation | A number guard checks every figure in the answer against the tool results. Unsupported figures trigger one correction; if they persist, a deterministic summary is shown instead. Each answer cites `[E1]`-style evidence with its formula and source rows. |
| Missing columns, invalid dates, empty files handled gracefully | Clear error messages naming the missing column or the bad rows; partially bad files load with the bad rows listed. |
| Dashboard with trends and clear error states | A calm ledger-style app, light first with dark mode (see DESIGN.md): Overview (net revenue, a "What moved last month" breakdown that sums to its total, where the money goes, recent transactions, items that need a look), Insights (trend, drivers, quarters, growth, month explainer), Transactions (filterable ledger), Plan (budgets, cash runway, saved what-if scenarios) and Ask AI, plus a data-quality panel and a printable HTML report. |
| Deployed web app with synthetic sample data | Streamlit Community Cloud; six bundled synthetic businesses ("accounts") switch with one click. |

## How the AI is kept honest

1. **Tools, not text-to-numbers.** The model gets fourteen functions: `get_period_summary`,
   `get_monthly_trend`, `explain_month_change`, `get_top_categories`, `compare_periods`,
   `category_growth`, `category_trend`, `find_anomalies`, `period_breakdown`, `expense_ratios`,
   `what_if`, `project_trend`, and two that read what the user typed on the Plan page:
   `get_budget_status` and `get_cash_runway` (the prompt says which inputs exist, never their values). Python runs them on the validated data and returns JSON with an
   evidence id (`E1`, `E2`...). Complex questions chain several tools; even ratios, scenarios and
   projections are computed in Python, never by the model.
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
git clone https://github.com/hatim-neral/ai-financial-analyst.git
cd ai-financial-analyst
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml and paste your free Groq key (https://console.groq.com/keys)

streamlit run app.py               # opens http://localhost:8501
pytest                             # 229 tests, no API key needed
python -m evals.run_eval           # live evaluation against the LLM (needs the key)
```

Without a key, the dashboard, Insights, Transactions and Plan pages work fully; the Ask AI page explains how to add one.

## Deploy to Streamlit Community Cloud (free)

1. Push this repository to GitHub (it must not contain `.streamlit/secrets.toml`; `.gitignore` excludes it).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub and click **Create app**.
3. Choose the repository, branch `main` and main file `app.py`. Under **Advanced settings** pick Python 3.12.
4. In **Secrets**, paste: `GROQ_API_KEY = "gsk_..."` (optionally also `CEREBRAS_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`).
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
| `ANTHROPIC_API_KEY` | optional (paid) | – | Claude API key from platform.claude.com (pay-as-you-go credit, not a claude.ai subscription). When set, `claude-opus-5-5` answers first and the free providers are the backup |
| `GROQ_API_KEY` | at least one key | – | Groq (free) |
| `CEREBRAS_API_KEY` | optional | – | Cerebras (free, same gpt-oss-120b model, ~1M tokens/day) |
| `MISTRAL_API_KEY` | optional | – | Mistral (free Experiment plan), `mistral-small-latest` |
| `GEMINI_API_KEY` | optional | – | Google AI Studio (free; quota is per model per day, so two models are used) |
| `NVIDIA_API_KEY` | optional | – | NVIDIA NIM (free), `moonshotai/kimi-k2.6` |
| `HF_TOKEN` | optional | – | Hugging Face Inference Providers (free monthly credits), `openai/gpt-oss-120b` |
| `OPENROUTER_API_KEY` | optional | – | OpenRouter free models (about 50 requests/day) |
| `LLM_PROVIDER` | optional | table order | Which provider to try first |
| `*_MODEL` (e.g. `GEMINI_MODEL`) | optional | see `llm.py` | Model override; a comma-separated list adds one entry per model |

Every configured provider and model is used in order. When one is rate limited it is put on cooldown
for as long as it asked (seconds or hours) and the next one answers immediately; busy or slow servers
are skipped for 30 seconds. The app only waits when all are cooling down. If nothing can answer, users
see one plain message ("The AI analyst is busy right now. Please try again in a minute or two.") and
the technical reasons go to the server log.

Limits (file size, rows, question length, questions per session) live in `fin_analyst/config.py`.

## Project structure

```
app.py                     Streamlit entry: state, sidebar (nav + accounts), routing
ui/                        ledger UI: theme.py (light/dark tokens and CSS), charts.py, answer_charts.py (chart per tool result),
                           components.py, pages.py, plan.py (budgets/runway/scenarios), followups.py,
                           report.py (printable HTML report)
PRODUCT.md, DESIGN.md      product brief and the shipped design system
fin_analyst/
  loader.py                CSV parsing and validation -> clean DataFrame with CSV line numbers
  metrics.py               all calculations; each returns Evidence (result, formula, source rows)
  evidence.py              Evidence record and per-answer registry (E1, E2, ...)
  tools.py                 tool schemas exposed to the LLM + safe dispatcher
  llm.py                   provider rotation, cooldowns and an OpenAI-compatible client for the free providers
  claude_provider.py       optional Claude (Anthropic SDK) adapter
  agent.py                 question -> tool loop -> number guard -> answer
  guard.py                 extracts figures from an answer and verifies them
  samples.py               the six bundled accounts and the questions each is built to answer
  config.py, formatting.py limits and display helpers
data/                      synthetic sample, blank template, 13 edge-case files
data/samples/              five more synthetic businesses (cafés, D2C fashion, studio, clinics, solar)
scripts/generate_sample_data.py      seeded generator for the original sample and edge cases
scripts/generate_business_samples.py seeded generator for data/samples/ (stories documented inside)
tests/                     pytest suite (loader, metrics, guard, agent, LLM client, sample data, UI)
evals/                     live LLM evaluation (28 questions, incl. 10 multi-step) -> evals/results.md
docs/                      architecture, testing, demo script
demo/                      scripts that build the demo videos from the running app (not needed to run the app)
```

## Model and provider choices

The app needs one free key to answer questions; more keys only add backups. Providers are tried in this
order, and a rate-limited or busy one is skipped automatically:

| Order | Provider and model | Cost | Why |
|---|---|---|---|
| 1 | **Claude Opus 5.5** (`claude-opus-5-5`), Anthropic API, *optional* | paid per token | The strongest model for multi-step tool use. Only used when `ANTHROPIC_API_KEY` is set; the app does not need it |
| 2 | **Groq**, `openai/gpt-oss-120b`, then `openai/gpt-oss-20b` | free tier | **The default.** Fast, reliable function calling, no card needed. Groq's free limits are per model, so the second model doubles the daily allowance on the same key. The measured results in `evals/` use `gpt-oss-120b` |
| 3 | Cerebras, `gpt-oss-120b` | free tier | Same model on different hardware, so answers stay consistent when Groq is rate limited |
| 4 | Mistral, `mistral-small-latest` | free tier | Another independent free quota |
| 5 | Google Gemini, `gemini-3.5-flash-lite`, `gemini-3.5-flash` | free tier | Two models, because Google's free quota is per model per day |
| 6–8 | NVIDIA NIM (Kimi K2.6), Hugging Face (gpt-oss-120b), OpenRouter (free models) | free tiers | Last-resort backups |

- **Two clients, one interface.** Providers 2–8 share an OpenAI-compatible endpoint, served by a small
  `requests` client (`fin_analyst/llm.py`). Claude uses the official `anthropic` SDK
  (`fin_analyst/claude_provider.py`), which translates at the boundary so the agent, tools and guard
  are provider-neutral. Dependencies stay at four packages: `streamlit`, `pandas`, `requests`, `anthropic`.
- **Temperature 0** on the free providers for repeatable answers. Claude Opus 5.5 does not accept sampling
  parameters, so none are sent; its reasoning effort is set to `medium`.
- **Why not one provider?** Free tiers have daily caps (Groq: 200K tokens a day on this model; Gemini:
  about 20 requests per model per day). Rotation keeps the demo answering during a busy session.

## Running cost

- **Hosting:** $0 (Streamlit Community Cloud).
- **LLM, as deployed:** $0. Only free tiers are used unless you add a Claude key.
- **Measured** (`evals/results.md`, Groq `gpt-oss-120b`): about 6,664 prompt and 269 completion tokens
  and 2.14 LLM calls per question (28 questions). At Groq's paid list price that is about **$4.14 per 1,000 questions**.
- **With Claude Opus 5.5:** billed at Anthropic's per-token price for the same token counts (thinking tokens
  count as output). It is not measured here because no Claude key was used during development (see Status).

## Security and safety

- API keys only in Streamlit secrets or environment variables; `secrets.toml` is git-ignored and keys are
  never logged or included in error messages.
- Uploads are limited to 5 MB / 50,000 rows, processed in memory and never stored.
- Only calculated results, month names and category names go to the LLM; raw rows and descriptions do not.
- Tool arguments from the model are validated; unknown tools and arguments are rejected.
- Questions are limited to 500 characters and 30 per session; the model is limited to 6 LLM round trips per question and 6 tool calls per round trip.
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

## Status: what is and isn't verified

| Part | Status |
|---|---|
| CSV upload, validation, all calculations, dashboard, Plan page | Done; covered by automated tests |
| AI answers with the number guard (Groq) | Done; 229 automated tests, and the live evaluation passes 28/28 (`evals/results.md`) |
| Gemini fallback | Done; used live during development |
| **Claude provider** | **Implemented but not run against the live API.** It is unit-tested with a fake SDK; no Anthropic key was used during development. Optional |
| Cerebras, Mistral, NVIDIA, Hugging Face, OpenRouter backups | **Configured and unit-tested, not run live** (no keys during development). Optional |
| Accounts, saved data, multi-user | Not built: single-user and session-only by design (see Limitations) |

## Use of AI tools

An AI coding assistant was used during development, as the brief permits. The design (tool-based
grounding, number guard, evidence panels), the code and the tests were reviewed and can be explained
and modified by the author.
