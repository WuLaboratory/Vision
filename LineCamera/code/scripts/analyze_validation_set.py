#!/usr/bin/env python3
"""
Batch-analyze validation JPEGs using the same pipeline as line_camera.py.
Writes JSON results, overlay images, and VALIDATION_RESULTS.md.

Usage (from Linear/):
  .venv/bin/python scripts/analyze_validation_set.py
  .venv/bin/python scripts/analyze_validation_set.py --include-a-variants
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from line_camera import (  # noqa: E402
    AxisConfig,
    analyze_shape,
    draw_warp_preview,
    find_largest_quad,
    warp_plot,
)

GT_PATH = ROOT / "validation" / "ground_truth.json"
OUT_DIR = ROOT / "validation" / "results"
OVERLAY_DIR = OUT_DIR / "overlays"

PRIMARY = [
    "line1.jpg",
    "line2.jpg",
    "line3.jpg",
    "sinusoid1.jpg",
    "sinusoid2.jpg",
    "sinusoid3.jpg",
    "quadratic1.jpg",
    "quadratic2.jpg",
]

A_VARIANTS = [
    "line1a.jpg",
    "line3a.jpg",
    "sinusoid1a.jpg",
    "sinusoid2a.jpg",
    "sinusoid3a.jpg",
    "quadratic1a.jpg",
    "quadratic2a.jpg",
]


def load_ground_truth() -> dict:
    with open(GT_PATH) as f:
        return json.load(f)


def resolve_entry(name: str, gt: dict) -> dict:
    entry = gt[name]
    if "inherits" in entry:
        base = dict(gt[entry["inherits"]])
        base["inherits"] = entry["inherits"]
        return base
    return entry


def axes_from_entry(entry: dict) -> AxisConfig:
    a = entry["axes"]
    return AxisConfig(a["x_min"], a["x_max"], a["y_min"], a["y_max"])


def detect_quad(img: np.ndarray) -> tuple[np.ndarray, str]:
    quad = find_largest_quad(img)
    if quad is not None:
        return quad, "auto_quad"
    h, w = img.shape[:2]
    m = 0.02
    quad = np.array(
        [
            [w * m, h * m],
            [w * (1 - m), h * m],
            [w * (1 - m), h * (1 - m)],
            [w * m, h * (1 - m)],
        ],
        dtype=np.float32,
    )
    return quad, "inset_fallback"


def param_errors(entry: dict, analysis) -> dict[str, float]:
    """Percent or absolute errors vs. ground truth."""
    if analysis is None:
        return {}
    p = analysis.best.params
    gt = entry["params"]
    cls = entry["class"]
    err: dict[str, float] = {}
    if cls == "LINE" and analysis.shape == "LINE":
        err["m_pct"] = abs(p["m"] - gt["m"]) / abs(gt["m"]) * 100
        err["b_abs"] = abs(p["b"] - gt["b"])
    elif cls == "QUADRATIC" and analysis.best.name == "quadratic":
        for k in ("a", "b", "c"):
            denom = abs(gt[k]) if gt[k] != 0 else 1.0
            err[f"{k}_pct"] = abs(p[k] - gt[k]) / denom * 100
    elif cls == "SINUSOID" and analysis.best.name == "sinusoid":
        err["A_pct"] = abs(p["A"] - gt["A"]) / gt["A"] * 100
        err["omega_pct"] = abs(p["omega"] - gt["omega"]) / gt["omega"] * 100
        # Phase wraps; report smallest circular difference in radians
        dphi = abs((p["phi"] - gt["phi"] + math.pi) % (2 * math.pi) - math.pi)
        err["phi_rad"] = dphi
    return err


def analyze_file(name: str, gt: dict) -> dict:
    path = ROOT / name
    entry = resolve_entry(name, gt)
    axes = axes_from_entry(entry)
    img = cv2.imread(str(path))
    if img is None:
        return {"file": name, "error": "could not read image"}

    quad, quad_method = detect_quad(img)
    warped, _ = warp_plot(img, quad)
    analysis = analyze_shape(warped, axes)

    overlay = draw_warp_preview(warped, analysis)
    cv2.imwrite(str(OVERLAY_DIR / name.replace(".jpg", "_overlay.jpg")), overlay)

    result = {
        "file": name,
        "ground_truth_class": entry["class"],
        "ground_truth_equation": entry["equation"],
        "axes": entry["axes"],
        "quad_method": quad_method,
        "detected_shape": analysis.shape if analysis else None,
        "best_model": analysis.best.name if analysis else None,
        "equation": analysis.best.equation if analysis else None,
        "rmse": analysis.best.rmse if analysis else None,
        "r2": analysis.best.r2 if analysis else None,
        "line_rmse": analysis.line_scores.rmse if analysis else None,
        "arc_length": analysis.arc_length if analysis else None,
        "params_fitted": analysis.best.params if analysis else None,
        "class_correct": (
            analysis is not None and analysis.shape == entry["class"]
        ),
        "param_errors": param_errors(entry, analysis),
    }
    if analysis and analysis.shape == "LINE":
        result["seg_length"] = analysis.seg_length
    return result


def write_markdown(results: list[dict], out_path: Path) -> None:
    n = len(results)
    correct = sum(1 for r in results if r.get("class_correct"))
    lines = [
        "# Validation Results — Static JPEG Analysis",
        "",
        f"**Images analyzed:** {n}  ",
        f"**Classification correct:** {correct}/{n} ({100*correct/n:.0f}%)",
        "",
        "Pipeline: `find_largest_quad` → `warp_plot` → `analyze_shape` (same as camera app).",
        "",
        "## Results table",
        "",
        "| File | True class | Detected | OK | Best equation | RMSE | R² |",
        "|------|------------|----------|-----|---------------|------|-----|",
    ]
    for r in results:
        if "error" in r:
            lines.append(f"| {r['file']} | — | ERROR | — | {r['error']} | — | — |")
            continue
        ok = "yes" if r["class_correct"] else "**no**"
        eq = (r.get("equation") or "")[:42]
        rmse = f"{r['rmse']:.4g}" if r.get("rmse") is not None else "—"
        r2 = f"{r['r2']:.3f}" if r.get("r2") is not None else "—"
        lines.append(
            f"| {r['file']} | {r['ground_truth_class']} | {r['detected_shape']} | {ok} | {eq} | {rmse} | {r2} |"
        )

    lines.extend(["", "## Parameter errors vs. MATLAB ground truth (`linear.m`)", ""])
    for r in results:
        if not r.get("param_errors"):
            continue
        pe = ", ".join(f"{k}={v:.4g}" for k, v in r["param_errors"].items())
        lines.append(f"- **{r['file']}:** {pe}")

    lines.extend(
        [
            "",
            "## Camera verification (next step)",
            "",
            "1. Print each labeled JPEG (or use the `*a` unlabeled grid variants).",
            "2. Run `.venv/bin/python line_camera.py`.",
            "3. Calibrate corners (`m`) and set axis preset to match:",
            "   - Lines: preset `1`/`2`/`3` for line1/2/3",
            "   - Sinusoids / quadratics: tune `[` `]` `,` `.` to match printed axis ranges above.",
            "4. Compare on-screen **Shape** and equation to this table.",
            "5. Save frames with `s` into `captures/` for records.",
            "",
            f"Overlay images: `{OVERLAY_DIR.relative_to(ROOT)}/`",
            "",
        ]
    )
    out_path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--include-a-variants",
        action="store_true",
        help="Also analyze unlabeled *a.jpg grid variants",
    )
    args = parser.parse_args()

    gt = load_ground_truth()
    files = list(PRIMARY)
    if args.include_a_variants:
        files.extend(A_VARIANTS)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)

    results = [analyze_file(name, gt) for name in files]
    json_path = OUT_DIR / "validation_results.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)

    md_path = OUT_DIR / "VALIDATION_RESULTS.md"
    write_markdown(results, md_path)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Overlays in {OVERLAY_DIR}")
    correct = sum(1 for r in results if r.get("class_correct"))
    print(f"Classification: {correct}/{len(results)} correct")


if __name__ == "__main__":
    main()
