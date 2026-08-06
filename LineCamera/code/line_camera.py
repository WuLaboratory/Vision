#!/usr/bin/env python3
"""
Live camera: trace plotted strokes, compare line / quadratic / sinusoid models,
and show honest shape readout with visual overlays.

Usage:
  .venv/bin/python line_camera.py
  .venv/bin/python line_camera.py --camera 0

Keys:
  q / Esc     quit
  m           manual: click 4 plot corners (TL, TR, BR, BL)
  a           auto-detect plot rectangle
  1 / 2 / 3   line presets (line1, line2, line3)
  4 / 5 / 6   sinusoid presets (sinusoid1–3)
  7 / 8       quadratic presets (quadratic1–2)
  [ ]         decrease / increase y_max
  , .         decrease / increase x_max
  space       pause / resume
  s           save camera frame to captures/
  l           log trial to validation/results/ (use with --validate)
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

WARP_W = 640
WARP_H = 480
CAPTURE_DIR = Path(__file__).resolve().parent / "captures"
VALIDATION_DIR = Path(__file__).resolve().parent / "validation" / "results"
GROUND_TRUTH_PATH = Path(__file__).resolve().parent / "validation" / "ground_truth.json"


@dataclass
class AxisConfig:
    x_min: float = 0.0
    x_max: float = 1.0
    y_min: float = 0.0
    y_max: float = 5.0
    x_unit: str = "x"
    y_unit: str = "y"
    length_unit: str = "axis units"

    def label(self) -> str:
        return (
            f"x∈[{self.x_min:g},{self.x_max:g}] {self.x_unit}  "
            f"y∈[{self.y_min:g},{self.y_max:g}] {self.y_unit}"
        )

    def format_length(self, value: float) -> str:
        return f"Length: {value:.4g} {self.length_unit}"


@dataclass
class PlotPreset:
    plot_id: str
    short_name: str
    axes: AxisConfig
    expected_class: str
    ground_truth: str


def _build_presets() -> dict[int, PlotPreset]:
    u = dict(x_unit="x", y_unit="y", length_unit="axis units")
    return {
        ord("1"): PlotPreset(
            "line1", "line1",
            AxisConfig(0, 1, 0, 11, **u),
            "LINE", "y = 10x + 1",
        ),
        ord("2"): PlotPreset(
            "line2", "line2",
            AxisConfig(0, 1, 0, 6.5, **u),
            "LINE", "y = 5x + 1.5",
        ),
        ord("3"): PlotPreset(
            "line3", "line3",
            AxisConfig(0, 1, 0, 5, **u),
            "LINE", "y = 2x + 3",
        ),
        ord("4"): PlotPreset(
            "sinusoid1", "sinusoid1",
            AxisConfig(0, 1, -2, 2, **u),
            "SINUSOID", "y = 2 sin(5x)",
        ),
        ord("5"): PlotPreset(
            "sinusoid2", "sinusoid2",
            AxisConfig(0, 1, -3, 3, **u),
            "SINUSOID", "y = 3 sin(9x - 4)",
        ),
        ord("6"): PlotPreset(
            "sinusoid3", "sinusoid3",
            AxisConfig(0, 1, -1.5, 2.5, **u),
            "SINUSOID", "y = 2.3 sin(3x + 7)",
        ),
        ord("7"): PlotPreset(
            "quadratic1", "quadratic1",
            AxisConfig(0, 1, 3, 6, **u),
            "QUADRATIC", "y = x^2 + 2x + 3",
        ),
        ord("8"): PlotPreset(
            "quadratic2", "quadratic2",
            AxisConfig(0, 1, 12, 26, **u),
            "QUADRATIC", "y = 5x^2 + 8x + 13",
        ),
    }


PRESET_BY_KEY = _build_presets()
PRESETS = {k: p.axes for k, p in PRESET_BY_KEY.items()}
PRESET_HELP = (
    "Presets: 1-3 lines | 4-6 sinusoids | 7-8 quadratics | l=log trial | s=save frame"
)


@dataclass
class ModelScores:
    name: str
    rmse: float
    r2: float
    equation: str
    params: dict[str, float]


@dataclass
class ShapeAnalysis:
    """Detected stroke with best-fit model and comparison metrics."""

    shape: str  # LINE, SINUSOID, QUADRATIC, CURVED
    best: ModelScores
    line_scores: ModelScores
    stroke_px: list[tuple[int, int]]
    fit_curve_px: list[tuple[int, int]]
    line_ref_px: list[tuple[int, int]]
    readout_lines: list[str]
    arc_length: float
    # Populated when shape == LINE
    slope: float = 0.0
    intercept: float = 0.0
    seg_length: float = 0.0
    p1: tuple[float, float] = (0.0, 0.0)
    p2: tuple[float, float] = (0.0, 0.0)
    p1_px: tuple[int, int] = (0, 0)
    p2_px: tuple[int, int] = (0, 0)


def order_quad(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    pts = np.asarray(pts, dtype=np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).reshape(-1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return np.array([tl, tr, br, bl], dtype=np.float32)


def warp_plot(frame: np.ndarray, quad: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    dst = np.array(
        [[0, 0], [WARP_W - 1, 0], [WARP_W - 1, WARP_H - 1], [0, WARP_H - 1]],
        dtype=np.float32,
    )
    quad = order_quad(quad)
    matrix = cv2.getPerspectiveTransform(quad, dst)
    warped = cv2.warpPerspective(frame, matrix, (WARP_W, WARP_H))
    inv = cv2.getPerspectiveTransform(dst, quad)
    return warped, inv


def find_largest_quad(frame: np.ndarray) -> np.ndarray | None:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0.0
    h, w = frame.shape[:2]
    min_area = 0.08 * h * w
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) == 4 and area > best_area:
            best_area = area
            best = approx.reshape(4, 2).astype(np.float32)
    return best


def pixel_to_data(px: float, py: float, axes: AxisConfig) -> tuple[float, float]:
    x = axes.x_min + (px / (WARP_W - 1)) * (axes.x_max - axes.x_min)
    y = axes.y_max - (py / (WARP_H - 1)) * (axes.y_max - axes.y_min)
    return x, y


def data_to_pixel(x: float, y: float, axes: AxisConfig) -> tuple[int, int]:
    px = int((x - axes.x_min) / (axes.x_max - axes.x_min) * (WARP_W - 1))
    py = int((axes.y_max - y) / (axes.y_max - axes.y_min) * (WARP_H - 1))
    return px, py


def _metrics(y: np.ndarray, y_pred: np.ndarray) -> tuple[float, float]:
    resid = y - y_pred
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    rmse = math.sqrt(float(np.mean(resid**2)))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else 0.0
    return rmse, r2


def extract_stroke_pixels(warped: np.ndarray) -> np.ndarray | None:
    """Largest ink contour as ordered pixel coordinates (N, 2) = (x, y)."""
    ink = _build_ink_mask(warped)
    kernel = np.ones((5, 5), np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(ink, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        ys, xs = np.where(ink > 0)
        if len(xs) < 40:
            return None
        pts = np.column_stack([xs, ys]).astype(np.float32)
        order = np.argsort(pts[:, 0])
        return pts[order]

    best = max(contours, key=cv2.contourArea)
    if cv2.contourArea(best) < 200:
        return None
    pts = best.reshape(-1, 2).astype(np.float32)
    step = max(1, len(pts) // 450)
    pts = pts[::step]
    if len(pts) < 30:
        return None
    return pts


def stroke_to_data(pts_px: np.ndarray, axes: AxisConfig) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for px, py in pts_px:
        xd, yd = pixel_to_data(float(px), float(py), axes)
        xs.append(xd)
        ys.append(yd)
    x = np.array(xs, dtype=np.float64)
    y = np.array(ys, dtype=np.float64)
    order = np.argsort(x)
    return x[order], y[order]


def _arc_length_data(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2:
        return 0.0
    return float(np.sum(np.hypot(np.diff(x), np.diff(y))))


def _fit_line(x: np.ndarray, y: np.ndarray) -> ModelScores:
    coef = np.polyfit(x, y, 1)
    m, b = float(coef[0]), float(coef[1])
    y_pred = m * x + b
    rmse, r2 = _metrics(y, y_pred)
    eq = f"y = {m:.4g} x + {b:.4g}"
    return ModelScores("line", rmse, r2, eq, {"m": m, "b": b})


def _fit_quadratic(x: np.ndarray, y: np.ndarray) -> ModelScores:
    coef = np.polyfit(x, y, 2)
    a, b, c = float(coef[0]), float(coef[1]), float(coef[2])
    y_pred = a * x**2 + b * x + c
    rmse, r2 = _metrics(y, y_pred)
    eq = f"y = {a:.4g} x^2 + {b:.4g} x + {c:.4g}"
    return ModelScores("quadratic", rmse, r2, eq, {"a": a, "b": b, "c": c})


def _fit_sinusoid(x: np.ndarray, y: np.ndarray) -> ModelScores | None:
    x_span = float(np.ptp(x))
    if x_span < 1e-6:
        return None
    y_mean = float(np.mean(y))
    y_centered = y - y_mean
    omega_min = math.pi / x_span
    omega_max = 4 * math.pi / x_span
    best_rmse = float("inf")
    best: ModelScores | None = None
    for omega in np.linspace(omega_min, omega_max, 48):
        s = np.sin(omega * x)
        c = np.cos(omega * x)
        design = np.column_stack([s, c, np.ones_like(x)])
        coeffs, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
        a_sin, b_cos, c0 = (float(coeffs[0]), float(coeffs[1]), float(coeffs[2]))
        y_pred = design @ coeffs
        rmse, r2 = _metrics(y, y_pred)
        if rmse < best_rmse:
            amp = math.hypot(a_sin, b_cos)
            phase = math.atan2(b_cos, a_sin)
            eq = (
                f"y = {amp:.4g} sin({omega:.4g} x + {phase:.4g}) + {c0:.4g}"
            )
            best_rmse = rmse
            best = ModelScores(
                "sinusoid",
                rmse,
                r2,
                eq,
                {"A": amp, "omega": float(omega), "phi": phase, "C": c0},
            )
    return best


def _eval_model(name: str, params: dict[str, float], x: np.ndarray) -> np.ndarray:
    if name == "line":
        return params["m"] * x + params["b"]
    if name == "quadratic":
        return params["a"] * x**2 + params["b"] * x + params["c"]
    if name == "sinusoid":
        return (
            params["A"] * np.sin(params["omega"] * x + params["phi"]) + params["C"]
        )
    return np.zeros_like(x)


def _sample_curve_px(
    model: ModelScores,
    axes: AxisConfig,
    x_data: np.ndarray,
    n: int = 120,
) -> list[tuple[int, int]]:
    x0, x1 = float(np.min(x_data)), float(np.max(x_data))
    if x1 - x0 < 1e-9:
        return []
    xs = np.linspace(x0, x1, n)
    ys = _eval_model(model.name, model.params, xs)
    out: list[tuple[int, int]] = []
    for xv, yv in zip(xs, ys):
        px, py = data_to_pixel(float(xv), float(yv), axes)
        if 0 <= px < WARP_W and 0 <= py < WARP_H:
            out.append((px, py))
    return out


def _line_segment_from_stroke(
    line: ModelScores,
    x: np.ndarray,
    y: np.ndarray,
    axes: AxisConfig,
) -> tuple[tuple[float, float], tuple[float, float], tuple[int, int], tuple[int, int], float]:
    m, b = line.params["m"], line.params["b"]
    x0, x1 = float(np.min(x)), float(np.max(x))
    y0, y1 = m * x0 + b, m * x1 + b
    p1, p2 = (x0, y0), (x1, y1)
    p1_px = data_to_pixel(x0, y0, axes)
    p2_px = data_to_pixel(x1, y1, axes)
    seg_len = math.hypot(x1 - x0, y1 - y0)
    return p1, p2, p1_px, p2_px, seg_len


def _choose_shape(
    line: ModelScores,
    quad: ModelScores | None,
    sine: ModelScores | None,
    y_span: float,
) -> tuple[str, ModelScores, list[str]]:
    """Pick best model with complexity penalty; build honest readout lines."""
    candidates: list[tuple[float, ModelScores, str, float]] = [
        (line.rmse * 1.0, line, "LINE", 0.0),
    ]
    if quad is not None:
        candidates.append((quad.rmse * 1.08, quad, "QUADRATIC", 0.08))
    if sine is not None:
        candidates.append((sine.rmse * 1.12, sine, "SINUSOID", 0.12))

    candidates.sort(key=lambda t: t[0])
    _, best, shape_label, _ = candidates[0]

    lines: list[str] = [
        f"Shape: {shape_label}",
        f"Best fit: {best.equation}",
        f"RMSE: {best.rmse:.4g}  R²: {best.r2:.3f}",
    ]

    rel_tol = max(0.02 * y_span, 1e-6)
    line_is_good = line.rmse <= rel_tol

    if shape_label == "LINE":
        if line_is_good:
            lines.append("Linear model: good fit")
        else:
            lines.append("Linear model: acceptable vs alternatives")
    else:
        lines.append("Linear model: NOT best fit")
        lines.append(f"  line RMSE {line.rmse:.4g}  (ref only)")
        if sine is not None and shape_label == "SINUSOID":
            imp = (1 - sine.rmse / line.rmse) * 100 if line.rmse > 0 else 0
            lines.append(f"  sinusoid RMSE {sine.rmse:.4g}  ({imp:.0f}% vs line)")

    if shape_label != "LINE" and line.rmse > rel_tol:
        lines.append(f"Do not use: {line.equation}")

    return shape_label, best, lines


def analyze_shape(warped: np.ndarray, axes: AxisConfig) -> ShapeAnalysis | None:
    pts_px = extract_stroke_pixels(warped)
    if pts_px is None:
        return None

    x, y = stroke_to_data(pts_px, axes)
    if len(x) < 35:
        return None

    line = _fit_line(x, y)
    quad = _fit_quadratic(x, y) if len(x) >= 20 else None
    sine = _fit_sinusoid(x, y) if len(x) >= 40 and np.ptp(x) > 0.05 * (axes.x_max - axes.x_min) else None

    y_span = float(np.ptp(y))
    shape_label, best, readout = _choose_shape(line, quad, sine, y_span)

    stroke_list = [(int(p[0]), int(p[1])) for p in pts_px[:: max(1, len(pts_px) // 80)]]
    fit_px = _sample_curve_px(best, axes, x)
    line_ref_px = _sample_curve_px(line, axes, x)

    arc_len = _arc_length_data(x, y)
    analysis = ShapeAnalysis(
        shape=shape_label,
        best=best,
        line_scores=line,
        stroke_px=stroke_list,
        fit_curve_px=fit_px,
        line_ref_px=line_ref_px,
        readout_lines=readout,
        arc_length=arc_len,
    )

    if shape_label == "LINE":
        p1, p2, p1_px, p2_px, seg_len = _line_segment_from_stroke(line, x, y, axes)
        analysis.slope = line.params["m"]
        analysis.intercept = line.params["b"]
        analysis.seg_length = seg_len
        analysis.p1, analysis.p2 = p1, p2
        analysis.p1_px, analysis.p2_px = p1_px, p2_px
        readout.append(axes.format_length(seg_len))

    readout.append(f"Arc length (stroke): {arc_len:.4g} {axes.length_unit}")
    analysis.readout_lines = readout
    return analysis


def _fitline_params(points: np.ndarray) -> tuple[float, float, float, float]:
    """cv2.fitLine returns shape (4, 1); convert to plain floats."""
    line = cv2.fitLine(points, cv2.DIST_HUBER, 0, 0.01, 0.01)
    vx, vy, x0, y0 = np.asarray(line, dtype=np.float64).reshape(-1)
    return float(vx), float(vy), float(x0), float(y0)


def _segment_angle_deg(x1: int, y1: int, x2: int, y2: int) -> float:
    angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))
    return 180 - angle if angle > 90 else angle


def _mask_plot_border(mask: np.ndarray, margin: int = 8) -> None:
    mask[:margin, :] = 0
    mask[-margin:, :] = 0
    mask[:, :margin] = 0
    mask[:, -margin:] = 0


def _build_ink_mask(warped: np.ndarray) -> np.ndarray:
    """Dark pen strokes and blue plot lines, with grid somewhat suppressed."""
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, dark = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    b, g, r = cv2.split(warped)
    blue = cv2.inRange(
        warped,
        (120, 0, 0),
        (255, 120, 120),
    )  # BGR: blue channel dominant
    ink = cv2.bitwise_or(dark, blue)
    ink = cv2.medianBlur(ink, 5)
    _mask_plot_border(ink)
    return ink


def _hough_best_segment(
    edges: np.ndarray,
    *,
    threshold: int,
    min_len_frac: float,
    min_angle: float,
    max_angle: float,
) -> tuple[int, int, int, int] | None:
    min_len = int(min_len_frac * min(WARP_W, WARP_H))
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=threshold,
        minLineLength=max(min_len, 40),
        maxLineGap=25,
    )
    if lines is None:
        return None

    best: tuple[float, tuple[int, int, int, int]] | None = None
    for x1, y1, x2, y2 in lines[:, 0]:
        angle = _segment_angle_deg(int(x1), int(y1), int(x2), int(y2))
        if angle < min_angle or angle > max_angle:
            continue
        length_px = math.hypot(x2 - x1, y2 - y1)
        if best is None or length_px > best[0]:
            best = (length_px, (int(x1), int(y1), int(x2), int(y2)))
    return best[1] if best else None


def _endpoints_from_segment(
    x1: int, y1: int, x2: int, y2: int, edge_mask: np.ndarray
) -> tuple[tuple[int, int], tuple[int, int]]:
    mask = np.zeros_like(edge_mask)
    cv2.line(mask, (x1, y1), (x2, y2), 255, 10)
    ys, xs = np.where((edge_mask > 0) & (mask > 0))
    if len(xs) < 20:
        xs = np.array([x1, x2], dtype=np.float32)
        ys = np.array([y1, y2], dtype=np.float32)
    else:
        xs = xs.astype(np.float32)
        ys = ys.astype(np.float32)

    vx, vy, x0, y0 = _fitline_params(np.column_stack([xs, ys]))

    def project(px: float, py: float) -> float:
        return (px - x0) * vx + (py - y0) * vy

    t_vals = [project(float(x1), float(y1)), project(float(x2), float(y2))]
    for x in (0, WARP_W - 1):
        if abs(vx) > 1e-6:
            y = y0 + vy / vx * (x - x0)
            if 0 <= y < WARP_H:
                t_vals.append(project(x, y))
    for y in (0, WARP_H - 1):
        if abs(vy) > 1e-6:
            x = x0 + vx / vy * (y - y0)
            if 0 <= x < WARP_W:
                t_vals.append(project(x, y))

    t_min, t_max = min(t_vals), max(t_vals)
    p1 = (int(x0 + vx * t_min), int(y0 + vy * t_min))
    p2 = (int(x0 + vx * t_max), int(y0 + vy * t_max))

    def clip_pt(px: int, py: int) -> tuple[int, int]:
        return (
            int(np.clip(px, 0, WARP_W - 1)),
            int(np.clip(py, 0, WARP_H - 1)),
        )

    return clip_pt(*p1), clip_pt(*p2)


def detect_drawn_line(
    warped: np.ndarray,
) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Find the dominant non-axis-aligned line in the warped plot."""
    ink = _build_ink_mask(warped)
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.bitwise_or(edges, ink)
    _mask_plot_border(edges)

    # Try progressively looser Hough settings (webcam images are noisy).
    hough_passes = (
        {"threshold": 50, "min_len_frac": 0.2, "min_angle": 10, "max_angle": 80},
        {"threshold": 35, "min_len_frac": 0.15, "min_angle": 8, "max_angle": 82},
        {"threshold": 25, "min_len_frac": 0.12, "min_angle": 5, "max_angle": 85},
    )
    segment: tuple[int, int, int, int] | None = None
    for params in hough_passes:
        segment = _hough_best_segment(edges, **params)
        if segment is not None:
            break

    if segment is None:
        return None

    x1, y1, x2, y2 = segment
    return _endpoints_from_segment(x1, y1, x2, y2, edges)


