"""Check the walkthrough before anyone watches it: a frame one second into every beat, labelled with the phrase
being spoken, on one contact sheet (build/verify.jpg), so each sentence can be checked against its picture."""

import functools, http.server, threading, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8768), functools.partial(Quiet, directory=str(HERE)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", headless=True)
    page = b.new_page(viewport={"width": 1920, "height": 1080})
    page.goto("http://127.0.0.1:8768/walk.html"); page.evaluate("load()")
    beats = page.evaluate("beatList()")
    shots = []
    for bt in beats:
        t = min(bt["at"] + 1.0, bt["end"] - 0.1)
        page.evaluate("t => renderAt(t)", t)
        path = HERE / "build" / f"beat_{len(shots):02d}.png"
        page.screenshot(path=str(path)); shots.append((bt, t, path))
    b.close()
srv.shutdown()
W, H = 640, 360
sheet = Image.new("RGB", (W * 3, (H + 34) * ((len(shots) + 2) // 3)), "white")
font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 17)
for i, (bt, t, path) in enumerate(shots):
    x, y = (i % 3) * W, (i // 3) * (H + 34)
    sheet.paste(Image.open(path).resize((W, H)), (x, y + 34))
    ImageDraw.Draw(sheet).text((x + 6, y + 8), f"{t:5.1f}s  {bt['scene']}: \"{bt['needle']}\"", fill=(180, 0, 0), font=font)
sheet.save(HERE / "build" / "verify.jpg", quality=82)
print(len(shots), "beats ->", HERE / "build" / "verify.jpg")
