#include <Arduino.h>
#include <SPI.h>
#include <RadioLib.h>
#include <RF24.h>
#include <esp_ota_ops.h>
#include <mbedtls/sha256.h>

constexpr char VERSION[] = "0.3.0";
#ifdef POCKET_ZERO_ADAPTER
constexpr char PROFILE[] = "zero-top-adapter";
constexpr int CC_CS = 6, CC_IRQ = 7;
constexpr int NRF_CS = 5, NRF_CE = 4;
constexpr int LORA_CS = 8, LORA_IRQ = 10, LORA_RST = 9;
constexpr int SPI_SCK = 11, SPI_MOSI = 12, SPI_MISO = 13;
constexpr int CHIP_SELECTS[] = {CC_CS, NRF_CS, LORA_CS};
#else
constexpr char PROFILE[] = "joseph-adv";
constexpr int SPI_SCK = 40, SPI_MOSI = 14, SPI_MISO = 39;
constexpr int CC_CS = 15, CC_IRQ = 13;
constexpr int NRF_CS = 9, NRF_CE = 8;
constexpr int LORA_CS = 5, LORA_IRQ = 4, LORA_RST = 3;
constexpr int CHIP_SELECTS[] = {CC_CS, NRF_CS, LORA_CS, 12, 1};
#endif
constexpr uint8_t ADDRESS[] = {'E', 'D', 'K', '0', '1'};
constexpr uint8_t MAGIC[] = {'E', 'D', 'K', 1};
constexpr unsigned PACKET = 29;
constexpr unsigned CHUNK = 384;
constexpr bool valid(char ch) { return ch >= 32 && ch <= 126; }

Module ccModule(CC_CS, CC_IRQ, RADIOLIB_NC, RADIOLIB_NC, SPI);
Module loraModule(LORA_CS, LORA_IRQ, LORA_RST, RADIOLIB_NC, SPI);
CC1101 cc(&ccModule);
SX1276 lora(&loraModule);
RF24 nrf(NRF_CE, NRF_CS);
esp_ota_handle_t ota = 0;
const esp_partition_t* target = nullptr;
mbedtls_sha256_context digest;
uint8_t expected[32];
size_t remaining;
uint32_t activity = 0;
uint32_t lastTx = 0;
bool hasSent = false;

void reply(const char* message) { Serial.println(message); }

int nibble(char ch) {
    if (ch >= '0' && ch <= '9') return ch - '0';
    if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
    return -1;
}

bool decode(const char* hex, uint8_t* data, size_t size) {
    if (strlen(hex) != 2 * size) return false;
    for (size_t i = 0; i < size; ++i) {
        int high = nibble(hex[2 * i]), low = nibble(hex[2 * i + 1]);
        if (high < 0 || low < 0) return false;
        data[i] = (high << 4) | low;
    }
    return true;
}

void stopUpdate() {
    if (ota) esp_ota_abort(ota);
    ota = 0;
    mbedtls_sha256_free(&digest);
}

void update(const char* action, const char* arg, const char* hash) {
    if (!strcmp(action, "BEGIN")) {
        char* end;
        unsigned long size = strtoul(arg, &end, 10);
        target = esp_ota_get_next_update_partition(nullptr);
        if (ota || !target || !size || *end || size > target->size ||
            !decode(hash, expected, sizeof(expected)) ||
            esp_ota_begin(target, size, &ota) != ESP_OK) {
            reply("ERR update preflight");
            return;
        }
        remaining = size;
        mbedtls_sha256_init(&digest);
        mbedtls_sha256_starts_ret(&digest, 0);
    } else if (!ota) {
        reply("ERR no staged update");
        return;
    } else if (!strcmp(action, "DATA")) {
        uint8_t data[CHUNK];
        size_t size = strlen(arg) / 2;
        if (!size || size > CHUNK || size > remaining || !decode(arg, data, size)
            || esp_ota_write(ota, data, size) != ESP_OK) {
            stopUpdate();
            reply("ERR update write");
            return;
        }
        mbedtls_sha256_update_ret(&digest, data, size);
        remaining -= size;
    } else if (!strcmp(action, "END")) {
        uint8_t actual[sizeof(expected)];
        mbedtls_sha256_finish_ret(&digest, actual);
        if (remaining || memcmp(actual, expected, sizeof(expected))) {
            stopUpdate();
            reply("ERR image checksum");
            return;
        }
        auto status = esp_ota_end(ota);
        ota = 0;
        mbedtls_sha256_free(&digest);
        if (status != ESP_OK || esp_ota_set_boot_partition(target) != ESP_OK) {
            reply("ERR image validation");
            return;
        }
        reply("OK reboot");
        Serial.flush();
        delay(250);
        ESP.restart();
        return;
    } else if (!strcmp(action, "CANCEL")) {
        stopUpdate();
    } else {
        reply("ERR update command");
        return;
    }
    activity = millis();
    reply("OK");
}

