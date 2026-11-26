"""CardputerZero top-header diagnostics and allowlisted native app handoff."""
import os
from pathlib import Path
import re
import subprocess

SPI = Path("/dev/spidev0.1")
LED = Path("/sys/class/leds/ext_usb_gpio_fun/brightness")
SUDO = ("/usr/bin/sudo", "-n", "--")
BIN = "/usr/share/APPLaunch/bin"

CAPS = (
    ("Cap CC1101", "U219  ·  CC1101 + ST25R3916",
     (("Sub-GHz 聊天", (*SUDO, f"{BIN}/M5CardputerZero-Cap-CC1101-SubG-Chat")),
      ("NFC 工具", (*SUDO, f"{BIN}/M5CardputerZero-Cap-CC1101-NFC")))),
    ("Cap LoRa-1262", "U214  ·  SX1262 + GNSS",
     (("LoRa 聊天", ("/usr/share/Cap-LoRa-1262/bin/Cap-LoRa-1262",)),
      ("GNSS 定位", (*SUDO, f"{BIN}/M5CardputerZero-Cap-LoRa-1262-GPS")))),
)


def available(command):
    return all(os.access(path, os.X_OK) for path in (command[0], command[-1]))


def status():
    """Read the host mux and device-node permissions without opening any bus."""
    try:
        data = subprocess.run(
            ["pinctrl", "get", "0-27"], check=True, capture_output=True, text=True, timeout=2
        ).stdout
    except (OSError, subprocess.SubprocessError):
        data = ""
    pins = {}
    for line in data.splitlines():
        match = re.match(r"\s*(\d+):.*?//.*?=\s*(\w+)", line)
        if match:
            pins[int(match[1])] = match[2]
    try:
        mode = {"0": "GPIO", "1": "USB"}.get(LED.read_text().strip(), "?")
    except OSError:
        mode = "?"
    return {
        "spi": os.access(SPI, os.R_OK | os.W_OK),
        "mode": mode,
        "pins": pins,
    }


def summary(snapshot):
    pins = snapshot["pins"]
    return [
        f"SPI0.1  {'可访问' if snapshot['spi'] else '不可访问'}    HAT  {snapshot['mode']}",
        f"G2 / G3   {pins.get(2, '?')} / {pins.get(3, '?')}",
        f"G14 / G15   {pins.get(14, '?')} / {pins.get(15, '?')}",
    ]
