"""The walkthrough's voice and timeline.

    python narration.py            # Gemini voice (one take, checked, cut per scene)
    python narration.py --draft    # macOS `say`, offline: for building and previewing the edit

Scene length = the line plus room to breathe, and never shorter than its footage can sensibly be shown
(footage plays at up to 1.35x; anything longer than that is held at the shot's key moments by the
compositor). Writes build/audio/<id>.wav and build/timeline.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

import imageio_ffmpeg

HERE = Path(__file__).parent
sys.path.append(str(HERE.parent))
from voice_gemini import make_lines  # noqa: E402

from script import FPS, SCENES, STYLE, VOICE  # noqa: E402

BUILD = HERE / "build"
FF = imageio_ffmpeg.get_ffmpeg_exe()
LEAD = {"card": 0.6, "app": 0.4}
TAIL = 1.4
TEMPO = 0.94        # a touch slower than the take: clearer for a technical walkthrough, and lands near 5 minutes
MAX_SPEED = 1.35
FF_WAIT = 1.6        # an AI wait is fast-forwarded to this many seconds


def seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def footage_need(shot: str, marks: dict) -> float:
    """Shortest sensible screen time for a shot: real time over MAX_SPEED, with AI waits fast-forwarded."""
    m = marks[shot]
    real = m["t1"] - m["t0"]
    if "wait0" in m and "answer0" in m:
        real -= (m["answer0"] - m["wait0"]) - FF_WAIT * MAX_SPEED
    return real / MAX_SPEED


def main(draft: bool) -> None:
    (BUILD / "audio").mkdir(parents=True, exist_ok=True)
    if draft:
        for s in SCENES:
            aiff, wav = BUILD / "audio" / f"{s['id']}.aiff", BUILD / "audio" / f"{s['id']}.wav"
            subprocess.run(["say", "-v", "Samantha", "-r", "165", "-o", str(aiff), s["say"]], check=True)
            subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(aiff), "-ar", "48000", "-ac", "1", str(wav)], check=True)
    else:
        make_lines(SCENES, VOICE, BUILD / "audio", FF, style=STYLE)     # the take: requested once, checked, cached
        # re-cut it at the words themselves (Whisper), which also times every caption word
        from whisper_cut import cut
        cut(BUILD / "audio" / "gemini_take.wav", SCENES, BUILD / "audio", TEMPO)
    marks = json.loads((BUILD / "marks_walk.json").read_text())
    timeline, t = [], 0.0
    for s in SCENES:
        speech = seconds(BUILD / "audio" / f"{s['id']}.wav")
        length = LEAD[s["kind"]] + speech + TAIL
        if s["kind"] == "app":
            length = max(length, footage_need(s["shot"], marks))
        else:
            length = max(length, 4.0)
        length = round(length * FPS) / FPS
        timeline.append(dict(s, start=round(t, 3), length=length, voice_at=round(t + LEAD[s["kind"]], 3), speech=round(speech, 3)))
        t += length
    (BUILD / "timeline.json").write_text(json.dumps({"fps": FPS, "duration": round(t, 3), "ff_wait": FF_WAIT,
                                                     "draft": draft, "scenes": timeline}, indent=1))
    for sc in timeline:
        print(f"{sc['id']:9} {sc['start']:6.1f}s +{sc['length']:5.1f}s  speech {sc['speech']:5.1f}s")
    print(f"total {t:.1f}s ({t / 60:.2f} min){'  [draft voice]' if draft else ''}")


if __name__ == "__main__":
    main("--draft" in sys.argv)