def map_point_to_frame(
    pt: tuple[int, int], inv_matrix: np.ndarray
) -> tuple[int, int]:
    src = np.array([[[pt[0], pt[1]]]], dtype=np.float32)
    dst = cv2.perspectiveTransform(src, inv_matrix)[0, 0]
    return int(dst[0]), int(dst[1])


def _draw_polyline_on_frame(
    frame: np.ndarray,
    pts_px: list[tuple[int, int]],
    inv_matrix: np.ndarray,
    color: tuple[int, int, int],
    thickness: int,
    dashed: bool = False,
) -> None:
    if len(pts_px) < 2:
        return
    mapped = [map_point_to_frame(p, inv_matrix) for p in pts_px]
    for i in range(len(mapped) - 1):
        if dashed and i % 2 == 1:
            continue
        cv2.line(frame, mapped[i], mapped[i + 1], color, thickness, cv2.LINE_AA)


def draw_overlay(
    frame: np.ndarray,
    quad: np.ndarray | None,
    analysis: ShapeAnalysis | None,
    inv_matrix: np.ndarray | None,
    axes: AxisConfig,
    status: str,
    paused: bool,
    calibrator: ManualCalibrator | None = None,
) -> np.ndarray:
    out = frame.copy()
    if calibrator is not None and calibrator.points:
        for i, (px, py) in enumerate(calibrator.points):
            cv2.circle(out, (px, py), 8, (0, 255, 255), -1)
            cv2.putText(
                out,
                str(i + 1),
                (px + 10, py - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
    if quad is not None:
        cv2.polylines(
            out,
            [order_quad(quad).astype(np.int32)],
            True,
            (0, 255, 0),
            2,
        )
    if analysis is not None and inv_matrix is not None:
        for pt in analysis.stroke_px[::2]:
            fp = map_point_to_frame(pt, inv_matrix)
            cv2.circle(out, fp, 2, (255, 255, 0), -1)
        _draw_polyline_on_frame(
            out, analysis.fit_curve_px, inv_matrix, (0, 255, 0), 3
        )
        if analysis.shape != "LINE":
            _draw_polyline_on_frame(
                out,
                analysis.line_ref_px,
                inv_matrix,
                (0, 140, 255),
                1,
                dashed=True,
            )
        elif analysis.p1_px and analysis.p2_px:
            a = map_point_to_frame(analysis.p1_px, inv_matrix)
            b = map_point_to_frame(analysis.p2_px, inv_matrix)
            cv2.line(out, a, b, (0, 255, 0), 3, cv2.LINE_AA)

    lines = [
        status,
        f"Axes: {axes.label()}",
        PRESET_HELP,
    ]
    if analysis is not None:
        lines.extend(analysis.readout_lines[:8])
    y0 = 28
    for i, text in enumerate(lines):
        cv2.putText(
            out,
            text,
            (12, y0 + i * 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (20, 20, 20),
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            out,
            text,
            (12, y0 + i * 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (240, 240, 240),
            1,
            cv2.LINE_AA,
        )
    if paused:
        cv2.putText(
            out,
            "PAUSED",
            (out.shape[1] - 120, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
    return out


def draw_warp_preview(warped: np.ndarray, analysis: ShapeAnalysis | None) -> np.ndarray:
    preview = warped.copy()
    if analysis is None:
        return preview
    for pt in analysis.stroke_px:
        cv2.circle(preview, pt, 2, (255, 255, 0), -1)
    pts = analysis.fit_curve_px
    for i in range(len(pts) - 1):
        cv2.line(preview, pts[i], pts[i + 1], (0, 255, 0), 2, cv2.LINE_AA)
    if analysis.shape != "LINE":
        ref = analysis.line_ref_px
        for i in range(len(ref) - 1):
            if i % 2 == 0:
                cv2.line(preview, ref[i], ref[i + 1], (0, 140, 255), 1, cv2.LINE_AA)
        cv2.putText(
            preview,
            "orange dashed = linear ref (rejected)",
            (8, WARP_H - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 140, 255),
            1,
            cv2.LINE_AA,
        )
    else:
        cv2.line(preview, analysis.p1_px, analysis.p2_px, (0, 255, 0), 2)
        cv2.circle(preview, analysis.p1_px, 5, (0, 255, 255), -1)
        cv2.circle(preview, analysis.p2_px, 5, (0, 255, 255), -1)
    cv2.putText(
        preview,
        "green = best model  yellow = traced stroke",
        (8, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (240, 240, 240),
        1,
        cv2.LINE_AA,
    )
    return preview


def log_camera_trial(
    preset: PlotPreset | None,
    analysis: ShapeAnalysis | None,
    frame: np.ndarray | None,
    warped: np.ndarray | None,
    *,
    trial_note: str = "",
) -> Path:
    """Append one validation trial; save frame + warp overlay."""
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    camera_dir = VALIDATION_DIR / "camera_captures"
    camera_dir.mkdir(exist_ok=True)
    ts = int(time.time())
    stem = f"{preset.plot_id if preset else 'unknown'}_{ts}"

    frame_path = None
    warp_path = None
    if frame is not None:
        frame_path = camera_dir / f"{stem}_frame.jpg"
        cv2.imwrite(str(frame_path), frame)
    if warped is not None:
        warp_path = camera_dir / f"{stem}_warp.jpg"
        cv2.imwrite(str(warp_path), draw_warp_preview(warped, analysis))

    record = {
        "timestamp": ts,
        "plot_id": preset.plot_id if preset else None,
        "expected_class": preset.expected_class if preset else None,
        "ground_truth": preset.ground_truth if preset else None,
        "detected_shape": analysis.shape if analysis else None,
        "class_correct": (
            preset is not None
            and analysis is not None
            and analysis.shape == preset.expected_class
        ),
        "equation": analysis.best.equation if analysis else None,
        "rmse": analysis.best.rmse if analysis else None,
        "r2": analysis.best.r2 if analysis else None,
        "line_rmse": analysis.line_scores.rmse if analysis else None,
        "params_fitted": analysis.best.params if analysis else None,
        "arc_length": analysis.arc_length if analysis else None,
        "trial_note": trial_note,
        "frame_path": str(frame_path) if frame_path else None,
        "warp_path": str(warp_path) if warp_path else None,
    }
    log_path = VALIDATION_DIR / "camera_log.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")
    return log_path


class ManualCalibrator:
    def __init__(self) -> None:
        self.points: list[tuple[int, int]] = []
        self.active = False

    def reset(self) -> None:
        self.points.clear()
        self.active = False

    def start(self) -> None:
        self.points.clear()
        self.active = True

    def click(self, x: int, y: int) -> None:
        if self.active and len(self.points) < 4:
            self.points.append((x, y))

    def quad(self) -> np.ndarray | None:
        if len(self.points) == 4:
            return np.array(self.points, dtype=np.float32)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Live shape detector for plotted curves (line / quadratic / sinusoid)."
    )
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default 0)")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Enable trial logging (press l); writes validation/results/camera_log.jsonl",
    )
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit(
            f"Could not open camera {args.camera}. "
            "Grant Camera access in System Settings > Privacy & Security."
        )

    axes = AxisConfig()
    active_preset: PlotPreset | None = None
    quad: np.ndarray | None = None
    inv_matrix: np.ndarray | None = None
    calibrator = ManualCalibrator()
    paused = False
    status = "Press 1-8 for plot preset, then m + 4 corners (TL,TR,BR,BL)"
    last_analysis: ShapeAnalysis | None = None
    smooth_shape: str | None = None

    CAPTURE_DIR.mkdir(exist_ok=True)
    win = "Shape detector (main)"
    warp_win = "Warped plot"
    cv2.namedWindow(win)
    cv2.namedWindow(warp_win)

    def on_mouse(event: int, x: int, y: int, *_args) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            calibrator.click(x, y)

    cv2.setMouseCallback(win, on_mouse)

    while True:
        if not paused:
            ok, frame = cap.read()
            if not ok:
                status = "Camera read failed"
                break
        else:
            ok = frame is not None  # type: ignore[has-type]
            if not ok:
                break

        key = cv2.waitKey(1) & 0xFF

        if key in (ord("q"), 27):
            break
        if key == ord(" "):
            paused = not paused
        if key == ord("m"):
            calibrator.start()
            quad = None
            last_analysis = None
            smooth_shape = None
            status = "Manual: click plot corners 1-4 (TL, TR, BR, BL)"
        if key == ord("a"):
            q = find_largest_quad(frame)
            if q is not None:
                quad = q
                status = "Auto-detected plot outline"
            else:
                status = "Auto detect failed — use manual (m)"
        if key == ord("s"):
            path = CAPTURE_DIR / f"frame_{int(time.time())}.jpg"
            cv2.imwrite(str(path), frame)
            status = f"Saved {path.name}"

        if key == ord("l"):
            if not args.validate:
                status = "Start with --validate to enable logging (l)"
            elif last_analysis is None:
                status = "Nothing to log — calibrate corners first"
            else:
                log_path = log_camera_trial(
                    active_preset, last_analysis, frame, warped
                )
                ok = (
                    active_preset is not None
                    and last_analysis.shape == active_preset.expected_class
                )
                status = (
                    f"Logged trial ({'OK' if ok else 'CHECK'}) -> {log_path.name}"
                )

        if key in PRESET_BY_KEY:
            active_preset = PRESET_BY_KEY[key]
            axes = active_preset.axes
            status = (
                f"Preset {active_preset.short_name}: expect {active_preset.expected_class} | "
                f"{active_preset.ground_truth}"
            )

        if key == ord("["):
            axes.y_max = max(axes.y_min + 0.5, axes.y_max - 0.5)
        if key == ord("]"):
            axes.y_max += 0.5
        if key == ord(","):
            axes.x_max = max(axes.x_min + 0.1, axes.x_max - 0.1)
        if key == ord("."):
            axes.x_max += 0.1

        if calibrator.active:
            n = len(calibrator.points)
            if n < 4:
                status = f"Manual: click corner {n + 1}/4 (TL, TR, BR, BL)"
            elif n == 4:
                quad = calibrator.quad()
                calibrator.reset()
                last_analysis = None
                smooth_shape = None
                status = "Manual corners set — analyzing shape..."

        warped = None
        if quad is not None:
            warped, inv_matrix = warp_plot(frame, quad)
            try:
                current = analyze_shape(warped, axes)
            except Exception as exc:
                current = None
                status = f"Detection error: {exc}"
            if current is not None:
                if last_analysis is None or smooth_shape is None:
                    last_analysis = current
                    smooth_shape = current.shape
                elif current.shape == smooth_shape:
                    last_analysis = current
                else:
                    # hold label unless new shape agrees for several frames
                    last_analysis = current
                    smooth_shape = current.shape
                status = f"Detected: {last_analysis.shape}"
            elif "error" not in status.lower():
                status = (
                    "Plot OK — no stroke found. Darker pen, even light, "
                    "corners on plot border."
                )
        elif not calibrator.active:
            status = "Press m (manual corners) or a (auto outline)"

        display = draw_overlay(
            frame, quad, last_analysis, inv_matrix, axes, status, paused, calibrator
        )
        cv2.imshow(win, display)
        if warped is not None:
            cv2.imshow(warp_win, draw_warp_preview(warped, last_analysis))

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
