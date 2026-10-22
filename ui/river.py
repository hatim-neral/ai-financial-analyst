"""The money river: revenue sources flow into the business and out to each cost and to profit.

Ribbon widths are the real amounts for the period (from fin_analyst.metrics); both sides always sum
to the same total (a loss period adds a "Shortfall" source so the river balances, which is what a
loss is). Rupee particles stream along the ribbons; hovering a ribbon shows its amount.

It renders in a small sandboxed component frame so it can draw with SVG and a script. Labels are
formatted in Python so they match the rest of the app. Particles stop when the tab is hidden and
never start under prefers-reduced-motion; without scripts nothing is lost that the cards don't say.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from fin_analyst import formatting as fmt
from fin_analyst import metrics

from .components import esc
from .theme import T

TOP = 5


def _short(x: float) -> str:
    return fmt.money_words(x) if abs(x) >= 1e5 else fmt.money(x)


def flows(df: pd.DataFrame, start: str, end: str) -> dict | None:
    """Left (sources) and right (uses) nodes with amounts; None when there is nothing to draw."""
    summary = metrics.period_summary(df, start, end).result
    revenue, expenses, net = summary["total_revenue"], summary["total_expenses"], summary["net_revenue"]
    if revenue <= 0 and expenses <= 0:
        return None

    def side(metric: str, total: float) -> list[dict]:
        try:
            cats = metrics.top_categories(df, metric, start, end, n=15).result["categories"]
        except metrics.MetricError:
            return []
        top = cats[:TOP]
        nodes = [{"name": c["category"], "value": c["total"]} for c in top]
        other = round(total - sum(c["total"] for c in top), 2)
        if other > 0.5:
            rest = cats[TOP:]
            nodes.append({"name": rest[0]["category"] if len(rest) == 1 else f"{len(rest)} others", "value": other})
        return nodes

    left = [dict(n, kind="in") for n in side("revenue", revenue)]
    right = [dict(n, kind="out") for n in side("expenses", expenses)]
    if net > 0:
        right.append({"name": "Profit", "value": net, "kind": "profit"})
    elif net < 0:
        left.append({"name": "Shortfall", "value": -net, "kind": "gap"})
    total = sum(n["value"] for n in left)
    for n in left + right:
        n["label"] = _short(n["value"])
        n["share"] = f"{n['value'] / total * 100:.1f}%" if total else "—"
    return {"left": left, "right": right, "total": total, "total_label": _short(total),
            "revenue_label": _short(revenue), "net": net}


_HTML = """<!doctype html><html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  html, body { margin: 0; background: transparent; font-family: Geist, Inter, system-ui, sans-serif; color: __TEXT__; }
  svg { display: block; width: 100%; overflow: visible; }
  .lbl { font-size: 12px; fill: __MUTED__; } .lbl b, .amt { font-weight: 600; fill: __TEXT__; }
  .ribbon { transition: opacity .2s ease; cursor: default; }
  svg:hover .ribbon { opacity: .45; } svg .ribbon:hover { opacity: 1; }
  #tip { position: fixed; pointer-events: none; padding: 6px 10px; border-radius: 6px; font-size: 12px;
         background: __TEXT__; color: __SURFACE__; opacity: 0; transition: opacity .12s; white-space: nowrap;
         font-variant-numeric: tabular-nums; }
