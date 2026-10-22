# The film: "Priya's two cafés"

`film.mp4`: a 1:42 cinematic story for the product. 1080p30, stereo, −14 LUFS. Made entirely in this
folder; the app footage, the numbers and the AI answer are real.

**Story:** a fictional owner (Priya) runs the Masala Street Cafés sample business. Sales nearly
doubled, but one cost grew faster: the delivery apps now keep about ₹28 of every ₹100 they sell, up
from ₹22. The app finds it, she tests a fix, and she ends with a plan. It closes on "This was Priya's
story. Upload your own numbers, and see yours."

## Rebuild (from the repo root, with the app running on :8501)

```bash
.venv/bin/python demo/film/facts.py                                           # 1. every figure checked against the data
cd demo/film && uv run --with imageio-ffmpeg --with requests python narration.py && cd ../..   # 2. voice + beat-locked timeline
cd demo/film && uv run --with numpy --with scipy python score.py && cd ../..    # 3. the score
uv run --with playwright python demo/film/record_film.py                     # 4. app footage (one live AI answer)
uv run --with playwright --with imageio-ffmpeg --with numpy --with scipy python demo/film/render_film.py   # 5. frames, mix, film.mp4
```
`render_film.py 12 40 70` renders stills at those seconds instead.

| File | Does |
|---|---|
| `script.py` | The story: scenes, acts, narration, the voice's direction, the question |
| `facts.py` | Fails the build if the script says anything the data doesn't |
| `narration.py` | One Gemini TTS take (voice Aoede), checked against a transcript and cut per scene; scenes snap to the beat, acts to bars |
| `score.py` | The music, synthesised in code (96 bpm: night piano, build, drop, pulse, morning resolve); ours, so no licence |
| `record_film.py` | Captures the app at 2× for the reveal, river, ask and plan shots |
| `film.html` | Every frame: photos with slow pushes, the ledger of real rows, the 3D app window, kinetic type, the question card, the end card, grain, letterbox, light leaks, subtitles |
| `mix.py` | Voice on top, score ducked under it, synthesised effects on the edit's events |
| `render_film.py` | Renders, mixes and encodes |

Photos (Wikimedia Commons, credited on the end card): "Empty Table, Lisbon" (Sam, CC BY 2.0), "Masala Chai" (public
domain), "Coffe House in the early hours of the morning…" (Esin Üstün, CC BY 2.0).
