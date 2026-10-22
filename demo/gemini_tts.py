"""Speech from Google's Gemini TTS (uses GEMINI_API_KEY from .streamlit/secrets.toml).
Only the narration text is sent. Returns 24 kHz mono 16-bit PCM written as a WAV file."""

from __future__ import annotations

import base64
import time
import tomllib
import wave
from pathlib import Path

import requests

MODEL = "gemini-3.8-flash-tts"
STYLE = ("Style: the narrator of a polished product launch video. Warm, confident, conversational, "
         "like a real person who loves the product, with a light smile in the voice. Not salesy.\n"
         "Pacing: natural and unhurried, brief pauses at commas and full stops.\n"
         "Speak only the transcript below.")
SECRETS = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"


def speak(text: str, voice: str, out: Path, style: str = STYLE, model: str = MODEL, tries: int = 6) -> float:
    key = tomllib.load(SECRETS.open("rb"))["GEMINI_API_KEY"]
    # Director's notes, then the transcript: only the transcript is spoken
    prompt = f"### DIRECTOR'S NOTES\n{style}\n\n### TRANSCRIPT\n{text}"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    for attempt in range(tries):
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                          headers={"x-goog-api-key": key}, json=body, timeout=120)
        if r.status_code == 200:
            cand = (r.json().get("candidates") or [{}])[0]
            parts = (cand.get("content") or {}).get("parts") or []
            if not parts or "inlineData" not in parts[0]:
                raise RuntimeError(f"no audio in the reply (finishReason {cand.get('finishReason')})")
            part = parts[0]["inlineData"]
            data, mime = base64.b64decode(part["data"]), part.get("mimeType", "")
            if "wav" in mime:                      # newer models send a complete WAV file
                out.write_bytes(data)
            else:                                  # older ones send raw PCM: audio/L16;rate=24000
                rate = int(mime.split("rate=")[-1].split(";")[0]) if "rate=" in mime else 24000
                with wave.open(str(out), "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(data)
            with wave.open(str(out)) as w:
                return w.getnframes() / w.getframerate()
        if r.status_code in (429, 500, 503):
            wait = 8 * (attempt + 1)
            print(f"   {r.status_code}, retrying in {wait}s")
            time.sleep(wait)
            continue
        raise RuntimeError(f"Gemini TTS {r.status_code}: {r.text[:300]}")
    raise RuntimeError("Gemini TTS kept failing (rate limit or busy)")


if __name__ == "__main__":
    text = ("Meet AI Financial Analyst. Ask your business's books anything, in plain English. "
            "The money river follows every rupee, from where it came in to where it went.")
    import sys
    for v in sys.argv[1:] or ("Kore", "Aoede", "Charon", "Puck"):
        print(v, round(speak(text, v, Path(f"demo/voice-samples/gemini_{v}.wav")), 2), "s")
