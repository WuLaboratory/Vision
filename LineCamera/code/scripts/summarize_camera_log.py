#!/usr/bin/env python3
"""Summarize validation/results/camera_log.jsonl after a camera session."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "validation" / "results" / "camera_log.jsonl"


def main() -> None:
    if not LOG.exists():
        print(f"No log yet: {LOG}")
        print("Run: .venv/bin/python line_camera.py --validate")
        print("Then press l after each trial.")
        return

    trials = []
    with open(LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                trials.append(json.loads(line))

    if not trials:
        print("Log file is empty.")
        return

    by_plot: dict[str, list] = defaultdict(list)
    for t in trials:
        pid = t.get("plot_id") or "unknown"
        by_plot[pid].append(t)

    correct = sum(1 for t in trials if t.get("class_correct"))
    print(f"Trials logged: {len(trials)}")
    print(f"Classification correct: {correct}/{len(trials)} ({100*correct/len(trials):.0f}%)\n")
    print(f"{'Plot':<14} {'N':>4} {'OK':>4} {'Rate':>6}")
    print("-" * 32)
    for pid in sorted(by_plot):
        rows = by_plot[pid]
        ok = sum(1 for r in rows if r.get("class_correct"))
        print(f"{pid:<14} {len(rows):>4} {ok:>4} {100*ok/len(rows):>5.0f}%")

    print(f"\nLog: {LOG}")


if __name__ == "__main__":
    main()
