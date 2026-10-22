"""Voice every scene's line, measure it, and write the timeline.

ENGINE in script.py picks the voice: "gemini" (one Gemini TTS take, see voice_gemini.py) or "say"
(macOS, offline). Output: demo/build/audio/<id>.wav per scene, demo/build/voice.wav (all lines on one track at their
start times) and demo/build/timeline.json (each scene's start and length in seconds).
"""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg

from script import ENGINE, FPS, PAD_S, QUESTION, RATE, SCENES, TEMPO, VOICE

ROOT = Path(__file__).parent
BUILD = ROOT / "build"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
MIN_S = {"card": 2.6, "app": 3.2}   # short lines still get time for their motion


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def main() -> None:
    (BUILD / "audio").mkdir(parents=True, exist_ok=True)
    timeline, t = [], 0.0
    if ENGINE == "gemini":
        from voice_gemini import make_lines
        make_lines(SCENES, VOICE, BUILD / "audio", FFMPEG)
        if TEMPO != 1:
            for s in SCENES:
                wav = BUILD / "audio" / f"{s['id']}.wav"
                tmp = wav.with_suffix(".tmp.wav")
                subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(wav), "-af", f"atempo={TEMPO}", str(tmp)], check=True)
                tmp.replace(wav)
    for s in SCENES:
        wav = BUILD / "audio" / f"{s['id']}.wav"
        if ENGINE == "say":
            aiff = BUILD / "audio" / f"{s['id']}.aiff"
            subprocess.run(["say", "-v", VOICE, "-r", str(RATE), "-o", str(aiff), s["say"]], check=True)
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(aiff), "-ar", "48000", "-ac", "1", str(wav)], check=True)
        speech = wav_seconds(wav)
        lead = 0.35 if s["kind"] == "app" else 0.5          # let the picture land before the voice
        length = max(MIN_S[s["kind"]], lead + speech + PAD_S)
        length = round(length * FPS) / FPS
        timeline.append(dict(s, start=round(t, 3), length=length, voice_at=round(t + lead, 3), speech=round(speech, 3)))
        t += length
    # one voice track: each line placed at its start
    inputs, filters = [], []
    for i, sc in enumerate(timeline):
        inputs += ["-i", str(BUILD / "audio" / f"{sc['id']}.wav")]
        filters.append(f"[{i}]adelay={int(sc['voice_at'] * 1000)}:all=1[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(timeline)))
    filters.append(f"{mix}amix=inputs={len(timeline)}:normalize=0,apad=whole_dur={t:.3f},"
                   "loudnorm=I=-16:TP=-1.5:LRA=11[out]")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters),
                    "-map", "[out]", "-ar", "48000", str(BUILD / "voice.wav")], check=True)
    (BUILD / "timeline.json").write_text(json.dumps({"fps": FPS, "duration": round(t, 3), "question": QUESTION, "scenes": timeline}, indent=1))
    for sc in timeline:
        print(f"{sc['id']:9} {sc['start']:6.2f}s  +{sc['length']:5.2f}s  (speech {sc['speech']:.2f}s)")
    print(f"total {t:.2f}s")


if __name__ == "__main__":
    main()
