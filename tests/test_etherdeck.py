import hashlib
import json
import os
from pathlib import Path
import pty
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from etherdeck import bridge
from etherdeck.app import App, result
from etherdeck.keys import Keyboard


class ProtocolTests(unittest.TestCase):
    def test_real_serial_connection_and_radio(self):
        master, slave = pty.openpty()
        port = os.ttyname(slave)
        requests = []

        def board():
            with os.fdopen(os.dup(master), "rb") as stream:
                for reply in (b"OK EtherDeck joseph-adv 0.1.0 112233445566\r\n",
                              b"OK packet -65 7 48656c6c6f\n"):
                    requests.append(stream.readline())
                    os.write(master, reply[:3])
                    os.write(master, reply[3:])

        thread = threading.Thread(target=board, daemon=True)
        thread.start()
        try:
            received = bridge.radio(port, "LORA", "RX", 0)
            self.assertEqual(result("LORA", "RX", received)[1], ["Hello", "RSSI -65 dBm", "SNR 7 dB"])
            self.assertEqual(requests, [b"EDK1 HELLO\n", b"EDK1 LORA RX 0\n"])
        finally:
            os.close(slave)
            os.close(master)
            thread.join(1)

    def test_corrupt_bundle_stops_before_usb(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bridge, "FIRMWARE", Path(tmp)):
            (Path(tmp) / "manifest.json").write_text(json.dumps(
                {"profile": bridge.PROFILE, "version": "0.2.0", "sha256": "invalid"}))
            (Path(tmp) / "firmware.bin").write_bytes(b"firmware")
            with self.assertRaisesRegex(bridge.BridgeError, "invalid"):
                bridge.pack()

    def test_update_checks_target_and_restart_and_transfers_all_bytes(self):
        data = bytes(range(255)) * 5
        digest = hashlib.sha256(data).hexdigest()
        old = Mock(version="0.1.0", identity="bridge-a")
        old.ask.side_effect = lambda command, **_: "reboot" if command == "UPDATE END" else ""
        new = Mock(version="0.2.0", identity="bridge-a")
        contexts = [Mock(), Mock()]
        for mgr, board in zip(contexts, (old, new)):
            mgr.__enter__ = Mock(return_value=board)
            mgr.__exit__ = Mock(return_value=False)
        progress = []
        with (patch.object(bridge, "pack", return_value=("0.2.0", data, digest)),
              patch.object(bridge, "Bridge", side_effect=contexts),
              patch.object(bridge.time, "sleep")):
            self.assertEqual(bridge.update("/dev/ttyACM0", "bridge-a", "0.1.0", progress.append), "0.2.0")
        commands = [call.args[0] for call in old.ask.call_args_list]
        self.assertEqual(commands[0], f"UPDATE BEGIN {len(data)} {digest}")
        self.assertEqual(b"".join(bytes.fromhex(c.removeprefix("UPDATE DATA "))
                                 for c in commands[1:-1]), data)
        self.assertEqual(commands[-1], "UPDATE END")
        self.assertEqual(progress[-1], 100)

    def test_interrupted_update_cancels_without_commit(self):
        link = Mock(version="0.1.0", identity="bridge-a")
        link.ask.side_effect = ["", bridge.BridgeError("write timeout"), ""]
        mgr = Mock()
        mgr.__enter__ = Mock(return_value=link)
        mgr.__exit__ = Mock(return_value=False)
        with (patch.object(bridge, "pack", return_value=("0.2.0", b"abc", "digest")),
              patch.object(bridge, "Bridge", return_value=mgr),
              self.assertRaisesRegex(bridge.BridgeError, "write timeout")):
            bridge.update("usb", "bridge-a", "0.1.0", Mock())
        self.assertEqual(link.ask.call_args.args[0], "UPDATE CANCEL")

    def test_wrong_device_before_update(self):
        mgr = Mock()
        mgr.__enter__ = Mock(return_value=Mock(identity="other", version="0.1.0"))
        mgr.__exit__ = Mock(return_value=False)
        with (patch.object(bridge, "pack", return_value=("0.2.0", b"data", "digest")),
              patch.object(bridge, "Bridge", return_value=mgr),
              self.assertRaisesRegex(bridge.BridgeError, "changed")):
            bridge.update("usb", "bridge-a", "0.1.0", Mock())
        mgr.__enter__.return_value.ask.assert_not_called()

    def test_multiple_ports_require_explicit_selection(self):
        with patch.object(bridge.list_ports, "comports",
                          return_value=[Mock(vid=0x303A, pid=0x1001)] * 2):
            with self.assertRaisesRegex(bridge.BridgeError, "Multiple"):
                bridge.port_name()


class InterfaceTests(unittest.TestCase):
    def test_keys_and_lock(self):
        app = App()
        keypad = Keyboard(open_devices=False)
        keys = keypad.events([(389, 1), (45, 1), (45, 0), (389, 0)])
        for key in keys:
            app.key(key, 1)
        self.assertEqual(app.home, 1)
        app.key("TAB_DOWN", 2)
        app.key("TAB_UP", 2.1)
        app.key("ENTER", 3)
        self.assertEqual(app.page, "home")
        app.key("ENTER", 4)
        self.assertEqual(app.page, "radio")
        app.key("ESC_DOWN", 5)
        app.key("ESC_UP", 5.1)
        self.assertEqual(app.page, "home")
        app.key("ESC_DOWN", 6)
        app.key("ESC_UP", 7)
        self.assertFalse(app.running)

    def test_channel_and_rate_keys_are_independent(self):
        app = App()
        app.key("2", 1)
        app.key("LEFT", 2)
        self.assertEqual(app.profiles[1], 157)
        app.key("b", 3)
        self.assertEqual(app.profiles[1], 236)
        app.key("RIGHT", 4)
        self.assertEqual(app.profiles[1], 158)

    def test_transmit_has_a_separate_confirmation(self):
        app = App()
        app.key("3", 1)
        app.action = 3
        app.operate = Mock()
        app.key("ENTER", 2)
        app.key("A", 3)
        app.key("ENTER", 4)
        app.key("ENTER", 5)
        self.assertEqual(app.page, "send")
        app.operate.assert_not_called()
        app.key("Y", 6)
        app.operate.assert_called_once_with("TX")

    def test_cc_315_transmit_is_unavailable(self):
        app = App()
        app.key("1", 1)
        app.key("LEFT", 2)
        app.action = 3
        app.key("ENTER", 3)
        self.assertEqual(app.view[0], "315 MHz 仅接收")

    def test_scan_results_expect_distinct_module_formats(self):
        self.assertEqual(len(result("CC", "SCAN", "-104 " * 17)[2]), 17)
        self.assertEqual(len(result("NRF", "SCAN", "1 " * 84)[2]), 84)
        self.assertEqual(result("LORA", "SCAN", "-90 1")[1], ["检测到 LoRa 活动"])
        with self.assertRaises(ValueError):
            result("NRF", "SCAN", "9 " * 84)

    def test_render_every_view(self):
        app = App()
        app.usb = ("usb", "bridge-a", "0.0.1")
        for page in ("home", "radio", "compose", "send", "waiting", "result", "firmware",
                     "confirm-update", "updating", "firmware-result", "live",
                     "live-result", "history", "history-detail", "alerts", "area", "hardware"):
            with self.subTest(page=page):
                app.page = page
                self.assertEqual(app.draw().size, (320, 170))


if __name__ == "__main__":
    unittest.main()
