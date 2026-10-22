"""Achromatic ledger: ink chrome on a blue-grey ledger ground, one chart hue on the main data element.

Colours must match .streamlit/config.toml. The palette follows the theme Streamlit is using
(system setting, or the choice in Settings); `T` always reads the active palette, so charts and
HTML pick the right colours on every run.

Rules this file keeps (design-taste-frontend app screens, impeccable craft floor): no gradients,
glows, glass or shadows at rest; colour only on data, on status and on the one primary action;
one typeface; tabular figures.

Playful ledger (impeccable delight): each account brings its own data hue (`set_accent`), and the
moments that matter move: totals count up, charts draw in, "What moved" rows slide in from the side
their sign points to, budget tracks fill, verified answers get a rubber stamp, real wins get
confetti. Every animation is dropped under prefers-reduced-motion.

All CSS is injected as one <style> block; it must not contain anything that looks like an HTML
tag (Streamlit's sanitiser would cut the block there), which `inject()` checks.
"""

from __future__ import annotations

import random
import re

import streamlit as st

LIGHT = {
    "ground": "#f2f4f7", "surface": "#ffffff", "raised": "#f7f8fa", "active": "#e6e9ee",
    "border": "#e3e6eb", "rule": "#eef0f3", "control": "#d0d4da",
    "text": "#0a0a0a", "muted": "#5f646d", "faint": "#6b7079",
    "primary": "#141414", "on_primary": "#ffffff",
    "hue": "#1d5fbf", "hue_soft": "#e8effa",
    "ink": "#141414", "grey": "#9aa0a8",
    "positive": "#2e7d32", "negative": "#c4242a", "warning": "#92400e",
    "pos_bg": "#dcfae5", "pos_ink": "#04250e", "neg_bg": "#ffedea", "neg_ink": "#831c1e",
    "warn_bg": "#fffbeb", "warn_ink": "#92400e", "neutral_bg": "#eeeeee", "neutral_ink": "#3d3d3d",
    "grid": "#e5e7eb", "selection": "#d6e4f8",
}
DARK = {
    "ground": "#000000", "surface": "#111111", "raised": "#171717", "active": "#222222",
    "border": "#262626", "rule": "#1c1c1c", "control": "#444444",
    "text": "#ffffff", "muted": "#b4b4b4", "faint": "#949494",
    "primary": "#f2f2f2", "on_primary": "#0a0a0a",
    "hue": "#6ea2ef", "hue_soft": "#16233a",
    "ink": "#f2f2f2", "grey": "#6b6b6b",
    "positive": "#3fc07a", "negative": "#e5566f", "warning": "#f0b45a",
    "pos_bg": "#172a1d", "pos_ink": "#3fc07a", "neg_bg": "#2c1a20", "neg_ink": "#e5566f",
    "warn_bg": "#2a2213", "warn_ink": "#f0b45a", "neutral_bg": "#222222", "neutral_ink": "#d0d0d0",
    "grid": "#2b2b2b", "selection": "#1f3557",
}
FONT = "Geist"


def is_dark() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:  # outside a Streamlit run (tests, scripts)
        return False


def shade(hex_color: str, factor: float = 0.85) -> str:
    """A deeper version of a colour (for a field that carries white text)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(c * factor))) for c in (r, g, b)))


def field() -> str:
    """The account's colour field: always its deep (light-theme) hue, shaded so white text reads."""
    try:
        accent = st.session_state.get("_accent")
    except Exception:
        accent = None
    return shade((accent or (LIGHT["hue"],))[0])


def set_accent(light: str, dark: str) -> None:
    """The current account's data hue (the current period, its avatar, the mark's traced row)."""
    st.session_state["_accent"] = (light, dark)


def palette() -> dict:
    base = dict(DARK if is_dark() else LIGHT)
    base["field"] = field()
    try:
        accent = st.session_state.get("_accent")
    except Exception:  # outside a Streamlit run
        accent = None
    if accent:
        base["hue"] = accent[1] if is_dark() else accent[0]
    return base


class _Tokens:
    """Dict-like view of the active palette (with the account's hue)."""

    def __getitem__(self, key: str) -> str:
        return palette()[key]


