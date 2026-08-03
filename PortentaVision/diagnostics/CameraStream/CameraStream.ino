/*
  Portenta H7 + Vision Shield camera stream over USB serial.

  SENSOR_HM0360: 1 = Rev.2 (HM0360), 0 = Rev.1 (HM01B0)
*/

#include "camera.h"

#ifndef SENSOR_HM0360
#define SENSOR_HM0360 1
#endif

#if SENSOR_HM0360
  #include "hm0360.h"
  HM0360 himax;
#else
  #include "himax.h"
  HM01B0 himax;
#endif

Camera cam(himax);
FrameBuffer fb(320, 240, 2);

static const uint8_t START_SEQUENCE[4] = {0xfa, 0xce, 0xfe, 0xed};
static const uint8_t STOP_SEQUENCE[4] = {0xda, 0xbb, 0xad, 0x00};
static const uint8_t FRAME_REQUEST = 0x01;

bool camera_ok = false;
int frame_w = 320;
int frame_h = 240;

uint8_t readReg16(uint8_t dev, uint16_t reg) {
  uint8_t buf[2] = {(uint8_t)(reg >> 8), (uint8_t)(reg & 0xFF)};
  CameraWire.beginTransmission(dev);
  CameraWire.write(buf, 2);
  CameraWire.endTransmission(false);
  CameraWire.requestFrom(dev, (uint8_t)1);
  return CameraWire.available() ? CameraWire.read() : 0xFF;
}

bool initCamera() {
  himax.debug(Serial);
  cam.debug(Serial);

  // Try QVGA then QQVGA
  const int32_t resolutions[] = {CAMERA_R320x240, CAMERA_R160x120};
  const int heights[] = {240, 120};
  const int widths[] = {320, 160};

  for (int r = 0; r < 2; r++) {
    for (int attempt = 1; attempt <= 3; attempt++) {
      Serial.print("begin res=");
      Serial.print(resolutions[r]);
      Serial.print(" attempt=");
      Serial.println(attempt);
      Serial.flush();
      if (cam.begin(resolutions[r], CAMERA_GRAYSCALE, 30)) {
        frame_w = widths[r];
        frame_h = heights[r];
        return true;
      }
      pinMode(PC_13, OUTPUT);
      digitalWrite(PC_13, LOW);
      delay(20);
      digitalWrite(PC_13, HIGH);
      delay(150);
    }
  }
  return false;
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(LEDR, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);
  digitalWrite(LEDR, HIGH);

  Serial.begin(115200);
  while (!Serial && millis() < 5000) {}
  delay(400);
  Serial.println();
  Serial.println("PortentaVision CameraStream");
#if SENSOR_HM0360
  Serial.println("sensor=HM0360");
#else
  Serial.println("sensor=HM01B0");
#endif
  Serial.flush();

  camera_ok = initCamera();

  // Diagnostic: Himax MODEL_ID should be 0x01B0 or 0x0360 when shield is seated.
  uint8_t idh = readReg16(0x24, 0x0000);
  uint8_t idl = readReg16(0x24, 0x0001);
  Serial.print("MODEL_ID=0x");
  Serial.print(idh, HEX);
  Serial.println(idl, HEX);

  if (!camera_ok) {
    Serial.println("cam.begin FAILED");
    Serial.println("HINT: reseat Vision Shield firmly on Portenta headers, then power-cycle USB");
    digitalWrite(LEDR, LOW);
  } else {
    Serial.print("cam.begin OK ");
    Serial.print(frame_w);
    Serial.print("x");
    Serial.println(frame_h);
  }
  Serial.println("READY");
  Serial.flush();
}

void sendFrame() {
  if (!camera_ok) {
    Serial.println("ERR camera_not_ready");
    return;
  }
  if (cam.grabFrame(fb, 3000) != 0) {
    Serial.println("ERR grabFrame");
    return;
  }

  uint8_t* buffer = fb.getBuffer();
  size_t bufferSize = cam.frameSize();
  uint16_t w = (uint16_t)frame_w;
  uint16_t h = (uint16_t)frame_h;
  uint8_t bpp = 1;

  digitalWrite(LED_BUILTIN, LOW);
  Serial.write(START_SEQUENCE, sizeof(START_SEQUENCE));
  Serial.write((uint8_t*)&w, sizeof(w));
  Serial.write((uint8_t*)&h, sizeof(h));
  Serial.write(&bpp, 1);
  Serial.write(buffer, bufferSize);
  Serial.write(STOP_SEQUENCE, sizeof(STOP_SEQUENCE));
  Serial.flush();
  digitalWrite(LED_BUILTIN, HIGH);
}

void loop() {
  if (Serial.available() > 0) {
    int b = Serial.read();
    if (b == FRAME_REQUEST) {
      sendFrame();
    }
  }
}
