from datetime import datetime, timezone
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from etherdeck import bridge, observations
from etherdeck.app import App, result


def alert(ident, status="Actual", severity="Minor", expiry="2099-01-01T00:00:00Z"):
    return {"id": ident, "properties": {"status": status, "severity": severity,
                                       "event": ident, "areaDesc": "Test area",
                                       "sent": "2026-01-01T00:00:00Z", "expires": expiry}}


class ObservationsTests(unittest.TestCase):
    def test_nws_excludes_exercises_expired_and_duplicates(self):
        now = int(datetime(2026, 11, 26, tzinfo=timezone.utc).timestamp())
        alerts, count = observations.alert_records({"features": [
            alert("Minor"), alert("Severe", severity="Severe"), alert("Minor"),
            alert("Exercise", status="Exercise"), alert("Expired", expiry="2020-01-01T00:00:00Z"),
        ]}, now)
        self.assertEqual(count, 2)
        self.assertEqual([a["event"] for a in alerts], ["Severe", "Minor"])
        self.assertGreater(alerts[0]["expires"], now)

    def test_correct_area_cache_survives_failed_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nws.json"
            with patch.object(observations, "urlopen") as connect:
                response = connect.return_value.__enter__.return_value
                response.geturl.return_value = observations.NWS + "?area=IL"
                response.read.return_value = b'{"features":[]}'
                snapshot = observations.fetch("IL", path)
                self.assertEqual(observations.cached(path), snapshot)
                self.assertEqual(connect.call_args.kwargs["timeout"], 5)
                response.read.return_value = b'{"bogus":[]}'
                with self.assertRaises(ValueError):
                    observations.fetch("IL", path)
                self.assertEqual(observations.cached(path), snapshot)

    def test_history_is_bounded_and_persistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rf-history.json"
            current = observations.record("LoRa", "433.50 MHz", "Signal", "Activity", [])
            observations.write(path, [current] * observations.HISTORY_LIMIT)
            new = dict(current, title="Newest")
            observations.save(path, new)
            loaded = observations.history(path)
            self.assertEqual(len(loaded), observations.HISTORY_LIMIT)
            self.assertEqual(loaded[0], new)
            path.write_text("{unfinished")
            self.assertEqual(observations.history(path), [])

    def test_no_network_until_requested(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(observations, "fetch") as fetch:
            app = App(storage=Path(tmp))
            app.key("5", 1)
            self.assertEqual(app.page, "alerts")
            fetch.assert_not_called()
            app.key("r", 2)
            self.assertEqual(app.page, "area")
            fetch.assert_not_called()

    def test_grid_scan_stop_then_save_from_real_ui_handlers(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bridge, "Bridge") as connect:
            link = connect.return_value.__enter__.return_value
            link.ask.return_value = "-105 " * 17
            app = App(storage=Path(tmp))
            app.key("1", 1)
            app.key("f", 2)
            app.key("ENTER", 3)
            self.assertEqual(app.page, "live")
            self.drain(app, lambda: app.sample is not None)
            app.key("ESC_DOWN", 4)
            self.drain(app, lambda: app.page == "live-result")
            app.key("ESC_UP", 4.1)
            self.assertEqual(app.page, "live-result")
            app.key("s", 5)
            self.drain(app, lambda: app.job is None)
            app.go("home")
            app.key("4", 6)
            self.assertEqual(app.records[0]["source"], "RF")
            self.assertEqual(len(app.records[0]["samples"]), 17)
            self.assertEqual(link.ask.call_args.args[0], "CC SCAN 1")

    def test_catalogue_knows_which_unit_each_radio_measures(self):
        self.assertEqual(result("NRF", "SCAN", "0 " * 84)[2], [0] * 84)
        self.assertIn("dBm", result("CC", "SCAN", "-110 " * 17)[0])

    def drain(self, app, condition):
        deadline = time.monotonic() + 2
        while not condition() and time.monotonic() < deadline:
            app.poll()
            time.sleep(0.005)
        self.assertTrue(condition())


if __name__ == "__main__":
    unittest.main()
