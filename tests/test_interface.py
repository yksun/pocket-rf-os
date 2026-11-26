import tempfile
from pathlib import Path
from unittest import TestCase

from etherdeck import observations
from etherdeck.app import App, font, wrap_alert
from etherdeck.keys import Keyboard


class ReleaseTests(TestCase):
    def test_four_arrows_follow_physical_grid(self):
        for keys in ((103, 108, 105, 106), (33, 45, 44, 46)):
            app = App()
            app.home = 4
            kb = Keyboard(open_devices=False)
            kb.events([(389, 1)])
            for code, expected in zip((keys[0], keys[1], keys[2], keys[3]), (1, 4, 3, 4)):
                for key in kb.events([(code, 1), (code, 0)]):
                    app.key(key, 1)
                self.assertEqual(app.home, expected)

    def test_alert_details_survive_cache_and_scroll(self):
        features = {"features": [{"id": "test", "properties": {
            "status": "Actual", "event": "Example", "expires": "2099-01-01T00:00:00Z",
            "sent": "2025-01-01T00:00:00Z", "headline": "Header",
            "description": "Please read. " * 100, "instruction": "Follow local instructions.",
        }}]}
        alerts, total = observations.alert_records(features, now=1770000000)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            app = App(storage=path)
            observations.write(app.alert_file, {"area": "IL", "time": 1770000000, "total": total, "alerts": alerts})
            app.key("5", 1)
            app.key("ENTER", 2)
            self.assertEqual(app.page, "alert-detail")
            app.key("RIGHT", 3)
            self.assertEqual(app.alert_scroll, 5)
            self.assertIn("Follow local instructions.", " ".join(app.alert_lines))
            self.assertEqual(app.draw().size, (320, 170))
        lines = wrap_alert("一" * 300)
        self.assertTrue(all(font(11).getlength(line) <= 296 for line in lines))
        self.assertEqual("".join(lines), "一" * 300)

    def test_tab_then_ok_stays_reserved_for_system_lock(self):
        app = App()
        for key, tick in (("TAB_DOWN", 1), ("TAB_UP", 1.1), ("ENTER", 1.2)):
            app.key(key, tick)
        self.assertEqual(app.page, "home")
        app.key("ENTER", 3)
        self.assertEqual(app.page, "cap-confirm")
