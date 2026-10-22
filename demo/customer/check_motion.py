"""After rendering: find every stretch of the finished film where the picture barely changes for more than 2 s."""
import subprocess, sys
from pathlib import Path
import imageio_ffmpeg, numpy as np

HERE = Path(__file__).parent
W, H, FPS = 192, 108, 10
raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", str(HERE / "ai-financial-analyst.mp4"),
                      "-vf", f"fps={FPS},scale={W}:{H},format=gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
f = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.int16)
# ignore the caption strip and the progress line: they always move
# compare each frame with the one 1 s later: slow, steady movement counts as movement
crop = f[:, :int(H * .86)]
diff = np.abs(crop[FPS:] - crop[:-FPS]).mean(axis=(1, 2))
still = diff < 0.6
runs, i = [], 0
while i < len(still):
    if still[i]:
        j = i
        while j < len(still) and still[j]:
            j += 1
        if (j - i) / FPS > 2.0:
            runs.append((i / FPS, j / FPS))
        i = j
    else:
        i += 1
print(f"{len(f) / FPS:.0f}s analysed; stretches over 2 s with no visible change: {len(runs)}")
for a, b in runs:
    print(f"  {int(a // 60)}:{a % 60:04.1f} – {int(b // 60)}:{b % 60:04.1f}  ({b - a:.1f}s)")
