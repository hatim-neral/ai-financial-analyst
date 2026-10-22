"""Drive the running app through every scene and capture it in high resolution.

Chrome's screencast streams frames (1440x810 CSS px at 2x, so 2880x1620) while Playwright clicks,
types and scrolls. Each scene stores its start and end on the capture clock plus the on-screen
boxes the camera will frame later. A glide-in cursor is drawn into the page, since headless Chrome
has none. Output in demo/build/: frames/*.jpg, frames.json, marks.json, and the same for the dark-mode clip (the phone clip is optional: `record.py phone`).

Needs the app running at http://localhost:8501 with an AI provider that answers.
    uv run --with playwright python demo/record.py
"""

from __future__ import annotations

import base64
import json
import math
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from script import QUESTION  # noqa: E402

URL = "http://localhost:8501"
BUILD = Path(__file__).parent / "build"
VIEW = {"width": 1440, "height": 810}

CURSOR_JS = """
(() => {
  if (window.__cur) return;
  const c = document.createElement('div');
  c.id = 'demo-cursor';
  c.innerHTML = '<svg width="26" height="26" viewBox="0 0 26 26"><path d="M5 3 L5 21 L10 16.5 L13.4 23.6 L16.6 22.1 L13.3 15.2 L20 15.2 Z" fill="#0a0a0a" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  Object.assign(c.style, {position: 'fixed', left: 0, top: 0, zIndex: 2147483647, pointerEvents: 'none',
    transform: 'translate(-100px,-100px)', filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.25))'});
  const r = document.createElement('div');
  Object.assign(r.style, {position: 'fixed', width: '34px', height: '34px', marginLeft: '-17px', marginTop: '-17px',
    borderRadius: '50%', border: '2px solid rgba(29,95,191,.9)', zIndex: 2147483646, pointerEvents: 'none', opacity: 0});
  document.body.append(r, c);
  window.__cur = (x, y) => { c.style.transform = `translate(${x - 5}px, ${y - 3}px)`; r.style.left = x + 'px'; r.style.top = y + 'px'; };
  window.__press = () => { r.animate([{transform: 'scale(.4)', opacity: 1}, {transform: 'scale(1.5)', opacity: 0}],
    {duration: 520, easing: 'cubic-bezier(.2,.8,.2,1)'}); c.animate([{scale: 1}, {scale: .86}, {scale: 1}], {duration: 220}); };
})();
"""

REPLAY_JS = """(sel) => document.querySelectorAll(sel).forEach(e => {
  e.style.animation = 'none'; void e.offsetWidth; e.style.animation = ''; })"""


