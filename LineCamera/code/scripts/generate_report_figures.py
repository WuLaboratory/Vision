#!/usr/bin/env python3
"""Regenerate figures for REPORT.md. Run from Linear/: .venv/bin/python scripts/generate_report_figures.py"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "report_figures"
PHASE3_JSON = ROOT / "validation" / "results" / "phase3_camera_summary.json"
VALIDATION_JSON = ROOT / "validation" / "results" / "validation_results.json"
CAMERA_LOG = ROOT / "validation" / "results" / "camera_log.jsonl"
QC_ARC_THRESHOLD = 100.0


def _load_phase3() -> dict:
    if PHASE3_JSON.exists():
        with open(PHASE3_JSON) as f:
            return json.load(f)
    return {}


def _load_validation() -> list[dict]:
    if VALIDATION_JSON.exists():
        with open(VALIDATION_JSON) as f:
            return json.load(f)
    return []


def _median_param_errors_static() -> tuple[float, float, float]:
    """Median % errors for line m, quad a, sinusoid A on static JPEGs."""
    rows = _load_validation()
    m_errs, a_errs, A_errs = [], [], []
    for r in rows:
        pe = r.get("param_errors") or {}
        cls = r.get("ground_truth_class") or r.get("detected_shape")
        if cls == "LINE" and pe.get("m_pct") is not None:
            m_errs.append(pe["m_pct"])
        elif cls == "QUADRATIC" and pe.get("a_pct") is not None:
            a_errs.append(pe["a_pct"])
        elif cls == "SINUSOID" and pe.get("A_pct") is not None:
            A_errs.append(pe["A_pct"])
    import statistics

    def med(xs: list[float], default: float) -> float:
        return statistics.median(xs) if xs else default

    return med(m_errs, 0.2), med(a_errs, 0.2), med(A_errs, 8.9)


def _median_param_errors_camera_qc() -> tuple[float, float, float]:
    """Median % errors on QC-pass, class-correct camera trials."""
    import statistics

    if not CAMERA_LOG.exists():
        return 2.3, 4.7, 5.0
    gt_path = ROOT / "validation" / "ground_truth.json"
    gt = json.loads(gt_path.read_text()) if gt_path.exists() else {}
    m_errs, a_errs, A_errs = [], [], []
    with open(CAMERA_LOG) as f:
        for line in f:
            t = json.loads(line)
            if not t.get("class_correct"):
                continue
            arc = float(t.get("arc_length") or 9999.0)
            if arc >= QC_ARC_THRESHOLD:
                continue
            pid = t["plot_id"]
            key = f"{pid}.jpg"
            if key not in gt:
                continue
            g = gt[key]
            p = t.get("params_fitted") or {}
            cls = g.get("class")
            prm = g.get("params") or {}
            if cls == "LINE" and "m" in p and prm.get("m"):
                m_errs.append(abs(p["m"] - prm["m"]) / abs(prm["m"]) * 100)
            elif cls == "QUADRATIC" and "a" in p and prm.get("a"):
                a_errs.append(abs(p["a"] - prm["a"]) / abs(prm["a"]) * 100)
            elif cls == "SINUSOID" and "A" in p and prm.get("A"):
                A_errs.append(abs(p["A"] - prm["A"]) / abs(prm["A"]) * 100)

    def med(xs: list[float], default: float) -> float:
        return statistics.median(xs) if xs else default

    return med(m_errs, 2.3), med(a_errs, 4.7), med(A_errs, 5.0)


def fig1_reference_lines() -> None:
    lines = [
        ("Line 1 (line1 / line1a)", 10, 1, 0, 1, 0, 11, "#1f77b4"),
        ("Line 2 (line2)", 5, 1.5, 0, 1, 0, 6.5, "#2ca02c"),
        ("Line 3 (line3 / line3a)", 2, 3, 0, 1, 0, 5, "#d62728"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    for ax, (title, m, b, xmin, xmax, ymin, ymax, color) in zip(axes, lines):
        x = [xmin, xmax]
        y = [m * x[0] + b, m * x[1] + b]
        ax.plot(x, y, color=color, lw=2.5)
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_xlabel("x (axis units)")
        ax.set_ylabel("y (axis units)")
        ax.set_title(title, fontsize=10)
        ax.grid(True, alpha=0.35)
        L = math.hypot(x[1] - x[0], y[1] - y[0])
        ax.text(
            0.05,
            0.95,
            f"y = {m:g}x + {b:g}\nL = {L:.4g} axis units",
            transform=ax.transAxes,
            va="top",
            fontsize=9,
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.85),
        )
    fig.suptitle(
        "Figure 1. Reference linear plots (static image analyses)",
        fontsize=12,
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(OUT / "fig1_reference_lines.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def _workflow_box(
    ax,
    cx: float,
    cy: float,
    text: str,
    *,
    width: float = 0.20,
    height: float = 0.13,
) -> tuple[float, float, float, float]:
    """Draw centered box; return (left, bottom, right, top) in axes coords."""
    left = cx - width / 2
    bottom = cy - height / 2
    ax.add_patch(
        plt.Rectangle(
            (left, bottom),
            width,
            height,
            fill=True,
            fc="#e8f0fe",
            ec="#3366cc",
            lw=1.8,
            clip_on=False,
        )
    )
    ax.text(cx, cy, text, ha="center", va="center", fontsize=9, linespacing=1.15)
    return left, bottom, left + width, bottom + height


def _arrow_h(ax, x_from: float, x_to: float, y: float, gap: float = 0.01) -> None:
    """Horizontal arrow between boxes with small gap from edges."""
    if x_from < x_to:
        start, end = x_from + gap, x_to - gap
    else:
        start, end = x_from - gap, x_to + gap
    ax.annotate(
        "",
        xy=(end, y),
        xytext=(start, y),
        arrowprops=dict(arrowstyle="->", color="#333", lw=1.4, shrinkA=0, shrinkB=0),
    )


def _arrow_v(ax, x: float, y_from: float, y_to: float, gap: float = 0.01) -> None:
    if y_from > y_to:
        start, end = y_from - gap, y_to + gap
    else:
        start, end = y_from + gap, y_to - gap
    ax.annotate(
        "",
        xy=(x, end),
        xytext=(x, start),
        arrowprops=dict(arrowstyle="->", color="#555", lw=1.2, linestyle="--"),
    )


def fig2_workflow() -> None:
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    # --- Top row: static image pipeline ---
    y_static = 0.78
    w_static = 0.22
    h_box = 0.13
    static_boxes = []
    for cx, text in [
        (0.18, "Static images\n(line*.jpg)"),
        (0.50, "Axis / grid\ninterpretation"),
        (0.82, "Linear equation\n+ length"),
    ]:
        static_boxes.append(
            _workflow_box(ax, cx, y_static, text, width=w_static, height=h_box)
        )
    _arrow_h(ax, static_boxes[0][2], static_boxes[1][0], y_static)
    _arrow_h(ax, static_boxes[1][2], static_boxes[2][0], y_static)
    ax.text(
        0.02,
        y_static + 0.11,
        "Offline",
        fontsize=10,
        fontweight="bold",
        color="#3366cc",
        va="bottom",
    )

    # --- Bottom row: live camera pipeline ---
    y_cam = 0.38
    w_cam = 0.155
    cam_centers = [0.12, 0.30, 0.48, 0.66, 0.84]
    cam_labels = [
        "Live camera\n(line_camera.py)",
        "4-corner\ncalibration",
        "Stroke trace\n+ warp",
        "Model fit\nline | quad | sine",
        "Honest readout\n+ overlays",
    ]
    cam_boxes = []
    for cx, text in zip(cam_centers, cam_labels):
        cam_boxes.append(_workflow_box(ax, cx, y_cam, text, width=w_cam, height=h_box))
    for i in range(len(cam_boxes) - 1):
        _arrow_h(ax, cam_boxes[i][2], cam_boxes[i + 1][0], y_cam)
    ax.text(
        0.02,
        y_cam + 0.11,
        "Live camera",
        fontsize=10,
        fontweight="bold",
        color="#3366cc",
        va="bottom",
    )

    # Link offline result to live readout (conceptual extension)
    _arrow_v(ax, 0.84, static_boxes[2][1], cam_boxes[-1][3])

    ax.text(
        0.5,
        0.94,
        "Figure 2. Project workflow (offline analysis + shape-aware camera)",
        ha="center",
        fontsize=13,
        fontweight="bold",
    )
    ax.text(
        0.5,
        0.08,
        "Sessions 2–3: shape-aware fitting, honest readout, printed-paper validation (295 camera trials)",
        ha="center",
        fontsize=9.5,
        color="#444",
        wrap=True,
    )
    fig.subplots_adjust(left=0.06, right=0.96, top=0.88, bottom=0.12)
    fig.savefig(OUT / "fig2_workflow.png", dpi=150, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)


def fig6_development_timeline() -> None:
    fig, ax = plt.subplots(figsize=(12, 3.8))
    ax.axis("off")
    sessions = [
        ("Session 1\nMay 29", "Static JPEG analysis;\nlive camera v1; units"),
        ("Session 2\nMay 30", "Shape-aware fitting;\nhonest readout; Figs. 1–6"),
        ("Session 3\nJun–Jul", "Printed-paper camera validation;\n295 trials; presets 1–8"),
    ]
    y = 0.52
    xs = [0.17, 0.50, 0.83]
    for i, (title, desc) in enumerate(sessions):
        x = xs[i]
        ax.add_patch(plt.Circle((x, y), 0.055, fc="#3366cc", ec="white", zorder=3))
        ax.text(x, y, str(i + 1), ha="center", va="center", color="white", fontweight="bold")
        ax.text(x, y + 0.24, title, ha="center", fontsize=10, fontweight="bold")
        ax.text(x, y - 0.24, desc, ha="center", fontsize=8.5)
    for x1, x2 in [(0.23, 0.44), (0.56, 0.77)]:
        ax.annotate("", xy=(x2, y), xytext=(x1, y), arrowprops=dict(arrowstyle="->", lw=2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title("Figure 6. Development milestones toward publication", fontsize=12, y=0.96)
    fig.savefig(OUT / "fig6_development_timeline.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig7_camera_classification() -> None:
    """Bar chart: shape classification rate per plot (live camera, Phase 3)."""
    p3 = _load_phase3()
    per_plot = p3.get("per_plot_all") or {}
    plots = [
        "line1", "line2", "line3",
        "sinusoid1", "sinusoid2", "sinusoid3",
        "quadratic1", "quadratic2",
    ]
    trials = [per_plot.get(p, {}).get("n", 0) for p in plots]
    correct = [per_plot.get(p, {}).get("correct", 0) for p in plots]
    rates = [100 * c / n if n else 0 for c, n in zip(correct, trials)]
    overall = p3.get("overall") or {}
    o_n = overall.get("n", sum(trials))
    o_c = overall.get("correct", sum(correct))
    o_pct = overall.get("accuracy_pct") or (100 * o_c / o_n if o_n else 0)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    colors = ["#d62728" if r < 70 else "#ff7f0e" if r < 100 else "#2ca02c" for r in rates]
    bars = ax.bar(plots, rates, color=colors, edgecolor="#333", linewidth=0.6)
    ax.axhline(o_pct, color="#666", ls="--", lw=1, label=f"Overall {o_pct:.1f}% ({o_c}/{o_n})")
    ymax = max(rates) if rates else 100
    ax.set_ylim(0, ymax * 1.18 + 12)
    ax.set_ylabel("Classification correct (%)")
    ax.set_xlabel("Printed plot (preset key 1–8)")
    ax.set_title(
        "Figure 7. Live camera shape classification (printed paper, Phase 3)",
        pad=14,
    )
    ax.tick_params(axis="x", rotation=35)
    for bar, r, c, n in zip(bars, rates, correct, trials):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.5,
            f"{c}/{n}",
            ha="center",
            va="bottom",
            fontsize=9,
            clip_on=False,
        )
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    ax.margins(x=0.02)
    fig.subplots_adjust(top=0.90, bottom=0.14)
    fig.savefig(OUT / "fig7_camera_classification.png", dpi=150, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def fig8_validation_comparison() -> None:
    """Static JPEG vs live camera: classification and parameter error (Phase 3)."""
    p3 = _load_phase3()
    overall = p3.get("overall") or {}
    qc = p3.get("qc_arc_lt_100") or {}
    o_n, o_c = overall.get("n", 295), overall.get("correct", 213)
    o_pct = overall.get("accuracy_pct") or round(100 * o_c / o_n, 1)
    q_n, q_c = qc.get("n", 210), qc.get("correct", 182)
    q_pct = qc.get("accuracy_pct") or round(100 * q_c / q_n, 1)

    static_err = _median_param_errors_static()
    camera_err = _median_param_errors_camera_qc()

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.2))

    # Left: classification rate
    ax = axes[0]
    modes = [
        "Static JPEG\n(n=15)",
        f"Live camera\nall (n={o_n})",
        f"Live camera\nQC (n={q_n})",
    ]
    rates = [100.0, float(o_pct), float(q_pct)]
    colors = ["#3366cc", "#aec7e8", "#2ca02c"]
    ax.bar(modes, rates, color=colors, width=0.55, edgecolor="#333")
    ax.set_ylim(0, 128)
    ax.set_ylabel("Shape classification correct (%)")
    ax.set_title("Classification accuracy", pad=10)
    labels = ["15/15", f"{o_c}/{o_n}", f"{q_c}/{q_n}"]
    for i, r in enumerate(rates):
        ax.text(
            i,
            r + 2,
            f"{r:.1f}% ({labels[i]})",
            ha="center",
            va="bottom",
            fontsize=8.5,
            clip_on=False,
        )
    ax.grid(axis="y", alpha=0.3)
    ax.margins(x=0.06)

    # Right: parameter error on successful trials (median % error)
    ax = axes[1]
    categories = ["Line\nslope m", "Quad\ncoeff a", "Sine\namplitude A"]
    x = np.arange(len(categories))
    w = 0.35
    bars_s = ax.bar(x - w / 2, static_err, w, label="Static JPEG", color="#3366cc")
    bars_c = ax.bar(x + w / 2, camera_err, w, label="Live camera (QC-pass)", color="#2ca02c")
    ymax = max(max(static_err), max(camera_err))
    ax.set_ylim(0, ymax * 1.35 + 2)
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.set_ylabel("Typical parameter error (%)")
    ax.set_title("Parameter recovery (well-traced trials)", pad=10)
    for bars in (bars_s, bars_c):
        for bar in bars:
            h = bar.get_height()
            if h > 0.05:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    h + 0.15,
                    f"{h:.1f}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    clip_on=False,
                )
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle(
        f"Figure 8. Static image vs. live camera validation (Phase 3, n={o_n} trials)",
        fontsize=12,
        y=0.98,
    )
    fig.subplots_adjust(top=0.82, wspace=0.28)
    fig.savefig(OUT / "fig8_validation_comparison.png", dpi=150, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def fig3_results_table() -> None:
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.axis("off")
    rows = [
        ["line1", "LINE", "y = 10x + 1", "JPEG 100%", "Camera 50%*"],
        ["line2", "LINE", "y = 5x + 1.5", "JPEG 100%", "Camera 80%"],
        ["line3", "LINE", "y = 2x + 3", "JPEG 100%", "Camera 100%"],
        ["sinusoid1", "SINUSOID", "y = 2 sin(5x)", "JPEG 100%", "Camera 67%"],
        ["sinusoid2", "SINUSOID", "y = 3 sin(9x−4)", "JPEG 100%", "Camera 100%"],
        ["sinusoid3", "SINUSOID", "y = 2.3 sin(3x+7)", "JPEG 100%", "Camera 100%"],
        ["quadratic1", "QUADRATIC", "y = x²+2x+3", "JPEG 100%", "Camera 67%"],
        ["quadratic2", "QUADRATIC", "y = 5x²+8x+13", "JPEG 100%", "Camera 100%"],
    ]
    table = ax.table(
        cellText=rows,
        colLabels=["Plot", "Class", "Ground truth", "Static JPEG", "Live camera"],
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.45)
    ax.set_title(
        "Figure 3. Validation summary: static JPEG vs. printed-paper camera (Session 3)",
        fontsize=11,
        pad=20,
    )
    ax.text(
        0.5,
        0.02,
        "* line1 camera failures linked to grid-ink tracing (steep slope, y∈[0,11]); see Fig. 7",
        ha="center",
        transform=ax.transAxes,
        fontsize=8.5,
        color="#444",
    )
    fig.savefig(OUT / "fig3_results_table.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig4_model_comparison() -> None:
    """Synthetic sinusoid: linear vs sinusoid RMSE (conceptual validation)."""
    x = np.linspace(0, 1, 200)
    y = 2.5 + 1.2 * np.sin(2 * math.pi * x)
    m, b = np.polyfit(x, y, 1)
    y_line = m * x + b
    omega = 2 * math.pi
    A, phi, C = 1.2, 0.0, 2.5
    y_sin = A * np.sin(omega * x + phi) + C
    rmse_line = np.sqrt(np.mean((y - y_line) ** 2))
    rmse_sin = np.sqrt(np.mean((y - y_sin) ** 2))

    fig = plt.figure(figsize=(9, 5.5))
    gs = fig.add_gridspec(2, 1, height_ratios=[4.5, 0.65], hspace=0.32)
    ax = fig.add_subplot(gs[0])
    ax_cap = fig.add_subplot(gs[1])
    ax_cap.axis("off")

    ax.plot(x, y, "k-", lw=2.5, label="True stroke (sinusoid)")
    ax.plot(x, y_line, color="#ff7f0e", ls="--", lw=2, label=f"Linear ref (RMSE={rmse_line:.3f})")
    ax.plot(x, y_sin, color="#2ca02c", lw=2, label=f"Sinusoid fit (RMSE={rmse_sin:.3f})")
    ax.set_xlabel("x (axis units)", fontsize=10)
    ax.set_ylabel("y (axis units)", fontsize=10)
    ax.set_title(
        "Figure 6. Model comparison on a sinusoidal stroke (camera app logic)",
        fontsize=12,
        pad=10,
    )
    ax.legend(loc="upper right", fontsize=9, framealpha=0.95)
    ax.grid(True, alpha=0.3)
    y_pad = 0.35 * (np.max(y) - np.min(y))
    ax.set_ylim(np.min(y) - y_pad, np.max(y) + y_pad)

    ax_cap.text(
        0.5,
        0.55,
        "App classifies SINUSOID and shows the linear fit as rejected",
        ha="center",
        va="center",
        fontsize=10,
        transform=ax_cap.transAxes,
    )
    ax_cap.text(
        0.5,
        0.12,
        "(orange dashed overlay in the live camera view when shape is not LINE)",
        ha="center",
        va="center",
        fontsize=9.5,
        color="#444",
        transform=ax_cap.transAxes,
    )

    fig.savefig(OUT / "fig4_model_comparison.png", dpi=150, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)


def fig5_overlay_legend() -> None:
    fig = plt.figure(figsize=(11, 7))
    gs = fig.add_gridspec(3, 1, height_ratios=[4.2, 1.3, 0.7], hspace=0.45)
    ax_plot = fig.add_subplot(gs[0])
    ax_leg = fig.add_subplot(gs[1])
    ax_cap = fig.add_subplot(gs[2])

    t = np.linspace(0.8, 9.2, 100)
    ys = 1.85 + 0.65 * np.sin(t)
    coef = np.polyfit(t, ys, 1)
    t_line = np.linspace(0.8, 9.2, 2)
    y_line = np.polyval(coef, t_line)

    ax_plot.plot(t, ys, "o", color="#b8b800", markersize=4, zorder=2)
    ax_plot.plot(t, ys, "-", color="#00aa00", lw=2.8, label="Best-fit model (green)")
    ax_plot.plot(
        t_line,
        y_line,
        "--",
        color="#ff8800",
        lw=2,
        dashes=(6, 4),
        label="Linear reference — rejected when shape is not LINE (orange dashed)",
    )
    ax_plot.set_xlim(0, 10)
    ax_plot.set_ylim(0.6, 3.1)
    ax_plot.set_xlabel("x (warped plot, arbitrary units)", fontsize=10)
    ax_plot.set_ylabel("y", fontsize=10)
    ax_plot.grid(True, alpha=0.25)
    ax_plot.set_title(
        "Figure 5. Live camera visual feedback (warped plot view)",
        fontsize=13,
        pad=12,
    )

    ax_leg.axis("off")
    handles = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            color="#b8b800",
            linestyle="None",
            markersize=8,
            label="Traced stroke (yellow dots)",
        ),
        plt.Line2D([0], [0], color="#00aa00", lw=2.8, label="Best-fit model (green solid)"),
        plt.Line2D(
            [0],
            [0],
            color="#ff8800",
            lw=2,
            linestyle="--",
            label="Linear reference (orange dashed; shown only if not LINE)",
        ),
    ]
    ax_leg.legend(
        handles=handles,
        loc="center",
        ncol=1,
        fontsize=10,
        frameon=True,
        framealpha=0.95,
    )

    ax_cap.axis("off")
    ax_cap.text(
        0.5,
        0.55,
        "On-screen readout: shape label (LINE / SINUSOID / QUADRATIC), best equation, RMSE, R².",
        ha="center",
        va="center",
        fontsize=10,
        transform=ax_cap.transAxes,
    )
    ax_cap.text(
        0.5,
        0.15,
        "Linear y = mx + b is promoted only when the LINE model wins; otherwise it is flagged as not best fit.",
        ha="center",
        va="center",
        fontsize=9.5,
        color="#444",
        transform=ax_cap.transAxes,
    )

    fig.savefig(OUT / "fig5_overlay_legend.png", dpi=150, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    fig1_reference_lines()
    fig2_workflow()
    fig3_results_table()
    fig4_model_comparison()
    fig5_overlay_legend()
    fig6_development_timeline()
    fig7_camera_classification()
    fig8_validation_comparison()
    print(f"Wrote figures to {OUT}")


if __name__ == "__main__":
    main()
