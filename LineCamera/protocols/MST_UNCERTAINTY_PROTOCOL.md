# Uncertainty Protocol (Phase 1)

**Goal:** Quantify how calibration uncertainty propagates to measured slope, intercept, and function class — supporting transparent uncertainty, precision, and accuracy reporting.

> Filename retained as `MST_UNCERTAINTY_PROTOCOL.md` for path compatibility with earlier packaging.

---

## Approach A — Monte Carlo corner jitter (automated)

**Rationale:** Manual corner clicks are the dominant error source. Perturbing the detected quadrilateral on static JPEGs isolates calibration uncertainty without confounding pose or lighting.

### Procedure

```bash
cd Linear
.venv/bin/python scripts/uncertainty_corner_jitter.py --samples 200 --sigma-px 2.0
```

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `--samples` | 200 | Monte Carlo draws per image |
| `--sigma-px` | 2.0 | Gaussian perturbation SD per corner (pixels in source image) |
| `--sigma-px 1.0 3.0` | — | Run sensitivity at multiple levels |

### Method

1. Detect plot quad with `find_largest_quad` (same as production pipeline).
2. For each sample, add independent Gaussian noise to each corner (x, y).
3. Warp, extract stroke, fit models.
4. Record slope m, intercept b (lines), class label, RMSE.

### Outputs

| File | Content |
|------|---------|
| `validation/results/uncertainty_jitter.json` | Per-image statistics |
| `validation/results/uncertainty_jitter.md` | Human-readable summary |
| `validation/results/figures/uncertainty_jitter.png` | Slope SD vs. σ_px (if matplotlib available) |

### Suggested uncertainty paragraph (template)

> Corner-position uncertainty was characterized by Monte Carlo simulation: each plot corner was perturbed with independent zero-mean Gaussian noise of standard deviation σ = {1, 2, 3} px in the source image, with N = 200 realizations per plot. Table X reports the mean and standard deviation of fitted slope m and intercept b. At σ = 2 px, line plots exhibited slope SD of {X}% and intercept SD of {Y} axis units, confirming calibration as the dominant uncertainty source.

---

## Approach B — Live-camera repeatability (manual, Phase 3)

**Rationale:** Precision under real operating conditions.

### Procedure

For each line plot (line2, line3 — avoid line1 for precision stats initially):

1. Run **5 centered trials** without changing paper position (re-click corners each time).
2. Log all with `l`.
3. Compute SD and coefficient of variation (CV) for m and b.

### Pass criterion

- Slope CV < 5% for line2 and line3 on centered repeat trials.

---

## Approach C — Inter-operator calibration (optional)

1. Second operator calibrates the same printed plot (3 trials).
2. Compare slope/intercept distributions between operators.
3. Report as expanded uncertainty component.

---

## Error budget summary table (for manuscript Table 4)

| Source | Estimation method | Typical contribution |
|--------|-------------------|----------------------|
| Corner position | Monte Carlo σ = 2 px | Dominant for slope |
| Perspective / pose | Camera condition matrix | Secondary |
| Stroke discretization | Pixel grid | Sub-pixel after warp |
| Model selection | Penalized RMSE | Class confusion near boundaries |
| Grid ink contamination | Arc-length outliers | Failures on line1, sinusoid1 |

Fill numerical values from `uncertainty_jitter.json` and Phase 3 camera repeats.
