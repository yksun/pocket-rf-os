from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from etherdeck import observations
from etherdeck.app import App


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

    def test_no_network_until_requested(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(observations, "fetch") as fetch:
            app = App(storage=Path(tmp))
            app.key("5", 1)
            self.assertEqual(app.page, "alerts")
            fetch.assert_not_called()
            app.key("r", 2)
            self.assertEqual(app.page, "area")
            fetch.assert_not_called()

if __name__ == "__main__":
    unittest.main()