class Recorder:
    def __init__(self, page: Page, name: str):
        self.page, self.name = page, name
        self.dir = BUILD / f"frames_{name}"
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True)
        self.frames: list[tuple[float, str]] = []
        self.marks: dict = {}
        self.pos = (VIEW["width"] / 2, VIEW["height"] / 2)
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._frame)

    def _frame(self, f):
        i = len(self.frames)
        path = self.dir / f"{i:05d}.jpg"
        path.write_bytes(base64.b64decode(f["data"]))
        self.frames.append((f["metadata"]["timestamp"], path.name))
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": f["sessionId"]})
        except Exception:
            pass

    def start(self):
        # frames come in device pixels because the browser itself runs at 2x (see launch())
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": 4000, "maxHeight": 4000})
        self.page.wait_for_timeout(400)

    def stop(self):
        self.page.wait_for_timeout(300)
        self.cdp.send("Page.stopScreencast")
        (BUILD / f"frames_{self.name}.json").write_text(json.dumps(self.frames))
        (BUILD / f"marks_{self.name}.json").write_text(json.dumps(self.marks, indent=1))
        print(f"{self.name}: {len(self.frames)} frames")

    # --- the capture clock is the screencast's own (seconds since epoch, like time.time()) ---
    def now(self) -> float:
        return time.time()

    def begin(self, scene: str, **boxes):
        self.marks[scene] = {"t0": self.now(), "boxes": {k: v for k, v in boxes.items() if v}}
        print("  ", scene)

    def mark(self, scene: str, key: str, value=None):
        self.marks[scene][key] = self.now() if value is None else value

    def box(self, scene: str, name: str, locator_or_box):
        b = locator_or_box if isinstance(locator_or_box, dict) else locator_or_box.bounding_box()
        if b:
            self.marks[scene]["boxes"][name] = [round(b["x"], 1), round(b["y"], 1), round(b["width"], 1), round(b["height"], 1)]

    def end(self, scene: str):
        self.marks[scene]["t1"] = self.now()

    # --- cursor ---
    def glide(self, x: float, y: float, dur: float = 0.7):
        x0, y0 = self.pos
        n = max(2, int(dur * 50))
        for i in range(1, n + 1):
            k = i / n
            e = 1 - (1 - k) ** 3 if k > 0.5 else 4 * k ** 3  # ease in-out
            e = k * k * (3 - 2 * k)
            xi, yi = x0 + (x - x0) * e, y0 + (y - y0) * e
            self.page.mouse.move(xi, yi)
            self.page.evaluate(f"window.__cur && window.__cur({xi:.1f}, {yi:.1f})")
            self.page.wait_for_timeout(dur / n * 1000)
        self.pos = (x, y)

    def to(self, locator, dur: float = 0.7, dx: float = 0.5, dy: float = 0.5):
        locator.scroll_into_view_if_needed()
        b = locator.bounding_box()
        self.glide(b["x"] + b["width"] * dx, b["y"] + b["height"] * dy, dur)
        return b

    def click(self, locator, dur: float = 0.7, settle: float = 0.15, **kw):
        self.to(locator, dur, **kw)
        self.page.wait_for_timeout(settle * 1000)
        self.page.evaluate("window.__press && window.__press()")
        self.page.mouse.down(); self.page.wait_for_timeout(60); self.page.mouse.up()

    def type(self, text: str, delay_ms: int = 28):
        self.page.keyboard.type(text, delay=delay_ms)


def scroll_main(page: Page, top: float, dur: float = 1.0):
    page.evaluate("""([top, dur]) => new Promise(done => {
      const el = document.querySelector('[data-testid=stMain]'); const y0 = el.scrollTop, t0 = performance.now();
      (function step(t) { const k = Math.min(1, (t - t0) / (dur * 1000)); const e = k < .5 ? 4*k*k*k : 1 - Math.pow(-2*k + 2, 3) / 2;
        el.scrollTop = y0 + (top - y0) * e; k < 1 ? requestAnimationFrame(step) : done(); })(t0); })""", [top, dur])


def scroll_to(page: Page, locator, offset: float = 90, dur: float = 1.0):
    top = page.evaluate("""([el, off]) => { const m = document.querySelector('[data-testid=stMain]');
      return m.scrollTop + el.getBoundingClientRect().top - off; }""", [locator.element_handle(), offset])
    scroll_main(page, max(0, top), dur)


def wait_idle(page: Page, timeout: float = 30):
    """Until Streamlit has finished its rerun (the running indicator is gone)."""
    t = time.time()
    page.wait_for_timeout(250)
    while time.time() - t < timeout:
        if not page.locator("[data-testid='stStatusWidget']").is_visible():
            return
        page.wait_for_timeout(100)


def inject(page: Page):
    page.evaluate(CURSOR_JS)


def pick_account(r: Recorder, label: str, dur: float = 0.7, hold: float = 0.9):
    page = r.page
    r.click(page.locator("[data-testid='stSelectbox']").first, dur)
    page.wait_for_timeout(hold * 1000)
    opt = page.get_by_role("option", name=label)
    r.click(opt, 0.6)


def launch(pw, w: int, h: int, scale: int, **ctx_kw):
    """Chrome's screencast streams CSS-pixel frames unless the whole browser runs at a device scale,
    so the scale is a launch flag and the window is sized to give a w x h page (87px of window frame)."""
    b = pw.chromium.launch(channel="chrome", headless=True,
                           args=[f"--force-device-scale-factor={scale}", f"--window-size={w},{h + 87}"])
    ctx = b.new_context(no_viewport=True, **ctx_kw)
    page = ctx.new_page()
    return b, ctx, page


