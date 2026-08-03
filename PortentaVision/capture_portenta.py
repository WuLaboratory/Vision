#!/usr/bin/env python3
"""
Host-side capture / live preview for Portenta H7 + Vision Shield (HM-01B0).

Talks the CameraCaptureRawBytes wire protocol over USB serial:
  host sends 0x01  ->  device returns 320x240 grayscale bytes (76800).

Examples:
  python capture_portenta.py --probe
  python capture_portenta.py --frames 1 --out captures/shot.png
  python capture_portenta.py --live
  python capture_portenta.py --live --rotate 90
  python capture_portenta.py --live --stock-sketch   # stock Arduino example
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import serial
from serial.tools import list_ports

FRAME_REQUEST = bytes([1])
DEFAULT_W = 320
DEFAULT_H = 240


def find_portenta_port(preferred: str | None = None) -> str:
    if preferred:
        return preferred
    for p in list_ports.comports():
        desc = f"{p.description} {p.manufacturer or ''} {p.product or ''}".lower()
        if "envie" in desc or "portenta" in desc or "arduino" in desc:
            return p.device
        if "usbmodem" in p.device:
            return p.device
    raise SystemExit(
        "No Portenta serial port found. Plug in USB and check /dev/cu.usbmodem* "
        "(macOS) or the equivalent COM port (Windows)."
    )


def read_exact(ser: serial.Serial, n: int, timeout_s: float) -> bytes:
    deadline = time.time() + timeout_s
    buf = bytearray()
    while len(buf) < n:
        if time.time() > deadline:
            raise TimeoutError(f"Timed out waiting for {n} bytes (got {len(buf)})")
        chunk = ser.read(n - len(buf))
        if chunk:
            buf.extend(chunk)
    return bytes(buf)


def capture_rawbytes(
    ser: serial.Serial,
    width: int = DEFAULT_W,
    height: int = DEFAULT_H,
    *,
    min_interval_s: float = 0.0,
    read_timeout_s: float = 8.0,
) -> np.ndarray:
    """Request one grayscale frame using the RawBytes protocol."""
    if min_interval_s > 0:
        time.sleep(min_interval_s)
    nbytes = width * height
    ser.reset_input_buffer()
    ser.write(FRAME_REQUEST)
    ser.flush()
    payload = read_exact(ser, nbytes, timeout_s=read_timeout_s)
    return np.frombuffer(payload, dtype=np.uint8).reshape((height, width))


def apply_orientation(img: np.ndarray, rotate: int, flip: str | None) -> np.ndarray:
    if rotate == 90:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    elif rotate == 180:
        img = cv2.rotate(img, cv2.ROTATE_180)
    elif rotate == 270:
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if flip == "h":
        img = cv2.flip(img, 1)
    elif flip == "v":
        img = cv2.flip(img, 0)
    elif flip == "hv":
        img = cv2.flip(img, -1)
    return img


def annotate(img: np.ndarray, fps: float, n: int) -> np.ndarray:
    out = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    cv2.putText(
        out,
        f"Portenta HM01B0  frame={n}  {fps:.1f} fps  [q]=quit  [s]=save",
        (8, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (0, 255, 0),
        1,
        cv2.LINE_AA,
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--port", default=None, help="Serial port (auto-detect if omitted)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--width", type=int, default=DEFAULT_W)
    parser.add_argument("--height", type=int, default=DEFAULT_H)
    parser.add_argument(
        "--stock-sketch",
        action="store_true",
        help="Add ~2.05 s spacing required by stock CameraCaptureRawBytes.ino",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Continuous OpenCV preview (q=quit, s=save)",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=1,
        help="Number of frames to save when not using --live",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "captures" / "frame.png",
    )
    parser.add_argument("--rotate", type=int, choices=(0, 90, 180, 270), default=0)
    parser.add_argument("--flip", choices=("h", "v", "hv"), default=None)
    parser.add_argument("--probe", action="store_true", help="List serial ports and exit")
    args = parser.parse_args()

    if args.probe:
        for p in list_ports.comports():
            print(f"{p.device}\t{p.description}\t{p.manufacturer}")
        return 0

    port = find_portenta_port(args.port)
    min_interval = 2.05 if args.stock_sketch else 0.0
    print(f"Opening {port} @ {args.baud}")
    if args.stock_sketch:
        print("Mode: stock CameraCaptureRawBytes (~0.5 fps)")
    else:
        print("Mode: CameraCaptureRawBytesLive (request-driven)")

    try:
        ser = serial.Serial(port, args.baud, timeout=0.2)
    except serial.SerialException as e:
        print(f"Could not open {port}: {e}", file=sys.stderr)
        print(
            "Close Arduino Serial Monitor / other apps using the port.",
            file=sys.stderr,
        )
        return 2

    time.sleep(2.0)  # allow USB CDC / sketch reset after port open
    ser.reset_input_buffer()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    last = None
    n = 0
    fps = 0.0
    t_prev = time.time()
    try:
        if args.live:
            print("Live preview started. Keys: q=quit, s=save PNG")
            while True:
                try:
                    img = capture_rawbytes(
                        ser,
                        args.width,
                        args.height,
                        min_interval_s=min_interval,
                    )
                except TimeoutError as e:
                    print(f"timeout: {e}", file=sys.stderr)
                    continue
                n += 1
                now = time.time()
                dt = now - t_prev
                t_prev = now
                if dt > 0:
                    instant = 1.0 / dt
                    fps = 0.8 * fps + 0.2 * instant if fps > 0 else instant
                img = apply_orientation(img, args.rotate, args.flip)
                last = img
                cv2.imshow("Portenta Vision Shield", annotate(img, fps, n))
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("s"):
                    path = args.out.with_name(f"{args.out.stem}_{n:04d}{args.out.suffix}")
                    cv2.imwrite(str(path), img)
                    print(f"Saved {path}")
        else:
            t0 = time.time()
            for i in range(args.frames):
                img = capture_rawbytes(
                    ser,
                    args.width,
                    args.height,
                    min_interval_s=min_interval,
                )
                img = apply_orientation(img, args.rotate, args.flip)
                last = img
                out = (
                    args.out
                    if args.frames == 1
                    else args.out.with_name(f"{args.out.stem}_{i:03d}{args.out.suffix}")
                )
                cv2.imwrite(str(out), img)
                print(
                    f"Saved {out}  shape={img.shape}  "
                    f"min={int(img.min())} max={int(img.max())} "
                    f"mean={float(img.mean()):.1f} std={float(img.std()):.1f}"
                )
            elapsed = time.time() - t0
            if args.frames > 1 and elapsed > 0:
                print(f"Average {args.frames / elapsed:.2f} fps over {args.frames} frames")
    finally:
        ser.close()
        if args.live:
            cv2.destroyAllWindows()

    if last is None:
        print("No frame captured", file=sys.stderr)
        return 1
    if float(np.asarray(last).std()) < 1.0:
        print(
            "WARNING: nearly constant image — check lens cover / lighting / init.",
            file=sys.stderr,
        )
        return 3
    print("Camera preview OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
