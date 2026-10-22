# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- **Small business owners and founders** checking their own revenue, costs, margin and cash, typically weekly, and asking why a number moved before deciding what to cut or where to push.
- **Finance and accounting staff** (analysts, accountants, bookkeepers) who work in it for longer sessions: comparing periods, explaining month-on-month changes, checking budgets and exporting a report for someone else.

Both arrive with a CSV of transactions (revenue and expense rows) and want answers they can repeat to a boss, a partner or a client without re-checking the maths.

## Product Purpose
Turn a transactions CSV into a trustworthy picture of the business and answer plain-English questions about it. Success: the user gets a correct, sourced answer to "why did this change?" or "what if we did that?" in under a minute, and can show the rows behind every figure.

## Positioning
The AI never does arithmetic. It only chooses which deterministic calculation to run; Python computes every figure, and a number guard checks every figure in the answer against those results before it is shown, with the formula and source CSV lines one click away. A chatbot over a spreadsheet cannot truthfully claim this.

## Operating Context
- Data arrives as a CSV upload (one row per transaction, or a wide date/category/revenue/expenses layout); validation reports bad rows by CSV line number.
- Six bundled synthetic sample businesses ("accounts") for trying it: B2B SaaS, café chain, D2C fashion, design studio, clinics, solar installer. Each has planted, test-checked stories.
- Amounts are Indian rupees (₹); people read magnitudes in lakh and crore.
- Planning inputs typed in the app: monthly budgets per category, a cash balance for runway, saved what-if scenarios. Session-only today.
- Output leaves the app as a printable HTML report.

## Capabilities and Constraints
- Streamlit app (Python); UI is Streamlit widgets plus injected CSS and HTML, Altair charts. No custom frontend framework. Must keep working in Streamlit Community Cloud.
- Screens: Home (overview), Insights (trends, drivers, quarters, growth, month explainer), Activity (filterable transactions), Plan (budgets, runway, scenarios), Ask AI.
- 14 deterministic calculation tools; LLM providers Groq, Cerebras, Gemini, OpenRouter (free tiers, rate-limit rotation).
- Every figure traceable: Evidence panels show formula and source rows.
- Uploaded data stays in memory for the session; only calculated results go to the LLM.

## Evidence on Hand
- Synthetic sample data only (`data/sample_financials.csv`, `data/samples/*.csv`). No real customers, testimonials or usage figures exist; none may be invented.
- Live evaluation results in `evals/results.md`.

## Product Principles
1. Every number is calculated, never generated, and can be traced to its rows.
2. Answer the question first; show the evidence beside it.
3. Built for repeat use by people who handle money: precision and calm over spectacle.
4. Honest states: zeros as zeros, missing as a dash, failures said plainly.