def desktop(pw):
    b, ctx, page = launch(pw, 1440, 810, 2, color_scheme="light", accept_downloads=True)
    page.goto(URL)
    print("   page", page.evaluate("[innerWidth, innerHeight, devicePixelRatio]"))
    page.wait_for_selector("[data-testid='stMetric']", timeout=60000)
    page.wait_for_timeout(2500)
    inject(page)
    r = Recorder(page, "desktop")
    page.evaluate("window.__cur(720, 420)"); r.pos = (720, 420)
    # quietly start on another account so the opening scene can pick Cloudnine and play its entrance
    pick_account(r, "Threadline", 0.2, 0.4)
    page.get_by_role("heading", name="Threadline").first.wait_for(timeout=30000)
    wait_idle(page); page.wait_for_timeout(1500)
    r.start()

    # 1. load: upload, then the six sample businesses
    r.begin("load")
    r.box("load", "sidebar", page.locator("[data-testid='stSidebar']"))
    r.to(page.get_by_text("Upload a CSV").first, 0.9); page.wait_for_timeout(900)
    r.click(page.locator("[data-testid='stSelectbox']").first, 0.7)
    page.wait_for_timeout(250)
    r.box("load", "options", page.locator("[data-testid='stSelectboxVirtualDropdown']").first
          if page.locator("[data-testid='stSelectboxVirtualDropdown']").count() else page.get_by_role("listbox").first)
    page.wait_for_timeout(1300)
    r.click(page.get_by_role("option", name="Cloudnine"), 0.7)
    r.end("load")

    # 2. hero: the colour field and the odometer
    page.get_by_role("heading", name="Cloudnine Software").first.wait_for(timeout=30000)
    wait_idle(page)
    page.evaluate(REPLAY_JS, ".odo-figure .odo-strip, [class*=st-key-card_net] [data-testid=stVegaLiteChart]")
    r.begin("hero")
    net = page.locator("[class*='st-key-card_net']").first
    r.box("hero", "net", net)
    r.box("hero", "figure", page.locator(".odo-figure").first)
    r.glide(980, 300, 1.6); page.wait_for_timeout(1500)
    r.glide(900, 470, 1.4); page.wait_for_timeout(3200)
    r.end("hero")

    # 3. bridge: replay the bars growing in turn
    moved = page.locator("[class*='st-key-card_moved']").first
    r.begin("bridge")
    r.box("bridge", "moved", moved)
    page.evaluate(REPLAY_JS, ".bridge-step .bar i")
    r.glide(1260, 330, 1.2); page.wait_for_timeout(600)
    r.glide(1290, 520, 2.2); page.wait_for_timeout(2200)
    r.end("bridge")

    # 4. river: scroll to it and hover two ribbons
    river = page.locator("[class*='st-key-card_river']").first
    r.begin("river")
    scroll_to(page, river, 72, 1.3)
    page.wait_for_timeout(200)
    r.box("river", "river", river)
    frame_el = river.locator("iframe").first
    fb = frame_el.bounding_box()
    pts = frame_el.element_handle().content_frame().evaluate("""() => { const rs = [...document.querySelectorAll('rect')];
      const vb = document.querySelector('svg').viewBox.baseVal; const s = document.querySelector('svg').clientWidth / vb.width;
      const L = rs.filter(r => +r.getAttribute('x') < vb.width / 2 - 30), R = rs.filter(r => +r.getAttribute('x') > vb.width / 2 + 30);
      const c = r => [(+r.getAttribute('x')) * s, (+r.getAttribute('y') + +r.getAttribute('height') / 2) * s];
      return {left: c(L[0]), profit: c(R[R.length - 1]), nodeW: 10 * s}; }""")
    lx, ly = pts["left"]; px, py = pts["profit"]
    r.glide(fb["x"] + lx + 70, fb["y"] + ly, 1.2); page.wait_for_timeout(2000)
    r.box("river", "hover1", {"x": fb["x"] + lx - 160, "y": fb["y"] + ly - 70, "width": 520, "height": 140})
    r.glide(fb["x"] + px - 80, fb["y"] + py, 1.3); page.wait_for_timeout(2200)
    r.box("river", "hover2", {"x": fb["x"] + px - 380, "y": fb["y"] + py - 80, "width": 560, "height": 160})
    r.end("river")

    # 5. evidence: open the formula and source rows
    r.begin("evidence")
    exp = river.locator("[data-testid='stExpander'] summary").first
    r.click(exp, 0.9)
    page.wait_for_timeout(500)
    scroll_to(page, river.locator("[data-testid='stExpander']").first, 150, 1.0)
    page.wait_for_timeout(300)
    r.box("evidence", "evidence", river.locator("[data-testid='stExpander']").first)
    r.glide(700, 520, 1.0); page.wait_for_timeout(2400)
    r.end("evidence")

    # 6. switch account
    r.begin("switch")
    scroll_main(page, 0, 0.7)
    pick_account(r, "Masala Street", 0.6, 0.6)
    page.get_by_role("heading", name="Masala Street Cafés").first.wait_for(timeout=30000)
    wait_idle(page)
    page.wait_for_timeout(1400)
    r.box("switch", "net", page.locator("[class*='st-key-card_net']").first)
    r.end("switch")

    # 7. period (the account toast sits over the control: close it first)
    page.evaluate("document.querySelectorAll('[data-testid=stToast] button').forEach(b => b.click())")
    page.wait_for_timeout(400)
    r.begin("period")
    seg = page.locator("[class*='st-key-period_preset'] button, [data-testid='stButtonGroup'] button").filter(has_text="6M").first
    r.box("period", "control", seg)
    r.click(seg, 0.7)
    wait_idle(page)
    page.wait_for_timeout(1800)
    r.box("period", "net", page.locator("[class*='st-key-card_net']").first)
    r.end("period")

    # 8. insights
    r.begin("insights")
    r.click(page.locator("[class*='st-key-nav_insights'] button").first, 0.7)
    wait_idle(page); page.wait_for_timeout(800)
    scroll_main(page, 330, 1.6); page.wait_for_timeout(1600)
    r.end("insights")

    # 9. ledger: search
    r.begin("ledger")
    scroll_main(page, 0, 0.3)
    r.click(page.locator("[class*='st-key-nav_activity'] button").first, 0.6)
    wait_idle(page); page.wait_for_timeout(400)
    search = page.locator("[class*='st-key-data_search'] input, input[placeholder^='Search categories']").first
    r.click(search, 0.6)
    r.type("rent", 70)
    page.keyboard.press("Enter")
    wait_idle(page); page.wait_for_timeout(1000)
    r.end("ledger")

    # 10. ask: type, wait for the agent, then read the answer
    r.begin("ask")
    r.click(page.locator("[class*='st-key-nav_ask'] button").first, 0.6)
    wait_idle(page); page.wait_for_timeout(500)
    box = page.locator("[data-testid='stChatInput'] textarea").first
    r.click(box, 0.6)
    r.mark("ask", "type0")
    r.type(QUESTION, 22)
    page.wait_for_timeout(300)
    page.keyboard.press("Enter")
    r.mark("ask", "wait0")
    page.locator(".stamp").first.wait_for(timeout=180000)
    page.wait_for_timeout(200)
    r.mark("ask", "answer0")
    page.wait_for_timeout(1400)
    answer = page.locator(".stamp").first
    r.box("ask", "stamp", answer)
    main_h = page.evaluate("document.querySelector('[data-testid=stMain]').scrollHeight")
    cur = page.evaluate("document.querySelector('[data-testid=stMain]').scrollTop")
    target = page.evaluate("""() => { const m = document.querySelector('[data-testid=stMain]');
      const v = m.querySelector('[data-testid=stVegaLiteChart]'); return v ? m.scrollTop + v.getBoundingClientRect().top - 200 : m.scrollTop + 300; }""")
    scroll_main(page, max(cur, target), 2.4); page.wait_for_timeout(1200)
    scroll_main(page, main_h, 2.2); page.wait_for_timeout(1000)
    r.end("ask")

    # 11. plan: suggest budgets, save a scenario
    r.begin("plan")
    scroll_main(page, 0, 0.3)
    r.click(page.locator("[class*='st-key-nav_plan'] button").first, 0.6)
    wait_idle(page); page.wait_for_timeout(400)
    r.click(page.locator("[class*='st-key-budget_suggest'] button").first, 0.7)
    wait_idle(page); page.wait_for_timeout(1400)
    r.box("plan", "budgets", page.locator("[class*='st-key-card_budgets']").first)
    name = page.locator("[class*='st-key-scen_name'] input").first
    scroll_to(page, name, 220, 1.2)
    r.click(name, 0.6)
    r.type("Revenue up 5%", 45)
    page.keyboard.press("Tab")
    wait_idle(page); page.wait_for_timeout(400)
    r.box("plan", "scenario", page.locator("[class*='st-key-scen_save']").first)
    r.click(page.locator("[class*='st-key-scen_save'] button").first, 0.7)
    wait_idle(page); page.wait_for_timeout(2400)
    r.end("plan")

    # 12. anywhere: download the report, then dark mode
    r.begin("anywhere")
    scroll_main(page, 0, 0.3)
    r.click(page.locator("[class*='st-key-nav_home'] button").first, 0.5)
    wait_idle(page)
    try:
        with page.expect_download(timeout=15000) as dl:
            r.click(page.get_by_role("button", name="Download report"), 0.6)
        dl.value.save_as(BUILD / "report.html")
    except Exception as exc:
        print("  report download skipped:", exc)
    page.wait_for_timeout(1800)
    r.end("anywhere")
    r.stop()
    b.close()


