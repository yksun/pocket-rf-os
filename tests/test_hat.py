from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from etherdeck import hat
from etherdeck.app import App


class HatTests(TestCase):
    def test_pinctrl_reads_host_mux_without_bus_transactions(self):
        fixture = " 2: a0 -- | hi // GPIO2 = SDA1\n 14: a5 -- | hi // GPIO14 = TXD1\n"
        with (patch.object(hat.subprocess, "run", return_value=SimpleNamespace(stdout=fixture)) as run,
              patch.object(Path, "read_text", return_value="0\n"),
              patch.object(hat.os, "access", return_value=True)):
            snapshot = hat.status()
        self.assertEqual(snapshot, {"spi": True, "mode": "GPIO", "pins": {2: "SDA1", 14: "TXD1"}})
        self.assertEqual(run.call_args.args[0], ["pinctrl", "get", "0-27"])

    def test_both_official_caps_require_confirmation(self):
        for key, selection in (("1", 0), ("2", 1)):
            with self.subTest(key=key), patch.object(hat, "available", return_value=True):
                app = App()
                app.key(key, 1)
                self.assertEqual(app.page, "cap")
                app.key("x", 2)
                app.key("ENTER", 3)
                self.assertEqual(app.page, "cap-confirm")
                self.assertTrue(app.running)
                self.assertIsNone(app.launch_target)
                self.assertEqual(app.draw().size, (320, 170))
                app.key("Y", 4)
                self.assertEqual(app.launch_target, hat.CAPS[selection][2][1][1])
                self.assertFalse(app.running)

    def test_missing_official_app_cannot_launch(self):
        with patch.object(hat, "available", return_value=False):
            app = App()
            app.key("1", 1)
            app.key("ENTER", 2)
            app.key("Y", 3)
            self.assertIsNone(app.launch_target)
            self.assertEqual(app.page, "cap")
            self.assertIn("安装", app.notice)

    def test_joseph_entry_checks_host_without_initializing_radio(self):
        app = App()
        with patch.object(app, "start") as start:
            app.key("3", 1)
            app.key("R", 2)
            self.assertEqual(app.page, "joseph")
            self.assertIsNone(app.launch_target)
        self.assertEqual([call.args for call in start.call_args_list],
                         [("hat", hat.status), ("hat", hat.status)])
