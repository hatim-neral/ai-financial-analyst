# Design

Recorded from the shipped build (October 2026). Source of truth for tokens: `ui/theme.py` and
`.streamlit/config.toml`. Direction: design-taste-frontend app style **Achromatic ledger**
(seed 971377457), strict app-screen rules, light first. Notes: `.taste-skill/app/notes.md`.

## The world
A ledger, not a dashboard kit. Ink chrome on a blue-grey ledger ground, white cards with a 1px
border, no shadows at rest, no gradients, glows or glass. Colour goes on data only: one chart hue
on each screen's main data element, the negative colour on what hurts, green with a plus sign on
money in.

**Playful ledger** (impeccable `delight`, October 2026): the ledger comes alive at the moments that
matter, the way an accountant's desk would. Each account has its own data hue (`fin_analyst/samples.py`
ACCENTS: Cloudnine blue, Masala saffron, Threadline teal, Pixel & Pine bark, GreenLeaf olive, Sunrise
amber; uploads blue), used on the current period, the account avatar, the lakh/crore reading, the
active nav icon and the mark's traced row. Big money figures count up (700ms) and carry their Indian
reading ("≈ ₹93.7 lakh"); charts wipe in; "What moved" rows slide in from the side their sign points
(the focal moment: it shows how the change was built); budget tracks and ranking bars fill; a verified
AI answer gets a rubber stamp that thumps down once; real wins only (best month of the period, every
budget on track, a saved scenario that lifts the margin) get one confetti burst per session, starting
below the title row. Sound and haptics are off until the viewer turns them on. Everything is dropped
under prefers-reduced-motion.

**Big colour and the money river** (impeccable `overdrive`, October 2026). Home's one loud moment:
- *The colour field.* The Net revenue card is filled with the account's hue, shaded to 85% so white
  text passes contrast (`theme.field()`). On it, the figure is an odometer (each digit rolls into place,
  40ms apart; digits are drawn by CSS and the value is in the aria-label), and the monthly columns are
  white for the current month and translucent white for the others. It is the only filled card in the
  app; the inspector's colour-sprawl warning on Home is this decision.
- *The bridge.* "What moved" is a bridge from last month's net to this month's: each of the five
  biggest moves, then "All other categories", grows from a centre line (gains right in green, drags
  left in red, 110ms apart), so the bars always land exactly on the total shown.
- *The money river* (`ui/river.py`). It runs full width under the hero: revenue sources on the left,
  the business in the middle, costs and profit on the right. Ribbon widths are the real amounts, and
  both sides always balance (a loss adds a red "Shortfall" source). Dots stream along the ribbons, more
  on the bigger ones; hovering a ribbon shows its amount and share. On a phone, the ribbons carry
  amounts only and a two-column legend underneath names them. The dots stop while the tab is hidden
  and never start under reduced motion.

## Tokens (light / dark)
| Role | Light | Dark |
|---|---|---|
| Ground | #f2f4f7 (blue-grey ledger) | #000000 |
| Surface (cards) | #ffffff | #111111 |
| Active (nav pill, segmented track) | #e6e9ee | #222222 |
| Border / row rule / control | #e3e6eb / #eef0f3 / #d0d4da | #262626 / #1c1c1c / #444444 |
| Text / muted / faint | #0a0a0a / #5f646d / #6b7079 | #ffffff / #b4b4b4 / #949494 |
| Primary action | #141414 fill, white label | #f2f2f2 fill, near-black label |
| Chart hue (main data element) | #1d5fbf | #6ea2ef |
| Context series | #9aa0a8 grey, #141414 ink | #6b6b6b, #f2f2f2 |
| Positive / negative / warning | #2e7d32 / #c4242a / #92400e | #3fc07a / #e5566f / #f0b45a |

Radius 8 (cards), 6 (controls), 4 (pills). One gap value: 16px. Card padding 20px. Canvas max
1184px, sidebar 256px, gutters 32px desktop / 20px phone.

## Type
Geist only (Geist Mono is reserved for real code, e.g. CSV column names in the upload help).
h1 24/700; card title 16/500; answer figure 32/700 (28 on a phone); KPI strip 22/500; body 14;
meta 12-13. Tabular figures on every number; sentence case; no tracked capitals.

## Components
- **Shell:** open plane. Product mark (three ledger rows, the last in the chart hue: a traced row),
  account switcher as the scope, nav as grey-pill rows, Data utilities and AI status at the bottom.
  Phone: Streamlit's sidebar folds; a flat bottom tab bar of five destinations.
- **Title row:** a noun h1 (the account name on Overview) with one grey line carrying the finding;
  the period segmented control and the one primary action on the right.
- **KPIs:** the answer figure in its card, then one strip split by 1px rules (2-up on a phone).
  Deltas name their baseline ("vs May 2026") and are coloured by good or bad, not up or down.
- **Ledger rows:** 44px rows on 1px rules; name over a 12px grey subline; figures right-aligned.
  Ranked money lists carry a 2px proportional bar, the top one in ink.
- **Charts:** one series, straight 2px lines or columns with a 2px top radius, 4 faint gridlines,
  no y-axis line, lakh/crore ticks, no legend for one series. Projections are dashed.
- **Evidence:** every block ends in a "Formula and source rows" disclosure (the signature element,
  with the "What moved" bridge, whose steps always land on the total shown).
- **Tables:** ledger columns, signed amounts right-aligned, income green.
- **Plan:** settings rows: label column (title, description, current values, inputs) beside the panel.
- **States:** empty blocks keep their frame with a dashed one-sentence box; zeros print as zeros.

## Do not
Gradients, glows, glass, coloured nav fills, tinted KPI tiles (the Net revenue field is the one filled card), sparklines, donuts, rainbow charts,
violet, emoji, a second display face; confetti for anything but a real win; motion that delays or
hides content; sound before the viewer opts in.
