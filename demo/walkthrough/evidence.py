"""The figures on the walkthrough's "Evidence of testing" card, taken from real runs, never typed in:
the pytest summary (run now), evals/results.json (the last live evaluation) and the edge-case folder.
Writes build/evidence.json.    .venv/bin/python demo/walkthrough/evidence.py"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-o", "addopts="], cwd=REPO, capture_output=True, text=True).stdout
passed = int(re.search(r"(\d+) passed", out).group(1))
assert "failed" not in out.splitlines()[-1], out.splitlines()[-1]
ev = json.loads((REPO / "evals" / "results.json").read_text())
summ = ev.get("summary", ev)
lat = [c["latency_s"] for c in ev["cases"] if c.get("latency_s") is not None]
data = {
    "tests": passed,
    "edge_files": len(list((REPO / "data" / "edge_cases").glob("*.csv"))),
    "cases": summ["cases"], "passed": summ["passed"], "figures_checked": summ["figures_checked"],
    "caught": summ["first_drafts_with_unsupported_figures"], "shown": summ["unsupported_figures_shown_to_user"],
    "median_s": round(statistics.median(lat), 1) if lat else None,
}
(Path(__file__).parent / "build" / "evidence.json").write_text(json.dumps(data, indent=1))
print(data)
