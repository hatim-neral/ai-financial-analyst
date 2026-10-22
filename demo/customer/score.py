"""The customer film's score, synthesised from scratch (the film's instruments, a new arrangement), locked to
the timeline: a reflective piano hook that builds into the reveal, a light warm pulse under the app (kept
quiet: it sits under four minutes of voice), a soft accent on every chapter card, and a resolving close.
Ours, so no licence. Writes build/score.wav."""

from __future__ import annotations

import importlib.util
import json
import wave
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve

HERE = Path(__file__).parent
_spec = importlib.util.spec_from_file_location("film_score", HERE.parent / "film" / "score.py")
F = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(F)
SR = F.SR
BPM = 96
BEAT = 60 / BPM
BAR = 4 * BEAT
HOOK = [(57, [57, 60, 64, 71]), (53, [53, 57, 60, 64]), (48, [48, 55, 60, 64]), (47, [47, 55, 59, 62])]
BODY = [(48, [48, 55, 60, 64]), (43, [43, 50, 55, 59]), (45, [45, 52, 57, 60]), (41, [41, 48, 53, 57])]
CLOSE = [(48, [48, 55, 59, 64]), (41, [41, 48, 53, 57, 64]), (43, [43, 50, 55, 59, 62]), (48, [48, 55, 60, 64, 67])]


def main():
    tl = json.loads((HERE / "build" / "timeline.json").read_text())
    sc = {s["id"]: s for s in tl["scenes"]}
    total = tl["duration"]
    T = F.Track(total)
    drop, close0 = sc["meet"]["start"], sc["close"]["start"]

    # hook: felt piano and a slow pad, a room tone, a riser into the reveal
    T.add(F.room(drop + 1.0, 0.015), 0)
    t, b = 0.6, 0
    while t < drop - BEAT:
        root, ch = HOOK[(b // 2) % 4]
        if b % 2 == 0:
            T.add(F.piano(root - 12, BAR * 2, 0.3), t, send=0.45)
            T.add(F.pad(ch, BAR * 2 + .5, 0.13, 900), t, send=0.5)
        for off, m in ((0, ch[1]), (1.5, ch[2]), (2.5, ch[3]), (3.25, ch[2])):
            if t + off * BEAT < drop - BEAT:
                T.add(F.piano(m, BEAT * 1.5, 0.2), t + off * BEAT, pan=.15, send=0.55)
        t += BAR; b += 1
    rise = min(6.0, drop - 1.0)
    T.add(F.riser(rise - BEAT * .5, 0.26), drop - rise, send=0.3)
    T.add(F.impact(0.7), drop, send=0.4)

    # body: a light pulse; drops to pad and piano under each title card
    titles = [(s["start"], s["start"] + s["length"]) for s in tl["scenes"] if s["kind"] == "title"]
    nb = int((close0 - drop) / BEAT)
    for i in range(nb):
        t0 = drop + i * BEAT
        on_title = any(a <= t0 < b for a, b in titles)
        bar_i, pos = i // 4, i % 4
        root, ch = BODY[bar_i % 4]
        if not on_title:
            if pos in (0, 2):
                T.add(F.kick(0.42), t0, bus="drums")
            T.add(F.hat(0.035), t0 + BEAT / 2, bus="drums", pan=.3)
            T.add(F.bass(root - 12, BEAT * .9, 0.26), t0, bus="side")
            arp = [ch[0] + 24, ch[2] + 12, ch[3] + 12, ch[1] + 24]
            for q in range(2):
                T.add(F.pluck(arp[(pos * 2 + q) % 4], BEAT / 2, 0.055), t0 + q * BEAT / 2, pan=.35 * (1 if q else -1), send=.4)
        if pos == 0:
            T.add(F.pad(ch, BAR + .4, 0.15 if not on_title else 0.2, 1600), t0, bus="side", send=.5)
            T.add(F.piano(ch[0] + 12, BAR, 0.14), t0, pan=-.15, send=.45)
    for a, _ in titles:
        T.add(F.impact(0.32), a, send=0.4)
        T.add(F.hat(0.08, True), a, bus="drums", send=0.3)

    # close: resolve and ring out
    n_bars = max(4, int(round((total - close0) / BAR)))
    prog = [CLOSE[i % 3] for i in range(n_bars - 1)] + [CLOSE[3]]
    for b, (root, ch) in enumerate(prog):
        t0 = close0 + b * BAR
        last = b == len(prog) - 1
        T.add(F.piano(root - 12, BAR * (3 if last else 1), 0.28), t0, send=.5)
        for j, m in enumerate(ch[1:]):
            T.add(F.piano(m + 12, BAR * (3 if last else 1), 0.16), t0 + j * BEAT * (.12 if last else .5), pan=.2, send=.6)
        T.add(F.pad(ch, BAR * (3 if last else 1) + .6, 0.16, 1300), t0, send=.6)

    # mix: duck the bass and pad to the kick, reverb, gentle master
    env = F.lp(np.abs(T.bus["drums"][0]), 12)
    duck = 1 - 0.4 * np.clip(env / (env.max() + 1e-9) * 3, 0, 1)
    side = T.bus["side"] * duck
    ir = F.reverb_ir()
    verb = np.stack([fftconvolve(T.bus["verb"][c], ir[c])[: T.n] for c in range(2)])
    mix = F.hp(T.bus["dry"] + side + T.bus["drums"] * .85 + verb * .55, 28)
    end = int(total * SR)
    mix = mix[:, :end]
    fade = int(3.0 * SR); mix[:, -fade:] *= np.linspace(1, 0, fade) ** 1.5
    mix = np.tanh(mix / np.abs(mix).max() * 1.4) / np.tanh(1.4) * .89
    with wave.open(str(HERE / "build" / "score.wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix.T * 32767).astype(np.int16).tobytes())
    print("score", round(end / SR, 1), "s, drop at", drop)


if __name__ == "__main__":
    main()
