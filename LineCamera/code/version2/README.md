# line_camera version 2.4.0

Camera measurement of a plotted line, quadratic, or sinusoid. Version 2 adds hierarchical graph-paper detection, live-view recording, and an I–V (Ohm’s law) teaching mode.

This folder is the application only. It is ongoing work from peer review of the SoftwareX manuscript. It is not the version-1 validation freeze, and its trials are not part of the 295-trial accuracy tables.

`line_camera_v2.py` imports `line_camera.py` from the same directory. Keep both files together.

**License:** MIT. Copyright (c) 2026 Phillip M. Wu.

## Setup

Python 3.12.6 was used for the revision checks.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python line_camera_v2.py
```

On Windows:

```bash
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python line_camera_v2.py
```

Grant camera permission to the terminal or to Python.

## Keys

| Key | Action |
|-----|--------|
| `a` | Automatic frame: sheet, then the axes box with tick marks |
| `m` | Manual corners: top-left, top-right, bottom-right, bottom-left |
| `u` | Unlock a locked automatic box |
| `o` | I–V / Ohm mode. Press again to leave. Presets 1–8 also leave it |
| `1`–`8` | Validation-plot axis presets. These load axis limits only |
| `r` | Record the live view as MP4 (`captures/`) |
| `s` | Save the current frame |
| `l` | Log a trial when the program was started with `--validate` |
| space | Pause |
| `q` | Quit |

While I–V mode is on, the axes stay fixed: x is current from 0 to 1 A, y is voltage from 0 to 10 V. When the line model wins, the slope is the resistance in ohms. A line \(V = 10I\) reads about 10 ohm. Resistance is not shown for a quadratic or a sinusoid.

## Recording and logs

Recordings and saved frames go in `captures/`. With `--validate`, trials are appended to `validation/results/camera_log.jsonl` under this folder. That file is created on the first logged trial. It is separate from the 295-trial log used in the SoftwareX manuscript.