void scanCC(float center) {
    int values[17];
    for (int i = 0; i < 17; ++i) {
        if (cc.setFrequency(center + (i - 8) * 0.1f) != 0 || cc.startReceive() != 0) {
            cc.standby();
            reply("ERR CC1101 scan");
            return;
        }
        delay(5);
        const uint8_t reg = RADIOLIB_CC1101_REG_RSSI | RADIOLIB_CC1101_CMD_ACCESS_STATUS_REG;
        values[i] = roundf(static_cast<int8_t>(ccModule.SPIreadRegister(reg)) / 2.0f - 74);
        cc.standby();
    }
    Serial.print("OK");
    for (int value : values) Serial.printf(" %d", value);
    Serial.println();
}

void scanNRF() {
    uint8_t values[84] = {};
    // Each channel reports busy samples above the chip's RPD threshold.
    for (int pass = 0; pass < 8; ++pass) {
        for (int ch = 0; ch < 84; ++ch) {
            nrf.setChannel(ch);
            nrf.startListening();
            delayMicroseconds(190);
            values[ch] += nrf.isPVariant() ? nrf.testRPD() : nrf.testCarrier();
            nrf.stopListening();
        }
    }
    nrf.powerDown();
    Serial.print("OK");
    for (int value : values) Serial.printf(" %d", value);
    Serial.println();
}

int16_t sendCC(const uint8_t* packet) {
    // The expansion exposes GDO0 only; RadioLib's blocking TX waits on GDO2.
    int16_t status = cc.startTransmit(packet, PACKET);
    if (status) return status;
    constexpr uint8_t MARC = RADIOLIB_CC1101_REG_MARCSTATE | RADIOLIB_CC1101_CMD_ACCESS_STATUS_REG;
    constexpr uint8_t FIFO = RADIOLIB_CC1101_REG_TXBYTES | RADIOLIB_CC1101_CMD_ACCESS_STATUS_REG;
    uint32_t start = millis();
    while (millis() - start < 250) {
        uint8_t state = ccModule.SPIreadRegister(MARC) & 0x1f;
        if (state == RADIOLIB_CC1101_MARC_STATE_IDLE && ccModule.SPIreadRegister(FIFO) == 0) {
            return cc.finishTransmit();
        }
        if (state == RADIOLIB_CC1101_MARC_STATE_TXFIFO_UNDERFLOW) break;
        delay(1);
    }
    return RADIOLIB_ERR_TX_TIMEOUT;
}

