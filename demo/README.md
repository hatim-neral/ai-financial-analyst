# Demo video

`demo.mp4`: a 99-second product walkthrough. 1920×1080 at 30 fps, H.264 video with a stereo AAC
voiceover (Google Gemini TTS, voice "Aoede"), no music.

Everything is generated from this folder: the narration from `script.py`, the footage from the
running app, and every frame from `compose.html`.

## Rebuild

Start the app first (`.venv/bin/streamlit run app.py --server.port 8501`), with an AI provider that
answers. Then, from the repo root:

```bash
cd demo && uv run --with imageio-ffmpeg --with requests python narration.py && cd ..   # 1. voice and timeline
uv run --with playwright python demo/record.py                         # 2. capture the app (~4 min, includes one live AI answer)
uv run --with playwright --with imageio-ffmpeg python demo/render.py   # 3. render and encode demo.mp4 (~5 min)
```

To render a few stills instead of the whole video (seconds on the timeline):
`uv run --with playwright --with imageio-ffmpeg python demo/render.py 12 40 70`.

## The voice

`ENGINE = "gemini"` in `script.py` makes the whole script in **one** Gemini TTS take
(`voice_gemini.py`), using `GEMINI_API_KEY` from `.streamlit/secrets.toml`. Only the script text is sent
to Google. Before the take is used, it is transcribed and compared with the script (a take sometimes
repeats a line), then cut into one clip per scene at the pauses. The take is cached, so rebuilding with
the same words and voice costs no requests. The free tier allows 10 speech requests a day per model; the
code falls back to the next speech model when one is out of quota. `ENGINE = "say"` uses the offline macOS
voices instead. `TEMPO` speeds the Gemini voice up without changing its pitch (1.08 gives about 90 s).

## Changing the words

Edit `say=` in `script.py` and rerun steps 1 and 3. New words mean a new Gemini take (one request). Each scene's length follows its line, so the
picture stays in sync. Rerun step 2 only if the app or the question changes (`QUESTION` in
`script.py`).

## How it's put together

| File | Does |
|---|---|
| `script.py` | Scenes in order, the voiceover lines, the voice, the question typed into Ask AI |
| `narration.py` | One clip per scene (Gemini or `say`), measured; writes `build/timeline.json` and `build/voice.wav` (loudness-normalised to −16 LUFS) |
| `voice_gemini.py`, `gemini_tts.py` | The Gemini take: request, transcript check, cut into scene clips |
| `record.py` | Playwright drives the app: clicks, typing, scrolling and a drawn cursor. Chrome runs at 2× so the screencast frames are 2880×1620. Records each scene's start and end, and the on-screen boxes for the camera |
| `compose.html` | The motion graphics: framed window, camera zooms keyed to recorded boxes, chapter labels, callouts with leader lines, word-by-word subtitles, title and end cards, the closing light-to-dark crossfade. Pure functions of time, so every render is identical |
| `render.py` | Renders `compose.html` frame by frame and pipes the frames to ffmpeg with the voice track |

The AI's wait is real and is fast-forwarded in the edit; the chip on screen says by how much.
Nothing else is staged: the numbers, the answer and its verified stamp come from the live app.

## Storyboard

| # | Chapter | Voiceover |
|---|---|---|
| 1 | Title card | Meet AI Financial Analyst. Ask your business's books anything, in plain English. |
| 2 | Overview | Upload a CSV of your transactions, or start with one of six sample businesses. |
| 3 | Overview | The overview opens on what matters most: net revenue for the period, in rupees, and in lakh and crore, with every month beside it. |
| 4 | What moved | What moved shows how this month was built: each category's push or drag, adding up to the exact change. |
| 5 | Money river | The money river follows every rupee, from where it came in to where it went. Wider ribbons mean more money. Hover over any ribbon for its amount. |
| 6 | Evidence | And nothing is a black box. Every figure shows its formula, and the exact rows it came from. |
| 7 | Accounts | Switch businesses, and the whole app takes on their colour. |
| 8 | Periods | Change the period, and every number recalculates. |
| 9 | Insights | Insights spots trends, rising costs, and your best and worst quarters. |
| 10 | Transactions | The ledger has every transaction, ready to search. |
| 11 | Card | Then, just ask. |
| 12 | Ask AI | The AI picks the right tools, Python does the maths, and every number is checked against your data before you see it. You get a chart, a verified stamp, and follow-up questions. |
| 13 | Plan | Plan ahead with budgets, cash runway, and what-if scenarios. Try a five percent lift in revenue, and see the margin change instantly. |
| 14 | Anywhere | Export a report to share, and work in light or dark, whichever suits you. |
| 15 | End card | AI Financial Analyst. Your numbers, explained. |

## The other two videos

- `demo/walkthrough/`: **the 5-minute walkthrough for the submission** (`walkthrough.mp4`). Same pipeline, plus
  `evidence.py` (the results card reads real test and eval numbers) and `make_demo_script.py` (writes
  `docs/DEMO_SCRIPT.md` from the same script). The recorder checks every on-camera answer and re-asks if one
  isn't verified or doesn't address its question; how often that happens is what the evaluation measures.
- `demo/film/`: a 1:42 cinematic story ("Priya's two cafés"), see `demo/film/README.md`.
