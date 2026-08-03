void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  while (!Serial) {
    digitalWrite(LED_BUILTIN, LOW);
    delay(100);
    digitalWrite(LED_BUILTIN, HIGH);
    delay(100);
  }
  Serial.println("HELLO_FROM_PORTENTA");
}

void loop() {
  Serial.println("ping");
  digitalWrite(LED_BUILTIN, LOW);
  delay(250);
  digitalWrite(LED_BUILTIN, HIGH);
  delay(250);
  if (Serial.available()) {
    int b = Serial.read();
    Serial.print("echo=");
    Serial.println(b);
  }
}
