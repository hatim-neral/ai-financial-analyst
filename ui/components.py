"""Small building blocks shared by the pages. HTML is always built from escaped text."""

from __future__ import annotations

import html
import re

import pandas as pd
import streamlit as st

from fin_analyst import formatting as fmt
from fin_analyst.evidence import Evidence


def safe_md(text: str) -> str:
    """Markdown from the LLM or the uploaded file: drop images (no remote loads) and
    escape '$' so Streamlit doesn't render it as LaTeX."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text or "")
    return text.replace("$", "\\$")


def esc(x) -> str:
    return html.escape(str(x))


def title(h1: str, sub: str | None = None, avatar: str | None = None) -> None:
    """The screen's h1 and its one grey line (the finding, the period or the scope); an account
    screen leads with the account's avatar in its own hue."""
    head = f'<h1>{esc(h1)}</h1>'
    if avatar:
        head = f'<div class="title-row"><div class="avatar" aria-hidden="true">{esc(avatar[:1].upper())}</div>{head}</div>'
    st.html(f'<div class="title">{head}' + (f"<p>{sub}</p>" if sub else "") + "</div>")


def countup(value: float, cls: str = "answer-value", words: bool = True) -> str:
    """A big money figure that counts up when it appears (static under reduced motion or without JS),
    with its lakh/crore reading beside it."""
    shown = fmt.money(value)
    reading = fmt.money_words(value) if words and abs(value) >= 1e5 else ""
    return (f'<div class="{cls}"><span data-countup="{value:.0f}">{shown}</span>'
            + (f'<span class="words">≈ {esc(reading)}</span>' if reading else "") + "</div>")


_COUNTUP_JS = """
<script>
(function () {
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  function run() {
    document.querySelectorAll('[data-countup]:not([data-counted])').forEach(function (el) {
      el.setAttribute('data-counted', '1');
      var target = parseFloat(el.getAttribute('data-countup')); if (!isFinite(target)) return;
      var final = el.textContent, t0 = null, dur = 700;
      function frame(t) {
        if (t0 === null) t0 = t;
        var p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3), v = Math.round(target * e);
        el.textContent = p < 1 ? (v < 0 ? '-' : '') + '\u20b9' + Math.abs(v).toLocaleString('en-US') : final;
        if (p < 1) requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    });
  }
  run(); setTimeout(run, 150); setTimeout(run, 600);
})();
</script>
"""


def countup_script() -> None:
    """Animate any figures rendered this run (a fixed script; it reads numbers, never text from users)."""
    st.html(_COUNTUP_JS, unsafe_allow_javascript=True)


def card_head(name: str, meta: str | None = None, sub: str | None = None) -> None:
    """A card's title with its period right-aligned in grey, and an optional grey line under it."""
    st.html(f'<div class="card-head"><div class="card-title">{esc(name)}</div>'
            + (f'<div class="card-meta">{esc(meta)}</div>' if meta else "") + "</div>"
            + (f'<div class="card-sub">{sub}</div>' if sub else ""))


def section(name: str) -> None:
    st.html(f'<div class="section-title">{esc(name)}</div>')


def signed_class(value: float, good_when_up: bool) -> str:
    """Colour says good or bad, not up or down; zero is grey."""
    if not value:
        return "dash"
    return "pos" if (value > 0) == good_when_up else "neg"


def show_evidence(ev: Evidence, df: pd.DataFrame, label: str | None = None, show_table: bool = False) -> None:
    lines = len(ev.row_lines)
    with st.expander(label or f"Formula and source rows · {lines:,} CSV line{'s' if lines != 1 else ''}"):
        st.markdown(f"**Calculation:** {safe_md(ev.formula)}")
        if show_table and ev.table is not None:
            st.dataframe(ev.table, hide_index=True)
        src = df[df["line"].isin(ev.row_lines)]
        view = src.assign(date=src["date"].dt.strftime("%Y-%m-%d"))[
            ["line", "date", "type", "category", "amount", "description"]
        ].rename(columns={"line": "CSV line"})
        if len(view) > 1000:
            st.caption("Showing the first 1,000 rows.")
            view = view.head(1000)
        ledger_table(view, height=min(36 + 35 * len(view), 420))


def badge(text: str, warn: bool = False, fresh: bool = False) -> None:
    """The audit stamp on an AI answer; it thumps down once when the answer is new."""
    st.html(f'<div class="stamp{" warn" if warn else ""}{" fresh" if fresh else ""}"><i></i>{esc(text)}</div>')


