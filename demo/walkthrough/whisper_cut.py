"""Cut the narration take into scene clips at the words themselves, and time every caption word.

Whisper (local) transcribes the whole take with word timestamps; the script's words are matched to what it
heard. Each scene's clip runs from just before its first word to just after its last, cut in the middle of
the silence between scenes. The same matching gives every caption word its start and end, so the voice,
the captions and the scene they belong to always agree. (Guessing scene breaks from pause lengths, the
earlier method, put sentences in the wrong scenes: a long paragraph has pauses as long as a scene break.)

    from whisper_cut import cut
    cut(take_wav, scenes, out_dir, tempo)    # writes out_dir/<id>.wav and out_dir/../words.json
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np

FF = imageio_ffmpeg.get_ffmpeg_exe()
LEAD_IN, TAIL_OUT = 0.10, 0.30      # air kept before a scene's first word and after its last


def _load16k(path: Path) -> np.ndarray:
    raw = subprocess.run([FF, "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def align(take: Path, scenes: list[dict]) -> list[list[tuple[str, float, float]]]:
    """Per scene, the script's words with their times in the take (seconds)."""
    from faster_whisper import WhisperModel
    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(_load16k(take), word_timestamps=True, language="en")
    heard = [(w.word.strip(), w.start, w.end) for seg in segs for w in seg.words]
    words = [(w, i) for i, s in enumerate(scenes) for w in s["say"].split()]
    a, b = [_norm(w) for w, _ in words], [_norm(h[0]) for h in heard]
    times: list[tuple[float, float] | None] = [None] * len(words)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = heard[j1 + k][1:]
        elif tag == "replace" and j2 > j1:   # "six point nine eight" heard as "6.98": spread over the span
            t0, t1, n = heard[j1][1], heard[j2 - 1][2], i2 - i1
            for k in range(n):
                times[i1 + k] = (t0 + (t1 - t0) * k / n, t0 + (t1 - t0) * (k + 1) / n)
    matched = sum(1 for t in times if t) / len(times)
    if matched < 0.9:
        raise RuntimeError(f"only {matched:.0%} of the script was found in the take; is it the right take?")
    for i, t in enumerate(times):           # a word Whisper skipped sits between its neighbours
        if t is None:
            prev = next((times[j][1] for j in range(i - 1, -1, -1) if times[j]), 0.0)
            nxt = next((times[j][0] for j in range(i + 1, len(times)) if times[j]), prev + 0.3)
            times[i] = (prev, max(prev, nxt))
    per = [[] for _ in scenes]
    for (w, si), t in zip(words, times):
        per[si].append((w, t[0], t[1]))
    return per


def cut(take: Path, scenes: list[dict], out_dir: Path, tempo: float = 1.0) -> dict:
    per = align(take, scenes)
    with __import__("wave").open(str(take)) as w:
        total = w.getnframes() / w.getframerate()
    # the clip edges follow the sound: from the last silence before a scene's first word (Whisper can place a
    # first word a little late, which clipped its start) to the first silence after its last word
    import wave
    with wave.open(str(take)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        sr = w.getframerate()
    hop = sr // 50
    level = lambda t: 20 * np.log10(np.sqrt((x[max(0, int(t * sr)):max(0, int(t * sr)) + hop] ** 2).mean()) + 1e-9)

    def back_to_quiet(t, floor):
        quiet = 0
        while t > floor:
            quiet = quiet + 1 if level(t) < -45 else 0
            if quiet >= 6:
                return t + 6 * hop / sr
            t -= hop / sr
        return floor

    def on_to_quiet(t, ceil):
        quiet = 0
        while t < ceil:
            quiet = quiet + 1 if level(t) < -45 else 0
            if quiet >= 6:
                return t - 6 * hop / sr + 0.05
            t += hop / sr
        return ceil

    bounds = []
    for i, ws in enumerate(per):
        first, last = ws[0][1], ws[-1][2]
        lo = (per[i - 1][-1][2] + first) / 2 if i else 0.0                     # never past the middle of the gap
        hi = (last + per[i + 1][0][1]) / 2 if i + 1 < len(per) else total
        bounds.append((max(lo, back_to_quiet(first, lo) - LEAD_IN), min(hi, on_to_quiet(last, hi) + TAIL_OUT)))
    words = {}
    for s, ws, (c0, c1) in zip(scenes, per, bounds):
        af = f"atrim=start={c0:.3f}:end={c1:.3f},asetpts=PTS-STARTPTS" + (f",atempo={tempo}" if tempo != 1 else "")
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(take), "-af", af, "-ar", "48000", "-ac", "1",
                        str(out_dir / f"{s['id']}.wav")], check=True)
        words[s["id"]] = [[w, round((t0 - c0) / tempo, 3), round((t1 - c0) / tempo, 3)] for w, t0, t1 in ws]
    for s in scenes:                       # a word stretched across a silence starts where its sound starts
        words[s["id"]] = _onsets(out_dir / f"{s['id']}.wav", words[s["id"]])
    (out_dir.parent / "words.json").write_text(json.dumps(words, ensure_ascii=False))
    return words


def _onsets(clip: Path, ws: list) -> list:
    """Whisper sometimes starts a word at the end of the previous one, across a pause. For any word longer than
    0.5 s, move its start to the first 20 ms of real sound (above -35 dBFS) inside it."""
    import wave
    with wave.open(str(clip)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        sr = w.getframerate()
    hop = sr // 50
    out = []
    for word, a, b in ws:
        if b - a > 0.5:
            i0, i1 = int(a * sr), int(b * sr)
            db = [20 * np.log10(np.sqrt((x[i:i + hop] ** 2).mean()) + 1e-9) for i in range(i0, max(i0, i1 - hop), hop)]
            quiet = 0
            for k, d in enumerate(db):            # past a real pause (>= 0.15 s below -45 dB), start at the next sound
                quiet = quiet + 1 if d < -45 else (quiet if d < -35 else quiet)
                if quiet >= 8 and d > -35:
                    a = round((i0 + k * hop) / sr, 3)
                    break
                if d >= -35 and quiet < 8:
                    quiet = 0
        # the opposite case: sound starts after a pause but before the recorded start (a word squeezed to its end)
        prev_end = out[-1][2] if out else 0.0
        if a - prev_end > 0.2:
            j0, j1 = int(prev_end * sr), int(a * sr)
            db = [20 * np.log10(np.sqrt((x[i:i + hop] ** 2).mean()) + 1e-9) for i in range(j0, max(j0, j1 - hop), hop)]
            quiet = 0
            for k, d in enumerate(db):
                if d < -45:
                    quiet += 1
                elif d > -35 and quiet >= 5:
                    a = round((j0 + k * hop) / sr, 3)
                    break
        out.append([word, a, max(a, b)])
    return out