void radio(const char* name, const char* action, int profile, const char* payload) {
    const bool isCC = !strcmp(name, "CC");
    const bool isNRF = !strcmp(name, "NRF");
    const bool isLoRa = !strcmp(name, "LORA");
    const bool probe = !strcmp(action, "PROBE");
    const bool scan = !strcmp(action, "SCAN");
    const bool tx = !strcmp(action, "TX");
    const bool rx = !strcmp(action, "RX");
    constexpr float ccFreq[] = {315.0f, 433.92f, 868.3f, 915.0f};
    constexpr float loraFreq[] = {433.5f, 868.3f, 915.0f};
    constexpr int nrfChannels = 79;
    constexpr rf24_datarate_e nrfRates[] = {RF24_250KBPS, RF24_1MBPS, RF24_2MBPS};
    int count = isCC ? 4 : isNRF ? 3 * nrfChannels : isLoRa ? 18 : 0;
    if (profile < 0 || profile >= count || !(probe || scan || tx || rx)) {
        reply("ERR radio command");
        return;
    }
    uint8_t packet[PACKET] = {};
    if (tx) {
        auto length = strlen(payload) / 2;
        if (!length || length > 24 || !decode(payload, packet + sizeof(MAGIC), length)) {
            reply("ERR packet size");
            return;
        }
        for (size_t i = 0; i < length; ++i) {
            if (!valid(packet[sizeof(MAGIC) + i])) {
                reply("ERR packet text");
                return;
            }
        }
        memcpy(packet, MAGIC, sizeof(MAGIC));
        if (isCC && profile == 0) {
            reply("ERR 315 MHz receive only");
            return;
        }
        if (hasSent && millis() - lastTx < 2000) {
            reply("ERR wait before sending");
            return;
        }
    }
    PhysicalLayer* layer = nullptr;
    int16_t status = 0;
    if (isCC) {
        status = cc.begin(ccFreq[profile], 4.8, 5.2, 135, 0);
        if (!status) status = cc.setSyncWord(0x53, 0xed);
        layer = &cc;
    } else if (isLoRa) {
        status = lora.begin(loraFreq[profile % 3], 125.0, 7 + profile / 3, 5, 0x12, 2);
        layer = &lora;
    } else {
        if (!nrf.begin(&SPI)) {
            reply("ERR NRF24 no response");
            return;
        }
        nrf.setAutoAck(false);
        nrf.setPALevel(RF24_PA_MIN);
        nrf.setChannel(2 + profile % nrfChannels);
        if (!nrf.setDataRate(probe || scan ? RF24_1MBPS : nrfRates[profile / nrfChannels])) {
            nrf.powerDown();
            reply("ERR NRF24 rate unsupported");
            return;
        }
        nrf.setPayloadSize(PACKET);
        nrf.openWritingPipe(ADDRESS);
        nrf.openReadingPipe(1, ADDRESS);
    }
    if (status) {
        Serial.printf("ERR radio initialization %d\n", status);
        return;
    }
    if (scan && isCC) {
        scanCC(ccFreq[profile]);
        return;
    }
    if (scan && isNRF) {
        scanNRF();
        return;
    }
    float signal = 0;
    float snr = 0;
    bool received = false;
    if (tx) {
        hasSent = true;
        lastTx = millis();
        status = isCC ? sendCC(packet) : layer ? layer->transmit(packet, sizeof(packet))
                       : (nrf.write(packet, sizeof(packet)) ? 0 : -1);
    } else if (rx) {
        if (layer) status = layer->startReceive();
        else nrf.startListening();
        uint32_t start = millis();
        while (!status && millis() - start < 5000) {
            if (layer ? digitalRead(isCC ? CC_IRQ : LORA_IRQ) : nrf.available()) {
                if (layer) {
                    auto length = layer->getPacketLength();
                    int read = layer->readData(packet, sizeof(packet));
                    received = read == 0 && length == sizeof(packet);
                    if (received) {
                        signal = isCC ? cc.getRSSI() : lora.getRSSI(true);
                        if (isLoRa) snr = lora.getSNR();
                    }
                } else {
                    nrf.read(packet, sizeof(packet));
                    received = true;
                }
                if (received && !memcmp(packet, MAGIC, sizeof(MAGIC))) break;
                received = false;
                if (layer) status = layer->startReceive();
            }
            delay(1);
        }
    } else if (scan) {
        status = lora.startReceive();
        if (!status) {
            delay(20);
            signal = lora.getRSSI(false, true);
            status = lora.startChannelScan();
            uint32_t start = millis();
            while (!status && !digitalRead(LORA_IRQ) && millis() - start < 200) delay(1);
            if (!status) {
                status = digitalRead(LORA_IRQ) ? lora.getChannelScanResult() : RADIOLIB_ERR_RX_TIMEOUT;
            }
        }
    }
    if (layer) {
        if (isCC) cc.standby();
        else lora.standby();
    } else {
        nrf.stopListening();
        nrf.powerDown();
    }
    if (scan && (status == RADIOLIB_PREAMBLE_DETECTED || status == RADIOLIB_CHANNEL_FREE)) {
        Serial.printf("OK %d %d\n", (int)roundf(signal), status == RADIOLIB_PREAMBLE_DETECTED);
    } else if (status) {
        Serial.printf("ERR radio status %d\n", status);
    } else if (rx && received) {
        Serial.printf("OK packet %d %d ", (int)roundf(signal), (int)roundf(snr));
        for (size_t i = sizeof(MAGIC); i < sizeof(packet) && valid(packet[i]); ++i) {
            Serial.printf("%02x", packet[i]);
        }
        Serial.println();
    } else if (rx) {
        reply("OK timeout");
    } else {
        reply("OK");
    }
}

void command(char* line) {
    char* next;
    const char* prefix = strtok_r(line, " ", &next);
    const char* name = strtok_r(nullptr, " ", &next);
    if (!prefix || strcmp(prefix, "EDK1") || !name) return;
    if (!strcmp(name, "HELLO")) {
        Serial.printf("OK EtherDeck %s %s %012llx\n", PROFILE, VERSION,
                      (unsigned long long)ESP.getEfuseMac());
        return;
    }
    const char* action = strtok_r(nullptr, " ", &next);
    const char* arg = strtok_r(nullptr, " ", &next);
    const char* payload = strtok_r(nullptr, " ", &next);
    if (!action || strtok_r(nullptr, " ", &next)) {
        reply("ERR syntax");
        return;
    }
    if (!strcmp(name, "UPDATE")) {
        update(action, arg ? arg : "", payload ? payload : "");
    } else if (ota) {
        reply("ERR update in progress");
    } else {
        char* end;
        long profile = arg ? strtol(arg, &end, 10) : -1;
        if (!arg || end == arg || *end || profile < 0 || profile > 236) {
            reply("ERR profile");
            return;
        }
        radio(name, action, profile, payload ? payload : "");
    }
}

void setup() {
    for (int cs : CHIP_SELECTS) {
        pinMode(cs, OUTPUT);
        digitalWrite(cs, HIGH);
    }
    pinMode(NRF_CE, OUTPUT);
    digitalWrite(NRF_CE, LOW);
    SPI.begin(SPI_SCK, SPI_MISO, SPI_MOSI, -1);
    Serial.setRxBufferSize(1536);
    Serial.setTxBufferSize(512);
    Serial.begin(115200);
}

void loop() {
    static char line[800];
    static size_t size = 0;
    static bool overflow = false;
    if (ota && millis() - activity > 15000) stopUpdate();
    while (Serial.available()) {
        int ch = Serial.read();
        if (ch == '\n') {
            line[size] = 0;
            if (!overflow) command(line);
            size = 0;
            overflow = false;
        } else if (ch != '\r') {
            if (size < sizeof(line) - 1) line[size++] = ch;
            else overflow = true;
        }
    }
    delay(1);
}