def tx_rows(rows: pd.DataFrame) -> str:
    """Two-line ledger rows: category over description, signed amount over date."""
    items = []
    for _, r in rows.iterrows():
        income = r["type"] == "revenue"
        amount = f'+{fmt.money(r["amount"])}' if income else f'−{fmt.money(r["amount"])}'
        items.append(
            f'<div class="row"><div><div class="row-name">{esc(r["category"])}</div>'
            f'<div class="row-sub">{esc(r["description"] or "")}</div></div>'
            f'<div class="row-fig"><span class="{"pos" if income else ""}">{amount}</span>'
            f'<small>{r["date"].strftime("%-d %b %Y")}</small></div></div>')
    return f'<div class="rows">{"".join(items)}</div>'


def money_styler(view: pd.DataFrame):
    """Income green with a plus sign, spending in ink (the sign lives in the text, not the colour)."""
    from .theme import T

    if "type" not in view.columns:
        return view
    signs = view["type"].map({"revenue": "+", "expense": "−"}).fillna("")
    shown = view.assign(amount=[f"{s}₹{a:,.2f}" for s, a in zip(signs, view["amount"])])

    def row_css(row: pd.Series) -> list[str]:
        css = f"color: {T['positive']}" if row["type"] == "revenue" else ""
        return [css if c == "amount" else "" for c in row.index]

    return shown.style.apply(row_css, axis=1).set_properties(subset=["amount"], **{"text-align": "right"})


LEDGER_COLUMNS = {
    "CSV line": st.column_config.NumberColumn("CSV line", format="%d", width="small"),
    "date": st.column_config.TextColumn("Date", width="small"),
    "type": st.column_config.TextColumn("Type", width="small"),
    "category": st.column_config.TextColumn("Category"),
    "amount": st.column_config.TextColumn("Amount", alignment="right"),
    "description": st.column_config.TextColumn("Description", width="large"),
}


def ledger_table(view: pd.DataFrame, height: int | str = "auto") -> None:
    """Transactions as a ledger: signed amounts right-aligned, income in green, no duplicate month column."""
    view = view.drop(columns=[c for c in ("month",) if c in view.columns])
    st.dataframe(money_styler(view), hide_index=True, column_config=LEDGER_COLUMNS, height=height)


def odometer(value: float) -> str:
    """A big money figure whose digits roll into place (pure CSS; the final value is what stays).
    Screen readers get the plain amount; the rolling strips are hidden from them."""
    text = fmt.money(value)
    parts, n_digit = [], 0
    for ch in text:
        if ch.isdigit():
            strip = "".join(f'<span data-n="{d % 10}"></span>' for d in range(20))  # digits drawn by CSS
            parts.append(f'<span class="odo" aria-hidden="true"><span class="odo-strip" '
                         f'style="--d:{10 + int(ch)};animation-delay:{40 * n_digit}ms">{strip}</span></span>')
            n_digit += 1
        else:
            parts.append(f'<span class="odo-sep" aria-hidden="true">{esc(ch)}</span>')
    return f'<div class="odo-figure" role="img" aria-label="{esc(text)}">{"".join(parts)}</div>'


def bridge(start_label: str, start: float, steps: list[tuple[str, str, float]], end_label: str, end: float) -> str:
    """Last month -> each category's signed effect (bars from a centre line, in turn) -> this month.
    `steps` are (name, kind, effect on net); they must sum to end - start (the caller guarantees it)."""
    biggest = max((abs(v) for _, _, v in steps), default=0) or 1
    rows = [f'<div class="bridge-total"><span>{esc(start_label)}</span><span>{fmt.money(start)}</span></div>']
    for i, (name, kind, v) in enumerate(steps):
        width = 50 * abs(v) / biggest
        cls = "up" if v >= 0 else "down"
        tone = "pos" if v > 0 else "neg" if v < 0 else "dash"
        rows.append(f'<div class="bridge-step"><div class="name">{esc(name)}<span class="kind">{esc(kind)}</span></div>'
                    f'<div class="fig {tone}">{fmt.signed_money(v)}</div>'
                    f'<div class="bar"><i class="{cls}" style="width:{width:.1f}%;animation-delay:{150 + 110 * i}ms"></i></div></div>')
    rows.append(f'<div class="bridge-total end"><span>{esc(end_label)}</span><span>{fmt.money(end)}</span></div>')
    return f'<div class="bridge">{"".join(rows)}</div>'
