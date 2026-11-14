"""Build a self-contained HTML replay of a results folder: leaderboard plus a hand-by-hand table view."""

from __future__ import annotations

import csv
import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name("viewer_template.html")


def build_viewer(run_dir: str | Path, max_hands: int = 3000) -> Path:
    """Write <run_dir>/viewer.html and return its path. Only the first max_hands hands are embedded."""
    run_dir = Path(run_dir)
    hands_path = run_dir / "hands.jsonl"
    if not hands_path.exists():
        raise FileNotFoundError(f"{hands_path} not found: is this an arena results folder?")
    hands, total = [], 0
    with open(hands_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            total += 1
            if len(hands) < max_hands:
                hands.append(json.loads(line))
    leaderboard = []
    if (run_dir / "leaderboard.csv").exists():
        with open(run_dir / "leaderboard.csv", newline="", encoding="utf-8") as f:
            leaderboard = list(csv.DictReader(f))
    run = {}
    if (run_dir / "run.json").exists():
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    data = {"run": run, "leaderboard": leaderboard, "hands": hands, "total_hands": total, "truncated": total > len(hands)}
    payload = json.dumps(data).replace("</", "<\\/")  # never close the <script> early
    html = TEMPLATE.read_text(encoding="utf-8").replace("__ARENA_DATA__", payload)
    out = run_dir / "viewer.html"
    out.write_text(html, encoding="utf-8")
    return out
