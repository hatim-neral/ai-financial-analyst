"""The film's voice (one Gemini take, cut per scene) and its beat-locked timeline.

Every scene starts on a beat of the score; the first scene of each act starts on a bar, so the
music's sections line up with the story. Writes film/build/audio/<id>.wav and film/build/timeline.json.
"""

from __future__ import annotations

import json
import math
import sys
import wave
from pathlib import Path

import imageio_ffmpeg

HERE = Path(__file__).parent
sys.path.append(str(HERE.parent))   # voice_gemini; after this folder, so script.py is the film's
from voice_gemini import make_lines  # noqa: E402

from script import BPM, FPS, QUESTION, SCENES, STYLE, VOICE  # noqa: E402

BUILD = HERE / "build"
BEAT = 60 / BPM
BAR = 4 * BEAT
LEAD = {"night": 0.9, "build": 0.5, "day": 0.45, "morning": 0.7}   # picture first, then the voice
TAIL = {"night": 1.2, "build": 0.6, "day": 0.55, "morning": 1.0}   # room to breathe after the line
EXTRA = {"night": 2.5, "ask_books": 0.0, "question": 1.2, "answer": 2.2, "plan": 1.2, "yours": 1.4, "logo": 2.0}  # held picture beyond the line


def seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def own_take(s: dict, ffmpeg: str) -> None:
    """One line in its own request, checked against its words, trimmed, cached by its text."""
    import difflib
    import hashlib
    import subprocess
    from gemini_tts import speak
    from voice_gemini import TTS_MODELS, _words, transcribe
    style = STYLE.replace("Pause for two full seconds between paragraphs.\n", "") + \
        "\nThis is the closing line of the film: warm, inviting, a gentle smile."
    digest = hashlib.sha256(f"{VOICE}|{style}|{s['say']}".encode()).hexdigest()[:16]
    raw, out, meta = BUILD / "audio" / f"{s['id']}_take.wav", BUILD / "audio" / f"{s['id']}.wav", BUILD / "audio" / f"{s['id']}.json"
    if meta.exists() and json.loads(meta.read_text()).get("hash") == digest and out.exists():
        return
    for attempt in range(3):
        for m in TTS_MODELS:
            try:
                speak(s["say"], VOICE, raw, style=style, model=m, tries=2)
                break
            except RuntimeError as exc:
                print(f"   {m}: {exc}")
        else:
            raise RuntimeError("no Gemini speech model has quota left today")
        heard = transcribe(raw)
        score = difflib.SequenceMatcher(None, _words(s["say"]), _words(heard)).ratio()
        print(f"   {s['id']}: transcript matches {score:.0%} ({heard.strip()!r})")
        if score >= 0.93:
            break
    else:
        raise RuntimeError(f"the {s['id']} line kept coming out wrong")
    # trim silence at both ends, resample like the other lines
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(raw), "-af",
                    "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                    "adelay=80:all=1,apad=pad_dur=0.08", "-ar", "48000", "-ac", "1", str(out)], check=True)
    meta.write_text(json.dumps({"hash": digest, "heard": heard}))


def main() -> None:
    (BUILD / "audio").mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    make_lines([s for s in SCENES if not s.get("own_take")], VOICE, BUILD / "audio", ffmpeg, style=STYLE)
    for s in SCENES:
        if s.get("own_take"):
            own_take(s, ffmpeg)
    timeline, t = [], 0.0
    for i, s in enumerate(SCENES):
        speech = seconds(BUILD / "audio" / f"{s['id']}.wav")
        want = LEAD[s["act"]] + speech + TAIL[s["act"]] + EXTRA.get(s["id"], 0)
        nxt = SCENES[i + 1] if i + 1 < len(SCENES) else None
        unit = BAR if (nxt and nxt["act"] != s["act"]) or not nxt else BEAT   # an act ends on a bar line
        length = math.ceil((t + want) / unit - 1e-6) * unit - t
        timeline.append(dict(s, start=round(t, 4), length=round(length, 4), voice_at=round(t + LEAD[s["act"]], 4), speech=round(speech, 3)))
        t += length
    acts = {}
    for sc in timeline:
        acts.setdefault(sc["act"], [sc["start"], 0]); acts[sc["act"]][1] = sc["start"] + sc["length"]
    (BUILD / "timeline.json").write_text(json.dumps({"fps": FPS, "bpm": BPM, "beat": BEAT, "duration": round(t, 4),
                                                     "question": QUESTION, "acts": acts, "scenes": timeline}, indent=1))
    for sc in timeline:
        print(f"{sc['id']:10} {sc['act']:8} {sc['start']:6.2f}s +{sc['length']:5.2f}s  speech {sc['speech']:.2f}s")
    print("acts", {k: [round(a, 2), round(b, 2)] for k, (a, b) in acts.items()}, "total", round(t, 2))


if __name__ == "__main__":
    main()
