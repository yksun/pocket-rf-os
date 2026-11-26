#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
uv tool run --python 3.12 --from platformio==6.1.18 --with pip pio run -d firmware
build=firmware/.pio/build/joseph-adv
ota_init="${PLATFORMIO_CORE_DIR:-$HOME/.platformio}/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin"
mkdir -p bridge-firmware
uv tool run --python 3.12 --from esptool==4.9.0 esptool.py --chip esp32s3 merge_bin \
    -o bridge-firmware/bootstrap.bin --flash_size 8MB \
    0x0 "$build/bootloader.bin" 0x8000 "$build/partitions.bin" \
    0xe000 "$ota_init" 0x10000 "$build/firmware.bin"
cp "$build/firmware.bin" bridge-firmware/firmware.bin
python3 - <<'PY'
import hashlib
import json
from pathlib import Path
import re

directory = Path("bridge-firmware")
source = Path("firmware/src/main.cpp").read_text()
version = re.search(r'char VERSION\[\] = "([^"]+)"', source)[1]
manifest = {
    "profile": "joseph-adv",
    "version": version,
    "sha256": hashlib.sha256((directory / "firmware.bin").read_bytes()).hexdigest(),
    "bootstrap_sha256": hashlib.sha256((directory / "bootstrap.bin").read_bytes()).hexdigest(),
}
(directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY
