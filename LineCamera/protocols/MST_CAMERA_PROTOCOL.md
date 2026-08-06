# Camera Validation Protocol (Phase 3)

**Goal:** 80 logged trials (10 per plot × 8 plots) with stratified pose and lighting conditions, suitable for accuracy and repeatability reporting.

> Filename retained as `MST_CAMERA_PROTOCOL.md` for path compatibility with earlier packaging.

---

## Prerequisites

1. Print all eight labeled plots (`line1.jpg` … `quadratic2.jpg`) on white paper, black ink, light gray grid (same as MATLAB exports).
2. Even room lighting; avoid direct glare on the plot surface.
3. Reference hardware used in validation: iMac 24″ FaceTime HD 1080p webcam (commodity webcam of similar resolution is acceptable).

```bash
cd Linear
.venv/bin/python line_camera.py --validate
```

---

## Trial matrix

Use `validation/MST_TRIAL_MATRIX.json` as the run sheet. Each entry specifies:

| Field | Meaning |
|-------|---------|
| `trial_id` | Unique ID (e.g. `line1_T01`) |
| `plot_id` | Preset key target (`line1` … `quadratic2`) |
| `preset_key` | Key `1`–`8` |
| `condition` | `centered`, `tilt_left`, `tilt_right`, `near`, `far`, `dim`, `bright`, `repeat` |
| `notes` | Optional observer notes |

### Condition definitions

| Condition | Procedure |
|-----------|-----------|
| **centered** | Paper flat, plot centered, camera normal to paper (~0° tilt) |
| **tilt_left** | Rotate paper ~15° counter-clockwise about vertical axis |
| **tilt_right** | Rotate paper ~15° clockwise |
| **near** | Hold paper ~20% closer to camera (larger in frame) |
| **far** | Hold paper ~20% farther |
| **dim** | Reduce room light or shade one side slightly |
| **bright** | Add desk lamp from 45° (avoid specular glare on ink) |
| **repeat** | Second centered trial (repeatability) |

### Minimum allocation per plot (10 trials)

| Condition | Count |
|-----------|-------|
| centered | 3 |
| tilt_left | 1 |
| tilt_right | 1 |
| near | 1 |
| far | 1 |
| dim | 1 |
| bright | 1 |
| repeat | 1 |

---

## Per-trial procedure

1. Locate next row in `MST_TRIAL_MATRIX.json` (or printed run sheet).
2. Press **preset key** (`1`–`8`).
3. Set up pose per **condition**.
4. Press **`m`**, click four plot corners: TL → TR → BR → BL (plot border only).
5. Verify in **Warped plot** window:
   - Yellow stroke follows blue curve
   - Green fit tracks stroke
   - Grid appears rectangular
6. Record on-screen **Shape**, equation, RMSE, arc length.
7. Press **`l`** to log (requires `--validate`).
8. In the JSONL entry, add `trial_note` with condition if not auto-tagged (future script enhancement).

### Quality gate (do not log failed calibrations)

| Check | Action if fail |
|-------|----------------|
| Arc length > 150 axis units | Recalibrate; likely grid trace |
| Shape ≠ expected | Recalibrate; check preset and lighting |
| Warp visibly skewed | Re-click corners |

---

## Data logging

Logs append to `validation/results/camera_log.jsonl`.  
Warp captures: `validation/results/camera_captures/`.

After each session:

```bash
.venv/bin/python scripts/summarize_camera_log.py
.venv/bin/python scripts/analyze_mst_validation.py
```

---

## Reporting metrics (computed by analyze script)

- **Accuracy:** % correct class vs. ground truth  
- **Precision (repeatability):** SD and CV of slope m (lines) across `centered` + `repeat` trials per plot  
- **Parameter bias:** mean fitted − ground truth  
- **Arc-length QC:** fraction of trials with arc length < 100  

---

## Troubleshooting

See `validation/CAMERA_VALIDATION.md`. For line1 (steep slope), use extra care on corner clicks and lighting; consider logging only when arc length < 75.
