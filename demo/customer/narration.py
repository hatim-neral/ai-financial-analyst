"""The customer video's voice and timeline: one Gemini take (Despina), checked, cut at the words by Whisper,
which also times every caption word. Scene length = its line plus room; app scenes never shorter than the
footage their beats need. Writes build/audio/<id>.wav, build/words.json, build/timeline.json."""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import imageio_ffmpeg

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parent))
sys.path.append(str(HERE.parent / "walkthrough"))
from script import FPS, SCENES, STYLE, TITLES, TITLE_S, VOICE  # noqa: E402
from voice_gemini import make_lines  # noqa: E402
from whisper_cut import cut  # noqa: E402

BUILD = HERE / "build"
FF = imageio_ffmpeg.get_ffmpeg_exe()
LEAD = {"card": 1.0, "app": 0.25}
TAIL = {"card": 1.6, "app": 0.7}    # pauses stay short: the film runs straight through
TEMPO = 0.93       # a touch slower than the take, pitch unchanged


def seconds(p: Path) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def main():
    make_lines(SCENES, VOICE, BUILD / "audio", FF, style=STYLE, cut=False)
    cut(BUILD / "audio" / "gemini_take.wav", SCENES, BUILD / "audio", TEMPO)
    timeline, t = [], 0.0
    for s in SCENES:
        if s["id"] in TITLES:                    # a title card before the chapter, no voice
            n = len([x for x in timeline if x["kind"] == "title"]) + 1
            timeline.append(dict(id=f"title_{s['id']}", kind="title", chapter="", say="", title=TITLES[s["id"]], number=n,
                                 start=round(t, 3), length=TITLE_S, voice_at=round(t, 3), speech=0.0))
            t += TITLE_S
        speech = seconds(BUILD / "audio" / f"{s['id']}.wav")
        extra = {"hook": 0.6, "close": 3.0}.get(s["id"], 0.0)      # a beat after the hook line; the close holds on the logo
        length = round((LEAD[s["kind"]] + speech + TAIL[s["kind"]] + extra) * FPS) / FPS
        timeline.append(dict(s, start=round(t, 3), length=length, voice_at=round(t + LEAD[s["kind"]], 3), speech=round(speech, 3)))
        t += length
    (BUILD / "timeline.json").write_text(json.dumps({"fps": FPS, "duration": round(t, 3), "scenes": timeline}, indent=1))
    for sc in timeline:
        print(f"{sc['id']:7} {sc['start']:6.1f}s +{sc['length']:5.1f}s  speech {sc['speech']:5.1f}s")
    print(f"total {t:.1f}s ({t / 60:.2f} min)")


if __name__ == "__main__":
    main()
