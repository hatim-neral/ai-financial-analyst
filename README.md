# AI Financial Analyst

Upload a CSV of your business's revenue and expense transactions, see your numbers on a dashboard, and ask
questions about them in plain English, such as *"Why did revenue decline in March 2026?"*. The AI answers in
seconds, and every figure it gives is checked against the data before you see it, with the calculation and
source rows one click away.

- **Live demo:** https://aifinancialanalysthatim.streamlit.app
- **Demo video (4:42):** https://drive.google.com/drive/folders/1rc5rAGixqtXcF_I5wF1t7-zUKgPrW-pn?usp=drive_link

## What it does

- **Upload a CSV** of dates, revenue, expenses and categories. Every row is checked; empty files, missing
  columns and invalid dates get a clear message, and the rows skipped are listed by line.
- **Dashboard:** net revenue and margin, month-on-month changes, what drove each month's change, where the
  money went, trends, quarters and a searchable list of every transaction.
- **Ask AI:** questions in plain English, answered with the figures, a chart and the source rows behind them.
  The AI cannot invent numbers: any figure that doesn't match a calculation is caught before it is shown.
- **Plan ahead:** suggested budgets, cash runway and what-if scenarios.
- Six sample businesses to try it without a file.

## Run it locally

```bash
git clone https://github.com/hatim-neral/ai-financial-analyst.git
cd ai-financial-analyst
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # add a free Groq key from console.groq.com/keys
streamlit run app.py
```

## Documentation

- [Technical details](docs/DETAILS.md): how answers are checked, setup, model choices, running cost, limitations
- [Architecture](docs/ARCHITECTURE.md)
- [Testing and evaluation](docs/TESTING.md): 229 automated tests, 28/28 live evaluation questions
- [Demo walkthrough script](docs/DEMO_SCRIPT.md)
