# Diagnostics

Optional sketches for bring-up and troubleshooting.  
For normal camera use, flash `../CameraCaptureRawBytesLive` instead.

| Sketch | Purpose |
|---|---|
| `SerialProbe` | Confirm USB serial CDC works (prints `ping`) |
| `I2CScan` | Camera-bus / begin diagnostics (may be sketch-specific) |
| `CameraStream` | Experimental framed protocol (not used by the main host) |

Upload with the same FQBN as the main firmware:

```bash
arduino-cli compile --fqbn arduino:mbed_portenta:envie_m7 SerialProbe
arduino-cli upload -p PORT --fqbn arduino:mbed_portenta:envie_m7 SerialProbe
```
