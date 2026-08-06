#!/usr/bin/env python3
"""
Aggregate MST validation artifacts and print submission-readiness status.

Usage:
  .venv/bin/python scripts/analyze_mst_validation.py
  .venv/bin/python scripts/analyze_mst_validation.py --status
  .venv/bin/python scripts/analyze_mst_validation.py --write-md
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "validation" / "results"
CAMERA_LOG = RESULTS / "camera_log.jsonl"
PHASE3_JSON = RESULTS / "phase3_camera_summary.json"
TRIAL_MATRIX = ROOT / "validation" / "MST_TRIAL_MATRIX.json"
UNCERTAINTY = RESULTS / "uncertainty_jitter.json"
HOUGH = RESULTS / "baseline_hough.json"
WPD_CSV = RESULTS / "baseline_webplotdigitizer.csv"
OUT_MD = RESULTS / "MST_ANALYSIS_SUMMARY.md"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def camera_summary(trials: list[dict]) -> dict:
    if PHASE3_JSON.exists():
        p3 = json.loads(PHASE3_JSON.read_text())
        return {
            "n": p3["total_trials"],
            "correct": p3["overall"]["correct"],
            "accuracy_pct": p3["overall"]["accuracy_pct"],
            "qc_accuracy_pct": p3["qc_arc_lt_100"]["accuracy_pct"],
            "qc_n": p3["qc_arc_lt_100"]["n"],
            "qc_correct": p3["qc_arc_lt_100"]["correct"],
            "by_plot": {
                pid: {
                    "n": info["n"],
                    "correct": info["correct"],
                    "rate_pct": info["accuracy_pct"],
                }
                for pid, info in p3.get("per_plot_all", {}).items()
            },
        }
    if not trials:
        return {"n": 0}
    by_plot: dict[str, list] = defaultdict(list)
    for t in trials:
        by_plot[t.get("plot_id", "?")].append(t)
    correct = sum(1 for t in trials if t.get("class_correct"))
    good = [t for t in trials if t.get("class_correct") and (t.get("arc_length") or 999) < 100]
    return {
        "n": len(trials),
        "correct": correct,
        "accuracy_pct": 100 * correct / len(trials),
        "well_calibrated_n": len(good),
        "by_plot": {
            pid: {
                "n": len(rows),
                "correct": sum(1 for r in rows if r.get("class_correct")),
                "rate_pct": 100 * sum(1 for r in rows if r.get("class_correct")) / len(rows),
            }
            for pid, rows in sorted(by_plot.items())
        },
    }


def trial_matrix_progress() -> dict:
    if not TRIAL_MATRIX.exists():
        return {"exists": False}
    data = json.loads(TRIAL_MATRIX.read_text())
    trials = data.get("trials", [])
    done = sum(1 for t in trials if t.get("completed"))
    return {"target": data.get("target_trials", len(trials)), "completed": done}


def uncertainty_summary() -> dict | None:
    if not UNCERTAINTY.exists():
        return None
    data = json.loads(UNCERTAINTY.read_text())
    # summarize line plots at sigma=2
    lines = [
        r
        for r in data.get("results", [])
        if r.get("sigma_px") == 2.0 and r.get("file", "").startswith("line")
    ]
    if not lines:
        return {"exists": True, "lines_at_sigma2": 0}
    m_stds = [r["slope_m"]["std"] for r in lines if r.get("slope_m")]
    return {
        "exists": True,
        "sigma_px_values": data.get("sigma_px_values"),
        "line_slope_std_at_2px": m_stds,
        "mean_slope_std_at_2px": statistics.mean(m_stds) if m_stds else None,
    }


def hough_summary() -> dict | None:
    if not HOUGH.exists():
        return None
    data = json.loads(HOUGH.read_text())
    return {
        "classification": data.get("classification_correct"),
        "n": len(data.get("results", [])),
    }


def wpd_summary() -> dict:
    wpd_json = RESULTS / "baseline_webplotdigitizer.json"
    if wpd_json.exists():
        data = json.loads(wpd_json.read_text())
        n = len(data.get("results", []))
        return {
            "exists": True,
            "rows": n,
            "filled": n,
            "classification": data.get("classification_correct"),
        }
    if not WPD_CSV.exists():
        return {"exists": False}
    import csv

    rows = list(csv.DictReader(WPD_CSV.open()))
    filled = [r for r in rows if r.get("n_points", "").strip()]
    return {"exists": True, "rows": len(rows), "filled": len(filled)}


def submission_status() -> list[tuple[str, bool, str]]:
    cam = camera_summary(load_jsonl(CAMERA_LOG))
    matrix = trial_matrix_progress()
    unc = uncertainty_summary()
    hough = hough_summary()
    wpd = wpd_summary()

    items = [
        (
            "Static JPEG baseline",
            (RESULTS / "validation_results.json").exists(),
            "validation_results.json",
        ),
        (
            "Camera trials N≥80",
            cam.get("n", 0) >= 80,
            f"{cam.get('n', 0)}/80 trials logged",
        ),
        (
            "Camera QC accuracy (arc<100)",
            cam.get("qc_accuracy_pct", 0) >= 85,
            f"{cam.get('qc_correct', '?')}/{cam.get('qc_n', '?')} = {cam.get('qc_accuracy_pct', 0)}%",
        ),
        (
            "Uncertainty study",
            unc is not None and unc.get("exists"),
            "uncertainty_jitter.json",
        ),
        (
            "Hough baseline",
            hough is not None,
            "baseline_hough.json",
        ),
        (
            "WebPlotDigitizer baseline",
            wpd.get("exists") and wpd.get("filled", 0) >= 8,
            f"{wpd.get('filled', 0)}/8 plots ({wpd.get('classification', '?')})",
        ),
        (
            "MST manuscript",
            any(ROOT.glob("MST_manuscript_*.docx")),
            "run build_manuscript_mst.py",
        ),
    ]
    return items


def write_summary_md() -> None:
    cam = camera_summary(load_jsonl(CAMERA_LOG))
    lines = [
        "# MST validation analysis summary",
        "",
        "## Submission readiness",
        "",
        "| Criterion | Status | Detail |",
        "|-----------|--------|--------|",
    ]
    for name, ok, detail in submission_status():
        lines.append(f"| {name} | {'✓' if ok else '✗'} | {detail} |")

    lines.extend(["", "## Camera trials", ""])
    if cam.get("n"):
        lines.append(f"- Total: {cam['n']}")
        lines.append(f"- Accuracy (all): {cam['correct']}/{cam['n']} ({cam['accuracy_pct']}%)")
        if cam.get("qc_n") is not None:
            lines.append(
                f"- QC accuracy (arc<100): {cam['qc_correct']}/{cam['qc_n']} "
                f"({cam['qc_accuracy_pct']}%)"
            )
        lines.append("")
        lines.append("| Plot | N | Correct | Rate |")
        lines.append("|------|---|---------|------|")
        for pid, info in cam.get("by_plot", {}).items():
            lines.append(
                f"| {pid} | {info['n']} | {info['correct']} | {info['rate_pct']:.0f}% |"
            )
    else:
        lines.append("No camera_log.jsonl entries.")

    unc = uncertainty_summary()
    if unc:
        lines.extend(["", "## Uncertainty (corner jitter)", ""])
        lines.append(f"- σ values: {unc.get('sigma_px_values')}")
        if unc.get("mean_slope_std_at_2px") is not None:
            lines.append(f"- Mean slope SD at σ=2 px: {unc['mean_slope_std_at_2px']:.4g}")

    wpd_path = RESULTS / "baseline_webplotdigitizer.json"
    if wpd_path.exists():
        wpd = json.loads(wpd_path.read_text())
        lines.extend(["", "## WebPlotDigitizer baseline", ""])
        lines.append(f"- Classification: {wpd.get('classification_correct')}")
        lines.append(f"- Mean line slope error: {wpd.get('line_mape_pct_mean', 0):.3f}%")
        for r in wpd.get("results", []):
            note = f" ({r['notes']})" if r.get("notes") else ""
            lines.append(
                f"- {r['file']}: {r['best_model']}, class {r['class_correct']}{note}"
            )

    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT_MD}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true", help="Print readiness checklist")
    parser.add_argument("--write-md", action="store_true", help="Write MST_ANALYSIS_SUMMARY.md")
    args = parser.parse_args()

    if args.write_md or not args.status:
        write_summary_md()

    if args.status or not args.write_md:
        print("MST submission readiness")
        print("=" * 50)
        for name, ok, detail in submission_status():
            mark = "OK " if ok else "TODO"
            print(f"  [{mark}] {name}: {detail}")
        cam = camera_summary(load_jsonl(CAMERA_LOG))
        if cam.get("n"):
            qc = ""
            if cam.get("qc_accuracy_pct") is not None:
                qc = f"; QC {cam['qc_accuracy_pct']}%"
            print(
                f"\nCamera: {cam['correct']}/{cam['n']} correct "
                f"({cam['accuracy_pct']}%){qc}"
            )


if __name__ == "__main__":
    main()
