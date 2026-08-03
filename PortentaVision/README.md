# PortentaVision

USB serial capture and live preview for **Arduino Portenta H7 + Vision Shield** with the **Himax HM-01B0** camera.

Validated on macOS with:

- Portenta H7 (USB CDC shows as `Envie M7`)
- Vision Shield camera module marked **HM-01B0**
- Firmware: `CameraCaptureRawBytesLive`
- Host: `capture_portenta.py` (~15–16 fps QVGA grayscale over USB)

---

## Repository layout

```
PortentaVision/
├── README.md
├── requirements.txt
├── capture_portenta.py              # host: live preview / save PNG
├── CameraCaptureRawBytesLive/       # firmware (upload this)
│   └── CameraCaptureRawBytesLive.ino
├── captures/                        # saved frames (gitignored)
└── diagnostics/                     # optional USB / I2C helpers
```

---

## Hardware

| Item | Notes |
|---|---|
| Arduino Portenta H7 | Use the board USB-C data port |
| Portenta Vision Shield | Seat firmly on **both** high-density connectors |
| Camera module | Confirm marking **HM-01B0** (not HM0360) |
| USB cable | Must support data (not charge-only) |

### Camera FPC latch

1. Unplug USB.
2. Find the thin flat ribbon (FPC) into the ZIF connector on the shield.
3. Latch should be fully closed / flush; ribbon inserted straight to the stop.
4. Gentle tug should not pull the ribbon out.
5. Reseat the Vision Shield, then reconnect USB.

---

## Software prerequisites

### 1. Arduino tooling

Install either:

- **Arduino IDE 2.x**, or
- **arduino-cli** (used in the commands below)

Install the board core:

**Arduino IDE:**  
Tools → Board → Boards Manager → search **Portenta** → install **Arduino Mbed OS Portenta Boards**

**arduino-cli:**

```bash
arduino-cli core update-index
arduino-cli core install arduino:mbed_portenta
```

### 2. Python 3.10+ environment

```bash
cd PortentaVision
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Flash the camera firmware

### Option A — Arduino IDE

1. Open `CameraCaptureRawBytesLive/CameraCaptureRawBytesLive.ino`
2. Tools → Board → **Arduino Portenta H7 (M7 core)**
3. Tools → Port → select the Portenta (`Envie M7` / `cu.usbmodem…`)
4. Click **Upload**
5. Close **Serial Monitor** after upload (it locks the port)

**LED check**

- Green LED blinks **5 times** then stops → camera init OK  
- Green LED blinks **continuously** → `cam.begin()` failed (seating / FPC / wrong sensor)

### Option B — arduino-cli

```bash
cd PortentaVision

# list ports
arduino-cli board list

arduino-cli compile --fqbn arduino:mbed_portenta:envie_m7 CameraCaptureRawBytesLive
arduino-cli upload -p /dev/cu.usbmodem2301 --fqbn arduino:mbed_portenta:envie_m7 CameraCaptureRawBytesLive
```

Replace `/dev/cu.usbmodem2301` with the port from `board list` (Windows: `COMx`).

### Using the stock Arduino example instead

File → Examples → Camera → **CameraCaptureRawBytes**

For HM-01B0, uncomment:

```cpp
#include "himax.h"
HM01B0 himax;
Camera cam(himax);
```

and comment out the `hm0360.h` / `HM0360` block.

Then run the host with `--stock-sketch` (see below). The stock example gates frames at ~2 s intervals.

---

## Run the host

Always **close Serial Monitor** (and any other app using the serial port) first.

### Probe ports

```bash
python capture_portenta.py --probe
```

### Live preview

```bash
python capture_portenta.py --live
```

Keys:

- `q` — quit  
- `s` — save PNG into `captures/`

If the image looks rotated:

```bash
python capture_portenta.py --live --rotate 90
# also: --rotate 180|270   and/or   --flip h|v|hv
```

### Save one or more frames

```bash
python capture_portenta.py --frames 1 --out captures/shot.png
python capture_portenta.py --frames 10 --out captures/burst.png
```

### Stock IDE sketch mode

```bash
python capture_portenta.py --live --stock-sketch
```

---

## Wire protocol

Compatible with Arduino’s CameraCaptureRawBytes example:

| Direction | Payload |
|---|---|
| Host → device | 1 byte: `0x01` |
| Device → host | `320 × 240` grayscale bytes (`76800`), little-endian row-major, no framing |

USB CDC baud in firmware is `115200` (CDC ignores baud on many hosts; keep host and sketch consistent).

---

## Troubleshooting

| Symptom | What to try |
|---|---|
| Port not found | Unplug/replug USB; try another cable/port; check System Information / Device Manager |
| `Could not open …` | Close Arduino Serial Monitor / other serial apps |
| Green LED blinks forever after upload | Reseat Vision Shield; check FPC latch; confirm module is HM-01B0 |
| Timeout waiting for bytes | Firmware not running / wrong sketch / port busy / camera init failed |
| Nearly constant / black image | Remove lens cover; check lighting; confirm init succeeded (5 blinks) |
| Wrong sensor selected | HM0360 firmware on an HM-01B0 module (or reverse) will fail init |

Optional diagnostics sketches are under `diagnostics/` (`SerialProbe`, `I2CScan`).

---

## Notes for laboratory sharing

- This package targets **HM-01B0**. Vision Shield units with **HM0360** need the corresponding Arduino camera driver (`hm0360.h`) instead of `himax.h`.
- Captured images under `captures/` are gitignored by default.
- Typical live rate on USB serial QVGA grayscale is on the order of **10–16 fps** (host/USB dependent), not the full 30 fps camera setting.

---

## License

Add your laboratory / organization license before publishing the GitHub repository.
