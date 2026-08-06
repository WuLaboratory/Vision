#!/usr/bin/env python3
"""
Naive Hough-line baseline on static JPEGs (v1-style detector).

Usage:
  .venv/bin/python scripts/baseline_hough_static.py
"""

from __future__ import annotations

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
    WARP_H,
    WARP_W,
    _build_ink_mask,
    _fitline_params,
    _hough_best_segment,
    find_largest_quad,
    pixel_to_data,
    warp_plot,
)

from scripts.analyze_validation_set import (  # noqa: E402
    PRIMARY,
    axes_from_entry,
    load_ground_truth,
    resolve_entry,
)

OUT = ROOT / "validation" / "results" / "baseline_hough.json"


def hough_line_fit(warped: np.ndarray, axes: AxisConfig) -> dict | None:
    ink = _build_ink_mask(warped)
    edges = cv2.Canny(ink, 50, 150)
    seg = _hough_best_segment(edges, threshold=50, min_len_frac=0.15, min_angle=5, max_angle=175)
    if seg is None:
        return None
    x1, y1, x2, y2 = seg
    vx, vy, x0, y0 = _fitline_params(np.array([[x1, y1], [x2, y2]], dtype=np.float32))
    if abs(vx) < 1e-8:
        return None
    m_img = vy / vx
    b_img = y0 - m_img * x0
    # Convert image-line to data coords using two warp endpoints
    p1 = pixel_to_data(float(x1), float(y1), axes)
    p2 = pixel_to_data(float(x2), float(y2), axes)
    if abs(p2[0] - p1[0]) < 1e-9:
        return None
    m = (p2[1] - p1[1]) / (p2[0] - p1[0])
    b = p1[1] - m * p1[0]
    length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    return {"m": m, "b": b, "seg_length": length, "detected_class": "LINE"}


def analyze_file(name: str, gt: dict) -> dict:
    entry = resolve_entry(name, gt)
    axes = axes_from_entry(entry)
    img = cv2.imread(str(ROOT / name))
    quad = find_largest_quad(img)
    if quad is None:
        h, w = img.shape[:2]
        m = 0.02
        quad = np.array(
            [[w * m, h * m], [w * (1 - m), h * m], [w * (1 - m), h * (1 - m)], [w * m, h * (1 - m)]],
            dtype=np.float32,
        )
    warped, _ = warp_plot(img, quad)
    fit = hough_line_fit(warped, axes)
    gt_cls = entry["class"]
    gt_p = entry["params"]
    row = {
        "file": name,
        "ground_truth_class": gt_cls,
        "hough_detected_class": "LINE",
        "class_correct": gt_cls == "LINE",
        "equation": None,
        "param_errors": {},
    }
    if fit:
        row["equation"] = f"y = {fit['m']:.4g} x + {fit['b']:.4g}"
        row["params"] = {"m": fit["m"], "b": fit["b"]}
        if gt_cls == "LINE":
            row["param_errors"]["m_pct"] = abs(fit["m"] - gt_p["m"]) / abs(gt_p["m"]) * 100
            row["param_errors"]["b_abs"] = abs(fit["b"] - gt_p["b"])
        row["seg_length"] = fit["seg_length"]
    else:
        row["error"] = "hough failed"
    return row


def main() -> None:
    gt = load_ground_truth()
    results = [analyze_file(n, gt) for n in PRIMARY]
    correct = sum(1 for r in results if r.get("class_correct"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(
            {
                "method": "naive_hough_longest_segment",
                "classification_correct": f"{correct}/{len(results)}",
                "note": "Always reports LINE; fails class on sinusoids/quadratics",
                "results": results,
            },
            f,
            indent=2,
        )
    print(f"Wrote {OUT}")
    print(f"Hough class accuracy: {correct}/{len(results)} (only lines counted correct)")


if __name__ == "__main__":
    main()
