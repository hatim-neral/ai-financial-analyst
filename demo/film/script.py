"""The film: a short story about one owner and one leak in her numbers.

Every figure the narration says comes from the Masala Street Cafés sample, checked with the app's own
metrics (see facts.py): revenue up 95% (first three months vs last three), ₹1.58 crore net over the
two years, 674 transactions, delivery commissions up 131% and, since July 2025, the delivery apps
keeping about ₹28 of every ₹100 of delivery sales, up from about ₹22. "Priya" is a fictional owner.

Scenes are grouped into acts; the music follows the acts and every scene starts on a beat.
"""

VOICE = "Aoede"
BPM = 96
FPS = 30

STYLE = ("Style: a warm, intimate storyteller narrating a short film about a small business owner. "
         "Human and sincere, never salesy, with real feeling behind the words.\n"
         "Pacing: quiet and reflective at the start, a little slower, as if it were late at night. "
         "From the paragraph that starts 'Six hundred and seventy-four' the energy lifts: brighter, "
         "more confident, with a sense of discovery. The last two paragraphs are calm and satisfied.\n"
         "Pause for two full seconds between paragraphs.\n"
         "Speak only the transcript below, exactly once, in order.")

# own_take: voiced in its own small request (a line added after the main take was approved)
# act: night (piano, reflective) / build (riser) / day (the pulse) / morning (resolve)
SCENES = [
    dict(id="night", act="night", say="Eleven at night. The last table's gone home."),
    dict(id="chai", act="night", say="Priya runs two cafés. In two years, her sales have nearly doubled."),
    dict(id="rows", act="night", say="But one question keeps her up. Where is all that money actually going?"),
    dict(id="ask_books", act="build", say="Six hundred and seventy-four transactions. So she asks her books."),
    dict(id="reveal", act="day", say="One point five eight crore in net revenue, and every rupee traced, from where it came in, to where it went."),
    dict(id="leak", act="day", say="And there it is. Delivery commissions, up a hundred and thirty-one percent. "
                                  "The apps now keep twenty-eight rupees of every hundred they sell."),
    dict(id="question", act="day", say="So she asks: what if a fifth of those orders came in to dine?"),
    dict(id="answer", act="day", say="The AI picks the calculations, Python does the maths, and every number is checked before she sees it."),
    dict(id="plan", act="day", say="She saves the plan, and sees her margin before the month even starts."),
    dict(id="morning", act="morning", say="Tomorrow, she opens with a plan."),
    dict(id="yours", act="morning", own_take=True,
         say="This was Priya's story. Upload your own numbers, and see yours."),
    dict(id="logo", act="morning", say="AI Financial Analyst. Your numbers, explained."),
]

QUESTION = ("Delivery commissions jumped in mid-2025. How much more are we paying as a share of revenue, "
            "and what if we moved 20% of delivery to dine-in?")
