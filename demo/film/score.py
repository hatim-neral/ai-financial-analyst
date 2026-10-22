"""An original score for the film, synthesised from scratch and locked to its timeline.

96 bpm. Night (A minor): sparse felt piano, a slow pad, a quiet room tone. Build: an arpeggio that
speeds up, a rising noise sweep and a heartbeat kick, then half a beat of silence. Day (C major): the
pulse, with kick, soft clap, hats, a pumping bass, a plucked arpeggio and the pad, and an impact on the
leak, and a breakdown while she types the question. Morning: piano and pad resolve to C and ring out.

Everything here is ours, so the music carries no licence. Writes film/build/score.wav (48 kHz
stereo) and film/build/beats.json (the beat grid and the musical hits, for the edit).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
HERE = Path(__file__).parent
BUILD = HERE / "build"
rng = np.random.default_rng(7)


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def env_ar(n: int, a: float, r: float) -> np.ndarray:
    e = np.ones(n)
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e[:na] = np.linspace(0, 1, na)
    if nr < n:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


# ------------------------------------------------------------------ instruments
def piano(m: int, dur: float, vel: float = 0.6) -> np.ndarray:
    n = int((dur + 2.5) * SR)
    t = np.arange(n) / SR
    f = hz(m)
    out = np.zeros(n)
    for k in range(1, 9):
        fk = f * k * np.sqrt(1 + 0.0004 * k * k)
        if fk > 12000:
            break
        out += (1 / k ** 1.4) * np.exp(-t * (0.9 + 0.7 * k) * (1 + (m - 60) / 60)) * np.sin(2 * np.pi * fk * t + rng.random() * 6)
    hammer = lp(rng.standard_normal(int(0.012 * SR)), 2500) * np.linspace(1, 0, int(0.012 * SR)) * 0.25
    out[: len(hammer)] += hammer
    out *= env_ar(n, 0.003, 0.0)
    rel = int(dur * SR)                         # the damper comes down after `dur`
    if rel < n:
        out[rel:] *= np.exp(-np.arange(n - rel) / (0.25 * SR))
    return lp(out, 5000 * (0.5 + vel)) * vel


def pad(notes: list[int], dur: float, vel: float = 0.25, bright: float = 1400) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for m in notes:
        for det in (-0.07, 0.0, 0.07):
            f = hz(m + det)
            for k in range(1, 14):
                if f * k > 9000:
                    break
                out += np.sin(2 * np.pi * f * k * t + rng.random() * 6) / k
    out = lp(out, bright) * env_ar(n, min(1.6, dur / 3), min(1.6, dur / 3))
    return out / (len(notes) * 3) * vel


def bass(m: int, dur: float, vel: float = 0.5) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(m)
    x = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t)
    return lp(x * env_ar(n, 0.006, 0.05) * (0.65 + 0.35 * np.exp(-t * 6)), 900) * vel


def pluck(m: int, dur: float, vel: float = 0.3) -> np.ndarray:
    n = int((dur + 0.4) * SR)
    t = np.arange(n) / SR
    f = hz(m)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t * 7) + 0.5 * np.sin(4 * np.pi * f * t) * np.exp(-t * 12) \
        + 0.25 * np.sin(6 * np.pi * f * t) * np.exp(-t * 18)
    return x * env_ar(n, 0.002, 0.02) * vel


def kick(vel: float = 0.9) -> np.ndarray:
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 45 + 95 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-t * 7.5)
    x[: int(0.004 * SR)] += lp(rng.standard_normal(int(0.004 * SR)), 4000) * 0.4
    return np.tanh(x * 1.6) * vel


def clap(vel: float = 0.35) -> np.ndarray:
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    noise = bp(rng.standard_normal(n), 900, 5200)
    burst = sum(np.exp(-np.clip(t - d, 0, None) * 60) * (t >= d) for d in (0, 0.011, 0.022))
    x = noise * (burst * 0.5 + np.exp(-t * 14)) + 0.3 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30)
    return x * vel


def hat(vel: float = 0.12, open_: bool = False) -> np.ndarray:
    n = int((0.25 if open_ else 0.06) * SR)
    t = np.arange(n) / SR
    return hp(rng.standard_normal(n), 7500) * np.exp(-t * (12 if open_ else 70)) * vel


def riser(dur: float, vel: float = 0.35) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    k = t / dur
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    for i, (a, b) in enumerate(zip(np.linspace(300, 9000, 24)[:-1], np.linspace(300, 9000, 24)[1:])):
        seg = (k >= i / 23) & (k < (i + 1) / 23)
        out += bp(noise, a, b + 400) * seg
    tone = np.sin(2 * np.pi * np.cumsum(220 * 2 ** (k * 2)) / SR) * 0.15
    return (out + tone) * k ** 2.2 * vel


def impact(vel: float = 0.9) -> np.ndarray:
    n = int(2.6 * SR)
    t = np.arange(n) / SR
    f = 30 + 40 * np.exp(-t * 3)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.8)
    air = lp(rng.standard_normal(n), 1800) * np.exp(-t * 5) * 0.35
    return np.tanh((boom + air) * 1.4) * vel


def room(dur: float, vel: float = 0.02) -> np.ndarray:
    """A quiet night room: a low hum and soft air, with the odd far-off car."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    air = lp(rng.standard_normal(n), 900) * 0.6 + lp(hp(rng.standard_normal(n), 2000), 6000) * 0.08
    hum = 0.15 * np.sin(2 * np.pi * 50 * t) + 0.05 * np.sin(2 * np.pi * 100 * t)
    swell = 0.6 + 0.4 * np.sin(2 * np.pi * t / 9.0)
    return (air * swell + hum) * vel


