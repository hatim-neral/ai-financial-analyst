"""Render the customer film: frames from customer.html, the score, the voice and the effects mixed, then encoded.
    uv run --with playwright --with imageio-ffmpeg --with numpy --with scipy python demo/customer/render_customer.py [stills...]"""

from __future__ import annotations

import functools, http.server, importlib.util, json, subprocess, sys, threading, time
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
REPO = HERE.parents[1]
BUILD = HERE / "build"
FF = imageio_ffmpeg.get_ffmpeg_exe()
PORT = 8769


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Quiet, directory=str(REPO)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def mix():
    spec = importlib.util.spec_from_file_location("film_mix", HERE.parent / "film" / "mix.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    m.BUILD = BUILD
    m.main()


def main(stills):
    srv = serve()
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)
        page = b.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(f"http://127.0.0.1:{PORT}/demo/customer/customer.html")
        info = page.evaluate("load()")
        (BUILD / "events.json").write_text(json.dumps(page.evaluate("events()")))
        if stills:
            for t in stills:
                page.evaluate("t => renderAt(t)", t); page.screenshot(path=str(BUILD / f"still_{t:05.1f}.png"))
            print("stills", stills); b.close(); srv.shutdown(); return
        fps, n = info["fps"], round(info["duration"] * info["fps"])
        video = BUILD / "video.mp4"
        ff = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
                               "-vf", "scale=out_range=tv:out_color_matrix=bt709,format=yuv420p", "-colorspace", "bt709",
                               "-color_primaries", "bt709", "-color_trc", "bt709", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                               str(video)], stdin=subprocess.PIPE)
        t0 = time.time()
        for i in range(n):
            page.evaluate("t => renderAt(t)", i / fps)
            ff.stdin.write(page.screenshot(type="jpeg", quality=94))
            if i % 900 == 0:
                print(f"frame {i}/{n} {time.time() - t0:.0f}s", flush=True)
        ff.stdin.close(); ff.wait(); b.close()
    srv.shutdown()
    mix()
    out = HERE / "ai-financial-analyst.mp4"
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(video), "-i", str(BUILD / "mix.wav"), "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-maxrate", "10M", "-bufsize", "20M", "-pix_fmt", "yuv420p",
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                    "-af", "loudnorm=I=-14:TP=-1.0:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "256k", "-shortest",
                    "-movflags", "+faststart", str(out)], check=True)
    print("wrote", out)


if __name__ == "__main__":
    main([float(x) for x in sys.argv[1:]])
