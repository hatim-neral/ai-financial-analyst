"""Generate five more synthetic sample businesses into data/samples/.

Each business is fictional, seeded (every run writes identical files) and has a few
stories planted on purpose, so harder questions have known, checkable answers.
tests/test_business_samples.py asserts every story listed here.

  masala_street_cafes.csv   restaurant chain, Jan 2024 – Dec 2025
    * every Jul–Aug (monsoon) dine-in falls ~20% while delivery rises ~20%
    * every October festive catering spikes (~4x a normal month)
    * Apr 2025 a second outlet opens: rent and staff wages step up, dine-in ramps up
    * Jul 2025 delivery apps raise their commission from 22% to 28% of delivery sales
    * Jan 2025 a one-off gas price shock pushes utilities up ~70%
  threadline_d2c.csv        D2C fashion brand, Jul 2024 – Jun 2026
    * Oct–Nov festive season: sales roughly double, performance marketing spikes
    * Aug–Sep inventory is bought ahead of the festive season, so Sep is loss-making
    * returns & refunds climb from ~9% to ~15% of website sales from Feb 2026
    * a wholesale account starts in Mar 2026 with quarterly orders (Mar, Jun)
  pixel_and_pine_studio.csv design agency, Jan 2025 – Jun 2026
    * the biggest retainer client leaves after Sep 2025: retainers drop ~40% from Oct 2025
    * from Oct 2025 the studio loses money every month except Feb 2026
    * Feb 2026 a one-off brand project of ₹28 lakh, with freelancer costs to match
    * Jan 2026 laptop refresh: equipment ₹6 lakh
  greenleaf_clinics.csv     clinic group, Jul 2023 – Jun 2026 (36 months, three winters)
    * Dec–Feb flu season: consultations ~+25%
    * Jan 2025 an MRI machine lease starts (₹4.2 lakh/month); diagnostics revenue ramps up after it
    * insurance claims pay out quarterly (Mar, Jun, Sep, Dec); the Sep 2025 payout slipped to Oct 2025
    * consultations grow ~12% a year
  sunrise_solar.csv         rooftop solar installer, Apr 2024 – Mar 2026 (Indian FY), WIDE format
    * Mar–May pre-monsoon peak, Jul–Sep monsoon slump (both Jul–Sep quarters are loss-making)
    * panel and inverter prices fall ~18% from Oct 2024, lifting margins
    * big commercial projects in Feb 2025 and Dec 2025
    * government subsidy receipts stall Jun–Dec 2025, then catch up in Jan 2026

Usage:  python scripts/generate_business_samples.py
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "samples"
LONG_HEADER = ["date", "type", "category", "amount", "description"]


def _months(start: str, n: int) -> list[str]:
    y, m = int(start[:4]), int(start[5:])
    out = []
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


class Book:
    """Collects long-format rows with a seeded RNG for days and jitter."""

    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.rows: list[dict] = []

    def jitter(self, x: float, pct: float = 0.04) -> float:
        return x * self.rng.uniform(1 - pct, 1 + pct)

    def add(self, month: str, typ: str, category: str, amount: float, description: str, day: int | None = None):
        d = day or self.rng.randint(1, 28)
        self.rows.append({"date": f"{month}-{d:02d}", "type": typ, "category": category,
                          "amount": f"{amount:.2f}", "description": description})

    def split(self, month, typ, category, total, parts, label):
        weights = [1 + self.rng.uniform(-0.3, 0.3) for _ in range(parts)]
        s = sum(weights)
        amounts = [round(total * w / s, 2) for w in weights]
        amounts[-1] = round(total - sum(amounts[:-1]), 2)
        for i, a in enumerate(amounts):
            self.add(month, typ, category, a, f"{label} {i + 1}")

    def sorted_rows(self) -> list[dict]:
        return sorted(self.rows, key=lambda r: (r["date"], r["type"], r["category"], r["description"]))


# ---------------------------------------------------------------------------------
def masala_street_cafes() -> list[dict]:
    b = Book(101)
    for i, month in enumerate(_months("2024-01", 24)):
        mon = int(month[5:])
        two_outlets = month >= "2025-04"
        ramp = {"2025-04": 0.45, "2025-05": 0.65, "2025-06": 0.85}.get(month, 1.0) if two_outlets else 0.0
        size = 1 + 0.75 * ramp
        growth = 1.006 ** i
        monsoon = mon in (7, 8)

        dine_in = 1_450_000 * size * growth * (0.80 if monsoon else 1.0)
        delivery = 620_000 * (1 + 0.6 * ramp) * growth * (1.20 if monsoon else 1.0)
        catering = 140_000 * growth * (4.0 if mon == 10 else 1.0)
        b.split(month, "revenue", "Dine-in", b.jitter(dine_in), 8, "POS settlement week")
        b.split(month, "revenue", "Delivery apps", b.jitter(delivery), 4, "Delivery app payout")
        b.split(month, "revenue", "Catering", b.jitter(catering, 0.08), 3 if mon == 10 else 2,
                "Festive catering order" if mon == 10 else "Catering order")
        b.add(month, "revenue", "Merchandise", b.jitter(38_000, 0.15), "Sauces and spice-box sales")

        food_rev = dine_in + delivery + catering
        b.split(month, "expense", "Ingredients", b.jitter(food_rev * 0.31), 6, "Wholesale market purchase")
        b.add(month, "expense", "Staff wages", 520_000 * (1.45 if two_outlets else 1.0) * 1.004 ** i, "Payroll - kitchen and floor", 30 if mon != 2 else 28)
        b.add(month, "expense", "Rent", 260_000 * (1.6 if two_outlets else 1.0), "Outlet leases", 1)
        rate = 0.28 if month >= "2025-07" else 0.22
        b.add(month, "expense", "Delivery commissions", round(delivery * rate, 2), f"Platform commission at {int(rate * 100)}%", 5)
        utilities = 95_000 * (1.3 if two_outlets else 1.0) * (1.7 if month == "2025-01" else 1.0)
        b.add(month, "expense", "Utilities", b.jitter(utilities), "Gas, power and water")
        b.split(month, "expense", "Marketing", b.jitter(70_000 * (1.8 if mon == 10 else 1.0), 0.1), 2, "Social media campaign")
        repair = 320_000 if month == "2024-06" else b.jitter(22_000, 0.3)
        b.add(month, "expense", "Equipment & repairs", repair, "Walk-in freezer replacement" if month == "2024-06" else "Kitchen maintenance")
    return b.sorted_rows()


def threadline_d2c() -> list[dict]:
    b = Book(202)
    for i, month in enumerate(_months("2024-07", 24)):
        mon = int(month[5:])
        festive = mon in (10, 11)
        eoss = mon in (1, 7)  # end-of-season sale
        growth = 1.012 ** i
        web = 2_100_000 * growth * (2.1 if festive else 1.25 if eoss else 1.0)
        market = 1_200_000 * growth * (1.9 if festive else 1.2 if eoss else 1.0)
        b.split(month, "revenue", "Website sales", b.jitter(web), 10, "Shopify payout")
        b.split(month, "revenue", "Marketplace sales", b.jitter(market), 4, "Marketplace settlement")
        if month >= "2026-03" and mon in (3, 6):
            b.add(month, "revenue", "Wholesale", 1_350_000 if mon == 3 else 1_520_000, "Wholesale order - Kora Retail")

        inventory = (web + market) * 0.36
        if mon in (8, 9):
            inventory = 2_000_000 * growth * 2.0  # pre-festive stock build
        elif festive:
            inventory *= 0.45
        b.split(month, "expense", "Inventory purchases", b.jitter(inventory), 4, "Fabric and production run")
        b.split(month, "expense", "Performance marketing", b.jitter(480_000 * growth * (2.6 if festive else 1.3 if eoss else 1.0)), 3, "Meta and Google ads")
        b.add(month, "expense", "Shipping & logistics", round((web + market) * 0.075, 2), "Courier invoice")
        returns_rate = 0.15 if month >= "2026-02" else 0.09
        b.add(month, "expense", "Returns & refunds", round(web * returns_rate, 2), "Customer refunds")
        b.add(month, "expense", "Payment gateway fees", round(web * 0.021, 2), "Gateway fees")
        b.add(month, "expense", "Marketplace commissions", round(market * 0.18, 2), "Marketplace commission")
        b.add(month, "expense", "Warehouse", 185_000 * (1.15 if month >= "2025-04" else 1.0), "3PL warehouse fee", 3)
        b.add(month, "expense", "Salaries", 640_000 * 1.01 ** i, "Payroll", 28)
    return b.sorted_rows()


def pixel_and_pine_studio() -> list[dict]:
    b = Book(303)
    for i, month in enumerate(_months("2025-01", 18)):
        lost_client = month >= "2025-10"
        retainers = [("Northwind Foods", 420_000), ("Bluebird Bank", 260_000), ("Kite Mobility", 180_000),
                     ("Tandoor Co", 140_000)]
        for client, fee in retainers:
            if lost_client and client == "Northwind Foods":
                continue
            b.add(month, "revenue", "Retainers", fee * 1.003 ** i, f"Monthly retainer - {client}", 5)
        projects = b.jitter(380_000, 0.35)
        b.split(month, "revenue", "Projects", projects, b.rng.randint(1, 3), "Project milestone")
        if month == "2026-02":
            b.add(month, "revenue", "Projects", 2_800_000, "Brand identity project - Saffron Air", 20)
        b.add(month, "revenue", "Licensing", 45_000 * 1.03 ** i, "Font and template licensing", 15)

        b.add(month, "expense", "Salaries", 720_000 * (1.06 if month >= "2026-01" else 1.0), "Payroll", 28)
        freelancers = projects * 0.4 + (1_150_000 if month == "2026-02" else 0)
        b.split(month, "expense", "Freelancers", b.jitter(freelancers + 60_000), 3, "Freelancer invoice")
        b.add(month, "expense", "Software", 68_000 * 1.01 ** i, "Design software seats", 2)
        b.add(month, "expense", "Office", 150_000, "Studio rent and upkeep", 1)
        b.split(month, "expense", "Travel", b.jitter(42_000, 0.4), 2, "Client visit")
        b.add(month, "expense", "Equipment", 600_000 if month == "2026-01" else b.jitter(9_000, 0.5),
              "Laptop refresh for the team" if month == "2026-01" else "Accessories")
    return b.sorted_rows()


def greenleaf_clinics() -> list[dict]:
    b = Book(404)
    months = _months("2023-07", 36)
    for i, month in enumerate(months):
        mon = int(month[5:])
        flu = mon in (12, 1, 2)
        yearly = 1.12 ** (i / 12)
        mri = month >= "2025-01"
        mri_ramp = min(1.0, (months.index(month) - months.index("2025-01") + 1) / 6) if mri else 0.0

        consult = 1_900_000 * yearly * (1.25 if flu else 1.0)
        diagnostics = 820_000 * yearly * (1 + 0.6 * mri_ramp)
        b.split(month, "revenue", "Consultations", b.jitter(consult), 6, "OPD collections week")
        b.split(month, "revenue", "Diagnostics", b.jitter(diagnostics), 4, "Lab and imaging collections")
        b.split(month, "revenue", "Pharmacy", b.jitter(640_000 * yearly * (1.15 if flu else 1.0)), 4, "Pharmacy sales")
        payout_months = {3, 6, 9, 12}
        pays = mon in payout_months and month != "2025-09"
        if pays or month == "2025-10":
            quarter_value = 2_400_000 * yearly
            b.add(month, "revenue", "Insurance claims", quarter_value,
                  "Delayed Q3 insurance settlement" if month == "2025-10" else "Quarterly insurance settlement", 25)

        b.add(month, "expense", "Doctor fees", round(consult * 0.42, 2), "Visiting doctor payouts", 7)
        b.add(month, "expense", "Nursing staff", 560_000 * 1.006 ** i, "Payroll - nursing", 28)
        b.split(month, "expense", "Medical supplies", b.jitter((consult + diagnostics) * 0.11), 3, "Supplies order")
        b.add(month, "expense", "Rent", 380_000 * (1.07 if month >= "2025-04" else 1.0), "Clinic premises", 1)
        b.add(month, "expense", "Equipment lease", 120_000 + (420_000 if mri else 0),
              "Equipment leases incl. MRI" if mri else "Equipment leases", 3)
        b.add(month, "expense", "Utilities", b.jitter(110_000 * (1.2 if mon in (4, 5, 6) else 1.0)), "Power and water")
        b.add(month, "expense", "Marketing", b.jitter(55_000, 0.2), "Local outreach")
    return b.sorted_rows()


def sunrise_solar_wide() -> list[list[str]]:
    """Wide format: one row per category per month, month-end dates, revenue OR expenses filled."""
    rng = random.Random(505)
    rows = []
    for i, month in enumerate(_months("2024-04", 24)):
        mon = int(month[5:])
        season = 1.45 if mon in (3, 4, 5) else 0.55 if mon in (7, 8, 9) else 1.0
        y, m = int(month[:4]), mon
        last_day = [31, 29 if y % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
        date = f"{month}-{last_day:02d}"

        def j(x, p=0.05):
            return round(x * rng.uniform(1 - p, 1 + p), 2)

        residential = j(2_600_000 * season * 1.01 ** i)
        commercial = j(900_000 * season) + (3_800_000 if month in ("2025-02", "2025-12") else 0)
        maintenance = j(180_000 * 1.02 ** i, 0.02)
        stalled = "2025-06" <= month <= "2025-12"
        subsidy = 0.0 if stalled else j(420_000 * season)
        if month == "2026-01":
            subsidy = 2_950_000.0  # catch-up of the stalled receipts
        panel_cost = 0.82 if month >= "2024-10" else 1.0
        installs = residential + commercial
        revenue = [("Residential installs", residential), ("Commercial projects", commercial),
                   ("Maintenance contracts", maintenance), ("Government subsidy receipts", subsidy)]
        expenses = [("Panels & inverters", round(installs * 0.52 * panel_cost, 2)),
                    ("Installation crew", round(installs * 0.11, 2)),
                    ("Vehicles & fuel", j(140_000 * (0.8 + 0.2 * season))),
                    ("Permits & compliance", j(60_000)),
                    ("Salaries", round(820_000 * 1.008 ** i, 2)),
                    ("Marketing", j(150_000 * (1.4 if mon in (2, 3) else 1.0)))]
        for cat, v in revenue:
            if v:
                rows.append([date, cat, f"{v:.2f}", ""])
        for cat, v in expenses:
            rows.append([date, cat, "", f"{v:.2f}"])
    return rows


GENERATORS = {
    "masala_street_cafes.csv": masala_street_cafes,
    "threadline_d2c.csv": threadline_d2c,
    "pixel_and_pine_studio.csv": pixel_and_pine_studio,
    "greenleaf_clinics.csv": greenleaf_clinics,
}


def write_all() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, gen in GENERATORS.items():
        rows = gen()
        with (OUT / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=LONG_HEADER)
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote {len(rows):,} rows to {OUT / name}")
    rows = sunrise_solar_wide()
    with (OUT / "sunrise_solar.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "category", "revenue", "expenses"])
        w.writerows(rows)
    print(f"Wrote {len(rows):,} rows to {OUT / 'sunrise_solar.csv'} (wide format)")


if __name__ == "__main__":
    write_all()
