"""The demo's single source of truth: scenes in order, their narration and on-screen labels.

narration.py turns each line into speech (macOS `say`, voice Samantha) and measures it; record.py
captures the app for each "app" scene; compose.html animates every frame from timeline.json;
build.py renders and encodes demo.mp4. Edit the words here and rerun build.py.
"""

ENGINE = "gemini"   # "gemini": Google's Gemini TTS (needs GEMINI_API_KEY); "say": macOS voices, offline
VOICE = "Aoede"     # a Gemini prebuilt voice (with ENGINE = "say", a macOS voice such as "Samantha")
RATE = 182          # words per minute, `say` only
TEMPO = 1.0         # Gemini voice only: >1 speeds it up without changing pitch (1.08 lands near 90 s)
PAD_S = 0.55        # breath after each line
FPS = 30

# kind: "card" (pure motion graphics) or "app" (captured app footage, framed)
SCENES = [
    dict(id="intro", kind="card", chapter="",
         say="Meet AI Financial Analyst. Ask your business's books anything, in plain English."),
    dict(id="load", kind="app", chapter="Overview",
         say="Upload a CSV of your transactions, or start with one of six sample businesses."),
    dict(id="hero", kind="app", chapter="Overview",
         say="The overview opens on what matters most: net revenue for the period, in rupees, and in lakh and crore, "
             "with every month beside it."),
    dict(id="bridge", kind="app", chapter="What moved",
         say="What moved shows how this month was built: each category's push or drag, adding up to the exact change."),
    dict(id="river", kind="app", chapter="Money river",
         say="The money river follows every rupee, from where it came in to where it went. "
             "Wider ribbons mean more money. Hover over any ribbon for its amount."),
    dict(id="evidence", kind="app", chapter="Evidence",
         say="And nothing is a black box. Every figure shows its formula, and the exact rows it came from."),
    dict(id="switch", kind="app", chapter="Accounts",
         say="Switch businesses, and the whole app takes on their colour."),
    dict(id="period", kind="app", chapter="Periods",
         say="Change the period, and every number recalculates."),
    dict(id="insights", kind="app", chapter="Insights",
         say="Insights spots trends, rising costs, and your best and worst quarters."),
    dict(id="ledger", kind="app", chapter="Transactions",
         say="The ledger has every transaction, ready to search."),
    dict(id="askcard", kind="card", chapter="",
         say="Then, just ask."),
    dict(id="ask", kind="app", chapter="Ask AI",
         say="The AI picks the right tools, Python does the maths, and every number is checked against your data "
             "before you see it. You get a chart, a verified stamp, and follow-up questions."),
    dict(id="plan", kind="app", chapter="Plan",
         say="Plan ahead with budgets, cash runway, and what-if scenarios. "
             "Try a five percent lift in revenue, and see the margin change instantly."),
    dict(id="anywhere", kind="app", chapter="Anywhere",
         say="Export a report to share, and work in light or dark, whichever suits you."),
    dict(id="outro", kind="card", chapter="",
         say="AI Financial Analyst. Your numbers, explained."),
]

QUESTION = "What drove the change in net revenue in December 2025, and which costs are growing faster than revenue?"
