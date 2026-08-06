# Live Camera Validation Protocol

Use this checklist when testing **printed** line, sinusoid, and quadratic plots against the digital baseline in `validation/results/VALIDATION_RESULTS.md`.

## Before you start

```bash
cd /Users/p409wu/Desktop/WuLaboratory/Cursor/Linear
.venv/bin/python line_camera.py --validate
```

- Even, front-on lighting (avoid strong shadows on the grid).
- Hold paper flat; fill most of the camera view.
- Grant **Camera** access if macOS prompts.

## Preset keys (match printed figure)

| Key | Printed plot | Expected shape | y-axis range | Ground truth |
|-----|--------------|----------------|--------------|--------------|
| `1` | line1 | LINE | 0 → 11 | y = 10x + 1 |
| `2` | line2 | LINE | 0 → 6.5 | y = 5x + 1.5 |
| `3` | line3 | LINE | 0 → 5 | y = 2x + 3 |
| `4` | sinusoid1 | SINUSOID | −2 → 2 | y = 2 sin(5x) |
| `5` | sinusoid2 | SINUSOID | −3 → 3 | y = 3 sin(9x − 4) |
| `6` | sinusoid3 | SINUSOID | −1.5 → 2.5 | y = 2.3 sin(3x + 7) |
| `7` | quadratic1 | QUADRATIC | 3 → 6 | y = x² + 2x + 3 |
| `8` | quadratic2 | QUADRATIC | 12 → 26 | y = 5x² + 8x + 13 |

## Per-trial procedure (repeat for each printed page)

1. Press the **preset key** (`1`–`8`) for the sheet you are holding.
2. Press **`m`**, then click **four plot corners**: top-left → top-right → bottom-right → bottom-left (on the **plot border**, not the paper edge).
3. Check **Warped plot** window:
   - Yellow dots follow the blue curve.
   - Green curve matches the stroke.
   - Grid looks rectangular (not heavily skewed).
4. Check **Shape** and equation on the main window:
   - **Shape** must match the “Expected shape” column.
   - Equation should be close to ground truth (see static baseline table).
   - For sinusoids/quadratics: orange dashed line = rejected linear fit (expected).
5. Press **`l`** to **log** this trial (`--validate` required).
6. Optional: press **`s`** for an extra snapshot in `captures/`.

## Recommended test matrix (minimum)

For each of the **8** printed plots:

| Condition | Trials |
|-----------|--------|
| Centered, good light | 3 |
| Tilted ~15° | 2 |
| Slightly nearer / farther | 2 |

**Total:** 8 × 7 = **56 trials** (adjust as needed).

Log each trial with **`l`**. Logs append to `validation/results/camera_log.jsonl`. Images save to `validation/results/camera_captures/`.

## What to compare

| Metric | Pass guideline (initial) |
|--------|-------------------------|
| Shape classification | Matches expected (LINE / SINUSOID / QUADRATIC) |
| Line slope \(m\) | Within ~5% of static JPEG error (see VALIDATION_RESULTS.md) |
| Line intercept \(b\) | Within ~0.05 axis units |
| Quadratic coeffs | Within ~2% of static baseline |
| Sinusoid \(A\), \(\omega\) | Within ~20% (camera adds more error than JPEG) |
| RMSE | Lower than linear RMSE when shape is not LINE |

## After the session

```bash
# View log (last 5 trials)
tail -5 validation/results/camera_log.jsonl

# Summarize (optional — run from Linear/)
.venv/bin/python scripts/summarize_camera_log.py
```

Compare `camera_log.jsonl` to `validation/results/validation_results.json` (digital baseline).

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No yellow stroke | More light; recalibrate corners; darker print |
| Wrong shape | Wrong preset key; y-axis range wrong; recalibrate |
| Skewed warp | Click corners exactly on plot frame |
| “Start with --validate” | Relaunch with `--validate` flag |
| Flickering shape label | Hold steady; press Space to pause and read |

## Files

| File | Role |
|------|------|
| `validation/ground_truth.json` | Reference parameters |
| `validation/results/VALIDATION_RESULTS.md` | Digital JPEG baseline |
| `validation/results/camera_log.jsonl` | Your live trials |
| `validation/results/camera_captures/` | Logged frame + warp images |
