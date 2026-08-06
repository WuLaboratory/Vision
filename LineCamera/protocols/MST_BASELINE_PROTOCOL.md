# Baseline Comparison Protocol (Phases 1–2)

**Goal:** Demonstrate measurable advantage of shape-aware pipeline over (i) naive Hough linear fit and (ii) established offline digitizer WebPlotDigitizer.

> Filename retained as `MST_BASELINE_PROTOCOL.md` for path compatibility with earlier packaging.

---

## Baseline 1 — Naive Hough linear detector (automated)

Simulates the original `line_camera.py` v1 behavior: longest `HoughLinesP` segment → line equation. No shape classification.

```bash
cd Linear
.venv/bin/python scripts/baseline_hough_static.py
```

**Outputs:** `validation/results/baseline_hough.json`, summary in `analyze_mst_validation.py`

**Metrics:**

| Plot type | Expected Hough behavior |
|-----------|-------------------------|
| Lines | Reasonable m, b |
| Sinusoids | Tangent-like line; **wrong class** |
| Quadratics | Poor linear fit; **wrong class** |

**Manuscript claim:** Shape-aware pipeline reduces systematic mis-measurement on non-linear plots.

---

## Baseline 2 — WebPlotDigitizer (manual)

**Tool:** [WebPlotDigitizer](https://automeris.io/WebPlotDigitizer/) v4.x (cite Rohatgi, 2015; Drevon et al., 2017).

### Images

Use the eight primary JPEGs: `line1.jpg` … `quadratic2.jpg`.

### Per-image procedure

1. Open image in WebPlotDigitizer.
2. **Plot type:** 2D (X-Y) plot.
3. **Alignment:**
   - Define X1, X2 from axis min/max (0, 1 for all plots).
   - Define Y1, Y2 from ground truth `validation/ground_truth.json` y_min, y_max.
4. **Automatic trace** (or manual point mode if auto fails):
   - Use color picker on black stroke.
   - Export digitized points to CSV.
5. **Post-processing:** Fit same models as pipeline (least-squares line, quadratic, sinusoid grid search) using exported points — or record WPD’s built-in fit if available.

### Line plots — record

| Field | Description |
|-------|-------------|
| `file` | e.g. line1.jpg |
| `m_fitted` | Linear slope from digitized points |
| `b_fitted` | Intercept |
| `n_points` | Number of digitized points |
| `operator` | Initials |
| `session` | 1 or 2 (repeatability) |

### Curved plots — record

| Field | Description |
|-------|-------------|
| `detected_as_line` | yes/no — did operator use line tool only? |
| `best_model` | line / quadratic / sinusoid (if fitted offline) |
| `rmse` | vs. digitized points |

Follow `MST_BASELINE_PROTOCOL.md`. Export digitized points to `validation/WebPlotDigitizer_results/*.csv`, then run:

```bash
.venv/bin/python scripts/process_webplotdigitizer_baseline.py
```

### Time budget

~15 min per image × 8 = **~2 hours** (one session)  
Repeat session 2 for **inter-session repeatability** on line2, line3, quadratic1 (3 plots minimum).

---

## Comparison table (manuscript Table 5)

| Method | Modality | Class selection | Line slope error | Non-line handling |
|--------|----------|-----------------|------------------|-------------------|
| Hough baseline | Static | None (always line) | — | Fails on curves |
| WebPlotDigitizer | Static, manual | Operator-dependent | Report measured | Manual |
| This work (JPEG) | Static, auto | Penalized RMSE | Table 1 | Honest readout |
| This work (camera) | Live | Penalized RMSE | Table 2 | Honest readout |

---

## Statistical comparison (optional)

For line plots where all methods return slope m:

- Paired comparison: |m_fit − m_true| / m_true  
- Report mean absolute percentage error (MAPE) per method  
- At least a descriptive comparison is recommended; inferential tests are optional for N=8

---

## Citation requirements

- Rohatgi A. WebPlotDigitizer (2015)  
- Drevon D et al. Behav Modif 2017 (validity)  
- Kadić D, Hemels MEH. CPT PSP 2017 (digitizer accuracy benchmarks)
