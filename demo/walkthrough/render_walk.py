"""Render the walkthrough: every frame from walk.html, the voice placed on its scenes, encoded to walkthrough.mp4.
    uv run --with playwright --with imageio-ffmpeg python demo/walkthrough/render_walk.py          # full video
    uv run --with playwright --with imageio-ffmpeg python demo/walkthrough/render_walk.py 12 90   # stills
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
BUILD = HERE / "build"
PORT = 8767
FF = imageio_ffmpeg.get_ffmpeg_exe()


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Quiet, directory=str(HERE)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def voice_track(tl: dict) -> Path:
    inputs, filters = [], []
    for i, s in enumerate(tl["scenes"]):
        inputs += ["-i", str(BUILD / "audio" / f"{s['id']}.wav")]
        filters.append(f"[{i}]adelay={int(s['voice_at'] * 1000)}:all=1[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(tl["scenes"])))
    filters.append(f"{mix}amix=inputs={len(tl['scenes'])}:normalize=0,apad=whole_dur={tl['duration']:.3f},"
                   "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11[out]")
    out = BUILD / "voice.wav"
    subprocess.run([FF, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]",
                    "-ar", "48000", "-ac", "2", str(out)], check=True)
    return out


def main(stills: list[float]):
    srv = serve()
    tl = json.loads((BUILD / "timeline.json").read_text())
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)
        page = b.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(f"http://127.0.0.1:{PORT}/walk.html")
        info = page.evaluate("load()")
        if stills:
            for t in stills:
                page.evaluate("t => renderAt(t)", t)
                page.screenshot(path=str(BUILD / f"still_{t:05.1f}.png"))
            print("stills", stills); b.close(); srv.shutdown(); return
        fps, n = info["fps"], round(info["duration"] * info["fps"])
        voice = voice_track(tl)
        out = HERE / "walkthrough.mp4"
        ff = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
                               "-i", str(voice), "-vf", "scale=out_range=tv:out_color_matrix=bt709,format=yuv420p",
                               "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                               "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-profile:v", "high", "-movflags", "+faststart",
                               "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], stdin=subprocess.PIPE)
        t0 = time.time()
        for i in range(n):
            page.evaluate("t => renderAt(t)", i / fps)
            ff.stdin.write(page.screenshot(type="jpeg", quality=93))
            if i % 600 == 0:
                print(f"frame {i}/{n}  {time.time() - t0:.0f}s", flush=True)
        ff.stdin.close(); ff.wait()
        b.close()
    srv.shutdown()
    print("wrote", out, "draft voice" if tl.get("draft") else "")


if __name__ == "__main__":
    main([float(x) for x in sys.argv[1:]])
