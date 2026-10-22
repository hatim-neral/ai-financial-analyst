"""The narration in one Gemini TTS take, checked, then cut into one clip per scene.

One request for the whole script keeps the voice consistent and fits the free tier (10 speech
requests a day per model). Each scene's line is its own paragraph, and the notes ask for a long
pause between paragraphs; the take is cut at the longest silences. Before anything is used, the take is
transcribed (a separate Gemini text model) and compared with the script, because a TTS take
occasionally repeats a line or reads the notes aloud. A bad take is retried.

The finished take is cached in build/audio/gemini_take.wav with the script's hash, so rerunning
narration.py costs no requests unless the words or the voice change.
"""

from __future__ import annotations

import array
import base64
import difflib
import hashlib
import json
import math
import re
import subprocess
import time
import tomllib
import unicodedata
import wave
from pathlib import Path

import requests

from gemini_tts import SECRETS, speak

TTS_MODELS = ("gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-pro-preview-tts")
CHECK_MODELS = ("gemini-3.5-flash-lite", "gemini-3.5-flash")
STYLE = ("Style: the narrator of a polished product launch video. Warm, confident, conversational, "
         "like a real person who loves the product, with a light smile in the voice. Not salesy.\n"
         "Pacing: natural and unhurried, brief pauses at commas and full stops, and a long pause of "
         "two full seconds between paragraphs.\n"
         "Speak only the transcript below, exactly once, in order.")


NUMBER_WORDS = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
                   "seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand "
                   "lakh point percent and".split())


def _words(text: str) -> list[str]:
    """Words to compare a take with its script. Transcribers write "674" for "six hundred and seventy-four"
    and drop accents, so numbers (in digits or words) and accents are left out of the comparison."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    words = re.sub(r"[^a-z0-9 ]", " ", text.replace("'", "").replace("-", " ").replace("%", " percent ")).split()
    words = " ".join(words).replace("in to ", "into ").split()
    return [w for w in words if not w.isdigit() and w not in NUMBER_WORDS]


def transcribe(path: Path) -> str:
    key = tomllib.load(SECRETS.open("rb"))["GEMINI_API_KEY"]
    audio = base64.b64encode(path.read_bytes()).decode()
    for m in CHECK_MODELS * 3:                        # the free tier blips now and then
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                          headers={"x-goog-api-key": key}, timeout=180,
                          json={"contents": [{"parts": [{"inlineData": {"mimeType": "audio/wav", "data": audio}},
                                                        {"text": "Transcribe this audio word for word. Output only the words."}]}]})
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        time.sleep(5)
    raise RuntimeError("could not transcribe the take to check it")


def _samples(path: Path) -> tuple[array.array, int]:
    with wave.open(str(path)) as w:
        assert w.getsampwidth() == 2 and w.getnchannels() == 1, "expected 16-bit mono"
        return array.array("h", w.readframes(w.getnframes())), w.getframerate()


def cut_points(path: Path, n_cuts: int, lines: list[str]) -> list[tuple[int, int]]:
    """(start, end) sample ranges of each line: cut at the n longest silences, checked against line lengths."""
    a, rate = _samples(path)
    hop = rate // 50                                   # 20 ms frames
    db = [20 * math.log10(max(1.0, math.sqrt(sum(x * x for x in a[i:i + hop]) / hop)) / 32768) for i in range(0, len(a) - hop, hop)]
    quiet = [d < -42 for d in db]
    runs, i = [], 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    voiced = [k for k, q in enumerate(quiet) if not q]
    first, last = voiced[0], voiced[-1] + 1
    inner = [r for r in runs if r[0] > first and r[1] < last]
    if len(inner) < n_cuts:
        raise RuntimeError(f"found {len(inner)} pauses, need {n_cuts}")
    # Each paragraph break is expected where its share of the script's characters says. A long
    # paragraph can hold pauses as long as the breaks, so take the longest pause near each expected
    # point, in order, rather than the longest pauses overall.
    total_chars, acc, cuts = sum(len(l) for l in lines), 0, []
    span_frames = last - first
    for i in range(n_cuts):
        acc += len(lines[i])
        expect = first + span_frames * acc / total_chars
        after = cuts[-1][1] if cuts else first
        window = [r for r in inner if r[0] > after and abs((r[0] + r[1]) / 2 - expect) < span_frames * 0.06 + 50]
        if not window:
            window = [r for r in inner if r[0] > after]
        cuts.append(max(window, key=lambda r: (r[1] - r[0]) - abs((r[0] + r[1]) / 2 - expect) * 0.02))
    bounds, s = [], first
    for c0, c1 in cuts:
        bounds.append((s, c0)); s = c1
    bounds.append((s, last))
    # each piece must be roughly as long as its line (catches a cut inside a sentence)
    per_char = (sum(b - a_ for a_, b in bounds)) / sum(len(l) for l in lines)
    for (b0, b1), line in zip(bounds, lines):
        ratio = (b1 - b0) / (len(line) * per_char)
        if not 0.55 < ratio < 1.8:
            raise RuntimeError(f"a cut looks wrong near: {line[:40]!r} (length ratio {ratio:.2f})")
    pad = hop * 4                                      # keep 80 ms of air around each line
    return [(max(0, b0 * hop - pad), min(len(a), b1 * hop + pad)) for b0, b1 in bounds]


def make_lines(scenes: list[dict], voice: str, out_dir: Path, ffmpeg: str, tries: int = 3, style: str = STYLE,
               cut: bool = True) -> None:
    """cut=False: get and check the take only (whisper_cut.cut does the cutting)."""
    lines = [s["say"] for s in scenes]
    script = "\n\n".join(lines)
    digest = hashlib.sha256(f"{voice}|{style}|{script}".encode()).hexdigest()[:16]
    take, meta = out_dir / "gemini_take.wav", out_dir / "gemini_take.json"
    cached = meta.exists() and json.loads(meta.read_text()).get("hash") == digest and take.exists()

    def check(model: str) -> bool:
        heard = transcribe(take)
        score = difflib.SequenceMatcher(None, _words(script), _words(heard)).ratio()
        print(f"   take on {model}: transcript matches the script {score:.0%}")
        if score >= 0.93:
            meta.write_text(json.dumps({"hash": digest, "model": model, "match": round(score, 3), "heard": heard}, indent=1))
        return score >= 0.93

    if not cached and take.exists() and not meta.exists():   # a take from a run that stopped before its check
        cached = check("an earlier run")
    if not cached:
        for attempt in range(tries):
            model = TTS_MODELS[0]
            for m in TTS_MODELS:
                try:
                    speak(script, voice, take, style=style, model=m, tries=2)
                    model = m
                    break
                except RuntimeError as exc:
                    print(f"   {m}: {exc}")
            else:
                raise RuntimeError("no Gemini speech model has quota left today")
            if check(model):
                break
        else:
            raise RuntimeError("every take differed from the script; try again later")
    else:
        print("   using the cached Gemini take")
    if not cut:
        return
    a, rate = _samples(take)
    for s, (b0, b1) in zip(scenes, cut_points(take, len(lines) - 1, lines)):
        raw = out_dir / f"{s['id']}_raw.wav"
        with wave.open(str(raw), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(a[b0:b1].tobytes())
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raw), "-ar", "48000", "-ac", "1",
                        str(out_dir / f"{s['id']}.wav")], check=True)
        raw.unlink()
