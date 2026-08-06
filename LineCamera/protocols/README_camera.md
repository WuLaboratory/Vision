# Live shape detector (camera)

Traces ink on a calibrated plot, compares **line**, **quadratic**, and **sinusoid** models, and shows an **honest readout**.

**Camera validation:** see [`validation/CAMERA_VALIDATION.md`](validation/CAMERA_VALIDATION.md).

## Setup

```bash
cd /Users/p409wu/Desktop/WuLaboratory/Cursor/Linear
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Grant **Camera** access in **System Settings → Privacy & Security → Camera**.

## Run

```bash
.venv/bin/python line_camera.py --validate
```

Use `--validate` when logging live trials (press **`l`**).

## Preset keys (printed plots)

| Key | Plot | Expected shape |
|-----|------|----------------|
| `1`–`3` | line1–line3 | LINE |
| `4`–`6` | sinusoid1–3 | SINUSOID |
| `7`–`8` | quadratic1–2 | QUADRATIC |

## Usage

1. Hold plotted paper in view.
2. Press **`m`**, click **four plot corners**: top-left → top-right → bottom-right → bottom-left.
3. Press **`1`–`8`** for the printed plot you are holding.

## Visual feedback

| Color | Meaning |
|-------|---------|
| **Yellow dots** | Traced stroke (sampled ink pixels) |
| **Green curve** | Best-fit model (line, parabola, or sinusoid) |
| **Orange dashed** | Linear reference — shown only when **not** classified as LINE |

**Warped plot** legend explains the overlay.

## On-screen readout

- **Shape:** `LINE`, `SINUSOID`, or `QUADRATIC`
- **Best fit** equation with **RMSE** and **R²**
- For non-linear shapes: **“Linear model: NOT best fit”** and **“Do not use: y = …”**
- **Arc length** along the traced stroke (axis units)
- For **LINE** only: segment length between stroke extent on the fitted line

## Keys

| Key | Action |
|-----|--------|
| `m` | Manual corner calibration |
| `a` | Auto-detect plot outline |
| `1`–`8` | Plot presets (lines, sinusoids, quadratics) |
| `l` | Log trial (`--validate` mode) |
| `[` `]` | Decrease / increase y_max |
| `,` `.` | Decrease / increase x_max |
| Space | Pause / resume |
| `s` | Save frame to `captures/` |
| `q` | Quit |

## Notes

- Sinusoid fit searches frequency over the observed x-range; noisy video may flicker between models — hold the paper steady.
- Grid lines can add ink pixels; calibrate corners on the **plot border** only.
- Length in **axis units** (plot coordinates), not centimeters unless your axes are drawn that way.

## Troubleshooting

| Symptom | What to do |
|---------|------------|
| No readout | Darker pen, recalibrate corners, check **Warped plot** for yellow stroke dots |
| Sine labeled LINE | Show more of the wave (≥ ~½ period); improve lighting |
| Wrong shape | Adjust axis preset `1`/`2`/`3` so x,y ranges match the paper |
