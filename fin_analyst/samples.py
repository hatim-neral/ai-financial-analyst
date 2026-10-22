"""The bundled synthetic datasets ("accounts" in the UI) and the questions they are built to answer.

All businesses are fictional. The stories behind each one are documented in
scripts/generate_sample_data.py and scripts/generate_business_samples.py and checked by tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


@dataclass(frozen=True)
class Sample:
    key: str
    name: str
    kind: str
    icon: str            # Material icon name
    color: str           # accent for the account card
    path: Path
    blurb: str
    questions: tuple[str, ...]

    @property
    def filename(self) -> str:
        return self.path.name


SAMPLES: tuple[Sample, ...] = (
    Sample("cloudnine", "Cloudnine Software", "B2B SaaS", "cloud", "#0A84FF", DATA / "sample_financials.csv",
           "Subscriptions, enterprise licences and a rough March 2026.",
           ("Why did revenue decline in March 2026, and was it a one-off or part of a trend?",
            "Compare the first half of 2025 with the first half of 2026: did margins improve, and which categories drove the difference?",
            "Which expense categories are growing faster than revenue, and what share of revenue does each now take?",
            "If we cut Marketing by 25% and halve Travel, but Cloud Infrastructure grows 15%, what would net revenue and margin have been?")),
    Sample("masala", "Masala Street Cafés", "Restaurant chain", "restaurant", "#FF9F0A",
           DATA / "samples" / "masala_street_cafes.csv",
           "Two outlets, monsoon slumps, festive catering and pricier delivery apps.",
           ("How does the monsoon change the mix between dine-in and delivery, and what does it do to margins?",
            "Did opening the second outlet in April 2025 pay off? Compare the six months before and after.",
            "Delivery commissions jumped in mid-2025. How much more are we paying as a share of revenue, and what if we moved 20% of delivery to dine-in?",
            "Which quarter was the most profitable, and what made October so different every year?")),
    Sample("threadline", "Threadline", "D2C fashion brand", "checkroom", "#FF375F",
           DATA / "samples" / "threadline_d2c.csv",
           "Festive peaks, stock builds, rising returns and a new wholesale account.",
           ("Why do we lose money every September even though we are growing?",
            "Returns seem to be climbing. How have refunds evolved and what share of website sales do they eat now?",
            "Compare festive season 2024 (Oct–Nov) with festive 2025: revenue, marketing spend and net revenue.",
            "If performance marketing were 15% cheaper and returns fell back by a third, what would the margin have been over the last 12 months?")),
    Sample("pixelpine", "Pixel & Pine", "Design studio", "palette", "#BF5AF2",
           DATA / "samples" / "pixel_and_pine_studio.csv",
           "Retainer-driven agency that lost its biggest client in late 2025.",
           ("What happened to retainer revenue after September 2025, and how much monthly income did we lose?",
            "Were there any unusual months? Separate genuine one-offs from structural changes.",
            "Compare Q3 2025 with Q1 2026. Is the business healthier or weaker, and why?",
            "If the current trend continues, what will net revenue look like for the next three months?")),
    Sample("greenleaf", "GreenLeaf Clinics", "Healthcare clinics", "local_hospital", "#30D158",
           DATA / "samples" / "greenleaf_clinics.csv",
           "Three winters of flu seasons, an MRI lease and lumpy insurance payouts.",
           ("Is the MRI lease that started in January 2025 paying for itself through higher diagnostics revenue?",
            "How big is the flu-season effect on consultations each winter, and is it growing year over year?",
            "Why did October 2025 look so strong? Check whether insurance timing explains it.",
            "Compare each year's July–June totals: revenue growth, cost growth and margin.")),
    Sample("sunrise", "Sunrise Solar", "Solar installer (wide format)", "solar_power", "#FFD60A",
           DATA / "samples" / "sunrise_solar.csv",
           "Seasonal installer with falling panel prices and stalled subsidies.",
           ("Which quarters lose money and why? Is it the same pattern every year?",
            "Panel prices fell in late 2024. How much did that improve the cost of goods as a share of revenue?",
            "Government subsidy receipts went quiet in mid-2025. When did they stop, when did they come back, and how much was caught up?",
            "Compare FY 2024–25 (Apr 2024–Mar 2025) with FY 2025–26: what grew, what shrank, and how did the margin move?")),
)

# Each account's own data hue (light, dark): the current period, its avatar, the traced row in the mark.
# Chosen to pass 3:1 on the card surface and to stay apart from the green/red money colours.
ACCENTS = {
    "cloudnine": ("#1d5fbf", "#6ea2ef"),   # sky blue
    "masala": ("#c2570c", "#fb923c"),      # saffron
    "threadline": ("#0f766e", "#2dd4bf"),  # teal thread
    "pixelpine": ("#8b5a2b", "#d4a373"),   # pine bark
    "greenleaf": ("#6b7a00", "#c5d86d"),   # olive leaf
    "sunrise": ("#a16207", "#fbbf24"),     # sunrise amber
}
UPLOAD_ACCENT = ("#1d5fbf", "#6ea2ef")

BY_KEY = {s.key: s for s in SAMPLES}
DEFAULT = SAMPLES[0]


def by_filename(name: str) -> Sample | None:
    return next((s for s in SAMPLES if s.filename == name), None)
