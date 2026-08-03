/*
  CameraCaptureRawBytesLive
  -------------------------
  Arduino firmware for Portenta H7 + Vision Shield with Himax HM-01B0.

  Wire protocol (compatible with Arduino "CameraCaptureRawBytes"):
    1. Host sends one byte: 0x01
    2. Device replies with QVGA grayscale pixels: 320 * 240 = 76800 bytes
       (no header / trailer)

  Compared with the stock Arduino example:
    - Uses HM01B0 (himax.h) — match the marking on your camera module
    - Request-driven (no 2-second gate) for continuous live preview

  LED behavior:
    - Blinks forever  -> cam.begin() failed (check seating / FPC / sensor)
    - Blinks 5 times  -> camera initialized successfully
    - Blinks ~20 times during run -> grabFrame() failed once
*/

#include "camera.h"
#include "himax.h"

HM01B0 himax;
Camera cam(himax);
#define IMAGE_MODE CAMERA_GRAYSCALE

FrameBuffer fb(320, 240, 2);

void blinkLED(uint32_t count = 0xFFFFFFFF) {
  pinMode(LED_BUILTIN, OUTPUT);
  while (count--) {
    digitalWrite(LED_BUILTIN, LOW);   // Portenta LEDs are active-LOW
    delay(50);
    digitalWrite(LED_BUILTIN, HIGH);
    delay(50);
  }
}

void setup() {
  Serial.begin(115200);

  if (!cam.begin(CAMERA_R320x240, IMAGE_MODE, 30)) {
    blinkLED();  // never returns
  }

  blinkLED(5);
}

void loop() {
  if (!Serial) {
    return;
  }

  // Official RawBytes sync byte
  if (Serial.read() != 1) {
    return;
  }

  if (cam.grabFrame(fb, 3000) == 0) {
    Serial.write(fb.getBuffer(), cam.frameSize());
  } else {
    blinkLED(20);
  }
}
