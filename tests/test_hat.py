from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from etherdeck import hat
from etherdeck.app import App
from etherdeck.__main__ import run_app


class HatTests(TestCase):
    def test_pinctrl_reads_host_mux_without_bus_transactions(self):
        data = " 2: a0 -- | hi // GPIO2 = SDA1\n 14: a5 -- | hi // GPIO14 = TXD1\n"
        with (patch.object(hat.subprocess, "run", return_value=SimpleNamespace(stdout=data)) as run,
              patch.object(Path, "read_text", return_value="0\n"),
              patch.object(hat.os, "access", return_value=True)):
            snapshot = hat.status()
        self.assertEqual(snapshot, {"5v": "关闭", "spi": True, "mode": "GPIO", "pins": {2: "SDA1", 14: "TXD1"}})
        self.assertEqual(run.call_args.args[0], ["pinctrl", "get", "0-27"])

    def test_all_four_tools_confirm_once_then_open_directly(self):
        for index in range(4):
            with (self.subTest(index=index), patch.object(hat, "available", return_value=True),
                  patch.object(hat, "port_mode", return_value="GPIO")):
                app = App()
                app.key(str(index + 1), 1)
                self.assertEqual(app.page, "cap-confirm")
                self.assertIsNone(app.launch_target)
                app.key("Y", 2)
                self.assertEqual(app.confirmed_cap, index // 2)
                self.assertEqual(app.launch_target, hat.tool(index)[1])
                self.assertFalse(app.running)
                app.launch_target, app.running = None, True
                second = index ^ 1
                app.key(str(second + 1), 3)
                self.assertEqual(app.launch_target, hat.tool(second)[1])

    def test_wrong_board_requires_correct_sku_in_both_directions(self):
        for current, key in ((0, "3"), (1, "1")):
            with self.subTest(current=current):
                app = App()
                app.confirmed_cap = current
                app.key(key, 1)
                self.assertEqual(app.page, "cap-required")
                self.assertEqual(hat.CAP_IDS[app.required_cap], "U214" if current == 0 else "U219")
                self.assertEqual(app.draw().size, (320, 170))
                app.key("Y", 2)
                self.assertIsNone(app.launch_target)

    def test_missing_tool_cannot_launch(self):
        with (patch.object(hat, "available", return_value=False),
              patch.object(hat, "port_mode", return_value="GPIO")):
            app = App()
            app.key("1", 1)
            app.key("Y", 2)
            self.assertIsNone(app.launch_target)
            self.assertIn("安装", app.notice)

    def test_usb_mode_blocks_confirmation_and_launch(self):
        app = App()
        app.key("3", 1)
        with patch.object(hat, "port_mode", return_value="USB"):
            app.key("Y", 2)
            self.assertIsNone(app.confirmed_cap)
            self.assertIn("GPIO", app.notice)
            app.confirmed_cap = 1
            app.go("home")
            app.key("4", 3)
            self.assertIsNone(app.launch_target)

    def test_official_tool_returns_to_same_app_session(self):
        app = App()
        app.confirmed_cap = 1
        command = hat.tool(2)[1]
        visits = []

        def run():
            visits.append(app.confirmed_cap)
            if len(visits) == 1:
                app.launch_target = command
            app.running = False

        with (patch.object(app, "run", side_effect=run),
              patch("etherdeck.__main__.subprocess.run", return_value=SimpleNamespace(returncode=0)) as tool):
            run_app(app)
        tool.assert_called_once_with(command, check=False)
        self.assertEqual(visits, [1, 1])
        self.assertIsNone(app.launch_target)
