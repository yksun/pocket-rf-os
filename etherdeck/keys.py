"""TCA8418 keypad (CardputerZero) -> characters / named keys via evdev.

Copied from micius-claw. Differences: ESC and TAB report press and release
(ESC_DOWN/ESC_UP, TAB_DOWN/TAB_UP) so the app can tell a short press from a
long one, and Ctrl+Space is reported for the terminal.
"""
import glob
import os
import re
import struct

EV_KEY = 1
FMT = "llHHi"
SZ = struct.calcsize(FMT)
KEYMAP_FILE = "/usr/share/keymaps/tca8418_keypad_m5stack_keymap.map"
PREFERRED = "/dev/input/by-path/platform-3f804000.i2c-event"

SHIFT = {42, 54}
CTRL = {29, 97}
ALT = {56, 100}
FN = {389, 464}          # 389 observed on the CardputerZero (KEY_DVD), 464 = KEY_FN
SYM = {383}              # symbol-layer key on CardputerZero (KEY_CD)
MODS = SHIFT | CTRL | ALT | FN | SYM

LETTERS = {16: "q", 17: "w", 18: "e", 19: "r", 20: "t", 21: "y", 22: "u", 23: "i",
           24: "o", 25: "p", 30: "a", 31: "s", 32: "d", 33: "f", 34: "g", 35: "h",
           36: "j", 37: "k", 38: "l", 44: "z", 45: "x", 46: "c", 47: "v", 48: "b",
           49: "n", 50: "m"}
DIGITS = {2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 9: "8", 10: "9", 11: "0"}
SHIFT_DIGITS = dict(zip("1234567890", "!@#$%^&*()"))
STD_SYMBOLS = {12: ("-", "_"), 13: ("=", "+"), 26: ("[", "{"), 27: ("]", "}"),
               39: (";", ":"), 40: ("'", '"'), 41: ("`", "~"), 43: ("\\", "|"),
               51: (",", "<"), 52: (".", ">"), 53: ("/", "?")}
NAMED = {28: "ENTER", 96: "ENTER", 14: "BACKSPACE", 111: "DELETE",
         57: " ", 103: "UP", 108: "DOWN", 105: "LEFT", 106: "RIGHT",
         104: "PGUP", 109: "PGDN", 102: "HOME", 107: "END"}
# Fn + key fallbacks when the driver does not translate arrows itself
FN_NAMED = {33: "UP", 45: "DOWN", 44: "LEFT", 46: "RIGHT",39: "UP", 52: "DOWN", 51: "LEFT", 53: "RIGHT",   # ; . , /
            14: "DELETE"}

KEYSYM = {"exclam": "!", "at": "@", "numbersign": "#", "dollar": "$", "percent": "%",
          "asciicircum": "^", "ampersand": "&", "asterisk": "*", "parenleft": "(",
          "parenright": ")", "asciitilde": "~", "grave": "`", "underscore": "_",
          "minus": "-", "plus": "+", "equal": "=", "bracketleft": "[",
          "bracketright": "]", "braceleft": "{", "braceright": "}", "semicolon": ";",
          "colon": ":", "apostrophe": "'", "quotedbl": '"', "less": "<",
          "greater": ">", "backslash": "\\", "bar": "|", "comma": ",", "period": ".",
          "slash": "/", "question": "?", "space": " "}


def load_symbol_map(path=KEYMAP_FILE):
    m = {}
    try:
        with open(path) as f:
            for line in f:
                mm = re.match(r"\s*keycode\s+(\d+)\s*=\s*(\w+)", line)
                if mm and mm.group(2) in KEYSYM:
                    m[int(mm.group(1))] = KEYSYM[mm.group(2)]
    except OSError:
        pass
    return m


def _has_ev_key(fd):
    buf = bytearray(4)
    try:
        import fcntl
        fcntl.ioctl(fd, 0x80044520, buf)   # EVIOCGBIT(0, 4)
    except OSError:
        return False
    bits = int.from_bytes(buf, "little")
    return bool(bits & (1 << EV_KEY)) and not bits & (1 << 2)  # keys, no EV_REL


class Keyboard:
    def __init__(self, open_devices=True):
        self.fds = []
        if open_devices:
            paths = [PREFERRED] if os.path.exists(PREFERRED) else []
            if not paths:
                paths = sorted(glob.glob("/dev/input/event*"))
            for p in paths:
                try:
                    fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
                except OSError:
                    continue
                if p == PREFERRED or _has_ev_key(fd):
                    self.fds.append(fd)
                else:
                    os.close(fd)
        self.sym = load_symbol_map()
        self.down = set()
        self.latched = set()
        self._tap = None

    def translate(self, code):
        shift = bool(self.down & SHIFT)
        ctrl = bool(self.down & CTRL)
        fn = bool(self.down & FN)
        if ctrl and code in LETTERS:
            return "CTRL_" + LETTERS[code].upper()
        if ctrl and code == 57:
            return "CTRL_SPACE"
        if fn and code in FN_NAMED:
            return FN_NAMED[code]
        if code in NAMED:
            return NAMED[code]
        if code in LETTERS:
            ch = LETTERS[code]
            return ch.upper() if shift else ch
        if code in DIGITS:
            return SHIFT_DIGITS[DIGITS[code]] if shift else DIGITS[code]
        if code in self.sym:                 # driver-remapped symbol keycodes
            return self.sym[code]
        if code in STD_SYMBOLS:
            a, b = STD_SYMBOLS[code]
            return b if shift else a
        return None

    def events(self, raw):
        """Turn (code, value) pairs into key names. Separate from read() for tests."""
        out = []
        for code, val in raw:
            if code in (1, 15):                     # ESC / TAB: report press + release
                name = "ESC" if code == 1 else "TAB"
                if val == 1:
                    out.append(name + "_DOWN")
                elif val == 0:
                    out.append(name + "_UP")
                continue
            if val == 0:
                self.down.discard(code)
                # tapped a modifier alone -> latch it for the next key
                if code in MODS and self._tap == code:
                    self.latched.add(code)
                continue
            if code in MODS:
                self.down.add(code)
                self._tap = code if val == 1 else None
                continue
            self._tap = None
            saved = self.down
            self.down = self.down | self.latched
            k = self.translate(code)       # val 1 = press, 2 = autorepeat
            self.down = saved
            self.latched.clear()
            if k is not None:
                out.append(k)
        return out

    def read(self, ready):
        raw = []
        for fd in ready:
            try:
                data = os.read(fd, SZ * 64)
            except (BlockingIOError, OSError):
                continue
            for i in range(0, len(data) - SZ + 1, SZ):
                _, _, etype, code, val = struct.unpack(FMT, data[i:i + SZ])
                if etype == EV_KEY:
                    raw.append((code, val))
        return self.events(raw)
