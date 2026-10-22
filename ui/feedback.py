"""Sound, haptics and confetti, kept for the moments that earn them: a verified answer, a real win.

Sound and haptics are off until the viewer turns them on in the sidebar. The chime is a fixed
script written here (never built from user or model text): Web Audio for the tone, the Vibration
API for a tap on phones that support it.
"""

from __future__ import annotations

import streamlit as st

from . import theme

_CHIME = """
<script>
(function () {
  try {
    const kind = "%s";
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (Ctx) {
      const ctx = window.__ledgerAudio || (window.__ledgerAudio = new Ctx());
      const notes = kind === "win" ? [523, 659, 784] : [659, 988];
      const t0 = ctx.currentTime + 0.02;
      notes.forEach(function (freq, i) {
        const osc = ctx.createOscillator(), gain = ctx.createGain(), t = t0 + i * 0.09;
        osc.type = "sine"; osc.frequency.value = freq;
        gain.gain.setValueAtTime(0, t);
        gain.gain.linearRampToValueAtTime(0.06, t + 0.012);
        gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.36);
        osc.connect(gain).connect(ctx.destination);
        osc.start(t); osc.stop(t + 0.4);
      });
    }
    if (navigator.vibrate) navigator.vibrate(kind === "win" ? [12, 40, 12] : 10);
  } catch (e) {}
})();
</script>
"""


def sound_on() -> bool:
    return bool(st.session_state.get("sound_on", False))


def chime(kind: str = "verified") -> None:
    if sound_on():
        st.html(_CHIME % ("win" if kind == "win" else "verified"), unsafe_allow_javascript=True)


def celebrate(key: str) -> None:
    """Confetti (and the win chime if sound is on), once per `key` per session."""
    seen = st.session_state.setdefault("celebrated", set())
    if key in seen:
        return
    seen.add(key)
    st.html(theme.confetti(seed=sum(map(ord, key)) % 10_000))
    chime("win")
