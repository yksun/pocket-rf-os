"""EtherDeck's request/response USB protocol and bundled bridge update."""
import hashlib
import json
from pathlib import Path
import re
import time

import serial
from serial.tools import list_ports

PROFILE = "joseph-adv"
TOP_PROFILE = "zero-top-adapter"
PROFILES = (PROFILE, TOP_PROFILE)
FIRMWARE = Path(__file__).resolve().parent.parent / "bridge-firmware"
VERSION_RE = re.compile(r"(\d{1,3})\.(\d{1,3})\.(\d{1,3})")


class BridgeError(RuntimeError):
    pass


def version_tuple(version):
    match = VERSION_RE.fullmatch(version)
    if not match:
        raise BridgeError("Invalid bridge version")
    return tuple(map(int, match.groups()))


def pack(profile=PROFILE):
    if profile not in PROFILES:
        raise BridgeError("Unknown bridge profile")
    directory = FIRMWARE if profile == PROFILE else FIRMWARE / profile
    try:
        metadata = json.loads((directory / "manifest.json").read_text())
        image = (directory / "firmware.bin").read_bytes()
        if metadata["profile"] != profile or not 0 < len(image) <= 0x330000:
            raise ValueError("profile or size")
        version_tuple(metadata["version"])
        digest = hashlib.sha256(image).hexdigest()
        if digest != metadata["sha256"]:
            raise ValueError("checksum")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BridgeError("Bundled image missing or invalid") from exc
    return metadata["version"], image, digest


def port_name():
    ports = [p.device for p in list_ports.comports() if (p.vid, p.pid) == (0x303A, 0x1001)]
    if len(ports) != 1:
        raise BridgeError("Connect one ESP32-S3 bridge" if not ports else "Multiple ESP32-S3 USB devices")
    device = Path(ports[0])
    for link in sorted(Path("/dev/serial/by-id").glob("*")):
        if link.resolve() == device:
            return str(link)
    return str(device)


class Bridge:
    def __init__(self, port=None):
        self.port = port or port_name()
        self.serial = serial.Serial(port=self.port, baudrate=115200, timeout=0.15,
                                    write_timeout=1, exclusive=True)
        try:
            self.serial.reset_input_buffer()
            self.version, self.identity, self.profile = self.hello()
        except BaseException:
            self.serial.close()
            raise

    def ask(self, request, timeout=2):
        self.serial.write(f"EDK1 {request}\n".encode("ascii"))
        deadline = time.monotonic() + timeout
        pending = bytearray()
        while time.monotonic() < deadline:
            part = self.serial.read_until(b"\n", size=1024)
            pending.extend(part)
            if len(pending) > 1024:
                raise BridgeError("Oversized bridge response")
            if not part.endswith(b"\n"):
                continue
            line = pending.decode("ascii", errors="replace").strip()
            pending.clear()
            if line == "OK":
                return ""
            if line.startswith("OK "):
                return line[3:]
            if line.startswith("ERR "):
                raise BridgeError(line[4:])
        raise BridgeError("No reply from EtherDeck bridge")

    def hello(self):
        fields = self.ask("HELLO").split()
        if (len(fields) != 4 or fields[0] != "EtherDeck" or fields[1] not in PROFILES
                or not re.fullmatch(r"[0-9a-f]{12}", fields[3])):
            raise BridgeError("Wrong USB firmware or board")
        version_tuple(fields[2])
        return fields[2], fields[3], fields[1]

    def close(self):
        self.serial.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def radio(port, name, action, profile, message=""):
    if action == "TX" and (not 1 <= len(message) <= 24
                           or any(not 32 <= ord(c) <= 126 for c in message)):
        raise BridgeError("Enter 1–24 printable ASCII characters")
    request = f"{name} {action} {profile}"
    if message:
        request += " " + message.encode("ascii").hex()
    with Bridge(port) as link:
        return link.ask(request, timeout=7)


def update(port, identity, current, progress, *, profile=PROFILE):
    version, image, digest = pack(profile)
    if version_tuple(version) <= version_tuple(current):
        raise BridgeError("Bridge is up to date")
    with Bridge(port) as link:
        if (link.identity, link.version, link.profile) != (identity, current, profile):
            raise BridgeError("USB bridge changed")
        link.ask(f"UPDATE BEGIN {len(image)} {digest}", timeout=8)
        try:
            for offset in range(0, len(image), 384):
                chunk = image[offset:offset + 384]
                link.ask("UPDATE DATA " + chunk.hex())
                progress(100 * (offset + len(chunk)) // len(image))
        except (BridgeError, OSError, serial.SerialException):
            try:
                link.ask("UPDATE CANCEL", timeout=0.5)
            except (BridgeError, OSError, serial.SerialException):
                pass
            raise
        if link.ask("UPDATE END", timeout=8) != "reboot":
            raise BridgeError("Unexpected update response")
    time.sleep(0.7)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        try:
            with Bridge(port) as link:
                if (link.identity, link.version, link.profile) == (identity, version, profile):
                    return version
        except (BridgeError, OSError, serial.SerialException):
            pass
        time.sleep(0.35)
    raise BridgeError("Restarted version unverified. Reconnect and check USB.")
