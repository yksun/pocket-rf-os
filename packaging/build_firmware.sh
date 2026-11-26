#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
uv tool run --python 3.12 --from platformio==6.1.18 --with pip pio run -d firmware
ota_init="${PLATFORMIO_CORE_DIR:-$HOME/.platformio}/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin"
for profile in joseph-adv zero-top-adapter; do
build="firmware/.pio/build/$profile"
directory=bridge-firmware
[ "$profile" = joseph-adv ] || directory="$directory/$profile"
mkdir -p "$directory"
uv tool run --python 3.12 --from esptool==4.9.0 esptool.py --chip esp32s3 merge_bin \
    -o "$directory/bootstrap.bin" --flash_size 8MB \
    0x0 "$build/bootloader.bin" 0x8000 "$build/partitions.bin" \
    0xe000 "$ota_init" 0x10000 "$build/firmware.bin"
cp "$build/firmware.bin" "$directory/firmware.bin"
python3 - "$directory" "$profile" <<'PY'
import hashlib
import json
from pathlib import Path
import re
import sys

directory = Path(sys.argv[1])
source = Path("firmware/src/main.cpp").read_text()
version = re.search(r'char VERSION\[\] = "([^"]+)"', source)[1]
manifest = {
    "profile": sys.argv[2],
    "version": version,
    "sha256": hashlib.sha256((directory / "firmware.bin").read_bytes()).hexdigest(),
    "bootstrap_sha256": hashlib.sha256((directory / "bootstrap.bin").read_bytes()).hexdigest(),
}
(directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
PY
done