</style></head><body><svg id="river" role="img" aria-label="__ARIA__"></svg><div id="tip"></div>
<script>
(function () {
  const D = __DATA__, C = __COLORS__;
  const svg = document.getElementById('river'), tip = document.getElementById('tip'), NS = 'http://www.w3.org/2000/svg';
  const still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let dots = [], raf = null, narrow = false;

  function el(tag, attrs, parent) { const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]); (parent || svg).appendChild(e); return e; }

  function draw() {
    svg.innerHTML = ''; dots = [];
    const W = Math.max(320, svg.clientWidth || document.body.clientWidth); narrow = W < 640;
    const H = narrow ? 350 : 360, padY = 12, nodeW = 10, gap = narrow ? 6 : 9;
    // label margins sized to the longest label on each side, so nothing is cut off
    const probe = el('text', { class: 'lbl' });
    function widest(nodes) { return nodes.reduce((m, n) => { probe.textContent = labelText(n); return Math.max(m, probe.getComputedTextLength() * 1.07); }, 0) + 14; }
    const cap = W * (narrow ? 0.3 : 0.26), wl = Math.min(cap, widest(D.left)), wr = Math.min(cap, widest(D.right));
    probe.remove();
    const x0 = wl, x1 = W - wr - nodeW, cx = (x0 + nodeW + x1) / 2 - 7;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('height', H);
    const maxN = Math.max(D.left.length, D.right.length);
    const k = (H - 2 * padY - gap * (maxN - 1)) / D.total;

    function stack(nodes, x) { const used = nodes.reduce((s, n) => s + n.value * k, 0) + gap * (nodes.length - 1);
      let y = (H - used) / 2; return nodes.map(n => { const h = Math.max(2, n.value * k); const o = { n, x, y, h }; y += h + gap; return o; }); }
    const L = stack(D.left, x0), R = stack(D.right, x1);
    const centerH = D.total * k, cy0 = (H - centerH) / 2;

    function colour(kind) { return kind === 'in' ? C.hue : kind === 'profit' ? C.positive : kind === 'gap' ? C.negative : C.grey; }
    function ribbon(ax, ay, ah, bx, by, bh, node, side) {
      const mx = (ax + bx) / 2, c = colour(node.kind);
      const d = `M${ax},${ay} C${mx},${ay} ${mx},${by} ${bx},${by} L${bx},${by + bh} C${mx},${by + bh} ${mx},${ay + ah} ${ax},${ay + ah} Z`;
      const p = el('path', { d, fill: c, 'fill-opacity': node.kind === 'out' ? 0.22 : 0.32, class: 'ribbon' });
      p.addEventListener('mousemove', e => { tip.textContent = side === 'in'
          ? `${node.name} → business  ${node.label} · ${node.share}` : `Business → ${node.name}  ${node.label} · ${node.share}`;
        tip.style.left = (e.clientX + 12) + 'px'; tip.style.top = (e.clientY - 28) + 'px'; tip.style.opacity = 1; });
      p.addEventListener('mouseleave', () => { tip.style.opacity = 0; });
      // particles: count follows the amount, each rides the ribbon's centre band
      const n = Math.max(1, Math.round(node.value / D.total * (narrow ? 26 : 46)));
      for (let i = 0; i < n; i++) dots.push({ ax, ay, ah, bx, by, bh, mx, t: Math.random(), off: Math.random() * 0.7 + 0.15,
        speed: 0.0016 + Math.random() * 0.0012, c, e: null });
    }
    let cyl = cy0, cyr = cy0;
    L.forEach(o => { ribbon(o.x + nodeW, o.y, o.h, cx, cyl, o.h, o.n, 'in'); cyl += o.h; });
    R.forEach(o => { ribbon(cx + 14, cyr, o.h, o.x, o.y, o.h, o.n, 'out'); cyr += o.h; });
    // nodes and labels
    L.forEach(o => { el('rect', { x: o.x, y: o.y, width: nodeW, height: o.h, rx: 2, fill: colour(o.n.kind) });
      label(o.x - 8, o.y + o.h / 2, o.n, 'end'); });
    R.forEach(o => { el('rect', { x: o.x, y: o.y, width: nodeW, height: o.h, rx: 2, fill: colour(o.n.kind) });
      label(o.x + nodeW + 8, o.y + o.h / 2, o.n, 'start'); });
    el('rect', { x: cx, y: cy0, width: 14, height: centerH, rx: 3, fill: C.ink });
    const t = el('text', { x: cx + 7, y: cy0 - 6, 'text-anchor': 'middle', class: 'lbl' }); t.textContent = narrow ? '' : 'Your business';
    dots.forEach(d => { d.e = el('circle', { r: narrow ? 1.8 : 2.3, fill: d.c, 'fill-opacity': 0.9 }); });
    if (still) dots.forEach(d => d.e.remove());
  }
  function short(n) { return narrow && n.name.length > 14 ? n.name.slice(0, 13) + '…' : n.name; }
  // on a phone the names move to the legend under the river; the ribbons keep their amounts
  function labelText(n) { return narrow ? n.label : short(n) + '  ' + n.label; }
  function label(x, y, n, anchor) {
    const t = el('text', { x, y: y + 4, 'text-anchor': anchor, class: 'lbl' });
    const name = document.createElementNS(NS, 'tspan'); name.textContent = short(n) + '  ';
    const amt = document.createElementNS(NS, 'tspan'); amt.setAttribute('class', 'amt'); amt.textContent = n.label;
    if (!narrow) t.appendChild(name); t.appendChild(amt);
  }
  function bez(a, m1, m2, b, t) { const u = 1 - t; return u*u*u*a + 3*u*u*t*m1 + 3*u*t*t*m2 + t*t*t*b; }
  function tick() {
    for (const d of dots) {
      d.t += d.speed; if (d.t > 1) d.t -= 1;
      const x = bez(d.ax, d.mx, d.mx, d.bx, d.t);
      const top = bez(d.ay, d.ay, d.by, d.by, d.t), h = d.ah + (d.bh - d.ah) * d.t;
      d.e.setAttribute('cx', x.toFixed(1)); d.e.setAttribute('cy', (top + h * d.off).toFixed(1));
    }
    raf = requestAnimationFrame(tick);
  }
  function start() { if (!still && !raf && !document.hidden) raf = requestAnimationFrame(tick); }
  function stop() { if (raf) cancelAnimationFrame(raf); raf = null; }
  document.addEventListener('visibilitychange', () => document.hidden ? stop() : start());
  new ResizeObserver(() => { stop(); draw(); start(); }).observe(document.body);
  draw(); start();
})();
</script></body></html>"""


def render(df: pd.DataFrame, start: str, end: str) -> bool:
    data = flows(df, start, end)
    if not data:
        return False
    colors = {k: T[k] for k in ("hue", "positive", "negative", "grey", "ink")}
    aria = (f"Money flow: {data['revenue_label']} of revenue from {len([n for n in data['left'] if n['kind'] == 'in'])} "
            f"sources goes to {len([n for n in data['right'] if n['kind'] == 'out'])} cost groups"
            + (f" and {_short(data['net'])} of profit." if data["net"] > 0 else "."))
    page = (_HTML.replace("__DATA__", json.dumps(data, ensure_ascii=True).replace("</", "<\\/"))
            .replace("__COLORS__", json.dumps(colors)).replace("__ARIA__", aria.replace('"', "'"))
            .replace("__TEXT__", T["text"]).replace("__MUTED__", T["muted"]).replace("__SURFACE__", T["surface"]))
    components.html(page, height=372)
    st.html(legend(data))
    return True


def legend(data: dict) -> str:
    """Names and amounts in two columns; shown on a phone, where the river has room for amounts only."""
    def col(title, nodes):
        rows = "".join(f'<div><i class="sw {n["kind"]}"></i><span class="nm">{esc(n["name"])}</span><b>{esc(n["label"])}</b></div>' for n in nodes)
        return f'<div class="river-col"><div class="river-col-title">{title}</div>{rows}</div>'
    return f'<div class="river-legend">{col("Money in", data["left"])}{col("Money out", data["right"])}</div>'
