"""The customer video: 5 minutes, cinematic, for business owners. What the product does, never how it's built.

Every requirement of the brief is shown working (upload, bad files, totals, month-on-month changes,
drivers, trends, AI answers, their sources, no invented figures), in customer language. One voice:
Gemini "Despina", directed to a British accent. The app footage is the verified walkthrough recording.
"""

VOICE = "Despina"
FPS = 30
STYLE = ("Style: a female narrator with a natural British English accent (southern English, Received Pronunciation), "
         "warm, confident and intimate, like the voice of a premium product film. Never American. "
         "Keep exactly the same voice and accent from the first paragraph to the last.\n"
         "Pacing: unhurried; a little drama in the first paragraph, then clear and friendly. "
         "Pause for two full seconds between paragraphs.\n"
         "Speak only the transcript below, exactly once, in order.")

# kind: card (made here) or app (the recorded app). chapter: the small label at the top.
SCENES = [
    dict(id="hook", kind="card", chapter="",
         say="You know your sales went up. So why didn't your profit? The answer is already in your numbers, hidden in hundreds of rows. "
             "Most owners never have the time to read them. So what if you could simply ask?"),
    dict(id="meet", kind="app", chapter="",
         say="Meet AI Financial Analyst: your own financial analyst, on call whenever you need one. "
             "Drop in a spreadsheet of your transactions: dates, revenue, expenses and categories. "
             "In a second, it reads every row, checks it, and opens your business as its own dashboard. "
             "No setup, no formulas, and nothing to learn. And if you'd like to build your own file, there's a blank template to start from."),
    dict(id="messy", kind="app", chapter="",
         say="Real files are messy, so it tells you exactly what's wrong. An empty file? It says so. "
             "A missing amount column? It names the column, and shows what it found instead. "
             "Dates in a different format are read and flagged for you. A few bad dates? Your file still opens, and the rows it skipped are listed by line, so you can fix them in a minute. "
             "No guessing, no broken formulas. Fix it, upload again, and you're straight back in."),
    dict(id="samples", kind="app", chapter="",
         say="No file to hand? Start with one of six sample businesses, from a software company to a chain of cafés, "
             "each with its own story hidden in the numbers, and questions ready to try. Here, we'll look at the software company."),
    dict(id="glance", kind="app", chapter="",
         say="Here's your business at a glance. Net revenue for the period, with your margin and the number of transactions behind it. "
             "Every month side by side, and how revenue and expenses moved since last month. "
             "What moved shows exactly which categories pushed this month up or dragged it down, and it always adds up to the real change. "
             "Open the details under any figure, and you'll see exactly how it was worked out, down to the rows in your file. "
             "The money river follows every rupee, from where it came in to where it went: the wider the ribbon, the more money. "
             "Hover over any chart for the exact figure. Change the period, and everything updates. "
             "See your trends and biggest movers in Insights: compare quarters, and spot which costs are growing fastest. "
             "And search every transaction in one place."),
    dict(id="ask", kind="app", chapter="",
         say="Now, just ask, about any month, any category, or any period. Why did revenue decline in March? Your AI analyst reads the question, works through your numbers, "
             "and answers in plain English, in seconds. No formulas, and no waiting for a report. Revenue fell twenty-nine percent, almost entirely because enterprise licences "
             "dropped from three deals to one. And you're never asked to take its word for it. Every answer shows exactly where it "
             "came from: the calculation, and the very rows in your file. It even suggests what to ask next, so you can keep digging."),
    dict(id="more", kind="app", chapter="",
         say="Ask for the big picture: total expenses and net revenue for the whole period, in one line. Or ask something complex: "
             "which costs are growing faster than revenue, and how much of your revenue each one takes now. "
             "It works through every step for you, and shows a chart for each. And because it remembers the conversation, "
             "you can simply follow up, the way you would with a colleague."),
    dict(id="honest", kind="app", chapter="",
         say="And it won't tell you what you want to hear. Ask it to say revenue was five crore, and it simply gives you the real figure. "
             "Every number it says is checked against your own data before you see it. If a draft ever slips, it's sent back to be corrected, "
             "and if it still isn't right, you're shown the checked figures instead. Nothing invented ever reaches you."),
    dict(id="plan", kind="app", chapter="",
         say="Then look ahead. Press suggest, and it sets a monthly budget for every cost from your last three months, "
             "and shows which ones you're already over. Change any budget, and it updates instantly. Enter what's in the bank, and it tells you how long your cash will last. "
             "And save what-if plans, to compare your next move before you make it. Every plan is worked out from your own numbers, "
             "and your AI analyst can read all of it when you ask."),
    dict(id="close", kind="card", chapter="",
         say="Your data stays in your session, and every answer stays grounded in it. Upload your file, ask your first question, and see your business clearly. "
             "AI Financial Analyst. Your numbers, finally explained."),
]

# A short cinematic title card, carried by the music, opens each chapter
TITLES: dict = {}   # no title cards: the film runs straight through
TITLE_S = 3.0
