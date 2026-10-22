"""The film's soundtrack: voice on top, the score ducked under it, and sound effects on the edit's events.

Effects are synthesised here: whoosh (cuts), hit (the drop), ding (a figure lands), tick (the counter),
key and send (typing the question), stamp (the verified stamp), pop (the plan is saved).
Reads build/timeline.json, build/score.wav, build/audio/*.wav and build/events.json; writes build/mix.wav.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
BUILD = Path(__file__).parent / "build"
rng = np.random.default_rng(3)


def read(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64) / 32768
        x = x.reshape(-1, w.getnchannels()).T
        assert w.getframerate() == SR, f"{path} is not {SR} Hz"
    return x if x.shape[0] == 2 else np.vstack([x, x])


def filt(x, kind, f):
    return sosfilt(butter(2, f, kind, fs=SR, output="sos"), x)


def whoosh(v=1.0):
    n = int(0.9 * SR); t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    for i in range(12):                           # a band that sweeps up and back down
        seg = (t >= i * 0.075) & (t < (i + 1) * 0.075)
        f = 400 + 3200 * np.sin(np.pi * (i + .5) / 12)
        out += filt(noise, "band", [f * .6, f * 1.4]) * seg
    return out * np.sin(np.pi * t / t[-1]) ** 2 * 0.22 * v


def hit(v=1.0):
    n = int(1.6 * SR); t = np.arange(n) / SR
    body = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-t * 9)) / SR) * np.exp(-t * 2.4)
    crack = filt(rng.standard_normal(n), "high", 1500) * np.exp(-t * 26) * .35
    return np.tanh((body + crack) * 1.3) * 0.55 * v


def ding(v=1.0):
    n = int(1.8 * SR); t = np.arange(n) / SR
    f = 1318.5
    x = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t * d) for a, r, d in ((1, 1, 3.2), (.5, 2.76, 6), (.3, 5.4, 9), (.2, .5, 2.5)))
    return x * 0.11 * v


def tick(v=1.0):
    n = int(0.03 * SR); t = np.arange(n) / SR
    return filt(rng.standard_normal(n), "band", [2500, 7000]) * np.exp(-t * 300) * 0.25 * v


def key(v=1.0):
    n = int(0.05 * SR); t = np.arange(n) / SR
    click = filt(rng.standard_normal(n), "band", [1800, 6000]) * np.exp(-t * 180)
    thock = np.sin(2 * np.pi * 180 * t) * np.exp(-t * 90) * .4
    return (click + thock) * 0.16 * v


def send(v=1.0):
    n = int(0.35 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * np.cumsum(500 + 900 * t / t[-1]) / SR) * np.exp(-t * 9) * 0.12 * v


def stamp(v=1.0):
    n = int(0.6 * SR); t = np.arange(n) / SR
    thud = np.sin(2 * np.pi * np.cumsum(60 + 90 * np.exp(-t * 40)) / SR) * np.exp(-t * 12)
    slap = filt(rng.standard_normal(n), "band", [300, 2500]) * np.exp(-t * 55) * .7
    return np.tanh((thud + slap) * 1.6) * 0.42 * v


def pop(v=1.0):
    n = int(1.2 * SR); t = np.arange(n) / SR
    burst = filt(rng.standard_normal(n), "band", [900, 6000]) * np.exp(-t * 35) * .4
    sparkle = sum(np.sin(2 * np.pi * f * t) * np.exp(-np.clip(t - d, 0, None) * 8) * (t >= d) for f, d in ((1568, .03), (2093, .09), (2637, .15)))
    return (burst + sparkle * .35) * 0.25 * v


FX = dict(whoosh=whoosh, hit=hit, ding=ding, tick=tick, key=key, send=send, stamp=stamp, pop=pop)


def place(bus, x, at, pan=0.0):
    i = int(at * SR)
    if i < 0 or i >= bus.shape[1]:
        return
    x = x[: bus.shape[1] - i]
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    bus[0, i:i + len(x)] += x * l * 1.41
    bus[1, i:i + len(x)] += x * r * 1.41


def main():
    tl = json.loads((BUILD / "timeline.json").read_text())
    n = int((tl["duration"] + 0.5) * SR)
    voice = np.zeros((2, n))
    for s in tl["scenes"]:
        clip = BUILD / "audio" / f"{s['id']}.wav"
        if not s.get("say") or not clip.exists():      # title cards carry no voice
            continue
        place(voice, read(clip)[0], s["voice_at"])
    voice = filt(voice, "high", 80)
    voice *= 10 ** ((-16 - 20 * np.log10(np.sqrt((voice[voice != 0] ** 2).mean()) + 1e-9)) / 20)   # speech at about -16 dBFS RMS

    music = read(BUILD / "score.wav")
    music = np.pad(music, ((0, 0), (0, max(0, n - music.shape[1]))))[:, :n]
    # duck the score under the voice: 8 dB down while she speaks, with soft edges
    env = np.abs(voice[0])
    env = filt(env, "low", 4)
    gate = np.clip(env / (np.percentile(env[env > 1e-4], 60) + 1e-9), 0, 1)
    duck = 10 ** (-8 * gate / 20)
    music *= duck * 0.85

    fx = np.zeros((2, n))
    for e in json.loads((BUILD / "events.json").read_text()):
        pan = (rng.random() - .5) * .5 if e["kind"] in ("key", "tick") else 0
        place(fx, FX[e["kind"]](e.get("v", 1.0)), e["t"], pan)

    mixdown = voice + music + fx
    peak = np.abs(mixdown).max()
    if peak > 0.97:                              # gentle limiting
        mixdown = np.tanh(mixdown / peak * 2.2) / np.tanh(2.2) * 0.97
    pcm = (np.clip(mixdown, -1, 1).T * 32767).astype(np.int16)
    with wave.open(str(BUILD / "mix.wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    print("mix", round(n / SR, 2), "s, peak", round(20 * np.log10(np.abs(mixdown).max()), 1), "dB")


if __name__ == "__main__":
    main()