def dark(pw):
    """Overview in dark mode, for the closing split screen (a theme switch mid-capture stops the screencast)."""
    b, ctx, page = launch(pw, 1440, 810, 2, color_scheme="dark")
    page.goto(URL)
    print("   page", page.evaluate("[innerWidth, innerHeight, devicePixelRatio]"))
    page.wait_for_selector("[data-testid='stMetric']", timeout=60000)
    page.wait_for_timeout(3000)
    r = Recorder(page, "dark")
    # same account as the light shot it cross-fades from
    page.locator("[data-testid='stSelectbox']").first.click(); page.wait_for_timeout(500)
    page.get_by_role("option", name="Masala Street").click()
    page.get_by_role("heading", name="Masala Street Cafés").first.wait_for(timeout=30000)
    wait_idle(page); page.wait_for_timeout(4500)   # let the account toast clear
    page.evaluate(REPLAY_JS, ".odo-figure .odo-strip, .bridge-step .bar i")
    r.start()
    r.begin("dark")
    page.wait_for_timeout(3000)
    scroll_main(page, 700, 2.5); page.wait_for_timeout(1500)
    r.end("dark")
    r.stop()
    b.close()


def phone(pw):
    # Chrome windows can't be narrower than 500px, so the phone uses device emulation; it is shown
    # about 375px wide in the video, so its CSS-pixel frames are already sharp
    b = pw.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, color_scheme="light",
                        is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.goto(URL)
    print("   page", page.evaluate("[innerWidth, innerHeight, devicePixelRatio]"))
    page.wait_for_selector("[data-testid='stMetric']", timeout=60000)
    page.wait_for_timeout(3000)
    r = Recorder(page, "phone")
    page.evaluate(REPLAY_JS, ".odo-figure .odo-strip, .bridge-step .bar i")
    r.start()
    r.begin("phone")
    page.wait_for_timeout(1400)
    scroll_main(page, 900, 2.2); page.wait_for_timeout(600)
    scroll_main(page, 1900, 2.0); page.wait_for_timeout(1000)
    r.end("phone")
    r.stop()
    b.close()


if __name__ == "__main__":
    which = sys.argv[1:] or ["desktop", "dark"]
    with sync_playwright() as pw:
        for w in which:
            {"desktop": desktop, "dark": dark, "phone": phone}[w](pw)
