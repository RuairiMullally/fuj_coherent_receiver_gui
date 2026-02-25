/*
 * fim24725_mcu.ino
 *
 * Stateless MCU firmware for FIM24725 coherent receiver control.
 * Runs on Arduino Uno R3 connected via USB serial (/dev/arduino on host).
 *
 * Pin assignments:
 *   D2  - SD (Shutdown):  HIGH = module disabled, LOW = module enabled
 *   D3  - MC/AGC (Mode):  HIGH = AGC,             LOW = MGC
 *   A0  - PI_XI  (Peak Indicator X-I)
 *   A1  - PI_XQ  (Peak Indicator X-Q)
 *   A2  - PI_YI  (Peak Indicator Y-I)
 *   A3  - PI_YQ  (Peak Indicator Y-Q)
 *   A4  - MPD    (Monitor Photodiode)
 *
 * Protocol (115200 baud, ASCII, \n-terminated):
 *   Host -> Arduino:
 *     PING          -> PONG
 *     SD:1          -> SD:1   (disable module, SD HIGH)
 *     SD:0          -> SD:0   (enable module, SD LOW)
 *     MODE:AGC      -> MODE:AGC  (MC/AGC HIGH)
 *     MODE:MGC      -> MODE:MGC  (MC/AGC LOW)
 *     <unknown>     -> ERR:UNKNOWN:<cmd>
 *
 *   Arduino -> Host (errors):
 *     ERR:PIN_FAULT:SD    -- SD digitalRead mismatch after write
 *     ERR:PIN_FAULT:MODE  -- MC/AGC digitalRead mismatch after write
 *
 *   Arduino -> Host (telemetry, every 500ms, unsolicited):
 *     INIT:SD=1,MODE=AGC   -- emitted once on startup
 *     TELE:PI_XI=x.xxx,PI_XQ=x.xxx,PI_YI=x.xxx,PI_YQ=x.xxx,MPD=x.xxx
 *
 * ADC: default AREF = VCC = 5V.  voltage = (analogRead(pin) / 1024.0) * 5.0
 * PI and MPD signals are 0-2V; they map to 0-40.9% of ADC range (~4.9 mV/count).
 */

// ----- Pin definitions -----
static const int PIN_SD   = 2;
static const int PIN_MODE = 3;

static const int ADC_PI_XI = A0;
static const int ADC_PI_XQ = A1;
static const int ADC_PI_YI = A2;
static const int ADC_PI_YQ = A3;
static const int ADC_MPD   = A4;

// ----- Telemetry interval -----
static const unsigned long TELE_INTERVAL_MS = 500UL;

// ----- Serial input buffer -----
static String inputBuffer = "";

// ----- Timing -----
static unsigned long lastTelemetry = 0;

// ----- Connection state -----
// Telemetry is suppressed until the host sends HELLO, preventing unsolicited
// output from filling the serial buffer before the connection is established.
static bool tele_enabled = false;


// ============================================================
// Helpers
// ============================================================

static float adcToVolts(int raw) {
    return (raw / 1024.0f) * 5.0f;
}

static void sendTelemetry() {
    float pi_xi = adcToVolts(analogRead(ADC_PI_XI));
    float pi_xq = adcToVolts(analogRead(ADC_PI_XQ));
    float pi_yi = adcToVolts(analogRead(ADC_PI_YI));
    float pi_yq = adcToVolts(analogRead(ADC_PI_YQ));
    float mpd   = adcToVolts(analogRead(ADC_MPD));

    Serial.print("TELE:");
    Serial.print("PI_XI="); Serial.print(pi_xi, 3);
    Serial.print(",PI_XQ="); Serial.print(pi_xq, 3);
    Serial.print(",PI_YI="); Serial.print(pi_yi, 3);
    Serial.print(",PI_YQ="); Serial.print(pi_yq, 3);
    Serial.print(",MPD=");   Serial.println(mpd, 3);
}


// ============================================================
// Command processor
// ============================================================

static void processCommand(const String& cmd) {
    if (cmd == "PING") {
        Serial.println("PONG");

    } else if (cmd == "SD:1") {
        digitalWrite(PIN_SD, HIGH);
        if (digitalRead(PIN_SD) != HIGH) {
            Serial.println("ERR:PIN_FAULT:SD");
        } else {
            Serial.println("SD:1");
        }

    } else if (cmd == "SD:0") {
        digitalWrite(PIN_SD, LOW);
        if (digitalRead(PIN_SD) != LOW) {
            Serial.println("ERR:PIN_FAULT:SD");
        } else {
            Serial.println("SD:0");
        }

    } else if (cmd == "MODE:AGC") {
        digitalWrite(PIN_MODE, HIGH);
        if (digitalRead(PIN_MODE) != HIGH) {
            Serial.println("ERR:PIN_FAULT:MODE");
        } else {
            Serial.println("MODE:AGC");
        }

    } else if (cmd == "MODE:MGC") {
        digitalWrite(PIN_MODE, LOW);
        if (digitalRead(PIN_MODE) != LOW) {
            Serial.println("ERR:PIN_FAULT:MODE");
        } else {
            Serial.println("MODE:MGC");
        }

    } else if (cmd == "HELLO") {
        // Re-assert safe state, respond with current state, then enable telemetry
        digitalWrite(PIN_SD,   HIGH);
        digitalWrite(PIN_MODE, HIGH);
        Serial.println("INIT:SD=1,MODE=AGC");
        tele_enabled = true;

    } else {
        Serial.print("ERR:UNKNOWN:");
        Serial.println(cmd);
    }
}


// ============================================================
// Arduino lifecycle
// ============================================================

void setup() {
    Serial.begin(115200);

    // Set outputs before enabling — avoids glitch on FIM24725 control pins
    pinMode(PIN_SD,   OUTPUT);
    pinMode(PIN_MODE, OUTPUT);

    // Safe initial state: module disabled (SD HIGH), AGC mode (MC/AGC HIGH)
    digitalWrite(PIN_SD,   HIGH);
    digitalWrite(PIN_MODE, HIGH);
    // Host confirms connection via HELLO command; no autonomous INIT: broadcast needed
}

void loop() {
    // --- Non-blocking serial read ---
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n') {
            inputBuffer.trim();
            if (inputBuffer.length() > 0) {
                processCommand(inputBuffer);
            }
            inputBuffer = "";
        } else if (c != '\r') {
            inputBuffer += c;
        }
    }

    // --- Periodic telemetry (only after HELLO handshake) ---
    unsigned long now = millis();
    if (tele_enabled && (now - lastTelemetry >= TELE_INTERVAL_MS)) {
        lastTelemetry = now;
        sendTelemetry();
    }
}
