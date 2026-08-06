#!/usr/bin/env python3
"""
Process WebPlotDigitizer CSV exports into MST baseline comparison.

Reads validation/WebPlotDigitizer_results/*.csv, fits the same models as
line_camera.py, and writes validation/results/baseline_webplotdigitizer.csv
and baseline_webplotdigitizer.json.

Usage:
  .venv/bin/python scripts/process_webplotdigitizer_baseline.py
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from line_camera import (  # noqa: E402
    _choose_shape,
    _fit_line,
    _fit_quadratic,
    _fit_sinusoid,
)
from scripts.analyze_validation_set import (  # noqa: E402
    load_ground_truth,
    param_errors,
    resolve_entry,
)

WPD_DIR = ROOT / "validation" / "WebPlotDigitizer_results"
GT_PATH = ROOT / "validation" / "ground_truth.json"
OUT_CSV = ROOT / "validation" / "results" / "baseline_webplotdigitizer.csv"
OUT_JSON = ROOT / "validation" / "results" / "baseline_webplotdigitizer.json"
OUT_MD = ROOT / "validation" / "results" / "baseline_webplotdigitizer.md"

CSV_FIELDS = [
    "file",
    "plot_id",
    "ground_truth_class",
    "ground_truth_equation",
    "x_min",
    "x_max",
    "y_min",
    "y_max",
    "n_points",
    "y_obs_min",
    "y_obs_max",
    "axis_calibration_ok",
    "best_model",
    "class_correct",
    "equation",
    "rmse",
    "r2",
    "line_rmse",
    "line_equation",
    "m_fitted",
    "b_fitted",
    "m_pct_error",
    "b_abs_error",
    "A_pct_error",
    "omega_pct_error",
    "a_pct_error",
    "operator",
    "session",
    "notes",
]


def load_wpd_csv(path: Path) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) < 2:
                continue
            try:
                xs.append(float(parts[0].strip()))
                ys.append(float(parts[1].strip()))
            except ValueError:
                continue
    if len(xs) < 3:
        raise ValueError(f"Too few points in {path}")
    x = np.array(xs, dtype=np.float64)
    y = np.array(ys, dtype=np.float64)
    order = np.argsort(x)
    return x[order], y[order]


def axis_calibration_ok(entry: dict, y: np.ndarray) -> tuple[bool, str]:
    """Check if digitized y range is consistent with ground-truth axes."""
    ax = entry["axes"]
    y_min_gt, y_max_gt = ax["y_min"], ax["y_max"]
    y_span_gt = y_max_gt - y_min_gt
    y_obs_min, y_obs_max = float(np.min(y)), float(np.max(y))
    # Allow 15% margin on span and slight offset
    margin = 0.15 * y_span_gt + 0.5
    ok_lo = y_obs_min >= y_min_gt - margin
    ok_hi = y_obs_max <= y_max_gt + margin
    if ok_lo and ok_hi:
        return True, ""
    return (
        False,
        f"y_obs=[{y_obs_min:.2g},{y_obs_max:.2g}] vs GT y=[{y_min_gt},{y_max_gt}]",
    )


def analyze_wpd_file(csv_path: Path, gt: dict) -> dict:
    plot_id = csv_path.stem
    jpg_name = f"{plot_id}.jpg"
    entry = resolve_entry(jpg_name, gt)
    gt_class = entry["class"]
    x, y = load_wpd_csv(csv_path)

    line = _fit_line(x, y)
    quad = _fit_quadratic(x, y)
    sine = _fit_sinusoid(x, y) if len(x) >= 5 else None
    y_span = float(np.ptp(y))
    shape_label, best, _ = _choose_shape(line, quad, sine, y_span)

    cal_ok, cal_note = axis_calibration_ok(entry, y)
    pe = param_errors_from_fit(entry, shape_label, best)

    row = {
        "file": jpg_name,
        "plot_id": plot_id,
        "ground_truth_class": gt_class,
        "ground_truth_equation": entry["equation"],
        "x_min": entry["axes"]["x_min"],
        "x_max": entry["axes"]["x_max"],
        "y_min": entry["axes"]["y_min"],
        "y_max": entry["axes"]["y_max"],
        "n_points": len(x),
        "y_obs_min": round(float(np.min(y)), 4),
        "y_obs_max": round(float(np.max(y)), 4),
        "axis_calibration_ok": "yes" if cal_ok else "no",
        "best_model": shape_label,
        "class_correct": "yes" if shape_label == gt_class else "no",
        "equation": best.equation,
        "rmse": f"{best.rmse:.6g}",
        "r2": f"{best.r2:.4f}",
        "line_rmse": f"{line.rmse:.6g}",
        "line_equation": line.equation,
        "m_fitted": "",
        "b_fitted": "",
        "m_pct_error": "",
        "b_abs_error": "",
        "A_pct_error": "",
        "omega_pct_error": "",
        "a_pct_error": "",
        "operator": "PMW",
        "session": "1",
        "notes": cal_note,
    }

    # Always record linear fit for line ground-truth (WPD line-slope benchmark)
    if gt_class == "LINE":
        gt_p = entry["params"]
        row["m_fitted"] = f"{line.params['m']:.6g}"
        row["b_fitted"] = f"{line.params['b']:.6g}"
        row["m_pct_error"] = f"{abs(line.params['m'] - gt_p['m']) / abs(gt_p['m']) * 100:.6g}"
        row["b_abs_error"] = f"{abs(line.params['b'] - gt_p['b']):.6g}"
    for k, v in pe.items():
        col = {
            "A_pct": "A_pct_error",
            "omega_pct": "omega_pct_error",
            "a_pct": "a_pct_error",
        }.get(k)
        if col and not row.get(col):
            row[col] = f"{v:.6g}"

    return row


def param_errors_from_fit(entry: dict, shape_label: str, best) -> dict[str, float]:
    """Reuse analyze_validation_set logic via a minimal adapter."""
    from dataclasses import dataclass

    @dataclass
    class _A:
        shape: str
        best: object

    class _B:
        def __init__(self, name, params):
            self.name = name
            self.params = params

    adapter = _A(shape_label, _B(best.name, best.params))
    return param_errors(entry, adapter)  # type: ignore[arg-type]


def write_outputs(rows: list[dict]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)

    correct = sum(1 for r in rows if r["class_correct"] == "yes")
    line_rows = [r for r in rows if r["ground_truth_class"] == "LINE"]
    m_errors = [float(r["m_pct_error"]) for r in line_rows if r.get("m_pct_error")]

    summary = {
        "method": "WebPlotDigitizer + offline model fitting (same as pipeline)",
        "source_dir": str(WPD_DIR.relative_to(ROOT)),
        "classification_correct": f"{correct}/{len(rows)}",
        "line_mape_pct_mean": float(np.mean(m_errors)) if m_errors else None,
        "results": rows,
    }
    with open(OUT_JSON, "w") as f:
        json.dump(summary, f, indent=2)

    md_lines = [
        "# WebPlotDigitizer baseline",
        "",
        f"**Classification:** {correct}/{len(rows)} correct by penalized model selection",
        "",
        "| File | N pts | Cal OK | Detected | GT | m err% | Notes |",
        "|------|-------|--------|----------|-----|--------|-------|",
    ]
    for r in rows:
        m_err = r.get("m_pct_error") or "—"
        md_lines.append(
            f"| {r['file']} | {r['n_points']} | {r['axis_calibration_ok']} | "
            f"{r['best_model']} | {r['ground_truth_class']} | {m_err} | {r['notes'][:40]} |"
        )
    if m_errors:
        md_lines.extend(
            [
                "",
                f"Mean line slope error (WPD): {np.mean(m_errors):.3f}%",
            ]
        )
    OUT_MD.write_text("\n".join(md_lines) + "\n")


def main() -> None:
    if not WPD_DIR.is_dir():
        print(f"Missing directory: {WPD_DIR}")
        sys.exit(1)

    gt = load_ground_truth()
    csv_files = sorted(WPD_DIR.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files in {WPD_DIR}")
        sys.exit(1)

    rows = []
    for path in csv_files:
        row = analyze_wpd_file(path, gt)
        rows.append(row)
        print(
            f"{path.name}: {row['best_model']} "
            f"({'OK' if row['class_correct'] == 'yes' else 'MIS'}) "
            f"n={row['n_points']}"
        )

    write_outputs(rows)
    print(f"\nWrote {OUT_CSV}")
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    main()
