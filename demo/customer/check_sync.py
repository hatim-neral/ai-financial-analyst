"""After rendering: listen to the finished video and measure caption timing and scene placement.
For every script word: when Whisper hears it in walkthrough.mp4 vs when its caption lights up."""

import difflib, json, re, statistics, subprocess, sys
from pathlib import Path
import imageio_ffmpeg, numpy as np
from faster_whisper import WhisperModel

HERE = Path(__file__).parent
tl = json.loads((HERE / "build" / "timeline.json").read_text())
words = json.loads((HERE / "build" / "words.json").read_text())
raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", str(HERE / "ai-financial-analyst.mp4"), "-vn", "-ac", "1",
                      "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
segs, _ = WhisperModel("small.en", device="cpu", compute_type="int8").transcribe(audio, word_timestamps=True, language="en")
heard = [(w.word.strip(), w.start) for s in segs for w in s.words]
norm = lambda w: re.sub(r"[^a-z0-9]", "", w.lower())
expected = [(w, s["voice_at"] + a, s) for s in tl["scenes"] for w, a, b in words.get(s["id"], [])]
sm = difflib.SequenceMatcher(None, [norm(e[0]) for e in expected], [norm(h[0]) for h in heard], autojunk=False)
offs, outside, n = [], [], 0
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag != "equal":
        continue
    for k in range(i2 - i1):
        w, cap_t, s = expected[i1 + k]
        t = heard[j1 + k][1]
        offs.append(cap_t - t); n += 1
        if not (s["start"] - .05 <= t < s["start"] + s["length"] + .05):
            outside.append((s["id"], w, round(t, 2)))
offs_ms = [abs(o) * 1000 for o in offs]
print(f"words heard and matched: {n}/{len(expected)} ({n / len(expected):.0%})")
print(f"caption vs spoken: median {statistics.median(offs_ms):.0f} ms, 95% within {sorted(offs_ms)[int(.95 * len(offs_ms))]:.0f} ms, "
      f"worst {max(offs_ms):.0f} ms; mean signed {statistics.mean(offs) * 1000:+.0f} ms (+ = caption late)")
print("words spoken outside their own scene:", len(outside), outside[:5])

worst = sorted(((abs(o), w, s["id"]) for o, (w, _, s) in zip(offs, [e for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag == "equal" for e in expected[i1:i2]])), reverse=True)[:5]
print("largest offsets:", [(w, sid, f"{d * 1000:.0f} ms") for d, w, sid in worst])
