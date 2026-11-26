# Licensing and firmware source

Pocket RF OS source is offered under GPL-2.0-only. The license text is in [LICENSE](LICENSE). The Debian app uses Python, Pillow, NumPy, pyserial, and Noto CJK as runtime dependencies installed by Debian.

The ESP32-S3 USB bridge compiles these upstream dependencies from their pinned sources. The release provides the build scripts and links to the full corresponding upstream source for the pinned dependencies.

| Part | Version and source | License |
| --- | --- | --- |
| RF24 | [1.5.0](https://github.com/nRF24/RF24/tree/v1.5.0) | GPL-2.0-only |
| RadioLib | [7.4.0](https://github.com/jgromes/RadioLib/tree/7.4.0) | MIT |
| Arduino-ESP32 | [2.0.17](https://github.com/espressif/arduino-esp32/tree/2.0.17), [PlatformIO packaging](https://registry.platformio.org/tools/platformio/framework-arduinoespressif32) | LGPL-2.1 with component-specific notices |
| ESP-IDF | [4.4.x Arduino SDK base](https://github.com/espressif/esp-idf/tree/v4.4.7) | Apache-2.0 and component-specific notices |
| PlatformIO Espressif32 | [6.12.0](https://github.com/platformio/platform-espressif32/tree/v6.12.0) | Apache-2.0 |
| esptool | [4.9.0](https://github.com/espressif/esptool/tree/v4.9.0) | GPL-2.0-or-later |

The [JosephCGS project](https://github.com/JosephCGS/Cardputer-ADV-CC1101-NRF24L01-LoRa) is the hardware pin-mapping reference. This release uses its own application and bridge source.
