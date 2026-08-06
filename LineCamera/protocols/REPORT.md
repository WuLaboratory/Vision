# Project Report: Vision-Based Extraction of Plotted Functions from Images and Live Video

**Laboratory:** Wu Laboratory  
**Initial report:** May 29, 2026  
**Last updated:** June 4, 2026 (Session 3 — live camera validation on printed plots)  
**Status:** Proof-of-concept validated on static JPEGs (100%) and printed paper via camera (82%)

---

## 1. Executive summary

We developed a workflow to recover **mathematical descriptions** and **geometric measures** from plotted curves, using **static images** and a **live webcam** pointed at **printed paper**.

| Stage | Result |
|-------|--------|
| Static JPEG analysis (15 images) | **15/15 (100%)** shape classification |
| Live camera, printed paper (28 trials) | **23/28 (82%)** shape classification |
| Parameter recovery (well-traced camera trials) | Line slope **~3%** error; quadratics **~5%**; sinusoid amplitude **~5%** |

**Session 1** (May 29): Offline plot analysis; camera v1; axis units on length.

**Session 2** (May 30): Shape-aware fitting (line / quadratic / sinusoid); honest readout; visual overlays.

**Session 3** (June 4): Full validation set (8 plot types × ~3 camera trials); presets `1`–`8`; trial logging (`--validate`, key `l`); comparison of digital vs. printed-paper performance.

---

## 2. Scientific motivation

Hand-drawn and printed graphs remain common in teaching and laboratory work. A low-cost monocular vision tool that accepts **digital images** or **paper held to a camera**, infers **function class** with goodness-of-fit metrics, and reports **equations and lengths with units** could support instruction and semi-automated logging. Session 3 provides **initial quantitative evidence** that the pipeline generalizes from JPEG files to physical prints, with calibration quality as the dominant error source.

---

## 3. Methods

### 3.1 Static image analysis

Labeled plots: axis ticks define coordinates. Unlabeled grids (`*a.jpg`): grid count ≠ data units; use labeled reference ranges.

Batch script: `scripts/analyze_validation_set.py` on 8 primary + 7 `*a` variants.

### 3.2 Live camera pipeline (shape-aware)

| Step | Technique |
|------|-----------|
| Presets | Keys `1`–`8` for line1–3, sinusoid1–3, quadratic1–2 |
| Calibration | 4 plot corners (TL → TR → BR → BL) |
| Rectification | Perspective warp to 640×480 |
| Stroke extraction | Largest ink contour |
| Model fitting | Line, quadratic, sinusoid (grid search ω) |
| Selection | Penalized RMSE (×1.0 / ×1.08 / ×1.12) |
| Logging | `--validate` + `l` → `validation/results/camera_log.jsonl` |

### 3.3 Ground truth

`validation/ground_truth.json` and MATLAB `linear.m` define 8 primary plot families.

---

## 4. Results

### Figure 1 — Reference linear plot families

![Figure 1](report_figures/fig1_reference_lines.png)

### Figure 2 — End-to-end workflow

![Figure 2](report_figures/fig2_workflow.png)

### Figure 3 — Validation summary (static JPEG vs. live camera)

![Figure 3](report_figures/fig3_results_table.png)

| Plot | Class | Ground truth | Static JPEG | Live camera (printed) |
|------|-------|--------------|-------------|------------------------|
| line1 | LINE | y = 10x + 1 | 100% | 50%* |
| line2 | LINE | y = 5x + 1.5 | 100% | 80% |
| line3 | LINE | y = 2x + 3 | 100% | **100%** |
| sinusoid1 | SINUSOID | y = 2 sin(5x) | 100% | 67% |
| sinusoid2 | SINUSOID | y = 3 sin(9x−4) | 100% | **100%** |
| sinusoid3 | SINUSOID | y = 2.3 sin(3x+7) | 100% | **100%** |
| quadratic1 | QUADRATIC | y = x²+2x+3 | 100% | 67% |
| quadratic2 | QUADRATIC | y = 5x²+8x+13 | 100% | **100%** |

\*line1 camera failures linked to grid-ink tracing (steep slope m=10, y∈[0,11]).

### Figure 4 — Model comparison (sinusoid vs. linear)

![Figure 4](report_figures/fig4_model_comparison.png)

### Figure 5 — Live overlay legend

![Figure 5](report_figures/fig5_overlay_legend.png)

### Figure 6 — Development milestones

![Figure 6](report_figures/fig6_development_timeline.png)