def reverb_ir(seconds=2.6, bright=5000) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = np.stack([lp(rng.standard_normal(n), bright), lp(rng.standard_normal(n), bright)]) * np.exp(-t * 3.2 / seconds * 2.2)
    ir[:, : int(0.012 * SR)] = 0                 # a little pre-delay
    return ir / np.abs(ir).sum(axis=1, keepdims=True) * 18


# ------------------------------------------------------------------ the arrangement
NIGHT = [(57, [57, 60, 64, 71]), (53, [53, 57, 60, 64]), (48, [48, 55, 60, 64]), (47, [47, 55, 59, 62])]  # Am(add9) Fmaj7 C G/B
DAY = [(48, [48, 55, 60, 64]), (43, [43, 50, 55, 59]), (45, [45, 52, 57, 60]), (41, [41, 48, 53, 57])]      # C G Am F
MORNING = [(48, [48, 55, 59, 64]), (41, [41, 48, 53, 57, 64]), (43, [43, 50, 55, 59, 62]), (48, [48, 55, 60, 64, 67])]


class Track:
    def __init__(self, seconds: float):
        self.n = int((seconds + 4) * SR)
        self.bus = {k: np.zeros((2, self.n)) for k in ("dry", "verb", "drums", "side")}

    def add(self, x: np.ndarray, at: float, bus: str = "dry", pan: float = 0.0, send: float = 0.0):
        i = int(at * SR)
        if i >= self.n:
            return
        x = x[: self.n - i]
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        self.bus[bus][0, i:i + len(x)] += x * l
        self.bus[bus][1, i:i + len(x)] += x * r
        if send:
            self.bus["verb"][0, i:i + len(x)] += x * l * send
            self.bus["verb"][1, i:i + len(x)] += x * r * send


