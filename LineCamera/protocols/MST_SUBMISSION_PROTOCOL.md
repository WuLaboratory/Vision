# Validation and open-source packaging checklist

**Purpose:** Confirm that validation artifacts and the open-source deposit are complete before publishing code and data (Zenodo / GitHub).  
**Status:** Validation complete; DOI pending  
**Last updated:** 6 August 2026

> Filename retained as `MST_SUBMISSION_PROTOCOL.md` for path compatibility with earlier packaging.

---

## 1. Completeness criteria

Publish the software and data package when **all** items below are complete.

| # | Criterion | Protocol | Output artifact | Status |
|---|-----------|----------|-----------------|--------|
| A | Static JPEG baseline (accuracy) | `analyze_validation_set.py` | `validation_results.json` | [x] Done |
| B | Live-camera expanded study (N≥10/plot) | `MST_CAMERA_PROTOCOL.md` | `camera_log.jsonl` (≥80 trials) | [x] 295 trials |
| C | Uncertainty / precision analysis | `MST_UNCERTAINTY_PROTOCOL.md` | `uncertainty_jitter.json` | [x] Done |
| D | WebPlotDigitizer baseline | `MST_BASELINE_PROTOCOL.md` | `baseline_webplotdigitizer.csv` | [x] Done (7/8 class; see notes) |
| E | Naive Hough baseline | `scripts/baseline_hough_static.py` | `baseline_hough.json` | [x] Done |
| F | Open-source README and license | `Zenodo_Upload/README.md`, `LICENSE` | README + CC BY 4.0 LICENSE | [x] |
| G | Data & code DOI | Zenodo deposit | DOI in README / citation | [ ] |
| H | Figures packaged with deposit | `figures/` | Report and analysis PNGs | [x] |

Item C (uncertainty) is treated as mandatory for transparent measurement reporting, independent of any publication venue.

---

## 2. Study phases and timeline

### Phase 0 — Complete (May–June 2026)

- [x] Pipeline: homography, stroke extraction, shape-aware fitting
- [x] 15 static JPEGs: 100% classification
- [x] 28 pilot camera trials: 82% classification
- [x] Internal report and draft documentation

### Phase 1 — Automated baselines and uncertainty (1–2 days, desk work)

```bash
cd Linear
.venv/bin/python scripts/baseline_hough_static.py
.venv/bin/python scripts/uncertainty_corner_jitter.py --samples 200
.venv/bin/python scripts/analyze_mst_validation.py
```

**Deliverables:** Hough baseline table, corner-jitter uncertainty table, draft error-budget paragraph.

### Phase 2 — WebPlotDigitizer baseline (2–3 hours, manual)

```bash
.venv/bin/python scripts/process_webplotdigitizer_baseline.py
```

Exports go in `validation/WebPlotDigitizer_results/*.csv`. The script fits models and writes `baseline_webplotdigitizer.csv`.

**Status (3 Jul 2026):** 8/8 plots processed; 7/8 class correct; mean line slope error 0.35%. Recalibrate `sinusoid1` in WPD (y-axis should be −2 to 2, not 0 to 6.5).

### Phase 3 — Expanded camera validation (2–3 sessions, ~3 hours total)

Follow `MST_CAMERA_PROTOCOL.md`. Target **80 trials** (10 per plot × 8 plots) using `validation/MST_TRIAL_MATRIX.json`.

```bash
.venv/bin/python line_camera.py --validate
# Log each trial with 'l'
.venv/bin/python scripts/analyze_mst_validation.py
```

**Pass targets (achieved / reported):**

| Metric | Target | Result |
|--------|--------|--------|
| Overall trials | ≥ 80 | **295** |
| QC accuracy (arc < 100) | ≥ 85% | **86.7%** (182/210) |
| Static JPEG | 100% | **100%** |
| Uncertainty study | Complete | **Done** |
| Baselines | WPD + Hough | **Done** |

### Phase 4 — Open-source packaging

1. Confirm `Zenodo_Upload/README.md` is venue-neutral and lists package contents
2. Confirm LICENSE is CC BY 4.0 (already in `LICENSE`)
3. Upload `Zenodo_Upload/` (or equivalent tree) to Zenodo
4. Push the public GitHub repository and link the Zenodo DOI
5. Update README citation block with the assigned DOI

---

## 3. File map

| File | Role |
|------|------|
| `validation/MST_SUBMISSION_PROTOCOL.md` | This checklist |
| `validation/MST_CAMERA_PROTOCOL.md` | Expanded live-camera trials |
| `validation/MST_UNCERTAINTY_PROTOCOL.md` | Corner-jitter Monte Carlo |
| `validation/MST_BASELINE_PROTOCOL.md` | WebPlotDigitizer procedure |
| `validation/MST_TRIAL_MATRIX.json` | 80-trial schedule |
| `validation/CAMERA_VALIDATION.md` | General camera validation guide |
| `scripts/uncertainty_corner_jitter.py` | Automated uncertainty study |
| `scripts/baseline_hough_static.py` | Hough-only baseline |
| `scripts/analyze_phase3_camera.py` | Phase 3 tables and figures |
| `scripts/analyze_mst_validation.py` | Validation completeness summary |
| `validation/results/baseline_webplotdigitizer_template.csv` | WPD data entry template |

---

## 4. Quick status command

```bash
.venv/bin/python scripts/analyze_mst_validation.py --status
```
