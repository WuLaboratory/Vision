# line_camera: camera-based measurement of plotted function parameters

**Open-source software and supporting data** for recovering plotted function class and parameters from graph paper imaged by a commodity webcam.

After four-point homographic rectification, the software traces ink strokes and compares linear, quadratic, and sinusoidal models using penalized RMSE, with an arc-length quality gate that flags grid-ink contamination. This deposit packages the Python application, ground-truth plots, validation logs, baseline comparisons, uncertainty study outputs, protocols, and figure assets needed to reproduce the reported results.

**Authors:** Phillip M. Wu et al.  
**Institution:** Institute of Physics, Academia Sinica  

**Software:** `line_camera` (Python 3; OpenCV, NumPy)

---

## Package contents

| Path | Description |
|------|-------------|
| `LICENSE` | Creative Commons Attribution 4.0 International (CC BY 4.0) |
| `code/line_camera.py` | Live camera measurement app (homography, stroke tracing, shape-aware fitting) |
| `code/scripts/` | Batch analysis, baselines, uncertainty Monte Carlo, figure generation |
| `code/requirements.txt` | Python dependencies |
| `code/linear.m` | MATLAB script used to generate reference plot families |
| `data/static_plots/` | 15 labeled JPEG validation images (8 primary + 7 `*a` variants) |
| `data/ground_truth.json` | Reference class and equation parameters for each plot |
| `data/MST_TRIAL_MATRIX.json` | Planned live-camera trial schedule (filename retained for compatibility) |
| `data/WebPlotDigitizer_results/` | Digitized point CSVs from WebPlotDigitizer baseline |
| `data/matlab_figs/` | MATLAB `.fig` sources for primary plots |
| `results/camera_log.jsonl` | **295** live-camera trials (primary validation log) |
| `results/camera_captures/` | Warped frames linked from `camera_log.jsonl` |
| `results/validation_results.json` | Static JPEG batch analysis |
| `results/phase3_camera_summary.json` | Aggregated live-camera (Phase-3) metrics |
| `results/uncertainty_jitter.json` | Corner-jitter Monte Carlo uncertainty |
| `results/baseline_hough.json` | Naive Hough line baseline |
| `results/baseline_webplotdigitizer.*` | WebPlotDigitizer baseline summary |
| `results/MST_ANALYSIS_SUMMARY.md` | Aggregated validation summary (filename retained for compatibility) |
| `results/figures/` | Phase-3 and uncertainty analysis plots |
| `results/overlays/` | Static analysis overlay images |
| `figures/report_figures/` | Report figure PNGs |
| `figures/mst_submission/` | Additional packaged figure set (filename retained for compatibility) |
| `protocols/` | Camera, uncertainty, baseline, and validation protocols |
| `MANIFEST.txt` | Full file list for this deposit |

> **Note on filenames:** Some paths still use an `MST_` prefix or folder name from an earlier packaging iteration. They describe the same validation artifacts; content is not tied to any particular journal.

---

## Key reported metrics (from `results/MST_ANALYSIS_SUMMARY.md`)

- Static JPEG classification: **100%** (15/15)
- Live-camera trials: **295**; overall classification **72.2%** (213/295)
- QC-pass (stroke arc length &lt; 100 axis units): **86.7%** (182/210)
- Corner-jitter uncertainty: mean slope SD ≈ **0.020** at σ = 2 px
- WebPlotDigitizer: **7/8** class correct; mean line slope error **0.34%**

---

## Quick start (reproduce static + baselines)

```bash
# From a working copy of this deposit (or the project tree with the same layout)
python3 -m venv .venv
.venv/bin/pip install -r code/requirements.txt

# Place static plots and ground_truth where scripts expect them, or run from the
# original Linear/ project layout documented in protocols/README_camera.md

.venv/bin/python code/scripts/analyze_validation_set.py
.venv/bin/python code/scripts/baseline_hough_static.py
.venv/bin/python code/scripts/uncertainty_corner_jitter.py --samples 200
.venv/bin/python code/scripts/process_webplotdigitizer_baseline.py
.venv/bin/python code/scripts/analyze_mst_validation.py
```

Live camera logging (requires webcam and printed plots):

```bash
.venv/bin/python code/line_camera.py --validate
# After calibration, press l to log each trial
```

See `protocols/CAMERA_VALIDATION.md` and `protocols/README_camera.md` for the full procedure. Additional detailed run sheets live under `protocols/MST_*.md` (historical filenames; same methods).

**Note:** Analysis scripts assume the original project layout (`Linear/line_camera.py`, `Linear/validation/...`). When unpacking this Zenodo deposit alone, either restore that layout or adjust paths in the scripts.

---

## Suggested Zenodo / GitHub metadata

- **Title:** line_camera: supporting data and code for camera-based measurement of plotted function parameters  
- **Upload type:** Software (or Dataset + Software)  
- **Description:** Open-source Python tool for live webcam measurement of plotted linear, quadratic, and sinusoidal functions on graph paper, with shape-aware model selection, validation logs, and uncertainty protocols.  
- **Keywords:** graph digitization; camera measurement; homography; uncertainty; computer vision; curve fitting; open-source software; scientific software  
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0; see `LICENSE`)  
- **Related identifiers:** 10.5281/zenodo.21386582  

---

## Citation

> Wu, P. M. (2026). *line_camera: camera-based measurement of plotted function parameters* (software and supporting data). Institute of Physics, Academia Sinica. [10.5281/zenodo.21386582]

---

## Excluded from this deposit

The following project files were **not** copied (not required for reproducibility of the numerical results):

- Local Python virtualenv (`.venv`)
- Manuscript drafts and cover letters
- Large ad-hoc development screenshots
- Unrelated reference PDFs
- Opportunistic `captures/` frames outside the Phase-3 `camera_log.jsonl` set

---

## License

This software and the accompanying data, protocols, and figures in this deposit are released under the **Creative Commons Attribution 4.0 International (CC BY 4.0)** license. See `LICENSE` for the summary text and links to the full legal code.

Third-party tools used at runtime (e.g. OpenCV, NumPy, MATLAB for generating reference plots, WebPlotDigitizer for baseline CSVs) remain under their own licenses and are not covered by this CC BY 4.0 grant.

---

## Contact

Phillip M. Wu — Institute of Physics, Academia Sinica, Taipei, Taiwan R.O.C.