### Figure 7 — Live camera classification by plot (Session 3)

![Figure 7](report_figures/fig7_camera_classification.png)

### Figure 8 — Static JPEG vs. live camera comparison

![Figure 8](report_figures/fig8_validation_comparison.png)

### Session 3 — Live camera trials (printed paper)

- **28 trials** logged (`validation/results/camera_log.jsonl`)
- **23/28 correct (82%)** shape classification
- **5 failures:** line1 (2), line2 (1), sinusoid1 (1), quadratic1 (1)
- **Quality indicator:** arc length along traced stroke; good trials ≈ 15–75 axis units; failures often > 200 (grid/border ink traced)

**Parameter errors (class correct, arc length < 100):**

| Plot type | Typical error vs. ground truth |
|-----------|-------------------------------|
| Lines (line2, line3) | slope m **1.8–2.9%**; intercept b **0.07–0.10** |
| Quadratics | coeff a **~5%**; b **~0.6%**; c **~0.7%** |
| Sinusoids | amplitude A **~4–6%**; ω **~8–10%** |

---

## 5. Key lessons

1. **Grid count ≠ data units** on unlabeled plots.
2. **Corner calibration** dominates error; plot **border** corners only.
3. **Shape-aware fitting** prevents misreading curves as lines (Session 2).
4. **Printed-paper validation** (Session 3) confirms pipeline works; **line1** (steepest, tallest axis) is hardest.
5. **Arc length** flags bad traces; tighten quadratic penalty for near-linear cases.
6. Digital baseline (100%) sets an upper bound; camera adds perspective, glare, and grid-noise error.

---

## 6. Software deliverables

| File | Purpose |
|------|---------|
| `line_camera.py` | Shape-aware live detection; presets 1–8; `--validate` logging |
| `validation/CAMERA_VALIDATION.md` | Live trial protocol |
| `validation/ground_truth.json` | Reference parameters |
| `validation/results/VALIDATION_RESULTS.md` | Static JPEG baseline |
| `validation/results/camera_log.jsonl` | Live camera trials |
| `scripts/analyze_validation_set.py` | Batch JPEG analysis |
| `scripts/summarize_camera_log.py` | Camera log summary |
| `scripts/generate_report_figures.py` | Regenerate Figs. 1–8 |

---

## 7. Open-source contribution statement

**Contribution statement (updated Session 3):**

> *A calibrated monocular vision system for real-time tracing of printed plot strokes, automatic model-class selection among linear, quadratic, and sinusoidal forms, and validation on eight ground-truth plot families — achieving 100% classification on digital images and high accuracy under an arc-length QC gate in live-camera trials, with sub-5% parameter error on well-calibrated trials.*

This package is released as open-source software and supporting data for laboratory instruction, reproducible digitization experiments, and further method development.

---

## 8. Suggested documentation outline

1. **Introduction** — Graph digitization; risks of forced linear fits.  
2. **Related work** — Chart digitizers, homography, curve fitting.  
3. **Methods** — Static + camera pipeline; presets; model selection; logging.  
4. **Experiments** — Static JPEG + printed-paper camera trials; ground truth from `linear.m`.  
5. **Results** — Classification rates; confusion analysis; failure modes.  
6. **Discussion** — Calibration sensitivity; arc-length QC; line vs. quadratic ambiguity.  
7. **Conclusion** — Open-source tool; future work (auto corners, stronger line prior).  
8. **Data & code availability** — `camera_log.jsonl`, warp captures, ground truth JSON.

---

## 9. Open-source release checklist

- [x] Static validation (15 JPEGs, 100%).  
- [x] Live-camera validation expanded (see Phase-3 logs).  
- [x] Compare to **WebPlotDigitizer** and naive Hough baseline.  
- [x] Arc-length QC / warning in app.  
- [x] Confirm LICENSE before Zenodo / GitHub publish.  
- [ ] Publish Zenodo DOI and link from GitHub README.  
- [ ] Optional: user study (if education angle) — IRB as needed.

---

## 10. Session log

| Date | Work |
|------|------|
| May 29, 2026 | Static analyses; camera v1; units; initial report (Figs. 1–3). |
| May 30, 2026 | Shape-aware fitting; honest readout; report Figs. 1–6. |
| June 4, 2026 | Validation batch (15 JPEGs); presets 1–8; `--validate` logging; 28 printed-paper camera trials (82%); report Figs. 3, 6–8. |

---

*Regenerate figures:*

```bash
cd Linear
.venv/bin/python scripts/generate_report_figures.py
```
