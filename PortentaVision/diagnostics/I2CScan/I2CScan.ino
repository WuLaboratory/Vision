#include "camera.h"
#include "hm0360.h"

uint8_t readReg16(uint8_t dev, uint16_t reg) {
  uint8_t buf[2] = {(uint8_t)(reg >> 8), (uint8_t)(reg & 0xFF)};
  CameraWire.beginTransmission(dev);
  CameraWire.write(buf, 2);
  CameraWire.endTransmission(false);
  CameraWire.requestFrom(dev, (uint8_t)1);
  return CameraWire.available() ? CameraWire.read() : 0xFF;
}

void scanBus() {
  int found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    CameraWire.beginTransmission(addr);
    if (CameraWire.endTransmission() == 0) {
      Serial.print("  found 0x");
      Serial.println(addr, HEX);
      found++;
    }
  }
  if (!found) Serial.println("  (none)");
}

HM0360 himax;
Camera cam(himax);
FrameBuffer fb(320, 240, 2);

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);

  Serial.begin(115200);
  while (!Serial && millis() < 5000) {}
  delay(300);
  Serial.println("Vision Shield Rev.2 check (HM0360)");
  cam.debug(Serial);

  bool ok = cam.begin(CAMERA_R320x240, CAMERA_GRAYSCALE, 30);
  Serial.print("begin=");
  Serial.println(ok ? "OK" : "FAIL");

  Serial.println("I2C scan:");
  scanBus();

  uint8_t idh = readReg16(0x24, 0x0000);
  uint8_t idl = readReg16(0x24, 0x0001);
  Serial.print("MODEL_ID=0x");
  Serial.print(idh, HEX);
  Serial.println(idl, HEX);

  if (ok) {
    Serial.println("Camera OK — green LED should NOT blink forever");
  } else {
    Serial.println("Camera FAIL — if green LED blinked forever in RawBytes, same root cause");
  }
  Serial.println("DONE");
}

void loop() {
  // Slow heartbeat if init failed; off if OK
  static unsigned long t0 = 0;
  if (!cam && millis() - t0 > 1000) {
    t0 = millis();
  }
}