def main() -> dict:
    tl = json.loads((BUILD / "timeline.json").read_text())
    beat, bar, total = tl["beat"], tl["beat"] * 4, tl["duration"]
    acts = tl["acts"]
    scene = {s["id"]: s for s in tl["scenes"]}
    T = Track(total)
    hits = {}

    # ---- night: felt piano, pad from bar 3, room tone throughout
    n0, n1 = acts["night"]
    T.add(room(n1 + 1.0), 0, send=0.0)
    bars = int(round((n1 - n0) / bar))
    for b in range(bars):
        root, ch = NIGHT[(b // 2) % 4] if b < 8 else NIGHT[b % 4]
        t0 = n0 + b * bar
        T.add(piano(root - 12, bar * 2 if b % 2 == 0 else bar, 0.32), t0, pan=-0.1, send=0.45) if b % 2 == 0 else None
        pattern = [(0, ch[1]), (1.5, ch[2]), (2.5, ch[3]), (3.25, ch[2])] if b >= 1 else [(0, ch[1]), (2, ch[3])]
        for off, m in pattern:
            T.add(piano(m, beat * 1.5, 0.22 + 0.04 * (b % 2)), t0 + off * beat, pan=0.15, send=0.55)
        if b >= 2 and b % 2 == 0:
            T.add(pad(ch, bar * 2 + 0.5, 0.16, 900), t0, pan=0.0, send=0.5)

    # ---- build: arpeggio speeds up, riser, heartbeat; silence on the last half-beat
    b0, b1 = acts["build"]
    ch = NIGHT[3][1]
    t = b0
    step = beat / 2
    while t < b1 - beat * 0.5:
        k = (t - b0) / (b1 - b0)
        m = ch[int((t - b0) / step) % 4] + 12
        T.add(piano(m, step, 0.18 + 0.2 * k), t, pan=0.2 * np.sin(t * 3), send=0.45)
        step = beat / 2 if k < 0.5 else beat / 4
        t += step
    T.add(pad([45, 52, 57, 60, 64], b1 - b0, 0.22, 1600), b0, send=0.5)
    T.add(riser(b1 - b0 - beat * 0.5, 0.32), b0, send=0.3)
    beats_in = int((b1 - b0) / beat)
    for i in range(beats_in - 1):
        if i % 4 == 0 or (i >= beats_in - 5):
            T.add(kick(0.45 + 0.4 * i / beats_in), b0 + i * beat, bus="drums")

    # ---- day: the pulse
    d0, d1 = acts["day"]
    hits["drop"] = d0
    T.add(impact(0.75), d0, send=0.4)
    leak = scene["leak"]["start"] + 1.2           # the impact lands under "And there it is"
    hits["leak"] = round(leak, 3)
    T.add(impact(0.6), leak, send=0.5)
    brk0, brk1 = scene["question"]["start"], scene["answer"]["start"]
    hits["break"] = [brk0, brk1]
    nb = int(round((d1 - d0) / beat))
    for i in range(nb):
        t0 = d0 + i * beat
        in_break = brk0 <= t0 < brk1
        bar_i, pos = i // 4, i % 4
        root, ch = DAY[bar_i % 4]
        intro = bar_i < 2
        if not in_break:
            T.add(kick(0.8), t0, bus="drums")
            if pos in (1, 3) and not intro:
                T.add(clap(0.26), t0, bus="drums", pan=0.05, send=0.25)
            if not intro:
                T.add(hat(0.07), t0 + beat / 2, bus="drums", pan=0.3)
                T.add(hat(0.045), t0, bus="drums", pan=-0.3)
            for h in (0, 0.5):
                T.add(bass(root - 12, beat / 2 * 0.9, 0.42), t0 + h * beat, bus="side")
        if pos == 0:
            T.add(pad(ch, bar + 0.4, 0.2 if not in_break else 0.26, 2200 if not in_break else 1100), t0, bus="side", send=0.5)
            T.add(piano(ch[0] + 12, bar, 0.2), t0, pan=-0.15, send=0.4)
            T.add(piano(ch[2] + 12, bar, 0.16), t0 + 0.01, pan=-0.1, send=0.4)
        if not intro:
            arp = [ch[0] + 24, ch[2] + 12, ch[3] + 12, ch[1] + 24]
            for q in range(4):
                T.add(pluck(arp[(pos * 4 + q) % 4], beat / 4, 0.09 if not in_break else 0.12), t0 + q * beat / 4,
                      pan=0.35 * (1 if q % 2 else -1), send=0.35)
    T.add(riser(beat * 4, 0.22), brk1 - beat * 4, send=0.3)     # back in after the question
    T.add(hat(0.12, True), brk1, bus="drums", send=0.3)
    T.add(impact(0.4), brk1, send=0.3)

    # ---- morning: resolve and ring out
    m0, m1 = acts["morning"]
    hits["morning"] = m0
    n_bars = max(4, int(round((m1 - m0) / bar)))
    prog = [MORNING[i % 3] for i in range(n_bars - 1)] + [MORNING[3]]   # cycle C F G, end on the open C
    for b, (root, ch) in enumerate(prog):
        t0 = m0 + b * bar
        last = b == len(prog) - 1
        T.add(piano(root - 12, bar * (3 if last else 1), 0.3), t0, send=0.5)
        for j, m in enumerate(ch[1:]):
            T.add(piano(m + 12, bar * (3 if last else 1), 0.18), t0 + j * beat * (0.12 if last else 0.5), pan=0.2, send=0.6)
        T.add(pad(ch, bar * (3 if last else 1) + 0.6, 0.18, 1300), t0, send=0.6)

    # ---- mix: sidechain the bass and pad to the kick, reverb, gentle master
    kick_env = np.abs(T.bus["drums"][0])
    kick_env = lp(kick_env, 12)
    duck = 1 - 0.45 * np.clip(kick_env / (kick_env.max() + 1e-9) * 3, 0, 1)
    side = T.bus["side"] * duck
    verb = np.stack([fftconvolve(T.bus["verb"][c], reverb_ir()[c])[: T.n] for c in range(2)])

    def wide(x, ms=13, amount=1.5):
        """Haas delay on the right, then a touch more side signal: width without phasey mono."""
        d = int(ms / 1000 * SR)
        x = x.copy(); x[1, d:] = x[1, :-d].copy(); x[1, :d] = 0
        mid, sid = (x[0] + x[1]) / 2, (x[0] - x[1]) / 2 * amount
        return np.stack([mid + sid, mid - sid])
    side, verb = wide(side), wide(verb, 23, 1.8)
    mixdown = T.bus["dry"] + side + T.bus["drums"] * 0.9 + verb * 0.55
    mixdown = hp(mixdown, 28)
    end = int((total + 0.0) * SR)
    fade = int(2.5 * SR)
    mixdown = mixdown[:, :end]
    mixdown[:, -fade:] *= np.linspace(1, 0, fade) ** 1.5
    peak = np.abs(mixdown).max()
    mixdown = np.tanh(mixdown / peak * 1.4) / np.tanh(1.4) * 0.89
    pcm = (mixdown.T * 32767).astype(np.int16)
    import wave
    with wave.open(str(BUILD / "score.wav"), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    beats = [round(i * beat, 4) for i in range(int(total / beat) + 1)]
    (BUILD / "beats.json").write_text(json.dumps({"bpm": tl["bpm"], "beats": beats, "hits": hits}, indent=1))
    print("score", round(end / SR, 2), "s; hits", hits)
    return hits


if __name__ == "__main__":
    main()
