"""Render the film: every frame from film.html, the soundtrack from mix.py, muxed into demo/film/film.mp4.

    uv run --with playwright --with imageio-ffmpeg --with numpy --with scipy python demo/film/render_film.py
    ... render_film.py 12 40.5 70        # stills at those seconds instead (build/still_*.png)
"""

from __future__ import annotations

import functools
import http.server
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
REPO = HERE.parents[1]
BUILD = HERE / "build"
PORT = 8766
FF = imageio_ffmpeg.get_ffmpeg_exe()


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Quiet, directory=str(REPO)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main(stills: list[float]):
    srv = serve()
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)
        page = b.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(f"http://127.0.0.1:{PORT}/demo/film/film.html")
        info = page.evaluate("load()")
        (BUILD / "events.json").write_text(json.dumps(page.evaluate("events()"), indent=0))
        if stills:
            for t in stills:
                page.evaluate("t => renderAt(t)", t)
                page.screenshot(path=str(BUILD / f"still_{t:05.1f}.png"))
            print("stills", stills)
            b.close(); srv.shutdown(); return
        fps, n = info["fps"], round(info["duration"] * info["fps"])
        video = BUILD / "film_video.mp4"
        ff = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
                               "-vf", "scale=out_range=tv:out_color_matrix=bt709,format=yuv420p",
                               "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                               "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high", str(video)], stdin=subprocess.PIPE)
        t0 = time.time()
        for i in range(n):
            page.evaluate("t => renderAt(t)", i / fps)
            ff.stdin.write(page.screenshot(type="jpeg", quality=95))
            if i % 300 == 0:
                print(f"frame {i}/{n}  {time.time() - t0:.0f}s", flush=True)
        ff.stdin.close(); ff.wait()
        b.close()
    srv.shutdown()
    subprocess.run([sys.executable, str(HERE / "mix.py")], check=True)
    out = HERE / "film.mp4"
    # a shareable encode (grain is costly at high quality) with the sound at -14 LUFS, the streaming norm
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(video), "-i", str(BUILD / "mix.wav"), "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "22", "-maxrate", "12M", "-bufsize", "24M", "-pix_fmt", "yuv420p",
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                    "-af", "loudnorm=I=-14:TP=-1.0:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "256k",
                    "-shortest", "-movflags", "+faststart", str(out)], check=True)
    print("wrote", out)


if __name__ == "__main__":
    main([float(x) for x in sys.argv[1:]])
