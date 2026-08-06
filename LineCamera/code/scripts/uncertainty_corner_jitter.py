#!/usr/bin/env python3
"""
Monte Carlo corner-jitter uncertainty study for MST manuscript.

Perturbs detected plot corners on static JPEGs and measures spread in
fitted parameters (slope, intercept, class).

Usage:
  .venv/bin/python scripts/uncertainty_corner_jitter.py
  .venv/bin/python scripts/uncertainty_corner_jitter.py --samples 200 --sigma-px 1 2 3
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
    find_largest_quad,
    warp_plot,
)

from scripts.analyze_validation_set import (  # noqa: E402
    PRIMARY,
    axes_from_entry,
    load_ground_truth,
    resolve_entry,
)

OUT_JSON = ROOT / "validation" / "results" / "uncertainty_jitter.json"
OUT_MD = ROOT / "validation" / "results" / "uncertainty_jitter.md"
FIG_DIR = ROOT / "validation" / "results" / "figures"


def jitter_quad(quad: np.ndarray, sigma_px: float, rng: np.random.Generator) -> np.ndarray:
    noise = rng.normal(0, sigma_px, quad.shape).astype(np.float32)
    return quad + noise


def run_image(
    name: str,
    gt: dict,
    *,
    samples: int,
    sigma_px: float,
    rng: np.random.Generator,
) -> dict:
    path = ROOT / name
    entry = resolve_entry(name, gt)
    axes = axes_from_entry(entry)
    img = cv2.imread(str(path))
    if img is None:
        return {"file": name, "error": "read failed"}

    quad = find_largest_quad(img)
    if quad is None:
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

    gt_params = entry["params"]
    gt_class = entry["class"]
    ms, bs, classes, rmses = [], [], [], []
    ok = 0

    for _ in range(samples):
        jq = jitter_quad(quad, sigma_px, rng)
        try:
            warped, _ = warp_plot(img, jq)
            analysis = analyze_shape(warped, axes)
        except cv2.error:
            continue
        if analysis is None:
            continue
        classes.append(analysis.shape)
        rmses.append(analysis.best.rmse)
        if analysis.shape == gt_class:
            ok += 1
        if analysis.shape == "LINE":
            ms.append(analysis.best.params["m"])
            bs.append(analysis.best.params["b"])

    result = {
        "file": name,
        "ground_truth_class": gt_class,
        "sigma_px": sigma_px,
        "samples_requested": samples,
        "samples_valid": len(classes),
        "class_accuracy_pct": 100.0 * ok / len(classes) if classes else None,
        "class_mode": max(set(classes), key=classes.count) if classes else None,
    }
    if ms:
        result["slope_m"] = {
            "mean": float(np.mean(ms)),
            "std": float(np.std(ms)),
            "gt": gt_params.get("m"),
            "m_pct_error_mean": abs(float(np.mean(ms)) - gt_params["m"]) / abs(gt_params["m"]) * 100
            if gt_class == "LINE" and gt_params.get("m")
            else None,
        }
        result["slope_m"]["cv_pct"] = (
            100.0 * result["slope_m"]["std"] / abs(result["slope_m"]["mean"])
            if result["slope_m"]["mean"] != 0
            else None
        )
    if bs:
        result["intercept_b"] = {
            "mean": float(np.mean(bs)),
            "std": float(np.std(bs)),
            "gt": gt_params.get("b"),
        }
    if rmses:
        result["rmse"] = {"mean": float(np.mean(rmses)), "std": float(np.std(rmses))}
    return result


def write_markdown(all_results: list[dict], sigmas: list[float]) -> None:
    lines = [
        "# Corner-jitter uncertainty study",
        "",
        "Monte Carlo perturbation of plot corners on static JPEGs.",
        "",
    ]
    for sigma in sigmas:
        lines.append(f"## σ = {sigma} px")
        lines.append("")
        lines.append("| File | Class acc. | m mean ± SD | m CV% | b mean ± SD |")
        lines.append("|------|------------|-------------|-------|-------------|")
        for r in all_results:
            if r.get("sigma_px") != sigma or "error" in r:
                continue
            acc = f"{r['class_accuracy_pct']:.0f}%" if r.get("class_accuracy_pct") is not None else "—"
            sm = r.get("slope_m")
            ib = r.get("intercept_b")
            if sm:
                m_str = f"{sm['mean']:.4g} ± {sm['std']:.4g}"
                cv = f"{sm['cv_pct']:.2f}" if sm.get("cv_pct") is not None else "—"
            else:
                m_str, cv = "—", "—"
            if ib:
                b_str = f"{ib['mean']:.4g} ± {ib['std']:.4g}"
            else:
                b_str = "—"
            lines.append(f"| {r['file']} | {acc} | {m_str} | {cv} | {b_str} |")
        lines.append("")
    OUT_MD.write_text("\n".join(lines))


def maybe_plot(all_results: list[dict], sigmas: list[float]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    line_files = ["line1.jpg", "line2.jpg", "line3.jpg"]
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    for fname in line_files:
        ys = []
        for s in sigmas:
            r = next(
                (x for x in all_results if x.get("file") == fname and x.get("sigma_px") == s),
                None,
            )
            ys.append(r["slope_m"]["std"] if r and r.get("slope_m") else float("nan"))
        ax.plot(sigmas, ys, marker="o", label=fname.replace(".jpg", ""))
    ax.set_xlabel("Corner jitter σ (px)")
    ax.set_ylabel("Slope SD (axis units)")
    ax.set_title("Figure 7. Calibration uncertainty propagation (corner-jitter Monte Carlo)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "uncertainty_jitter.png", dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument(
        "--sigma-px",
        type=float,
        nargs="+",
        default=[1.0, 2.0, 3.0],
        help="Gaussian SD per corner in source-image pixels",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    gt = load_ground_truth()
    rng = np.random.default_rng(args.seed)
    all_results: list[dict] = []

    for sigma in args.sigma_px:
        for name in PRIMARY:
            all_results.append(
                run_image(name, gt, samples=args.samples, sigma_px=sigma, rng=rng)
            )
            print(f"σ={sigma} {name}: done")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(
            {
                "samples": args.samples,
                "sigma_px_values": args.sigma_px,
                "results": all_results,
            },
            f,
            indent=2,
        )
    write_markdown(all_results, args.sigma_px)
    maybe_plot(all_results, args.sigma_px)
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    main()