T = _Tokens()


def rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, {alpha})"


def _css(T: dict) -> str:
    T = {"field": shade(LIGHT["hue"]), **T}
    return f"""
<style>
  body {{ -webkit-font-smoothing: antialiased; }}
  ::selection {{ background: {T['selection']}; color: {T['text']}; }}
  * {{ scrollbar-color: {T['control']} transparent; scrollbar-width: thin; }}
  :focus-visible {{ outline: 2px solid {T['hue']}; outline-offset: 2px; }}
  [data-testid="stAppViewContainer"] {{ background: {T['ground']}; }}
  /* Streamlit's toolbar scrolls away with the page instead of covering the title */
  [data-testid="stHeader"] {{ position: absolute; background: transparent; }}
  [data-testid="stMainBlockContainer"] {{ padding: 3.75rem 2rem 4rem; max-width: 1184px; }}
  .num, [data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; }}

  /* ---------- Sidebar: open plane on the ground ---------- */
  [data-testid="stSidebar"] {{ background: {T['ground']}; border-right: 1px solid {T['border']}; }}
  [data-testid="stSidebar"][aria-expanded="true"] {{ min-width: 256px; max-width: 256px; }}
  .brand {{ display: flex; align-items: center; gap: 10px; margin: 0 0 14px 8px; }}
  .brand-mark {{ display: grid; gap: 3px; width: 18px; }}
  .brand-mark i {{ display: block; height: 3px; border-radius: 1px; background: {T['ink']}; }}
  .brand-mark i:nth-child(2) {{ width: 70%; }}
  .brand-mark i:nth-child(3) {{ width: 85%; background: {T['hue']}; }}
  .brand-name {{ font-weight: 600; font-size: 15px; color: {T['text']}; line-height: 20px; }}
  .rail-label {{ font-size: 12px; color: {T['muted']}; margin: 22px 0 6px 8px; }}
  .st-key-nav [data-testid="stVerticalBlock"] {{ gap: 2px; }}
  .st-key-nav button {{
    justify-content: flex-start !important; width: 100%; min-height: 32px; padding: 0 10px;
    border: 0 !important; border-radius: 6px; background: transparent; color: {T['muted']}; box-shadow: none;
  }}
  .st-key-nav button > div {{ justify-content: flex-start !important; width: 100%; }}
  .st-key-nav button p {{ font-size: 14px; }}
  .st-key-nav button:hover {{ background: {T['active']}; color: {T['text']}; }}
  .st-key-nav [data-testid="stBaseButton-secondary"] {{ background: {T['active']}; color: {T['text']}; }}
  .ai-status {{ display: flex; align-items: center; gap: 8px; font-size: 12px; color: {T['muted']}; margin: 14px 8px 2px; }}
  .ai-status i {{ width: 7px; height: 7px; border-radius: 50%; background: {T['positive']}; flex: none; }}
  .ai-status.off i {{ background: {T['faint']}; }}

  /* ---------- Title row ---------- */
  .title h1 {{ font-size: 24px; font-weight: 700; letter-spacing: -0.01em; line-height: 32px; margin: 0; padding: 0;
               color: {T['text']}; }}
  .title p {{ margin: 4px 0 0; color: {T['muted']}; font-size: 14px; line-height: 20px; max-width: 80ch; }}
  .title p b {{ color: {T['text']}; font-weight: 500; }}

  /* ---------- Cards: white on the ground, 1px border, no shadow ---------- */
  [class*="st-key-card"] {{
    background: {T['surface']}; border: 1px solid {T['border']}; border-radius: 8px; padding: 20px; gap: 12px;
  }}
  /* Cards that share a row share a bottom edge */
  [class*="st-key-row_eq"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]
    > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] {{ height: 100%; }}
  [class*="st-key-row_eq"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]
    > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] > [class*="st-key-card"] {{ height: 100%; }}
  .card-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }}
  .card-title {{ font-size: 16px; font-weight: 500; color: {T['text']}; margin: 0; line-height: 24px; }}
  .card-meta {{ font-size: 12px; color: {T['muted']}; white-space: nowrap; }}
  .card-sub {{ font-size: 13px; color: {T['muted']}; margin: 2px 0 0; line-height: 18px; }}
  .section-title {{ font-size: 16px; font-weight: 500; margin: 24px 0 4px; color: {T['text']}; }}

  /* ---------- Figures ---------- */
  .answer-label {{ font-size: 14px; color: {T['muted']}; }}
  .answer-value {{ font-size: 32px; font-weight: 700; letter-spacing: -0.02em; line-height: 40px; color: {T['text']};
                   font-variant-numeric: tabular-nums; margin-top: 2px; }}
  .answer-delta {{ font-size: 14px; color: {T['muted']}; font-variant-numeric: tabular-nums; }}
  .pos {{ color: {T['positive']}; }} .neg {{ color: {T['negative']}; }} .warn {{ color: {T['warning']}; }}
  .dash {{ color: {T['faint']}; }}
  [data-testid="stMetricLabel"] p {{ font-size: 13px; color: {T['muted']}; }}
  [data-testid="stMetricValue"] {{ font-size: 22px; font-weight: 500; letter-spacing: -0.01em; color: {T['text']}; }}
  [data-testid="stMetricValue"] > div {{ overflow: visible; text-overflow: clip; }}
  [data-testid="stMetricDelta"] {{ background: transparent !important; padding: 0 !important; font-size: 12px; }}
  [class*="st-key-strip"] {{ border-top: 1px solid {T['rule']}; padding-top: 14px; }}
  [class*="st-key-strip"] [data-testid="stColumn"] + [data-testid="stColumn"] {{ border-left: 1px solid {T['rule']}; padding-left: 16px; }}

  /* ---------- Rows: ledger lists ---------- */
  .rows {{ display: flex; flex-direction: column; }}
  .row {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: center; min-height: 44px;
          padding: 6px 0; border-top: 1px solid {T['rule']}; }}
  .row:first-child {{ border-top: 0; }}
  .row-name {{ font-size: 14px; color: {T['text']}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .row-sub {{ font-size: 12px; color: {T['muted']}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 1px; }}
  .row-fig {{ text-align: right; font-size: 14px; font-variant-numeric: tabular-nums; color: {T['text']}; white-space: nowrap; }}
  .row-fig small {{ display: block; font-size: 12px; color: {T['muted']}; margin-top: 1px; }}
  .row-bar {{ height: 2px; margin-top: 6px; background: {T['rule']}; }}
  .row-bar i {{ display: block; height: 2px; background: {T['grey']}; }}
  .row:first-child .row-bar i {{ background: {T['ink']}; }}
  .pill {{ display: inline-block; flex: none; white-space: nowrap; padding: 0 7px; border-radius: 4px; font-size: 12px;
           font-weight: 500; line-height: 20px; margin-left: 6px; vertical-align: 1px; }}
  .pill.neg {{ background: {T['neg_bg']}; color: {T['neg_ink']}; }}
  .pill.pos {{ background: {T['pos_bg']}; color: {T['pos_ink']}; }}
  .pill.warn {{ background: {T['warn_bg']}; color: {T['warn_ink']}; }}
  .pill.neutral {{ background: {T['neutral_bg']}; color: {T['neutral_ink']}; }}
  .track {{ height: 6px; border-radius: 3px; background: {T['rule']}; margin-top: 6px; overflow: hidden; }}
  .track i {{ display: block; height: 100%; background: {T['grey']}; }}
  .track i.over {{ background: {T['negative']}; }}
  .row.fixed {{ grid-template-columns: minmax(0, 1fr) 12rem; }}
  .empty {{ border: 1px dashed {T['control']}; border-radius: 8px; padding: 10px 14px; font-size: 14px; color: {T['muted']}; }}

  /* ---------- Controls ---------- */
  [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-secondary"] {{ min-height: 36px; box-shadow: none; }}
  [data-testid="stBaseButton-primary"] {{ background: {T['primary']}; border-color: {T['primary']}; color: {T['on_primary']}; }}
  [data-testid="stBaseButton-primary"] p, [data-testid="stBaseButton-primary"] span {{ color: {T['on_primary']}; }}
  [data-testid="stBaseButton-primary"]:hover {{ background: {T['primary']}; border-color: {T['primary']}; opacity: .88; }}
  [data-testid="stBaseButton-tertiary"] {{ color: {T['text']}; }}
  [data-testid="stBaseButton-tertiary"]:hover {{ color: {T['hue']}; }}
  [data-testid^="stBaseButton"] {{ transition: background-color .15s ease, border-color .15s ease, color .15s ease; }}
  [data-testid^="stBaseButton"]:active {{ transform: translateY(1px); }}
  [data-testid="stButtonGroup"] [role="radiogroup"] {{ background: {T['active']}; padding: 2px; border-radius: 8px; gap: 0; }}
  [data-testid="stButtonGroup"] button {{ border: 0 !important; background: transparent; min-height: 30px; border-radius: 6px !important;
                                          color: {T['muted']}; box-shadow: none; }}
  [data-testid="stButtonGroup"] button p {{ color: {T['muted']}; }}
  [data-testid="stButtonGroup"] button[data-selected="true"] {{ background: {T['surface']}; box-shadow: 0 1px 2px rgba(0,0,0,.06); }}
  [data-testid="stButtonGroup"] button[data-selected="true"] p {{ color: {T['text']}; }}
  [class*="st-key-data_cats"] [role="radiogroup"] {{ background: transparent; padding: 0; gap: 6px; }}
  [class*="st-key-data_cats"] button {{ border: 1px solid {T['control']} !important; border-radius: 999px !important; }}
  [class*="st-key-data_cats"] button[data-selected="true"] {{ background: {T['primary']}; }}
  [class*="st-key-data_cats"] button[data-selected="true"] p {{ color: {T['on_primary']}; }}

  [data-testid="stExpander"] details {{ border: 1px solid {T['border']}; border-radius: 8px; background: {T['surface']}; }}
  [data-testid="stExpander"] summary {{ font-size: 13px; color: {T['muted']}; padding-top: 8px; padding-bottom: 8px; }}
  [data-testid="stExpander"] summary:hover {{ color: {T['text']}; }}
  [class*="st-key-card"] [data-testid="stExpander"] details {{ border: 0; border-top: 1px solid {T['rule']}; border-radius: 0;
                                                                background: transparent; }}
  [class*="st-key-card"] [data-testid="stExpander"] summary {{ padding-left: 0; padding-right: 0; }}

  /* ---------- Ask AI ---------- */
  .q-row {{ display: flex; justify-content: flex-end; margin: 16px 0 8px; }}
  .q {{ max-width: min(70%, 36rem); padding: 8px 14px; border-radius: 8px; background: {T['active']}; color: {T['text']};
        font-size: 14px; line-height: 20px; overflow-wrap: anywhere; }}
  .st-key-ideas button, [class*="st-key-follow"] button {{
    justify-content: flex-start !important; text-align: left; width: 100%; border: 0 !important; border-radius: 6px;
    background: transparent; padding: 6px 8px; min-height: 36px; color: {T['text']}; box-shadow: none;
  }}
  .st-key-ideas button > div, [class*="st-key-follow"] button > div {{ justify-content: flex-start !important; }}
  .st-key-ideas button:hover:not(:disabled), [class*="st-key-follow"] button:hover {{ background: {T['active']}; color: {T['text']}; }}
  .st-key-ideas button p, [class*="st-key-follow"] button p {{ white-space: normal; text-align: left; }}
  .ideas-label {{ font-size: 12px; color: {T['muted']}; margin: 10px 0 2px 8px; }}
  [data-testid="stChatMessage"] {{ background: transparent; padding-left: 0; padding-right: 0; }}
  [data-testid="stChatMessageAvatarCustom"] {{ background: {T['active']}; color: {T['text']}; }}

  /* ---------- Phone: flat bottom tab bar ---------- */
  .st-key-tabbar {{ display: none; }}
  @media (max-width: 768px) {{
    [data-testid="stMainBlockContainer"] {{ padding: 3.75rem 1.25rem 6rem; }}
    .st-key-tabbar {{
      display: block; position: fixed; left: 0; right: 0; bottom: 0; z-index: 1000; padding: 4px 16px 8px;
      background: {T['surface']}; border-top: 1px solid {T['border']};
    }}
    .st-key-tabbar [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; gap: 2px !important; }}
    .st-key-tabbar [data-testid="stColumn"] {{ min-width: 0 !important; width: 20% !important; flex: 1 1 0 !important; }}
    .st-key-tabbar button {{ width: 100%; border: 0 !important; background: transparent; min-height: 48px; padding: 4px 2px;
                             border-radius: 6px; color: {T['muted']}; box-shadow: none; }}
    .st-key-tabbar button [data-has-shortcut] {{ display: flex; flex-direction: column; align-items: center; gap: 2px; }}
    .st-key-tabbar button p {{ font-size: 11px; white-space: nowrap; }}
    .st-key-tabbar [data-testid="stBaseButton-secondary"] {{ background: {T['active']}; color: {T['text']}; }}
    [data-testid="stBottom"] {{ bottom: 64px; }}
    .answer-value {{ font-size: 28px; line-height: 34px; }}
    /* KPI strip: a 2-column grid on a phone, never four squeezed columns */
    [class*="st-key-strip"] [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap !important; row-gap: 14px; }}
    [class*="st-key-strip"] [data-testid="stColumn"] {{ min-width: calc(50% - 8px) !important; width: calc(50% - 8px) !important;
                                                        flex: 1 1 calc(50% - 8px) !important; }}
    [class*="st-key-strip"] [data-testid="stColumn"] + [data-testid="stColumn"] {{ border-left: 0; padding-left: 0; }}
  }}
  @media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
  /* ---------- Playful ledger ---------- */
  @keyframes wipe {{ from {{ clip-path: inset(0 100% 0 0); }} to {{ clip-path: inset(0 0 0 0); }} }}
  @keyframes slide-pos {{ from {{ opacity: 0; transform: translateX(18px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes slide-neg {{ from {{ opacity: 0; transform: translateX(-18px); }} to {{ opacity: 1; transform: none; }} }}
  @keyframes fill {{ from {{ transform: scaleX(0); }} to {{ transform: none; }} }}
  @keyframes thump {{ 0% {{ opacity: 0; transform: rotate(-3deg) scale(1.6); }} 60% {{ opacity: 1; transform: rotate(-3deg) scale(.94); }}
                     100% {{ transform: rotate(-3deg) scale(1); }} }}
  @keyframes fall {{ 0% {{ opacity: 1; transform: translate3d(0, 0, 0) rotate(0); }}
                     100% {{ opacity: 0; transform: translate3d(var(--dx), 105vh, 0) rotate(var(--rot)); }} }}

  .title-row {{ display: flex; align-items: center; gap: 12px; }}
  .avatar {{ flex: none; width: 36px; height: 36px; border-radius: 9px; display: grid; place-items: center;
             font-weight: 700; font-size: 17px; background: {rgba(T['hue'], .14)}; color: {T['hue']}; }}
  .words {{ font-size: 13px; color: {T['hue']}; font-weight: 500; margin-left: 8px; }}
  .st-key-nav [data-testid="stBaseButton-secondary"] [data-testid="stIconMaterial"] {{ color: {T['hue']}; }}

  [class*="st-key-card"] [data-testid="stVegaLiteChart"] {{ animation: wipe .9s cubic-bezier(.2, .8, .2, 1) both; }}
  .row-bar i, .track i {{ transform-origin: left; animation: fill .8s cubic-bezier(.2, .8, .2, 1) both; }}
  .row.in-pos {{ animation: slide-pos .45s cubic-bezier(.2, .8, .2, 1) both; }}
  .row.in-neg {{ animation: slide-neg .45s cubic-bezier(.2, .8, .2, 1) both; }}
  [class*="st-key-card"] .rows .row {{ margin: 0 -8px; padding-left: 8px; padding-right: 8px; border-radius: 6px;
                                       transition: background-color .15s ease; }}
  [class*="st-key-card"] .rows .row:hover {{ background: {rgba(T['hue'], .06)}; }}

  .stamp {{ display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; margin: 2px 0 8px;
            border: 2px solid {T['positive']}; outline: 1px solid {T['positive']}; outline-offset: 2px; border-radius: 4px;
            color: {T['positive']}; font-weight: 600; font-size: 13px; transform: rotate(-3deg); }}
  .stamp.warn {{ border-color: {T['warning']}; outline-color: {T['warning']}; color: {T['warning']}; }}
  .stamp i {{ width: 9px; height: 5px; border-left: 2px solid currentColor; border-bottom: 2px solid currentColor;
              transform: rotate(-45deg) translateY(-2px); }}
  .stamp.warn i {{ width: 2px; height: 10px; border: 0; background: currentColor; transform: none; }}
  .stamp.fresh {{ animation: thump .5s cubic-bezier(.2, 1.4, .4, 1) both; }}

  /* No covering layer: the container has no box, each piece is its own small fixed element */
  .confetti {{ display: contents; }}
  /* the burst starts under the title row, so it never passes over the page's heading */
  .confetti i {{ position: fixed; z-index: 999999; pointer-events: none; top: 140px; width: 8px; height: 13px;
                border-radius: 2px; opacity: 0;
                animation: fall 1.9s cubic-bezier(.25, .6, .4, 1) forwards; }}

  @media (prefers-reduced-motion: reduce) {{
    [class*="st-key-card"] [data-testid="stVegaLiteChart"], .row-bar i, .track i, .row.in-pos, .row.in-neg, .stamp.fresh {{
      animation: none; }}
    .confetti {{ display: none; }}
  }}
  /* ---------- Overdrive: the account's colour field ---------- */
  [class*="st-key-card_net"] {{ background: {T['field']}; border-color: {T['field']}; color: #fff; padding: 24px 24px 18px; }}
  [class*="st-key-card_net"] .card-title, [class*="st-key-card_net"] .card-meta,
  [class*="st-key-card_net"] .answer-delta {{ color: rgba(255,255,255,.86); }}
  [class*="st-key-card_net"] .words {{ color: #fff; opacity: .9; }}
  [class*="st-key-card_net"] .pill.pos {{ background: #fff; color: {T['field']}; }}
  [class*="st-key-card_net"] [data-testid="stMetricLabel"] p {{ color: rgba(255,255,255,.82); }}
  [class*="st-key-card_net"] [data-testid="stMetricValue"] {{ color: #fff; }}
  [class*="st-key-card_net"] [data-testid="stMetricDelta"], [class*="st-key-card_net"] [data-testid="stMetricDelta"] * {{
    color: #fff !important; }}
  [class*="st-key-card_net"] [class*="st-key-strip"] {{ border-top-color: rgba(255,255,255,.22); }}
  [class*="st-key-card_net"] [class*="st-key-strip"] [data-testid="stColumn"] + [data-testid="stColumn"] {{
    border-left-color: rgba(255,255,255,.22); }}
  [class*="st-key-card_net"] [data-testid="stExpander"] details {{ border-top-color: rgba(255,255,255,.22); }}
  [class*="st-key-card_net"] [data-testid="stExpander"] summary,
  [class*="st-key-card_net"] [data-testid="stExpander"] summary * {{ color: rgba(255,255,255,.86); }}
  [class*="st-key-card_net"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] {{
    background: {T['surface']}; color: {T['text']}; border-radius: 8px; padding: 12px; }}

  /* Odometer: each digit is a strip of 0-9 twice that rolls to its value */
  .odo-figure {{ font-size: 64px; font-weight: 700; letter-spacing: -0.03em; line-height: 1; color: #fff;
                 font-variant-numeric: tabular-nums; margin: 6px 0 8px; display: flex; flex-wrap: wrap; align-items: baseline; }}
  .odo-figure .odo {{ display: inline-block; height: 1em; overflow: hidden; vertical-align: top; }}
  .odo-figure .odo-strip {{ display: flex; flex-direction: column; transform: translateY(calc(var(--d) * -1em));
                            animation: roll 1.2s cubic-bezier(.2, .8, .2, 1) both; }}
  .odo-figure .odo-strip span {{ height: 1em; line-height: 1; }}
  .odo-figure .odo-strip span::before {{ content: attr(data-n); }}
  .odo-figure .odo-sep {{ display: inline-block; height: 1em; line-height: 1; }}
  @keyframes roll {{ from {{ transform: translateY(0); }} }}

  /* Bridge: last month at the top, each category's push or drag grows from the centre line in turn */
  .bridge {{ display: flex; flex-direction: column; gap: 2px; }}
  .bridge-total {{ display: flex; justify-content: space-between; align-items: baseline; padding: 8px 0;
                   font-weight: 600; font-variant-numeric: tabular-nums; }}
  .bridge-total small {{ color: {T['muted']}; font-weight: 400; font-size: 12px; }}
  .bridge-total.end {{ color: {T['hue']}; font-size: 18px; border-top: 1px solid {T['rule']}; margin-top: 4px; }}
  .bridge-step {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; column-gap: 12px; row-gap: 4px;
                  align-items: baseline; padding: 3px 0 5px; font-size: 14px; }}
  .bridge-step .name {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .bridge-step .name .kind {{ color: {T['faint']}; font-size: 12px; margin-left: 6px; }}
  .bridge-step .bar {{ grid-column: 1 / -1; position: relative; height: 10px; }}
  .bridge-step .bar::before {{ content: ""; position: absolute; left: 50%; top: -3px; bottom: -3px; width: 1px; background: {T['control']}; }}
  .bridge-step .bar i {{ position: absolute; top: 0; height: 10px; border-radius: 3px; animation: fill .55s cubic-bezier(.2, .8, .2, 1) both; }}
  .bridge-step .bar i.up {{ left: 50%; background: {T['positive']}; transform-origin: left; }}
  .bridge-step .bar i.down {{ right: 50%; background: {T['negative']}; transform-origin: right; }}
  .bridge-step .fig {{ text-align: right; font-variant-numeric: tabular-nums; font-weight: 500; }}

  /* Money river */
  [class*="st-key-card_river"] iframe {{ border-radius: 8px; }}
  .river-legend {{ display: none; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; font-size: 12px; color: {T['muted']}; }}
  .river-col > div {{ display: flex; align-items: center; gap: 6px; padding: 3px 0; white-space: nowrap; }}
  .river-col .nm {{ flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; }}
  .river-col-title {{ color: {T['text']}; font-weight: 600; }}
  .river-legend .sw {{ width: 8px; height: 8px; border-radius: 2px; background: {T['grey']}; flex: none; }}
  .river-legend .sw.in {{ background: {T['hue']}; }} .river-legend .sw.profit {{ background: {T['positive']}; }}
  .river-legend .sw.gap {{ background: {T['negative']}; }}
  .river-legend b {{ color: {T['text']}; font-weight: 600; font-variant-numeric: tabular-nums; }}

  @media (max-width: 768px) {{
    .odo-figure {{ font-size: 44px; }}
    .river-legend {{ display: grid; }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    .odo-figure .odo-strip, .bridge-step .bar i {{ animation: none; }}
  }}
</style>
"""


def inject() -> None:
    css = _css(palette())
    body = css[css.index("<style>") + 7: css.rindex("</style>")]
    assert not re.search(r"<[a-zA-Z/!]", body), "CSS contains '<': Streamlit would truncate the style block"
    st.html(css)


def confetti(seed: int = 0, pieces: int = 70) -> str:
    """A one-shot confetti burst as plain HTML/CSS in the account's hue and the money colours."""
    rng = random.Random(seed)
    colors = [T["hue"], T["positive"], T["warning"], T["ink"], rgba(T["hue"], .55)]
    bits = []
    for _ in range(pieces):
        bits.append(f'<i style="left:{rng.uniform(0, 100):.1f}%;background:{rng.choice(colors)};'
                    f'animation-delay:{rng.uniform(0, .6):.2f}s;--dx:{rng.uniform(-120, 120):.0f}px;'
                    f'--rot:{rng.uniform(-720, 720):.0f}deg;width:{rng.randint(6, 10)}px"></i>')
    return f'<div class="confetti" aria-hidden="true">{"".join(bits)}</div>'
