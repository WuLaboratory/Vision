# Validation analysis summary

Aggregated status of static, live-camera, baseline, and uncertainty artifacts packaged with `line_camera`.

## Completeness checklist

| Criterion | Status | Detail |
|-----------|--------|--------|
| Static JPEG baseline | ✓ | validation_results.json |
| Camera trials N≥80 | ✓ | 295/80 trials logged |
| Camera QC accuracy (arc<100) | ✓ | 182/210 = 86.67% |
| Uncertainty study | ✓ | uncertainty_jitter.json |
| Hough baseline | ✓ | baseline_hough.json |
| WebPlotDigitizer baseline | ✓ | 8/8 plots (7/8 class correct) |

## Camera trials

- Total: 295
- Accuracy (all): 213/295 (72.2%)
- QC accuracy (arc<100): 182/210 (86.67%)

| Plot | N | Correct | Rate |
|------|---|---------|------|
| line1 | 15 | 9 | 60% |
| line2 | 24 | 14 | 58% |
| line3 | 15 | 14 | 93% |
| quadratic1 | 54 | 44 | 81% |
| quadratic2 | 63 | 55 | 87% |
| sinusoid1 | 23 | 14 | 61% |
| sinusoid2 | 35 | 25 | 71% |
| sinusoid3 | 66 | 38 | 58% |

## Uncertainty (corner jitter)

- σ values: [1.0, 2.0, 3.0]
- Mean slope SD at σ=2 px: 0.02007

## WebPlotDigitizer baseline

- Classification: 7/8
- Mean line slope error: 0.339%

## Notes

- Filename `MST_ANALYSIS_SUMMARY.md` is retained for script and path compatibility with earlier packaging.
- Regenerate this summary from the project tree with:  
  `.venv/bin/python scripts/analyze_mst_validation.py --write-md`
