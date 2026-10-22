"""Exact word timings for the captions: Whisper (local, free) listens to each narration clip, and its words
are matched to the script's words. Captions show the script's own words and spelling, each timed by when
it is actually spoken; a script word Whisper missed is placed between its neighbours.

Writes build/words.json: {scene id: [[word, start, end], ...]} in seconds from the clip's start.
    uv run --with faster-whisper --with imageio-ffmpeg --with numpy python demo/walkthrough/align.py
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from faster_whisper import WhisperModel

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from script import SCENES  # noqa: E402

BUILD = HERE / "build"
FF = imageio_ffmpeg.get_ffmpeg_exe()


def load16k(path: Path) -> np.ndarray:
    raw = subprocess.run([FF, "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def main():
    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    out, report = {}, []
    for s in SCENES:
        clip = BUILD / "audio" / f"{s['id']}.wav"
        segs, _ = model.transcribe(load16k(clip), word_timestamps=True, language="en", vad_filter=False)
        heard = [(w.word.strip(), w.start, w.end) for seg in segs for w in seg.words]
        script = s["say"].split()
        a, b = [norm(w) for w in script], [norm(w[0]) for w in heard]
        times: list[tuple[float, float] | None] = [None] * len(script)
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    times[i1 + k] = (heard[j1 + k][1], heard[j1 + k][2])
            elif tag == "replace" and j2 > j1:          # e.g. "twenty two" heard as "22": spread over the span
                t0, t1 = heard[j1][1], heard[j2 - 1][2]
                n = i2 - i1
                for k in range(n):
                    times[i1 + k] = (t0 + (t1 - t0) * k / n, t0 + (t1 - t0) * (k + 1) / n)
        matched = sum(1 for t in times if t)
        # fill words Whisper skipped by interpolating between known neighbours
        for i, t in enumerate(times):
            if t is None:
                prev = next((times[j][1] for j in range(i - 1, -1, -1) if times[j]), 0.0)
                nxt = next((times[j][0] for j in range(i + 1, len(times)) if times[j]), prev + 0.3)
                times[i] = (prev, max(prev, nxt))
        out[s["id"]] = [[w, round(t[0], 3), round(t[1], 3)] for w, t in zip(script, times)]
        report.append((s["id"], matched, len(script)))
    (BUILD / "words.json").write_text(json.dumps(out, ensure_ascii=False))
    for sid, m, n in report:
        print(f"{sid:9} {m}/{n} words matched by Whisper ({m / n:.0%})")


if __name__ == "__main__":
    main()
