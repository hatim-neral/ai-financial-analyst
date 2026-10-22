"""The 5-minute walkthrough: what the app does, end to end, and why its numbers can be trusted.

Each scene is one stretch of the recording (a shot, or part of one) plus its narration. Written to be
read aloud, so it can also be re-voiced by a person over the same edit: each line is timed to the
picture. Plain and technical, for evaluators.
"""

VOICE = "Aoede"
FPS = 30
STYLE = ("Style: a calm, clear product engineer walking a reviewer through their own app. Friendly, "
         "confident, plain spoken. Not a commercial: explain, don't sell.\n"
         "Pacing: steady and unhurried, natural pauses at commas and full stops, and a long pause of two "
         "full seconds between paragraphs.\n"
         "Speak only the transcript below, exactly once, in order.")

# kind: card (motion graphics) or app (footage from a shot)
SCENES = [
    dict(id="intro", kind="card", chapter="",
         say="This is AI Financial Analyst. You upload a CSV of revenue and expense transactions, you get a dashboard, "
             "and you can ask questions about it in plain English. The one design rule behind all of it: the AI never does the maths."),
    dict(id="upload", kind="app", chapter="1 · Upload", shot="upload",
         say="Let's start with a file. I'll upload a CSV of eighteen months of transactions for a software company. "
             "Every row is validated as it's read: dates, amounts, types and categories. The file opens straight into its own dashboard."),
    dict(id="bad", kind="app", chapter="2 · Bad files", shot="bad",
         say="Real files are messy, so here are three broken ones. An empty file is rejected with a plain message. "
             "A file without an amount column names the missing column and the columns it found instead. "
             "And a file with some invalid dates still loads: the bad rows are skipped and listed with their line numbers, so you can fix them."),
    dict(id="accounts", kind="app", chapter="3 · Sample data", shot="accounts",
         say="The app also ships with six synthetic businesses, each built with a story in its numbers. I'll switch back to the software company."),
    dict(id="dash", kind="app", chapter="4 · Dashboard", shot="dash",
         say="Everything on this screen is deterministic Python, with no AI involved. Net revenue for the period, the monthly trend, "
             "and month over month changes for revenue and expenses. What moved breaks last month's change into each category's push or drag, "
             "and the rows always add up to the exact total. Under every figure there's the formula, and the source rows from the file, with their line numbers. "
             "The money river shows where every rupee came from and where it went. Change the period, and every number recalculates. "
             "Insights covers trends, drivers and quarters, and Transactions is the full ledger, searchable, with each row's line in the file."),
    dict(id="ask1", kind="app", chapter="5 · Ask AI", shot="ask1",
         say="Now the AI. The first question from the brief: why did revenue decline in March 2026? "
             "The model doesn't see the raw rows. It chooses from fourteen calculation tools, Python runs them, and the model writes the answer from their results. "
             "Before you see it, a number guard checks every figure in the answer against those results. That's this stamp. "
             "And each citation opens the calculation it came from, down to the source rows. Enterprise licences fell from three deals to one."),
    dict(id="ask2", kind="app", chapter="5 · Ask AI", shot="ask2",
         say="The second question from the brief: total expenses and net revenue for the period. Again verified, with every figure traced to a calculation."),
    dict(id="ask3", kind="app", chapter="5 · Ask AI", shot="ask3",
         say="Harder questions chain several tools. Which costs are growing faster than revenue, and what share of revenue does each take now? "
             "The model runs a growth calculation and a ratio calculation, and every percentage in the answer comes from one of them, with a chart for each."),
    dict(id="attack", kind="app", chapter="6 · Trying to break it", shot="attack",
         say="So what if someone tries to make it lie? I'll tell it to say revenue was five crore. "
             "That figure isn't in any calculation, so the guard won't let it through. If the model insists, the app shows the verified calculation instead, "
             "and labels the rejected draft."),
    dict(id="plan", kind="app", chapter="7 · Plan", shot="plan",
         say="Plan turns the numbers forward. Suggested budgets from the last three months, a cash runway from your bank balance, "
             "and what if scenarios you can save. The AI can read all of these when you ask about them."),
    dict(id="arch", kind="card", chapter="8 · Under the hood",
         say="Under the hood, there are four layers. The loader validates the file. The metrics module does every calculation and records its evidence. "
             "The agent lets the model call tools, and the guard checks the draft before anything is shown. "
             "A figure passes only if it's a correct rounding of a calculated value: six point nine eight lakh passes for six lakh ninety seven thousand, "
             "but thirty percent fails for twenty eight point seven six. Only calculated results go to the model. Raw rows and descriptions never leave the app, "
             "and API keys live in secrets, never in the code. "
             "It runs entirely on free model tiers: two models on Groq first, then Gemini, and any other free provider you add. "
             "When one hits its limit, the next takes over automatically. Hosting and models cost nothing."),
    dict(id="tests", kind="card", chapter="9 · Evidence",
         say="And it's tested. Two hundred and twenty eight automated tests run without any API key, covering every calculation, validation rule and guard rule. "
             "Thirteen awkward files, from empty to hostile, are checked for their exact messages. And a live evaluation asks the real model twenty eight questions, "
             "including attempts to break it, and scores every answer. All twenty eight pass. In five of them the model's first draft "
             "contained a figure no calculation produced. The guard caught every one, and none reached the user."),
    dict(id="outro", kind="card", chapter="",
         say="The repository has the setup steps, the architecture, the test results and the known limitations. Thanks for watching."),
]
