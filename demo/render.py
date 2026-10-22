"""Render compose.html frame by frame and encode demo.mp4 with the voice track.

    uv run --with playwright --with imageio-ffmpeg python demo/render.py            # full video
    uv run --with playwright --with imageio-ffmpeg python demo/render.py 12.5 40    # stills at those seconds
"""

from __future__ import annotations

import functools
import http.server
import subprocess
import sys
import threading
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
BUILD = ROOT / "build"
PORT = 8765


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    handler = functools.partial(Quiet, directory=str(ROOT))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main(stills: list[float]):
    srv = serve()
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)
        page = b.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(f"http://127.0.0.1:{PORT}/compose.html")
        info = page.evaluate("load()")
        if stills:
            for t in stills:
                page.evaluate("t => renderAt(t)", t)
                page.screenshot(path=str(BUILD / f"still_{t:05.1f}.png"))
                print("still", t)
            b.close(); srv.shutdown(); return
        fps, dur = info["fps"], info["duration"]
        n = round(dur * fps)
        out = ROOT / "demo.mp4"
        ff = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
                               "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
                               "-i", str(BUILD / "voice.wav"),
                               "-vf", "scale=out_range=tv:out_color_matrix=bt709,format=yuv420p",   # standard range, so players don't wash it out
                               "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                               "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                               "-profile:v", "high", "-movflags", "+faststart",
                               "-c:a", "aac", "-b:a", "192k", "-ac", "2",  # stereo plays everywhere
                               "-shortest", str(out)], stdin=subprocess.PIPE)
        t0 = time.time()
        for i in range(n):
            page.evaluate("t => renderAt(t)", i / fps)
            ff.stdin.write(page.screenshot(type="jpeg", quality=94))
            if i % 150 == 0:
                print(f"frame {i}/{n}  {time.time() - t0:.0f}s", flush=True)
        ff.stdin.close(); ff.wait()
        b.close()
    srv.shutdown()
    print("wrote", out)


if __name__ == "__main__":
    main([float(x) for x in sys.argv[1:]])
