#!/usr/bin/env python3
"""
Phase 3 live-camera analysis for MST manuscript.

Reads validation/results/camera_log.jsonl and writes:
  - validation/results/phase3_camera_summary.json
  - validation/results/PHASE3_CAMERA_RESULTS.md
  - validation/results/figures/phase3_accuracy_vs_arc.png
  - validation/results/figures/phase3_per_plot_raw_vs_qc.png
  - validation/results/figures/phase3_confusion_matrix.png

Usage:
  .venv/bin/python scripts/analyze_phase3_camera.py
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "validation" / "results" / "camera_log.jsonl"
GT_PATH = ROOT / "validation" / "ground_truth.json"
OUT_JSON = ROOT / "validation" / "results" / "phase3_camera_summary.json"
OUT_MD = ROOT / "validation" / "results" / "PHASE3_CAMERA_RESULTS.md"
FIG_DIR = ROOT / "validation" / "results" / "figures"

QC_ARC_THRESHOLD = 100.0
PILOT_N = 28


def load_trials() -> list[dict]:
    trials = []
    with open(LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                trials.append(json.loads(line))
    return trials


def load_ground_truth() -> dict:
    with open(GT_PATH) as f:
        return json.load(f)


def arc_length(t: dict) -> float:
    return float(t.get("arc_length") or 9999.0)


def accuracy(subset: list[dict]) -> dict:
    if not subset:
        return {"n": 0, "correct": 0, "accuracy_pct": None}
    correct = sum(1 for t in subset if t.get("class_correct"))
    return {
        "n": len(subset),
        "correct": correct,
        "accuracy_pct": round(100.0 * correct / len(subset), 2),
    }


def per_plot_stats(trials: list[dict], qc_only: bool = False) -> dict[str, dict]:
    by_plot: dict[str, list[dict]] = defaultdict(list)
    for t in trials:
        by_plot[t["plot_id"]].append(t)
    out = {}
    for pid in sorted(by_plot):
        rows = by_plot[pid]
        if qc_only:
            rows = [t for t in rows if arc_length(t) < QC_ARC_THRESHOLD]
        out[pid] = {
            **accuracy(rows),
            "ground_truth": rows[0].get("ground_truth", "") if rows else "",
            "expected_class": rows[0].get("expected_class", "") if rows else "",
        }
    return out


def arc_threshold_curve(trials: list[dict]) -> list[dict]:
    thresholds = [25, 50, 75, 100, 125, 150, 200, 300, 500, 10000]
    curve = []
    for th in thresholds:
        sub = [t for t in trials if arc_length(t) < th]
        curve.append({"threshold": th if th < 10000 else None, "label": f"<{th}" if th < 10000 else "all", **accuracy(sub)})
    return curve


def confusion_counts(trials: list[dict], misclassified_only: bool = True) -> list[dict]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for t in trials:
        if misclassified_only and t.get("class_correct"):
            continue
        exp = t.get("expected_class") or "?"
        det = t.get("detected_shape") or "?"
        counts[(exp, det)] += 1
    return [
        {"expected": k[0], "detected": k[1], "count": v}
        for k, v in sorted(counts.items(), key=lambda x: -x[1])
    ]


def line_slope_errors(trials: list[dict], gt: dict) -> dict[str, dict]:
    by_plot: dict[str, list[dict]] = defaultdict(list)
    for t in trials:
        by_plot[t["plot_id"]].append(t)
    out = {}
    for pid in ("line1", "line2", "line3"):
        key = f"{pid}.jpg"
        m_true = gt[key]["params"]["m"]
        errs = []
        for t in by_plot[pid]:
            if not t.get("class_correct") or arc_length(t) >= QC_ARC_THRESHOLD:
                continue
            p = t.get("params_fitted") or {}
            if "m" in p:
                errs.append(abs(p["m"] - m_true) / abs(m_true) * 100)
        if errs:
            out[pid] = {
                "n": len(errs),
                "mean_pct": round(statistics.mean(errs), 3),
                "sd_pct": round(statistics.stdev(errs), 3) if len(errs) > 1 else 0.0,
            }
    return out


def build_summary(trials: list[dict], gt: dict) -> dict:
    mis = [t for t in trials if not t.get("class_correct")]
    qc_sub = [t for t in trials if arc_length(t) < QC_ARC_THRESHOLD]
    sweet = [t for t in trials if 15 <= arc_length(t) <= 75]

    return {
        "qc_arc_threshold": QC_ARC_THRESHOLD,
        "total_trials": len(trials),
        "overall": accuracy(trials),
        "qc_arc_lt_100": accuracy(qc_sub),
        "qc_arc_15_75": accuracy(sweet),
        "pilot_first_28": accuracy(trials[:PILOT_N]),
        "extended_after_pilot": accuracy(trials[PILOT_N:]) if len(trials) > PILOT_N else accuracy([]),
        "misclassified": {
            "n": len(mis),
            "fraction_with_arc_gt_threshold": round(
                sum(1 for t in mis if arc_length(t) > QC_ARC_THRESHOLD) / len(mis) * 100, 1
            )
            if mis
            else 0.0,
        },
        "per_plot_all": per_plot_stats(trials, qc_only=False),
        "per_plot_qc": per_plot_stats(trials, qc_only=True),
        "arc_threshold_curve": arc_threshold_curve(trials),
        "confusion": confusion_counts(trials),
        "line_slope_errors_qc": line_slope_errors(trials, gt),
    }


def write_markdown(summary: dict) -> None:
    o = summary["overall"]
    qc = summary["qc_arc_lt_100"]
    lines = [
        "# Phase 3 live-camera results",
        "",
        f"**Total trials:** {summary['total_trials']}",
        f"**Overall accuracy:** {o['correct']}/{o['n']} ({o['accuracy_pct']}%)",
        f"**QC accuracy (arc < {QC_ARC_THRESHOLD}):** {qc['correct']}/{qc['n']} ({qc['accuracy_pct']}%)",
        f"**Misclassified with arc > {QC_ARC_THRESHOLD}:** "
        f"{summary['misclassified']['fraction_with_arc_gt_threshold']}% of failures",
        "",
        "## Per plot (all trials | QC-pass)",
        "",
        "| Plot | N (all) | Acc all | N (QC) | Acc QC |",
        "|------|---------|---------|--------|--------|",
    ]
    for pid in sorted(summary["per_plot_all"]):
        a = summary["per_plot_all"][pid]
        q = summary["per_plot_qc"].get(pid, {"n": 0, "accuracy_pct": None})
        qacc = f"{q['accuracy_pct']}%" if q["n"] else "—"
        lines.append(
            f"| {pid} | {a['n']} | {a['accuracy_pct']}% | {q['n']} | {qacc} |"
        )
    lines.extend(["", "## Confusion (misclassified)", ""])
    for c in summary["confusion"][:10]:
        lines.append(f"- {c['expected']} → {c['detected']}: {c['count']}")
    lines.extend(["", "## Figures", ""])
    lines.append("- `figures/phase3_accuracy_vs_arc.png`")
    lines.append("- `figures/phase3_per_plot_raw_vs_qc.png`")
    lines.append("- `figures/phase3_confusion_matrix.png`")
    OUT_MD.write_text("\n".join(lines) + "\n")


def plot_accuracy_vs_arc(summary: dict) -> Path:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    curve = summary["arc_threshold_curve"]
    xs = [c["threshold"] for c in curve if c["threshold"] is not None]
    ys = [c["accuracy_pct"] for c in curve if c["threshold"] is not None]
    ns = [c["n"] for c in curve if c["threshold"] is not None]

    fig, ax1 = plt.subplots(figsize=(7, 4.5))
    ax1.plot(xs, ys, "o-", color="#1f77b4", lw=2, markersize=7)
    ax1.axvline(QC_ARC_THRESHOLD, color="#d62728", ls="--", lw=1.5, label=f"QC threshold ({QC_ARC_THRESHOLD:g})")
    ax1.set_xlabel("Maximum arc length included (axis units)")
    ax1.set_ylabel("Classification accuracy (%)")
    ax1.set_ylim(0, 105)
    ax1.grid(True, alpha=0.3)
    for x, y, n in zip(xs, ys, ns):
        if x in (50, 100, 150, 200):
            ax1.annotate(f"n={n}", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)
    ax1.legend(loc="lower right")
    ax1.set_title(f"Figure 4. Live-camera accuracy vs. arc-length quality gate (n={summary['total_trials']})")
    fig.tight_layout()
    path = FIG_DIR / "phase3_accuracy_vs_arc.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_per_plot_raw_vs_qc(summary: dict) -> Path:
    plots = sorted(summary["per_plot_all"].keys())
    raw = [summary["per_plot_all"][p]["accuracy_pct"] for p in plots]
    qc_vals = []
    for p in plots:
        q = summary["per_plot_qc"].get(p, {})
        qc_vals.append(q["accuracy_pct"] if q.get("n", 0) > 0 else 0)

    x = np.arange(len(plots))
    w = 0.35
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(x - w / 2, raw, w, label="All trials", color="#aec7e8")
    ax.bar(x + w / 2, qc_vals, w, label=f"QC arc < {QC_ARC_THRESHOLD:g}", color="#1f77b4")
    ax.set_xticks(x)
    ax.set_xticklabels(plots, rotation=30, ha="right")
    ax.set_ylabel("Classification accuracy (%)")
    ax.set_ylim(0, 105)
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_title("Figure 3. Per-plot accuracy: all trials vs. QC-pass subset (Phase 3)")
    fig.tight_layout()
    path = FIG_DIR / "phase3_per_plot_raw_vs_qc.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_confusion(summary: dict) -> Path:
    conf = summary["confusion"][:8]
    if not conf:
        return FIG_DIR / "phase3_confusion_matrix.png"
    labels = [f"{c['expected'][:4]}→{c['detected'][:4]}" for c in conf]
    counts = [c["count"] for c in conf]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(labels[::-1], counts[::-1], color="#ff7f0e")
    ax.set_xlabel("Count (misclassified trials)")
    ax.set_title("Figure 5. Top misclassification modes (Phase 3)")
    fig.tight_layout()
    path = FIG_DIR / "phase3_confusion_matrix.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def main() -> None:
    if not LOG.exists():
        raise SystemExit(f"No log: {LOG}")
    trials = load_trials()
    gt = load_ground_truth()
    summary = build_summary(trials, gt)
    OUT_JSON.write_text(json.dumps(summary, indent=2))
    write_markdown(summary)
    p1 = plot_accuracy_vs_arc(summary)
    p2 = plot_per_plot_raw_vs_qc(summary)
    p3 = plot_confusion(summary)
    print(f"Trials: {summary['total_trials']}")
    print(f"Overall: {summary['overall']['accuracy_pct']}%")
    print(f"QC (arc<{QC_ARC_THRESHOLD}): {summary['qc_arc_lt_100']['accuracy_pct']}%")
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {p1.name}, {p2.name}, {p3.name}")


if __name__ == "__main__":
    main()
