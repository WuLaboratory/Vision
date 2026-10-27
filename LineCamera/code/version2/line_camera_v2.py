#!/usr/bin/env python3
"""
line_camera v2.4.0 — camera-based plot measurement with hierarchical frame detect.

Builds on line_camera.py (v1) shape-aware model selection, and upgrades:

  1) Stroke tracing (Kato-inspired column-graph DP) — see Kato et al., WACV 2022.
  2) Plot-frame auto-detect for tilted paper (Jagannathan & Jawahar, CBDAR 2005):
     graph-paper grid ≈ Manhattan layout of parallel/perpendicular lines → two
     vanishing points → outermost border lines → quadrilateral → homography warp.
  3) Graph-paper priors (v2.1.1): prefer dense H/V grid inside the quad, paper-like
     aspect, near-center placement, and a plausible ink stroke after warp — so live
     clutter (monitors, desks) is less likely to win than the sheet itself.
  4) Live-view recording (v2.2.0): press r to save the composite window as MP4.
  5) Hierarchical autodetect (v2.3.0): sheet → nested axes box (tick marks) →
     warp the tick box for stroke tracing; optional lock so a good box sticks.
  6) I–V / Ohm mode (v2.4.0): key o loads a fixed teaching sheet, x = current
     (0–1 A), y = voltage (0–10 V). When the fit is a line, slope is R in ohms.
     This mode does not enter the version-1 validation tables.

Usage:
  .venv/bin/python line_camera_v2.py
  .venv/bin/python line_camera_v2.py --quad-mode auto
  .venv/bin/python line_camera_v2.py --quad-mode sheet
  .venv/bin/python line_camera_v2.py --record-on-start --record-raw

Keys: same as v1 (q, m, a, 1–8, [ ] , . , space, s, l) plus:
  a = hierarchical auto-detect (sheet + axes/tick box)
  o = I–V / Ohm teaching mode (fixed axes; slope is resistance)
  r = toggle live-view video recording
  u = unlock / clear auto lock (re-run a to redetect)
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

import line_camera as v1
from line_camera import (
    PRESET_BY_KEY,
    PRESET_HELP,
    AxisConfig,
    ManualCalibrator,
    ModelScores,
    PlotPreset,
    ShapeAnalysis,
    WARP_H,
    WARP_W,
    _arc_length_data,
    _build_ink_mask,
    _choose_shape,
    _fit_line,
    _fit_quadratic,
    _fit_sinusoid,
    _sample_curve_px,
    data_to_pixel,
    draw_overlay,
    draw_warp_preview,
    find_largest_quad,
    log_camera_trial,
    order_quad,
    stroke_to_data,
    warp_plot,
)

VERSION = "2.4.0"


def ohm_teaching_axes() -> AxisConfig:
    """Fixed I–V sheet: x is current (A), y is voltage (V), so slope is R in ohms.

    A fresh config is returned each time so live nudges cannot rewrite the
    teaching ranges. This mode is not part of the version-1 validation set.
    """
    return AxisConfig(
        0.0,
        1.0,
        0.0,
        10.0,
        x_unit="I (A)",
        y_unit="V (V)",
        length_unit="axis units",
    )
CAPTURE_DIR = Path(__file__).resolve().parent / "captures"


# ---------------------------------------------------------------------------
# Jagannathan-inspired tilt-aware plot frame detection
# ---------------------------------------------------------------------------


@dataclass
class QuadDetectResult:
    """Auto-detected plot quadrilateral with method metadata."""

    quad: np.ndarray  # (4, 2) float32 — warp target (axes box when available)
    method: str
    vp_h: tuple[float, float] | None = None
    vp_v: tuple[float, float] | None = None
    n_lines_h: int = 0
    n_lines_v: int = 0
    score: float = 0.0
    # v2.3 hierarchical extras
    sheet_quad: np.ndarray | None = None  # outer sheet, if axes nested inside
    n_ticks_x: int = 0
    n_ticks_y: int = 0
    axes_score: float = 0.0


def _segment_length(x1: float, y1: float, x2: float, y2: float) -> float:
    return float(math.hypot(x2 - x1, y2 - y1))


def _segment_angle(x1: float, y1: float, x2: float, y2: float) -> float:
    """Angle in [-pi/2, pi/2) — direction of undirected line."""
    a = math.atan2(y2 - y1, x2 - x1)
    # Fold to undirected
    if a < 0:
        a += math.pi
    if a >= math.pi / 2:
        a -= math.pi
    return a


def _line_axbyc(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float, float]:
    """Normalized line ax + by + c = 0."""
    a = y1 - y2
    b = x2 - x1
    c = x1 * y2 - x2 * y1
    n = math.hypot(a, b)
    if n < 1e-9:
        return 0.0, 0.0, 0.0
    return a / n, b / n, c / n


def _intersect_lines(
    l1: tuple[float, float, float], l2: tuple[float, float, float]
) -> tuple[float, float] | None:
    a1, b1, c1 = l1
    a2, b2, c2 = l2
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-9:
        return None
    x = (b1 * c2 - b2 * c1) / det
    y = (c1 * a2 - c2 * a1) / det
    return float(x), float(y)


def _detect_line_segments(
    frame: np.ndarray,
) -> list[tuple[float, float, float, float, float, float]]:
    """
    Return segments as (x1,y1,x2,y2, length, angle).
    Tuned for graph paper (grid + border) under mild–strong tilt.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    # Adaptive + Canny: preserve long grid/border edges on tilted paper
    edges = cv2.Canny(blur, 50, 140)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    h, w = gray.shape
    min_len = max(40, int(0.08 * min(h, w)))
    raw = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=max(40, min_len // 2),
        minLineLength=min_len,
        maxLineGap=max(12, min_len // 5),
    )
    segs: list[tuple[float, float, float, float, float, float]] = []
    if raw is None:
        return segs
    # OpenCV may return (N,1,4) or (N,4)
    rows = raw.reshape(-1, 4)
    for x1, y1, x2, y2 in rows:
        x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
        length = _segment_length(x1, y1, x2, y2)
        ang = _segment_angle(x1, y1, x2, y2)
        segs.append((x1, y1, x2, y2, length, ang))
    return segs


def _cluster_two_directions(
    segs: list[tuple[float, float, float, float, float, float]],
) -> tuple[list, list] | None:
    """
    Split segments into two near-orthogonal families (graph-paper axes).

    Under tilt, true parallels are not identical in image angle, but for typical
    handheld poses the two axis families still form two angle modes. We refine
    with vanishing points later (Jagannathan §4).
    """
    if len(segs) < 6:
        return None
    angles = np.array([s[5] for s in segs], dtype=np.float64)
    # Circular-ish 1D: angles in [-pi/2, pi/2)
    # Seed from histogram peaks
    hist, edges = np.histogram(angles, bins=18, range=(-math.pi / 2, math.pi / 2))
    peaks = np.argsort(hist)[-4:]
    centers = [0.5 * (edges[i] + edges[i + 1]) for i in peaks if hist[i] > 0]
    if len(centers) < 2:
        return None
    # Pick two centers that are ~90° apart in undirected sense
    best_pair = None
    best_score = -1.0
    for i in range(len(centers)):
        for j in range(i + 1, len(centers)):
            d = abs(centers[i] - centers[j])
            d = min(d, math.pi - d)
            # Prefer near-perpendicular families
            orth = 1.0 - abs(d - math.pi / 2) / (math.pi / 2)
            bi = int(np.clip((centers[i] + math.pi / 2) / math.pi * 18, 0, 17))
            bj = int(np.clip((centers[j] + math.pi / 2) / math.pi * 18, 0, 17))
            mass = float(hist[bi] + hist[bj])
            score = orth * mass
            if score > best_score and orth > 0.35:
                best_score = score
                best_pair = (centers[i], centers[j])
    if best_pair is None:
        # Fallback: median split by absolute angle
        med = float(np.median(np.abs(angles)))
        fam_a = [s for s in segs if abs(s[5]) <= med]
        fam_b = [s for s in segs if abs(s[5]) > med]
    else:
        c0, c1 = best_pair

        def dist_ang(a: float, c: float) -> float:
            d = abs(a - c)
            return min(d, math.pi - d)

        fam_a, fam_b = [], []
        for s in segs:
            if dist_ang(s[5], c0) <= dist_ang(s[5], c1):
                fam_a.append(s)
            else:
                fam_b.append(s)
    if len(fam_a) < 2 or len(fam_b) < 2:
        return None
    # Label roughly "more horizontal" vs "more vertical" by mean |angle|
    ma = float(np.mean([abs(s[5]) for s in fam_a]))
    mb = float(np.mean([abs(s[5]) for s in fam_b]))
    if ma < mb:
        return fam_a, fam_b  # horiz-ish, vert-ish
    return fam_b, fam_a


def _vanishing_point_ransac(
    segs: list[tuple[float, float, float, float, float, float]],
    *,
    iters: int = 80,
    inlier_px: float = 12.0,
) -> tuple[float, float] | None:
    """
    Estimate vanishing point for a parallel family (Jagannathan §4).

    Sample pairs of segments, intersect, score how many lines pass near the
    candidate point. Length-weighted voting prefers long grid/border lines.
    """
    if len(segs) < 2:
        return None
    lines = [_line_axbyc(s[0], s[1], s[2], s[3]) for s in segs]
    lengths = np.array([s[4] for s in segs], dtype=np.float64)
    best_vp: tuple[float, float] | None = None
    best_score = -1.0
    rng = np.random.default_rng(0)
    n = len(segs)
    for _ in range(iters):
        i, j = rng.choice(n, size=2, replace=False)
        vp = _intersect_lines(lines[i], lines[j])
        if vp is None:
            continue
        vx, vy = vp
        # Prefer VPs not deep inside the image center (true VPs often outside)
        score = 0.0
        for k, (a, b, c) in enumerate(lines):
            dist = abs(a * vx + b * vy + c)  # already normalized
            if dist < inlier_px:
                score += lengths[k] * (1.0 - dist / inlier_px)
        if score > best_score:
            best_score = score
            best_vp = vp
    return best_vp


def _line_signed_offset(
    seg: tuple[float, float, float, float, float, float],
    origin: tuple[float, float],
) -> float:
    """Scalar offset of line from origin along its normal (for ordering parallels)."""
    a, b, c = _line_axbyc(seg[0], seg[1], seg[2], seg[3])
    return a * origin[0] + b * origin[1] + c


def _outermost_pair(
    segs: list[tuple[float, float, float, float, float, float]],
    frame_shape: tuple[int, int],
) -> tuple[
    tuple[float, float, float],
    tuple[float, float, float],
] | None:
    """Pick two extreme lines of a family that can bound the plot."""
    if len(segs) < 2:
        return None
    h, w = frame_shape
    origin = (w * 0.5, h * 0.5)
    scored = []
    for s in segs:
        off = _line_signed_offset(s, origin)
        scored.append((off, s[4], s))
    scored.sort(key=lambda t: t[0])
    min_len = 0.04 * min(h, w)
    # Prefer long segments near both extremes of the offset distribution
    n_tail = max(2, len(scored) // 5)
    left_cands = [t for t in scored[:n_tail] if t[1] >= min_len] or scored[:n_tail]
    right_cands = [t for t in scored[-n_tail:] if t[1] >= min_len] or scored[-n_tail:]
    s_lo = max(left_cands, key=lambda t: t[1])[2]
    s_hi = max(right_cands, key=lambda t: t[1])[2]
    span = abs(_line_signed_offset(s_lo, origin) - _line_signed_offset(s_hi, origin))
    if span < 0.08 * min(h, w):
        # Fallback: absolute min/max offset regardless of length
        s_lo, s_hi = scored[0][2], scored[-1][2]
        span = abs(_line_signed_offset(s_lo, origin) - _line_signed_offset(s_hi, origin))
        if span < 0.05 * min(h, w):
            return None
    return (
        _line_axbyc(s_lo[0], s_lo[1], s_lo[2], s_lo[3]),
        _line_axbyc(s_hi[0], s_hi[1], s_hi[2], s_hi[3]),
    )


def _quad_from_family_hull(
    fam_h: list,
    fam_v: list,
    frame_shape: tuple[int, int],
) -> np.ndarray | None:
    """
    Fallback when border lines are weak: convex hull of long grid segments,
    then approximate as a quadrilateral (still benefits from H/V filtering).
    """
    h, w = frame_shape
    pts: list[list[float]] = []
    min_len = 0.05 * min(h, w)
    for fam in (fam_h, fam_v):
        for s in fam:
            if s[4] < min_len:
                continue
            pts.append([s[0], s[1]])
            pts.append([s[2], s[3]])
    if len(pts) < 8:
        return None
    arr = np.asarray(pts, dtype=np.float32)
    hull = cv2.convexHull(arr)
    peri = cv2.arcLength(hull, True)
    approx = cv2.approxPolyDP(hull, 0.02 * peri, True)
    if len(approx) != 4:
        # Force 4 corners via min-area rect
        rect = cv2.minAreaRect(hull)
        box = cv2.boxPoints(rect)
        return order_quad(box.astype(np.float32))
    return order_quad(approx.reshape(4, 2).astype(np.float32))


def _quad_from_line_pairs(
    horiz_pair: tuple[tuple[float, float, float], tuple[float, float, float]],
    vert_pair: tuple[tuple[float, float, float], tuple[float, float, float]],
    frame_shape: tuple[int, int],
) -> np.ndarray | None:
    """Intersect two H and two V lines → 4 corners."""
    h, w = frame_shape
    corners: list[tuple[float, float]] = []
    for lh in horiz_pair:
        for lv in vert_pair:
            p = _intersect_lines(lh, lv)
            if p is None:
                return None
            corners.append(p)
    pts = np.array(corners, dtype=np.float32)
    margin = 0.35 * max(h, w)
    if np.any(pts[:, 0] < -margin) or np.any(pts[:, 0] > w + margin):
        return None
    if np.any(pts[:, 1] < -margin) or np.any(pts[:, 1] > h + margin):
        return None
    ordered = order_quad(pts)
    area = float(cv2.contourArea(ordered.reshape(-1, 1, 2)))
    if area < 0.04 * h * w or area > 0.99 * h * w:
        return None
    return ordered


def _quad_side_lengths(q: np.ndarray) -> tuple[float, float, float, float]:
    def side(i: int, j: int) -> float:
        return float(np.linalg.norm(q[i] - q[j]))

    return side(0, 1), side(1, 2), side(2, 3), side(3, 0)


def _parallelogram_score(q: np.ndarray) -> float:
    s01, s12, s23, s30 = _quad_side_lengths(q)
    if min(s01, s12, s23, s30) < 1e-6:
        return 0.0
    return min(s01, s23) / max(s01, s23) * min(s12, s30) / max(s12, s30)


def _fill_preference(fill: float) -> float:
    """
    Prefer a sheet that occupies a mid-sized fraction of the frame.

    Huge almost-full-frame quads (monitors, walls) and tiny scraps are down-weighted.
    """
    if fill < 0.06:
        return 0.15 * (fill / 0.06)
    if fill <= 0.55:
        return 0.35 + 0.65 * ((fill - 0.06) / 0.49)
    if fill <= 0.85:
        return max(0.15, 1.0 - (fill - 0.55) / 0.45)
    return 0.08


def _aspect_preference(q: np.ndarray) -> float:
    """Soft prior for paper-like aspect (not extremely skinny strips)."""
    s01, s12, s23, s30 = _quad_side_lengths(q)
    w_like = 0.5 * (s01 + s23)
    h_like = 0.5 * (s12 + s30)
    if min(w_like, h_like) < 1e-6:
        return 0.0
    ar = max(w_like, h_like) / min(w_like, h_like)
    # Peak near ~1.0–1.6 (typical landscape plot sheet under mild tilt)
    if ar <= 1.6:
        return 1.0
    if ar <= 2.4:
        return max(0.2, 1.0 - (ar - 1.6) / 0.8)
    return 0.1


def _center_preference(q: np.ndarray, frame_shape: tuple[int, int]) -> float:
    """Prefer quads whose centroid is near the frame center (handheld framing)."""
    h, w = frame_shape
    c = q.mean(axis=0)
    dx = (float(c[0]) - 0.5 * w) / max(w, 1)
    dy = (float(c[1]) - 0.5 * h) / max(h, 1)
    dist = math.hypot(dx, dy)
    # dist≈0 → 1; dist≈0.5 (corner-ish) → ~0
    return float(max(0.0, 1.0 - dist / 0.55))


def _midpoint_in_quad(seg: tuple, q: np.ndarray) -> bool:
    mx = 0.5 * (float(seg[0]) + float(seg[2]))
    my = 0.5 * (float(seg[1]) + float(seg[3]))
    return cv2.pointPolygonTest(q.astype(np.float32), (mx, my), False) >= 0


def _grid_density_score(
    q: np.ndarray,
    *,
    fam_h: list | None,
    fam_v: list | None,
    segs: list | None,
) -> tuple[float, int, int]:
    """
    Dense orthogonal grid evidence inside the candidate quad.

    Graph paper should show many near-parallel lines in *both* families inside
    the region; a monitor bezel or desk edge typically has only a few.
    """
    q = order_quad(q)
    if fam_h is not None and fam_v is not None:
        nh = sum(1 for s in fam_h if _midpoint_in_quad(s, q))
        nv = sum(1 for s in fam_v if _midpoint_in_quad(s, q))
    elif segs:
        # Angle-split segs that fall inside the quad
        inside = [s for s in segs if _midpoint_in_quad(s, q)]
        if len(inside) < 4:
            return 0.0, 0, 0
        clustered = _cluster_two_directions(inside)
        if clustered is None:
            return 0.05 * min(1.0, len(inside) / 12.0), len(inside), 0
        fam_a, fam_b = clustered
        nh, nv = len(fam_a), len(fam_b)
    else:
        return 0.0, 0, 0

    # Saturate around ~8 lines/family (typical visible grid under webcam)
    sh = min(1.0, nh / 8.0)
    sv = min(1.0, nv / 8.0)
    # Geometric mean: both directions must contribute
    dens = math.sqrt(max(sh * sv, 0.0))
    if nh < 3 or nv < 3:
        dens *= 0.35
    return dens, nh, nv


def _ink_plausibility_after_warp(frame: np.ndarray, quad: np.ndarray) -> float:
    """
    Quick warp + ink check: reject empty walls / bright screens / wrong objects.

    Returns 0..1. Mid-range ink with at least one sizable connected component
    scores highest (plotted stroke on paper).
    """
    try:
        warped, _ = warp_plot(frame, order_quad(quad))
    except Exception:
        return 0.0
    ink = _build_ink_mask(warped)
    frac = float(np.mean(ink > 0))
    if frac < 0.0015 or frac > 0.40:
        return 0.0
    contours, _ = cv2.findContours(ink, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0
    best_area = max(float(cv2.contourArea(c)) for c in contours)
    area_frac = best_area / float(WARP_W * WARP_H)
    if area_frac < 0.0004:
        return 0.0
    # Prefer a stroke-sized blob, not page-filling dark region
    raw_size = area_frac / 0.015
    if raw_size <= 1.0:
        size_term = raw_size
    else:
        size_term = max(0.2, 2.0 - raw_size)
    cover_term = 1.0 if 0.004 <= frac <= 0.22 else 0.45
    return float(np.clip(0.55 * size_term + 0.45 * cover_term, 0.0, 1.0))


def _score_graph_paper_quad(
    quad: np.ndarray,
    frame: np.ndarray,
    *,
    fam_h: list | None = None,
    fam_v: list | None = None,
    segs: list | None = None,
    check_ink: bool = True,
) -> tuple[float, dict[str, float]]:
    """
    Rank candidates as graph paper, not merely large quadrilaterals.

    Emphasizes grid density, center framing, paper-like aspect, and ink after
    warp; down-weights "largest object in the room" behavior.
    """
    h, w = frame.shape[:2]
    q = order_quad(quad)
    area = float(cv2.contourArea(q.reshape(-1, 1, 2)))
    if area <= 0:
        return -1.0, {}

    fill = area / float(h * w)
    opp = _parallelogram_score(q)
    fill_t = _fill_preference(fill)
    aspect_t = _aspect_preference(q)
    center_t = _center_preference(q, (h, w))
    grid_t, nh, nv = _grid_density_score(q, fam_h=fam_h, fam_v=fam_v, segs=segs)
    ink_t = _ink_plausibility_after_warp(frame, q) if check_ink else 0.5

    score = (
        0.12 * fill_t
        + 0.12 * opp
        + 0.12 * aspect_t
        + 0.22 * center_t
        + 0.28 * grid_t
        + 0.14 * ink_t
    )
    # Soft reject: neither grid nor ink → almost certainly clutter
    if grid_t < 0.18 and ink_t < 0.25:
        score *= 0.2
    if fill > 0.90:
        score *= 0.45

    details = {
        "fill": fill_t,
        "opp": opp,
        "aspect": aspect_t,
        "center": center_t,
        "grid": grid_t,
        "ink": ink_t,
        "n_grid_h": float(nh),
        "n_grid_v": float(nv),
    }
    return float(score), details


def _quad_score(quad: np.ndarray, frame_shape: tuple[int, int]) -> float:
    """Backward-compatible geometric score (no frame / ink). Prefer _score_graph_paper_quad."""
    h, w = frame_shape
    q = order_quad(quad)
    area = float(cv2.contourArea(q.reshape(-1, 1, 2)))
    if area <= 0:
        return -1.0
    opp = _parallelogram_score(q)
    fill = area / float(h * w)
    return fill * 0.6 + opp * 0.4


def find_contour_quad_candidates(
    frame: np.ndarray,
    *,
    max_candidates: int = 6,
) -> list[np.ndarray]:
    """Top-N area 4-gons (not only the largest — monitors often win that race)."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = frame.shape[:2]
    min_area = 0.06 * h * w
    scored: list[tuple[float, np.ndarray]] = []
    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        if area < min_area:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) != 4:
            continue
        pts = order_quad(approx.reshape(4, 2).astype(np.float32))
        scored.append((area, pts))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [pts for _, pts in scored[:max_candidates]]


def find_plot_quad_vanishing(frame: np.ndarray) -> QuadDetectResult | None:
    """
    Detect plot rectangle using parallel/perpendicular grid structure.

    Follows Jagannathan & Jawahar (CBDAR 2005) layout/vanishing-point idea:
    graph paper provides two families of (world-)parallel lines → estimate
    families + vanishing points → outermost borders → quadrilateral.
    """
    h, w = frame.shape[:2]
    segs = _detect_line_segments(frame)
    if len(segs) < 6:
        return None
    clustered = _cluster_two_directions(segs)
    if clustered is None:
        return None
    fam_h, fam_v = clustered
    vp_h = _vanishing_point_ransac(fam_h)
    vp_v = _vanishing_point_ransac(fam_v)

    quad = None
    pair_h = _outermost_pair(fam_h, (h, w))
    pair_v = _outermost_pair(fam_v, (h, w))
    if pair_h is not None and pair_v is not None:
        quad = _quad_from_line_pairs(pair_h, pair_v, (h, w))
    if quad is None:
        quad = _quad_from_family_hull(fam_h, fam_v, (h, w))
    if quad is None:
        return None

    score, details = _score_graph_paper_quad(
        quad, frame, fam_h=fam_h, fam_v=fam_v, segs=segs, check_ink=True
    )
    if score < 0.08:
        return None
    # Prefer in-quad family counts for status when available
    n_h = int(details.get("n_grid_h", len(fam_h)))
    n_v = int(details.get("n_grid_v", len(fam_v)))
    return QuadDetectResult(
        quad=quad,
        method="vanishing_grid",
        vp_h=vp_h,
        vp_v=vp_v,
        n_lines_h=n_h,
        n_lines_v=n_v,
        score=score,
    )


def find_plot_quad(
    frame: np.ndarray,
    *,
    mode: str = "auto",
) -> QuadDetectResult | None:
    """
    Auto-detect plot corners.

    mode:
      vanishing — Jagannathan-style parallel-line / VP method only
      contour   — score top-N contour 4-gons with graph-paper priors
      auto      — rank vanishing + contour candidates; keep best score
    """
    cand: list[QuadDetectResult] = []
    segs = _detect_line_segments(frame)
    clustered = _cluster_two_directions(segs) if len(segs) >= 6 else None
    fam_h = clustered[0] if clustered else None
    fam_v = clustered[1] if clustered else None

    if mode in ("vanishing", "auto"):
        r = find_plot_quad_vanishing(frame)
        if r is not None:
            cand.append(r)

    if mode in ("contour", "auto"):
        for q in find_contour_quad_candidates(frame):
            score, details = _score_graph_paper_quad(
                q, frame, fam_h=fam_h, fam_v=fam_v, segs=segs, check_ink=True
            )
            if score < 0.08:
                continue
            cand.append(
                QuadDetectResult(
                    quad=q,
                    method="contour_v1",
                    n_lines_h=int(details.get("n_grid_h", 0)),
                    n_lines_v=int(details.get("n_grid_v", 0)),
                    score=score,
                )
            )
        # Keep v1 single-largest as a last-resort candidate (low weight if clutter)
        if not any(c.method == "contour_v1" for c in cand):
            q = find_largest_quad(frame)
            if q is not None:
                q = order_quad(q)
                score, details = _score_graph_paper_quad(
                    q, frame, fam_h=fam_h, fam_v=fam_v, segs=segs, check_ink=True
                )
                if score >= 0.05:
                    cand.append(
                        QuadDetectResult(
                            quad=q,
                            method="contour_v1",
                            n_lines_h=int(details.get("n_grid_h", 0)),
                            n_lines_v=int(details.get("n_grid_v", 0)),
                            score=score,
                        )
                    )

    if not cand:
        return None
    # Prefer ink+grid: among near-ties, vanishing_grid wins if within 8%
    cand.sort(key=lambda r: r.score, reverse=True)
    best = cand[0]
    if best.method != "vanishing_grid":
        for alt in cand[1:]:
            if alt.method == "vanishing_grid" and alt.score >= 0.92 * best.score:
                best = alt
                break
    best.sheet_quad = order_quad(best.quad)
    return best


# ---------------------------------------------------------------------------
# v2.3 — nested axes box (tick-marked plot frame) inside sheet
# ---------------------------------------------------------------------------


def _quad_iou(a: np.ndarray, b: np.ndarray) -> float:
    """IoU of two quads via filled polygon masks (axis-aligned bbox fallback)."""
    qa = order_quad(a).astype(np.int32)
    qb = order_quad(b).astype(np.int32)
    xs = np.concatenate([qa[:, 0], qb[:, 0]])
    ys = np.concatenate([qa[:, 1], qb[:, 1]])
    x0, x1 = int(xs.min()) - 2, int(xs.max()) + 2
    y0, y1 = int(ys.min()) - 2, int(ys.max()) + 2
    if x1 <= x0 or y1 <= y0:
        return 0.0
    w, h = x1 - x0, y1 - y0
    ma = np.zeros((h, w), np.uint8)
    mb = np.zeros((h, w), np.uint8)
    cv2.fillPoly(ma, [qa - np.array([x0, y0])], 1)
    cv2.fillPoly(mb, [qb - np.array([x0, y0])], 1)
    inter = int(np.logical_and(ma, mb).sum())
    union = int(np.logical_or(ma, mb).sum())
    return float(inter) / float(union) if union else 0.0


def _map_quad_through(quad: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    pts = order_quad(quad).reshape(-1, 1, 2).astype(np.float32)
    mapped = cv2.perspectiveTransform(pts, matrix).reshape(4, 2)
    return order_quad(mapped)


def _axis_aligned_bounds(q: np.ndarray) -> tuple[int, int, int, int]:
    q = order_quad(q)
    x0 = int(max(0, math.floor(min(q[0, 0], q[3, 0]))))
    x1 = int(math.ceil(max(q[1, 0], q[2, 0])))
    y0 = int(max(0, math.floor(min(q[0, 1], q[1, 1]))))
    y1 = int(math.ceil(max(q[2, 1], q[3, 1])))
    return x0, y0, x1, y1


def _peak_count_1d(profile: np.ndarray, *, min_sep: int, min_val: float) -> tuple[int, float]:
    """Count local maxima and score spacing regularity (0..1)."""
    if profile.size < 8:
        return 0, 0.0
    p = profile.astype(np.float64)
    p = p - np.median(p)
    thr = max(min_val, 0.35 * float(p.max()) if p.max() > 0 else min_val)
    peaks: list[int] = []
    for i in range(2, len(p) - 2):
        if p[i] < thr:
            continue
        if p[i] >= p[i - 1] and p[i] >= p[i + 1] and p[i] >= p[i - 2] and p[i] >= p[i + 2]:
            if peaks and i - peaks[-1] < min_sep:
                if p[i] > p[peaks[-1]]:
                    peaks[-1] = i
                continue
            peaks.append(i)
    n = len(peaks)
    if n < 3:
        return n, 0.15 * n
    gaps = np.diff(peaks).astype(np.float64)
    med = float(np.median(gaps))
    if med < 1e-6:
        return n, 0.2
    cv = float(np.std(gaps) / med)
    regularity = float(max(0.0, 1.0 - cv))
    return n, regularity


def _tick_evidence(
    edges: np.ndarray,
    box: np.ndarray,
) -> tuple[float, int, int]:
    """
    Score tick marks along bottom (vertical ticks) and left (horizontal ticks).

    Operates in a sheet-rectified warp where the axes box is nearly axis-aligned.
    """
    h, w = edges.shape[:2]
    x0, y0, x1, y1 = _axis_aligned_bounds(box)
    x0 = max(0, min(x0, w - 2))
    x1 = max(x0 + 8, min(x1, w))
    y0 = max(0, min(y0, h - 2))
    y1 = max(y0 + 8, min(y1, h))
    bw, bh = x1 - x0, y1 - y0
    if bw < 40 or bh < 40:
        return 0.0, 0, 0

    band = max(6, int(0.04 * min(bw, bh)))
    # Bottom interior strip: vertical tick stubs (slightly inside the border)
    yb0 = max(y0, y1 - band - 4)
    yb1 = max(yb0 + 2, y1 - 2)
    bottom = edges[yb0:yb1, x0:x1]
    if bottom.size == 0:
        return 0.0, 0, 0
    vproj = bottom.astype(np.float32).max(axis=0)
    margin = max(3, bw // 25)
    if vproj.size > 2 * margin:
        vproj[:margin] = 0
        vproj[-margin:] = 0
    nx, reg_x = _peak_count_1d(vproj, min_sep=max(4, bw // 30), min_val=30.0)

    # Left interior strip: horizontal tick stubs
    xl0 = min(x1 - 2, x0 + 2)
    xl1 = min(x1, x0 + band + 6)
    left = edges[y0:y1, xl0:xl1]
    if left.size == 0:
        return 0.0, nx, 0
    hproj = left.astype(np.float32).max(axis=1)
    if hproj.size > 2 * margin:
        hproj[:margin] = 0
        hproj[-margin:] = 0
    ny, reg_y = _peak_count_1d(hproj, min_sep=max(4, bh // 30), min_val=30.0)

    # Strong tick evidence: several peaks on both axes + regular spacing
    dens_x = min(1.0, nx / 5.0)
    dens_y = min(1.0, ny / 5.0)
    score = 0.35 * dens_x + 0.35 * dens_y + 0.15 * reg_x + 0.15 * reg_y
    if nx < 3 or ny < 3:
        score *= 0.45
    return float(score), int(nx), int(ny)


def _border_strength(edges: np.ndarray, box: np.ndarray) -> float:
    """How strongly the four sides of the box sit on edges."""
    h, w = edges.shape[:2]
    q = order_quad(box).astype(np.int32)
    mask = np.zeros((h, w), np.uint8)
    cv2.polylines(mask, [q], True, 1, 2, lineType=cv2.LINE_AA)
    on = edges > 0
    hit = int(np.logical_and(mask > 0, on).sum())
    tot = int(mask.sum())
    return float(hit) / float(tot) if tot else 0.0


def _score_axes_box(
    warped: np.ndarray,
    edges: np.ndarray,
    box: np.ndarray,
    *,
    allow_near_full: bool = False,
) -> tuple[float, int, int]:
    """Rank a nested rectangle as a MATLAB-style axes frame with ticks."""
    h, w = warped.shape[:2]
    q = order_quad(box)
    area = float(cv2.contourArea(q.reshape(-1, 1, 2)))
    fill = area / float(h * w)
    max_fill = 0.98 if allow_near_full else 0.90
    if fill < 0.18 or fill > max_fill:
        return -1.0, 0, 0

    if allow_near_full and fill > 0.88:
        nest = 0.95  # warp already is the axes frame
    elif fill < 0.28:
        nest = 0.45
    elif fill > 0.85:
        nest = 0.55
    elif 0.35 <= fill <= 0.80:
        nest = 1.0
    else:
        nest = 0.8

    opp = _parallelogram_score(q)
    aspect = _aspect_preference(q)
    x0, y0, x1, y1 = _axis_aligned_bounds(q)
    x0 = max(0, min(x0, w - 2))
    x1 = max(x0 + 8, min(x1, w))
    y0 = max(0, min(y0, h - 2))
    y1 = max(y0 + 8, min(y1, h))
    inset = min(x0, y0, w - x1, h - y1) / float(min(h, w))
    inset_t = float(np.clip(inset / 0.06, 0.0, 1.0))
    if allow_near_full:
        inset_t = max(inset_t, 0.7)

    tick_t, nx, ny = _tick_evidence(edges, q)
    border_t = _border_strength(edges, q)

    roi = warped[y0:y1, x0:x1]
    ink = _build_ink_mask(roi) if roi.size else np.zeros((1, 1), np.uint8)
    ink_frac = float(np.mean(ink > 0)) if ink.size else 0.0
    ink_t = 1.0 if 0.002 <= ink_frac <= 0.35 else 0.35

    score = (
        0.18 * nest
        + 0.12 * opp
        + 0.10 * aspect
        + 0.12 * inset_t
        + 0.30 * tick_t
        + 0.10 * border_t
        + 0.08 * ink_t
    )
    if tick_t < 0.2 and border_t < 0.25:
        score *= 0.35
    return float(score), nx, ny


def _axes_box_from_hv_lines(
    edges: np.ndarray,
) -> list[np.ndarray]:
    """Candidate axis-aligned rectangles from strong H/V Hough lines."""
    h, w = edges.shape[:2]
    min_len = max(30, int(0.2 * min(h, w)))
    raw = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=max(30, min_len // 3),
        minLineLength=min_len,
        maxLineGap=max(8, min_len // 8),
    )
    if raw is None:
        return []
    horiz: list[float] = []
    vert: list[float] = []
    for x1, y1, x2, y2 in raw.reshape(-1, 4):
        dx, dy = abs(float(x2 - x1)), abs(float(y2 - y1))
        if dx >= dy * 3:  # horizontal
            horiz.append(0.5 * (y1 + y2))
        elif dy >= dx * 3:  # vertical
            vert.append(0.5 * (x1 + x2))

    def cluster(vals: list[float], tol: float) -> list[float]:
        if not vals:
            return []
        vals = sorted(vals)
        groups: list[list[float]] = [[vals[0]]]
        for v in vals[1:]:
            if abs(v - groups[-1][-1]) <= tol:
                groups[-1].append(v)
            else:
                groups.append([v])
        return [float(np.mean(g)) for g in groups]

    ys = cluster(horiz, tol=max(6.0, 0.015 * h))
    xs = cluster(vert, tol=max(6.0, 0.015 * w))
    cands: list[np.ndarray] = []
    for i in range(len(ys)):
        for j in range(i + 1, len(ys)):
            y_a, y_b = ys[i], ys[j]
            if abs(y_b - y_a) < 0.2 * h:
                continue
            for k in range(len(xs)):
                for m in range(k + 1, len(xs)):
                    x_a, x_b = xs[k], xs[m]
                    if abs(x_b - x_a) < 0.2 * w:
                        continue
                    x0, x1 = (x_a, x_b) if x_a < x_b else (x_b, x_a)
                    y0, y1 = (y_a, y_b) if y_a < y_b else (y_b, y_a)
                    q = order_quad(
                        np.array(
                            [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                            dtype=np.float32,
                        )
                    )
                    cands.append(q)
    # Limit combinatorial explosion
    return cands[:40]


def find_axes_box_warped(warped: np.ndarray) -> tuple[np.ndarray, float, int, int] | None:
    """
    Locate the tick-marked axes rectangle inside a sheet-rectified warp.

    Returns (quad_in_warp, score, n_ticks_x, n_ticks_y) or None.
    """
    h, w = warped.shape[:2]
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)

    cand_quads: list[np.ndarray] = []
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        if area < 0.22 * h * w or area > 0.90 * h * w:
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) != 4:
            continue
        cand_quads.append(order_quad(approx.reshape(4, 2).astype(np.float32)))
    cand_quads.extend(_axes_box_from_hv_lines(edges))

    best: tuple[np.ndarray, float, int, int] | None = None
    seen: list[np.ndarray] = []
    for q in cand_quads:
        if any(_quad_iou(q, s) > 0.92 for s in seen):
            continue
        seen.append(q)
        score, nx, ny = _score_axes_box(warped, edges, q)
        if score < 0.28:
            continue
        # Require some tick evidence on at least one axis for nested boxes
        if nx + ny < 4:
            continue
        if best is None or score > best[1]:
            best = (q, score, nx, ny)

    # If the warp itself is already the axes frame (common when sheet
    # detector locked onto the tick box), score an inset of the full warp.
    m = max(4, int(0.02 * min(h, w)))
    full = order_quad(
        np.array(
            [[m, m], [w - 1 - m, m], [w - 1 - m, h - 1 - m], [m, h - 1 - m]],
            dtype=np.float32,
        )
    )
    full_score, fnx, fny = _score_axes_box(warped, edges, full, allow_near_full=True)
    # Slight boost: full-warp candidate means stage-1 already framed the plot
    full_score = full_score * 1.05 if full_score > 0 else full_score
    if full_score >= 0.30 and fnx + fny >= 4:
        if best is None or full_score >= best[1] * 0.92:
            # Prefer full warp when nested candidate is only marginally better
            # and much smaller (spurious strip)
            if best is not None:
                nested_fill = float(cv2.contourArea(best[0].reshape(-1, 1, 2))) / (h * w)
                if nested_fill < 0.40 and full_score >= 0.32:
                    best = (full, full_score, fnx, fny)
                elif full_score > best[1]:
                    best = (full, full_score, fnx, fny)
            else:
                best = (full, full_score, fnx, fny)

    return best


def run_autodetect(frame: np.ndarray, mode: str) -> QuadDetectResult | None:
    """
    Dispatch plot-frame detection.

    mode:
      auto / axes — sheet then nested tick/axes box (v2.3)
      sheet       — outer sheet only (v2.1 priors, no axes refine)
      vanishing / contour — legacy single-stage sheet detectors
    """
    if mode in ("auto", "axes"):
        return find_plot_hierarchical(frame, sheet_mode="auto")
    if mode == "sheet":
        return find_plot_quad(frame, mode="auto")
    return find_plot_quad(frame, mode=mode)


def find_plot_hierarchical(
    frame: np.ndarray,
    *,
    sheet_mode: str = "auto",
) -> QuadDetectResult | None:
    """
    Sheet → nested axes/tick box → return axes quad as the warp target.

    Falls back to sheet-only when tick-box confidence is low.
    """
    sheet = find_plot_quad(frame, mode=sheet_mode if sheet_mode != "axes" else "auto")
    if sheet is None:
        return None
    sheet_q = order_quad(sheet.quad)
    try:
        warped, inv = warp_plot(frame, sheet_q)
    except Exception:
        sheet.sheet_quad = sheet_q
        return sheet

    axes = find_axes_box_warped(warped)
    if axes is None:
        sheet.method = f"{sheet.method}+sheet_only"
        sheet.sheet_quad = sheet_q
        return sheet

    axes_w, axes_score, nx, ny = axes
    axes_frame = _map_quad_through(axes_w, inv)
    # Safety: axes must lie mostly inside the sheet
    if _quad_iou(axes_frame, sheet_q) < 0.15:
        sheet.method = f"{sheet.method}+sheet_only"
        sheet.sheet_quad = sheet_q
        return sheet

    return QuadDetectResult(
        quad=axes_frame,
        method="axes_box",
        vp_h=sheet.vp_h,
        vp_v=sheet.vp_v,
        n_lines_h=sheet.n_lines_h,
        n_lines_v=sheet.n_lines_v,
        score=0.55 * sheet.score + 0.45 * axes_score,
        sheet_quad=sheet_q,
        n_ticks_x=nx,
        n_ticks_y=ny,
        axes_score=axes_score,
    )


@dataclass
class QuadLock:
    """Keep a good hierarchical detection stable across frames / re-presses."""

    result: QuadDetectResult | None = None
    hits: int = 0

    def clear(self) -> None:
        self.result = None
        self.hits = 0

    def accept(self, new: QuadDetectResult | None) -> QuadDetectResult | None:
        if new is None:
            return self.result
        if self.result is None:
            self.result = new
            self.hits = 1
            return new
        iou = _quad_iou(self.result.quad, new.quad)
        if iou >= 0.82:
            # Same box — keep locked corners (stable for tracing)
            self.hits += 1
            # Refresh tick metadata if new axes detect is richer
            if new.method == "axes_box" and self.result.method != "axes_box":
                self.result = new
            elif new.n_ticks_x + new.n_ticks_y > self.result.n_ticks_x + self.result.n_ticks_y:
                self.result.n_ticks_x = new.n_ticks_x
                self.result.n_ticks_y = new.n_ticks_y
                self.result.axes_score = max(self.result.axes_score, new.axes_score)
            return self.result
        # Different box: only switch if clearly better
        if new.score >= self.result.score + 0.06 or (
            new.method == "axes_box" and self.result.method != "axes_box"
        ):
            self.result = new
            self.hits = 1
        return self.result


def draw_quad_debug(
    frame: np.ndarray,
    result: QuadDetectResult | None,
) -> np.ndarray:
    """Overlay sheet (cyan) + axes/warp target (yellow) and vanishing points."""
    out = frame.copy()
    if result is None:
        return out
    if result.sheet_quad is not None:
        sq = order_quad(result.sheet_quad).astype(np.int32)
        cv2.polylines(out, [sq], True, (220, 200, 40), 1, lineType=cv2.LINE_AA)
        cv2.putText(
            out,
            "sheet",
            (int(sq[0][0]) + 4, int(sq[0][1]) - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (220, 200, 40),
            1,
            cv2.LINE_AA,
        )
    q = order_quad(result.quad).astype(np.int32)
    color = (0, 220, 255) if result.method == "axes_box" else (0, 180, 255)
    cv2.polylines(out, [q], True, color, 2, lineType=cv2.LINE_AA)
    label = "axes" if result.method == "axes_box" else "warp"
    for i, corner in enumerate(("TL", "TR", "BR", "BL")):
        cv2.circle(out, tuple(q[i]), 6, (0, 255, 0), -1, lineType=cv2.LINE_AA)
        cv2.putText(
            out,
            corner if i else f"{corner}/{label}",
            (int(q[i][0]) + 6, int(q[i][1]) - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )
    if result.n_ticks_x or result.n_ticks_y:
        cv2.putText(
            out,
            f"ticks x={result.n_ticks_x} y={result.n_ticks_y}",
            (int(q[3][0]) + 4, int(q[3][1]) + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 180),
            1,
            cv2.LINE_AA,
        )
    h, w = frame.shape[:2]
    for vp, col in ((result.vp_h, (255, 128, 0)), (result.vp_v, (255, 0, 128))):
        if vp is None:
            continue
        x, y = int(vp[0]), int(vp[1])
        if -w <= x < 2 * w and -h <= y < 2 * h:
            cv2.drawMarker(out, (x, y), col, cv2.MARKER_TILTED_CROSS, 16, 2)
    return out


# ---------------------------------------------------------------------------
# Kato-inspired classical stroke tracing (column graph + DP)
# ---------------------------------------------------------------------------


@dataclass
class TraceConfig:
    """Parameters for column-graph tracing (classical Kato analogue)."""

    x_skip: int = 3  # subsample columns (Kato d≈3)
    max_candidates_per_col: int = 6
    smoothness_weight: float = 1.0
    ink_weight: float = 2.0
    min_ink_frac: float = 0.02  # column must have some ink mass
    max_jump_px: float = 40.0  # reject huge vertical jumps between columns
    n_strokes: int = 1  # simultaneous strokes to attempt (1 = primary path)


@dataclass
class StrokeTrace:
    """One traced polyline in warped pixel coordinates."""

    points_px: np.ndarray  # (N, 2) float32, ordered by x
    cost: float
    method: str
    n_columns: int = 0


def _ink_probability(warped: np.ndarray) -> np.ndarray:
    """Soft ink map in [0, 1] from classical ink mask (stand-in for Kato S)."""
    ink = _build_ink_mask(warped)
    kernel = np.ones((5, 5), np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel, iterations=2)
    blur = cv2.GaussianBlur(ink, (5, 5), 0)
    return (blur.astype(np.float32) / 255.0).clip(0.0, 1.0)


def _column_candidates(
    S: np.ndarray,
    x: int,
    max_n: int,
) -> list[tuple[int, float]]:
    """Local y peaks / cluster centers in one column of the ink map."""
    col = S[:, x]
    if float(col.max()) < 1e-3:
        return []
    # Connected runs above a relative threshold
    thr = max(0.15, 0.35 * float(col.max()))
    active = col >= thr
    cands: list[tuple[int, float]] = []
    y = 0
    h = S.shape[0]
    while y < h:
        if not active[y]:
            y += 1
            continue
        y0 = y
        while y < h and active[y]:
            y += 1
        y1 = y
        seg = col[y0:y1]
        y_c = int(y0 + np.argmax(seg))
        score = float(col[y_c])
        cands.append((y_c, score))
    cands.sort(key=lambda t: t[1], reverse=True)
    return cands[:max_n]


def _estimate_n_lines(S: np.ndarray, xs: np.ndarray) -> int:
    """Robust line-count estimate: top-15% of per-column cluster counts (Kato)."""
    counts: list[int] = []
    for x in xs:
        n = len(_column_candidates(S, int(x), max_n=8))
        if n > 0:
            counts.append(n)
    if not counts:
        return 1
    arr = np.asarray(counts, dtype=np.float64)
    return int(max(1, round(float(np.percentile(arr, 85)))))


def trace_strokes_column_graph(
    warped: np.ndarray,
    cfg: TraceConfig | None = None,
) -> list[StrokeTrace]:
    """
    Trace stroke(s) as min-cost path(s) on a column-sampled graph.

    Classical, real-time analogue of Kato et al. (WACV 2022) §3.3 without a
    trained segmentation network or full LP solver. Cost ≈ ink fidelity +
    vertical smoothness (related to Kato c_fg + c_sm).
    """
    cfg = cfg or TraceConfig()
    S = _ink_probability(warped)
    h, w = S.shape

    # x-range from vertical ink mass (Kato §3.3)
    mass = S.sum(axis=0)
    if float(mass.max()) < 1e-6:
        return []
    mass_n = mass / (mass.max() + 1e-9)
    xs_all = np.where(mass_n >= cfg.min_ink_frac)[0]
    if len(xs_all) < 8:
        return []
    x0, x1 = int(xs_all[0]), int(xs_all[-1])
    xs = np.arange(x0, x1 + 1, cfg.x_skip, dtype=np.int32)
    if len(xs) < 4:
        return []

    n_line_est = _estimate_n_lines(S, xs)
    n_strokes = max(1, min(cfg.n_strokes, n_line_est))

    # Nodes: list of candidate y's per column index
    nodes: list[list[tuple[int, float]]] = []
    for x in xs:
        cands = _column_candidates(S, int(x), cfg.max_candidates_per_col)
        if not cands:
            # fallback: soft argmax in column
            y_soft = int(np.argmax(S[:, int(x)]))
            cands = [(y_soft, float(S[y_soft, int(x)]))]
        nodes.append(cands)

    traces: list[StrokeTrace] = []
    used_mask = np.zeros_like(S, dtype=bool)

    for _stroke_i in range(n_strokes):
        # Suppress previously claimed ink for multi-stroke
        S_work = S.copy()
        if used_mask.any():
            S_work[used_mask] *= 0.05

        # Recompute node scores under suppression
        nodes_i: list[list[tuple[int, float]]] = []
        for xi, x in enumerate(xs):
            cands = []
            for y, _ in nodes[xi]:
                score = float(S_work[y, int(x)])
                cands.append((y, score))
            cands.sort(key=lambda t: t[1], reverse=True)
            nodes_i.append(cands[: cfg.max_candidates_per_col] or nodes[xi][:1])

        path = _dp_min_cost_path(xs, nodes_i, S_work, cfg)
        if path is None or len(path) < 8:
            break
        pts = np.array(path, dtype=np.float32)
        cost = float(_path_cost(pts, S_work, cfg))
        traces.append(
            StrokeTrace(
                points_px=pts,
                cost=cost,
                method="column_graph_dp",
                n_columns=len(xs),
            )
        )
        # Claim a tubular neighborhood so next stroke prefers other ink
        for px, py in pts.astype(int):
            y0, y1 = max(0, py - 6), min(h, py + 7)
            x0b, x1b = max(0, px - 2), min(w, px + 3)
            used_mask[y0:y1, x0b:x1b] = True

    return traces


def _dp_min_cost_path(
    xs: np.ndarray,
    nodes: list[list[tuple[int, float]]],
    S: np.ndarray,
    cfg: TraceConfig,
) -> list[tuple[int, int]] | None:
    """Dynamic programming path: min ink+smoothness cost across columns."""
    n = len(xs)
    if n == 0:
        return None

    # dp[i][j] = best cost to reach candidate j at column i
    dp: list[list[float]] = []
    parent: list[list[int]] = []

    for i in range(n):
        m = len(nodes[i])
        dp.append([math.inf] * m)
        parent.append([-1] * m)
        x = int(xs[i])
        for j, (y, ink_score) in enumerate(nodes[i]):
            ink_cost = cfg.ink_weight * (1.0 - ink_score)
            if i == 0:
                dp[i][j] = ink_cost
                continue
            best_k = -1
            best_val = math.inf
            for k, (y_prev, _) in enumerate(nodes[i - 1]):
                dy = abs(y - y_prev)
                if dy > cfg.max_jump_px:
                    continue
                # Smoothness ~ Kato c_sm; also prefer staying in ink corridor
                sm = cfg.smoothness_weight * (dy / max(S.shape[0], 1))
                val = dp[i - 1][k] + ink_cost + sm
                if val < best_val:
                    best_val = val
                    best_k = k
            if best_k >= 0:
                dp[i][j] = best_val
                parent[i][j] = best_k

    # Backtrack from best end node
    last = dp[-1]
    if not last or min(last) == math.inf:
        return None
    j = int(np.argmin(last))
    path_rev: list[tuple[int, int]] = []
    for i in range(n - 1, -1, -1):
        y, _ = nodes[i][j]
        path_rev.append((int(xs[i]), int(y)))
        j = parent[i][j]
        if i > 0 and j < 0:
            return None
    path_rev.reverse()
    return path_rev


def _path_cost(pts: np.ndarray, S: np.ndarray, cfg: TraceConfig) -> float:
    if len(pts) < 2:
        return math.inf
    ink = 0.0
    sm = 0.0
    for i, (px, py) in enumerate(pts):
        x, y = int(px), int(py)
        x = int(np.clip(x, 0, S.shape[1] - 1))
        y = int(np.clip(y, 0, S.shape[0] - 1))
        ink += cfg.ink_weight * (1.0 - float(S[y, x]))
        if i > 0:
            sm += cfg.smoothness_weight * abs(pts[i, 1] - pts[i - 1, 1]) / S.shape[0]
    return ink + sm


def extract_stroke_pixels_v2(
    warped: np.ndarray,
    *,
    trace_mode: str = "column_graph",
    cfg: TraceConfig | None = None,
) -> tuple[np.ndarray | None, list[StrokeTrace]]:
    """
    Stroke extraction for v2.

    Modes:
      contour       — v1 largest-contour fallback
      column_graph  — Kato-inspired DP path (default)
      both          — prefer column_graph; fall back to contour
    """
    cfg = cfg or TraceConfig()
    traces: list[StrokeTrace] = []

    if trace_mode in ("column_graph", "both"):
        traces = trace_strokes_column_graph(warped, cfg)
        if traces:
            return traces[0].points_px, traces

    if trace_mode in ("contour", "both"):
        pts = v1.extract_stroke_pixels(warped)
        if pts is not None:
            tr = StrokeTrace(
                points_px=pts.astype(np.float32),
                cost=0.0,
                method="contour_v1",
                n_columns=0,
            )
            return pts, [tr]

    return None, traces


# ---------------------------------------------------------------------------
# Analysis + readout (v1 model selection on v2 strokes)
# ---------------------------------------------------------------------------


@dataclass
class ShapeAnalysisV2(ShapeAnalysis):
    """Extends v1 analysis with tracing metadata for v2 logging/debug."""

    version: str = VERSION
    trace_method: str = "column_graph_dp"
    n_stroke_candidates: int = 1
    alt_strokes_px: list[list[tuple[int, int]]] = field(default_factory=list)


def analyze_shape_v2(
    warped: np.ndarray,
    axes: AxisConfig,
    *,
    trace_mode: str = "column_graph",
    trace_cfg: TraceConfig | None = None,
    ohm_mode: bool = False,
) -> ShapeAnalysisV2 | None:
    pts_px, traces = extract_stroke_pixels_v2(
        warped, trace_mode=trace_mode, cfg=trace_cfg
    )
    if pts_px is None:
        return None

    x, y = stroke_to_data(pts_px, axes)
    if len(x) < 35:
        return None

    line = _fit_line(x, y)
    quad = _fit_quadratic(x, y) if len(x) >= 20 else None
    sine = (
        _fit_sinusoid(x, y)
        if len(x) >= 40 and np.ptp(x) > 0.05 * (axes.x_max - axes.x_min)
        else None
    )

    y_span = float(np.ptp(y))
    shape_label, best, readout = _choose_shape(line, quad, sine, y_span)

    stroke_list = [
        (int(p[0]), int(p[1])) for p in pts_px[:: max(1, len(pts_px) // 80)]
    ]
    fit_px = _sample_curve_px(best, axes, x)
    line_ref_px = _sample_curve_px(line, axes, x)
    arc_len = _arc_length_data(x, y)

    alt: list[list[tuple[int, int]]] = []
    for tr in traces[1:3]:
        alt.append(
            [
                (int(p[0]), int(p[1]))
                for p in tr.points_px[:: max(1, len(tr.points_px) // 60)]
            ]
        )

    method = traces[0].method if traces else trace_mode
    analysis = ShapeAnalysisV2(
        shape=shape_label,
        best=best,
        line_scores=line,
        stroke_px=stroke_list,
        fit_curve_px=fit_px,
        line_ref_px=line_ref_px,
        readout_lines=readout,
        arc_length=arc_len,
        version=VERSION,
        trace_method=method,
        n_stroke_candidates=len(traces),
        alt_strokes_px=alt,
    )

    if shape_label == "LINE":
        m, b = line.params["m"], line.params["b"]
        x0, x1 = float(np.min(x)), float(np.max(x))
        y0, y1 = m * x0 + b, m * x1 + b
        analysis.slope = m
        analysis.intercept = b
        analysis.seg_length = math.hypot(x1 - x0, y1 - y0)
        analysis.p1, analysis.p2 = (x0, y0), (x1, y1)
        analysis.p1_px = data_to_pixel(x0, y0, axes)
        analysis.p2_px = data_to_pixel(x1, y1, axes)
        readout.append(axes.format_length(analysis.seg_length))
        if ohm_mode:
            readout.append(
                f"I-V mode: R = {m:.4g} ohm"
                " (x = I in A, y = V in V; slope is R)"
            )

    if ohm_mode and shape_label != "LINE":
        readout.append("I-V mode: R is shown only when the line model wins")

    readout.append(f"Arc length (stroke): {arc_len:.4g} {axes.length_unit}")
    readout.append(f"Trace: {method}  (v{VERSION})")
    if len(traces) > 1:
        readout.append(f"Alt strokes detected: {len(traces) - 1}")
    analysis.readout_lines = readout
    return analysis


def draw_warp_preview_v2(
    warped: np.ndarray, analysis: ShapeAnalysisV2 | None
) -> np.ndarray:
    preview = draw_warp_preview(warped, analysis)
    if analysis is None:
        return preview
    # Show alternate stroke candidates in magenta (multi-line hook)
    for stroke in analysis.alt_strokes_px:
        for px, py in stroke:
            cv2.circle(preview, (px, py), 2, (255, 0, 255), -1, lineType=cv2.LINE_AA)
    cv2.putText(
        preview,
        f"v{VERSION} | {analysis.trace_method}",
        (8, WARP_H - 12),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (40, 40, 40),
        1,
        cv2.LINE_AA,
    )
    return preview


# ---------------------------------------------------------------------------
# Future hooks (documented for v2.x roadmap; not required at runtime)
# ---------------------------------------------------------------------------


def estimate_axis_scale_ocr_stub(_warped: np.ndarray) -> dict[str, float] | None:
    """
    Placeholder for Kato §3.4 value extraction via OCR + RANSAC tick fitting.

    Planned inputs: CRAFT/STAR-Net (or Tesseract) tick labels → RANSAC
    pixel↔value maps → replace manual AxisConfig presets when confident.
    """
    return None


def style_probability_maps_stub(_warped: np.ndarray) -> np.ndarray | None:
    """
    Placeholder for Kato §3.2 FastFCN-style maps
    (solid / dashed / dash-dot / dotted / legend / ticks).

    Until a trained model ships, `_ink_probability` is the classical stand-in.
    """
    return None


# ---------------------------------------------------------------------------
# Live-view video recording (v2.2)
# ---------------------------------------------------------------------------


def _open_video_writer(
    path: Path,
    frame_size: tuple[int, int],
    fps: float,
) -> tuple[cv2.VideoWriter, Path] | None:
    """Try common MP4/AVI codecs until one opens (macOS / OpenCV vary)."""
    w, h = frame_size
    candidates = (
        ("mp4v", path.with_suffix(".mp4")),
        ("avc1", path.with_suffix(".mp4")),
        ("MJPG", path.with_suffix(".avi")),
    )
    for fourcc_name, out_path in candidates:
        fourcc = cv2.VideoWriter_fourcc(*fourcc_name)
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))
        if writer.isOpened():
            return writer, out_path
        writer.release()
    return None


@dataclass
class LiveViewRecorder:
    """Record the composite live-view window (and optionally raw camera frames)."""

    fps: float = 20.0
    record_raw: bool = False
    writer: cv2.VideoWriter | None = None
    raw_writer: cv2.VideoWriter | None = None
    path: Path | None = None
    raw_path: Path | None = None
    started_at: float | None = None
    frame_count: int = 0
    _size: tuple[int, int] | None = None

    @property
    def active(self) -> bool:
        return self.writer is not None

    @property
    def elapsed_s(self) -> float:
        if self.started_at is None:
            return 0.0
        return max(0.0, time.time() - self.started_at)

    def start(self, frame_bgr: np.ndarray, capture_dir: Path) -> str:
        self.stop()
        h, w = frame_bgr.shape[:2]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        capture_dir.mkdir(exist_ok=True)
        base = capture_dir / f"live_v2_{stamp}"
        opened = _open_video_writer(base, (w, h), self.fps)
        if opened is None:
            return "Recording failed — no usable video codec"
        self.writer, self.path = opened
        self._size = (w, h)
        self.started_at = time.time()
        self.frame_count = 0
        if self.record_raw:
            raw_base = capture_dir / f"live_v2_raw_{stamp}"
            raw_opened = _open_video_writer(raw_base, (w, h), self.fps)
            if raw_opened is not None:
                self.raw_writer, self.raw_path = raw_opened
        msg = f"REC start → {self.path.name}"
        if self.raw_path is not None:
            msg += f" (+ raw {self.raw_path.name})"
        return msg

    def stop(self) -> str | None:
        if self.writer is None:
            return None
        n = self.frame_count
        path = self.path
        self.writer.release()
        self.writer = None
        if self.raw_writer is not None:
            self.raw_writer.release()
            self.raw_writer = None
        self.started_at = None
        self._size = None
        self.frame_count = 0
        name = path.name if path is not None else "video"
        self.path = None
        self.raw_path = None
        return f"REC saved {name} ({n} frames)"

    def write(self, display_bgr: np.ndarray, raw_bgr: np.ndarray | None = None) -> None:
        if self.writer is None:
            return
        h, w = display_bgr.shape[:2]
        if self._size is not None and (w, h) != self._size:
            # Resolution change mid-session: skip rather than corrupt the file
            return
        self.writer.write(display_bgr)
        if self.raw_writer is not None and raw_bgr is not None:
            rh, rw = raw_bgr.shape[:2]
            if (rw, rh) == self._size:
                self.raw_writer.write(raw_bgr)
            else:
                resized = cv2.resize(raw_bgr, self._size)
                self.raw_writer.write(resized)
        self.frame_count += 1


def draw_rec_badge(display: np.ndarray, recorder: LiveViewRecorder) -> np.ndarray:
    """Corner badge so recording state is visible in the saved video too."""
    if not recorder.active:
        return display
    out = display
    elapsed = recorder.elapsed_s
    label = f"REC {elapsed:04.1f}s"
    x0, y0 = 12, 28
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    cv2.rectangle(
        out,
        (x0 - 6, y0 - th - 8),
        (x0 + tw + 22, y0 + 8),
        (0, 0, 0),
        -1,
        lineType=cv2.LINE_AA,
    )
    cv2.circle(out, (x0 + 6, y0 - th // 2), 6, (0, 0, 220), -1, lineType=cv2.LINE_AA)
    cv2.putText(
        out,
        label,
        (x0 + 18, y0),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (240, 240, 240),
        2,
        cv2.LINE_AA,
    )
    return out


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"line_camera v{VERSION} (hierarchical axes box + Kato + REC)"
    )
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument(
        "--trace-mode",
        choices=("column_graph", "contour", "both"),
        default="column_graph",
        help="Stroke extraction backend (default: column_graph)",
    )
    parser.add_argument(
        "--quad-mode",
        choices=("auto", "axes", "sheet", "vanishing", "contour"),
        default="auto",
        help="auto/axes=sheet→tick box; sheet=outer only; vanishing/contour=legacy",
    )
    parser.add_argument(
        "--n-strokes",
        type=int,
        default=1,
        help="Max simultaneous strokes to attempt (Kato multi-line hook)",
    )
    parser.add_argument(
        "--record-on-start",
        action="store_true",
        help="Begin live-view MP4 recording immediately (same as pressing r)",
    )
    parser.add_argument(
        "--record-raw",
        action="store_true",
        help="When recording, also write a raw camera MP4 (no overlays)",
    )
    parser.add_argument(
        "--record-fps",
        type=float,
        default=0.0,
        help="Recording FPS (0 = use camera FPS if available, else 20)",
    )
    args = parser.parse_args()

    trace_cfg = TraceConfig(n_strokes=max(1, args.n_strokes))

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit(
            f"Could not open camera {args.camera}. "
            "Grant Camera access in System Settings > Privacy & Security."
        )

    cam_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if args.record_fps > 1.0:
        rec_fps = float(args.record_fps)
    elif cam_fps > 1.0:
        rec_fps = cam_fps
    else:
        rec_fps = 20.0

    recorder = LiveViewRecorder(fps=rec_fps, record_raw=bool(args.record_raw))
    pending_record_start = bool(args.record_on_start)
    status_hold_until = 0.0
    quad_lock = QuadLock()

    axes = AxisConfig()
    iv_ohm_mode = False
    active_preset: PlotPreset | None = None
    quad: np.ndarray | None = None
    inv_matrix: np.ndarray | None = None
    calibrator = ManualCalibrator()
    paused = False
    last_quad_info: QuadDetectResult | None = None
    status = (
        f"line_camera v{VERSION} | quad={args.quad_mode} | "
        f"trace={args.trace_mode} | Press 1-8, then m or a | r=REC | u=unlock"
    )
    last_analysis: ShapeAnalysisV2 | None = None
    smooth_shape: str | None = None
    warped: np.ndarray | None = None
    frame: np.ndarray | None = None

    CAPTURE_DIR.mkdir(exist_ok=True)
    win = f"Shape detector v{VERSION}"
    warp_win = "Warped plot v2"
    cv2.namedWindow(win)
    cv2.namedWindow(warp_win)

    def on_mouse(event: int, x: int, y: int, *_a) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            calibrator.click(x, y)

    cv2.setMouseCallback(win, on_mouse)
    print(f"line_camera v{VERSION} starting")
    print(f"  quad-mode={args.quad_mode}  trace-mode={args.trace_mode}")
    print(f"  record-fps={rec_fps:.1f}  record-raw={args.record_raw}")
    print(PRESET_HELP)
    print("  r = toggle live-view recording")
    print("  a = hierarchical auto-detect (sheet + axes/tick box)")
    print("  o = I-V / Ohm teaching mode (x = I 0-1 A, y = V 0-10 V)")
    print("  u = unlock auto box (clear lock)")

    while True:
        if not paused:
            ok, frame = cap.read()
            if not ok:
                status = "Camera read failed"
                break
        else:
            ok = frame is not None
            if not ok:
                break

        assert frame is not None

        if pending_record_start and not recorder.active:
            status = recorder.start(frame, CAPTURE_DIR)
            status_hold_until = time.time() + 2.0
            pending_record_start = False

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break
        if key == ord(" "):
            paused = not paused
        if key == ord("r"):
            if recorder.active:
                status = recorder.stop() or "REC stopped"
                status_hold_until = time.time() + 3.0
            else:
                status = recorder.start(frame, CAPTURE_DIR)
                status_hold_until = time.time() + 2.0
        if key == ord("m"):
            calibrator.start()
            quad = None
            last_quad_info = None
            quad_lock.clear()
            last_analysis = None
            smooth_shape = None
            status = "Manual: click plot corners 1-4 (TL, TR, BR, BL)"
        if key == ord("o"):
            iv_ohm_mode = not iv_ohm_mode
            active_preset = None
            if iv_ohm_mode:
                axes = ohm_teaching_axes()
                status = (
                    f"v{VERSION} | I-V mode | x = I (0-1 A), y = V (0-10 V) | "
                    "slope = R (ohm)"
                )
            else:
                axes = AxisConfig()
                status = f"v{VERSION} | I-V mode off"
            status_hold_until = time.time() + 2.5
        if key == ord("u"):
            quad_lock.clear()
            quad = None
            last_quad_info = None
            last_analysis = None
            smooth_shape = None
            status = "Auto lock cleared — press a to redetect"
            status_hold_until = time.time() + 2.0
        if key == ord("a"):
            det = run_autodetect(frame, args.quad_mode)
            det = quad_lock.accept(det)
            if det is not None:
                quad = det.quad
                last_quad_info = det
                tick_bit = ""
                if det.n_ticks_x or det.n_ticks_y:
                    tick_bit = f" ticks x={det.n_ticks_x} y={det.n_ticks_y}"
                status = (
                    f"Auto [{det.method}] score={det.score:.2f} "
                    f"grid H={det.n_lines_h} V={det.n_lines_v}{tick_bit}"
                )
                status_hold_until = time.time() + 2.5
            else:
                last_quad_info = None
                status = (
                    "Auto detect failed — try --quad-mode sheet|contour or manual (m)"
                )
        if key == ord("s"):
            path = CAPTURE_DIR / f"frame_v2_{int(time.time())}.jpg"
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
                ok_cls = (
                    active_preset is not None
                    and last_analysis.shape == active_preset.expected_class
                )
                status = (
                    f"Logged trial ({'OK' if ok_cls else 'CHECK'}) -> {log_path.name}"
                )

        if key in PRESET_BY_KEY:
            iv_ohm_mode = False
            active_preset = PRESET_BY_KEY[key]
            axes = active_preset.axes
            status = (
                f"Preset {active_preset.short_name}: expect "
                f"{active_preset.expected_class} | {active_preset.ground_truth}"
            )
        if not iv_ohm_mode:
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
                last_quad_info = QuadDetectResult(
                    quad=order_quad(quad), method="manual", score=1.0
                )
                quad_lock.clear()
                calibrator.reset()
                last_analysis = None
                smooth_shape = None
                status = "Manual corners set — analyzing (v2)..."

        warped = None
        if quad is not None:
            warped, inv_matrix = warp_plot(frame, quad)
            try:
                current = analyze_shape_v2(
                    warped,
                    axes,
                    trace_mode=args.trace_mode,
                    trace_cfg=trace_cfg,
                    ohm_mode=iv_ohm_mode,
                )
            except Exception as exc:
                current = None
                status = f"Detection error: {exc}"
            if current is not None:
                last_analysis = current
                smooth_shape = current.shape
                qmeth = last_quad_info.method if last_quad_info else "quad"
                if iv_ohm_mode and current.shape == "LINE" and current.slope is not None:
                    status = (
                        f"v{VERSION} | I-V mode | LINE | "
                        f"R = {current.slope:.4g} ohm | frame={qmeth}"
                    )
                elif iv_ohm_mode:
                    status = (
                        f"v{VERSION} | I-V mode | {current.shape} | "
                        "R only if LINE | "
                        f"frame={qmeth}"
                    )
                else:
                    status = (
                        f"Detected: {current.shape} [{current.trace_method}] "
                        f"frame={qmeth}"
                    )
            elif "error" not in status.lower():
                status = (
                    "Plot OK — no stroke found. Try --trace-mode both, "
                    "darker pen, even light."
                )
        elif not calibrator.active:
            if time.time() < status_hold_until:
                pass
            elif recorder.active and recorder.path is not None:
                status = (
                    f"v{VERSION}: m/a calibrate | REC {recorder.path.name} "
                    f"{recorder.elapsed_s:.0f}s"
                )
            else:
                status = (
                    f"v{VERSION}: press m (manual) or a (auto; "
                    f"--quad-mode {args.quad_mode}) | o=I-V | r=REC"
                )

        display = draw_overlay(
            frame, quad, last_analysis, inv_matrix, axes, status, paused, calibrator
        )
        if last_quad_info is not None and last_quad_info.method != "manual":
            display = draw_quad_debug(display, last_quad_info)
        display = draw_rec_badge(display, recorder)
        cv2.putText(
            display,
            f"v{VERSION}",
            (10, display.shape[0] - 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        if recorder.active:
            recorder.write(display, raw_bgr=frame)
        cv2.imshow(win, display)
        if warped is not None:
            cv2.imshow(warp_win, draw_warp_preview_v2(warped, last_analysis))

    stop_msg = recorder.stop()
    if stop_msg:
        print(stop_msg)
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
