"""Capture the app for the film: Masala Street Cafés, from the reveal to the saved plan.

Shots: reveal (the account opens, the odometer rolls), river (follow the money to Delivery
commissions), ask (type the question, the live answer, its stamp, save its scenario), plan (the saved
scenario beside the actual, budgets suggested). Same capture as demo/record.py: Chrome at 2x, a drawn
cursor, marks and boxes per shot. Writes film/build/frames_film/, frames_film.json, marks_film.json.
    uv run --with playwright python demo/film/record_film.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
# load the film's own script by path: demo/record.py imports demo/script.py under the same name
_spec = importlib.util.spec_from_file_location("film_script", HERE / "script.py")
film_script = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(film_script)
QUESTION = film_script.QUESTION
sys.path.append(str(HERE.parent))
import record as R  # noqa: E402

R.BUILD = HERE / "build"


def main(pw):
    b, ctx, page = R.launch(pw, 1440, 810, 2, color_scheme="light", accept_downloads=True)
    page.goto(R.URL)
    page.wait_for_selector("[data-testid='stMetric']", timeout=60000)
    page.wait_for_timeout(2500)
    R.inject(page)
    r = R.Recorder(page, "film")
    page.evaluate("window.__cur(1100, 420)"); r.pos = (1100, 420)
    r.start()

    # reveal: open Masala; the colour floods in and the figure rolls
    r.begin("reveal")
    R.pick_account(r, "Masala Street", 0.8, 0.8)
    page.get_by_role("heading", name="Masala Street Cafés").first.wait_for(timeout=30000)
    R.wait_idle(page)
    page.evaluate("document.querySelectorAll('[data-testid=stToast] button').forEach(b => b.click())")
    page.evaluate(R.REPLAY_JS, ".odo-figure .odo-strip, [class*=st-key-card_net] [data-testid=stVegaLiteChart]")
    r.mark("reveal", "rolled")
    r.box("reveal", "figure", page.locator(".odo-figure").first)
    r.box("reveal", "net", page.locator("[class*='st-key-card_net']").first)
    r.glide(1000, 560, 1.6); page.wait_for_timeout(3400)
    r.end("reveal")

    # river: scroll to it, follow the money to Delivery commissions
    river = page.locator("[class*='st-key-card_river']").first
    r.begin("river")
    R.scroll_to(page, river, 60, 1.4)
    page.wait_for_timeout(300)
    r.box("river", "river", river)
    frame = river.locator("iframe").first
    fb = frame.bounding_box()
    pt = frame.element_handle().content_frame().evaluate("""() => {
      const t = [...document.querySelectorAll('text')].find(e => e.textContent.startsWith('Delivery commissions'));
      const b = t.getBBox(), s = document.querySelector('svg').clientWidth / document.querySelector('svg').viewBox.baseVal.width;
      return {x: b.x * s, y: (b.y + b.height / 2) * s, w: b.width * s}; }""")
    lx, ly = fb["x"] + pt["x"], fb["y"] + pt["y"]
    r.glide(fb["x"] + fb["width"] * 0.3, fb["y"] + fb["height"] * 0.35, 1.0)
    page.wait_for_timeout(500)
    r.glide(lx - 70, ly, 1.6)                                  # onto the commissions ribbon
    r.mark("river", "on_leak")
    r.box("river", "leak", {"x": lx - 260, "y": ly - 60, "width": pt["w"] + 300, "height": 120})
    r.box("river", "label", {"x": lx - 6, "y": ly - 14, "width": pt["w"] + 12, "height": 28})
    page.wait_for_timeout(3600)
    r.end("river")

    # ask: the question, the live answer, its stamp, then save the scenario
    r.begin("ask")
    R.scroll_main(page, 0, 0.4)
    r.click(page.locator("[class*='st-key-nav_ask'] button").first, 0.6)
    R.wait_idle(page); page.wait_for_timeout(400)
    r.click(page.locator("[data-testid='stChatInput'] textarea").first, 0.6)
    r.mark("ask", "type0")
    r.type(QUESTION, 16)
    page.wait_for_timeout(250)
    page.keyboard.press("Enter")
    r.mark("ask", "wait0")
    page.locator(".stamp").first.wait_for(timeout=240000)
    r.mark("ask", "answer0")
    page.wait_for_timeout(1200)
    r.box("ask", "stamp", page.locator(".stamp").first)
    r.box("ask", "answer", page.locator(".stamp").first.locator("xpath=ancestor::*[contains(@class,'st-key-')][1]"))
    save = page.get_by_role("button", name="Save this scenario to Plan")
    r.mark("ask", "has_save", save.count() > 0)
    target = page.evaluate("""() => { const m = document.querySelector('[data-testid=stMain]');
      const v = m.querySelector('[data-testid=stVegaLiteChart]'); return v ? m.scrollTop + v.getBoundingClientRect().top - 260 : m.scrollTop + 300; }""")
    R.scroll_main(page, target, 2.2); page.wait_for_timeout(1200)
    if save.count():
        R.scroll_to(page, save.first, 420, 1.4)
        r.box("ask", "save", save.first)
        r.mark("ask", "save0")
        r.click(save.first, 0.8)
        R.wait_idle(page); page.wait_for_timeout(1500)
    r.end("ask")

    # plan: the saved scenario beside the actual, then budgets
    r.begin("plan")
    R.scroll_main(page, 0, 0.3)
    r.click(page.locator("[class*='st-key-nav_plan'] button").first, 0.6)
    R.wait_idle(page); page.wait_for_timeout(500)
    card = page.locator("[class*='st-key-card_scenarios']").first
    R.scroll_to(page, card, 150, 1.6)
    page.wait_for_timeout(300)
    r.box("plan", "scenarios", card)
    r.glide(1100, 520, 1.2); page.wait_for_timeout(2400)
    R.scroll_main(page, 0, 1.2)
    r.click(page.locator("[class*='st-key-budget_suggest'] button").first, 0.7)
    R.wait_idle(page); page.wait_for_timeout(1600)
    r.box("plan", "budgets", page.locator("[class*='st-key-card_budgets']").first)
    page.wait_for_timeout(1600)
    r.end("plan")
    r.stop()
    b.close()


if __name__ == "__main__":
    with sync_playwright() as pw:
        main(pw)
