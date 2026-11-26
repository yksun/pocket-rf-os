"""Bounded RF observations and opt-in NWS alert snapshots."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.request import Request, urlopen

HISTORY_LIMIT = 100
ALERT_LIMIT = 25
MAX_FILE = 1024 * 1024
NWS = "https://api.weather.gov/alerts/active"
USER_AGENT = "Pocket-RF-OS/0.2.0 (https://github.com/yksun/pocket-rf-os)"
STATES = frozenset("AK AL AR AS AZ CA CO CT DC DE FL GA GU HI IA ID IL IN KS KY LA MA MD ME MI MN MO MP MS MT NC ND NE NH NJ NM NV NY OH OK OR PA PR RI SC SD TN TX UT VA VI VT WA WI WV WY".split())


def state_dir():
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "etherdeck"


def read(path, default):
    try:
        with path.open("rb") as stream:
            return json.loads(stream.read(MAX_FILE + 1)) if path.stat().st_size <= MAX_FILE else default
    except (OSError, ValueError):
        return default


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        staged = Path(tmp.name)
        try:
            json.dump(value, tmp, ensure_ascii=False)
            tmp.flush()
            os.fsync(tmp.fileno())
            os.replace(staged, path)
        finally:
            staged.unlink(missing_ok=True)


def record(radio, profile, title, detail, samples):
    return {"source": "RF", "time": int(time.time()), "radio": radio, "profile": profile,
            "title": title, "detail": detail, "samples": samples}


def history(path):
    saved = read(path, [])
    if not isinstance(saved, list):
        return []
    return [r for r in saved[:HISTORY_LIMIT] if isinstance(r, dict)
            and r.get("source") == "RF" and isinstance(r.get("time"), int)
            and 0 <= r["time"] < 4102444800
            and all(isinstance(r.get(k), str) for k in ("radio", "profile", "title", "detail"))]


def save(path, sample):
    write(path, [sample, *history(path)][:HISTORY_LIMIT])


def parse_time(value):
    try:
        stamp = datetime.fromisoformat(value)
        return int(stamp.timestamp()) if stamp.tzinfo else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def _text(value, limit):
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def alert_records(data, now):
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        raise ValueError("Unexpected NWS response")
    alerts = {}
    for feature in data["features"]:
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            raise ValueError("Unexpected NWS alert")
        p = feature["properties"]
        expires = parse_time(p.get("expires"))
        event, ident = _text(p.get("event"), 100), _text(feature.get("id") or p.get("id"), 240)
        if p.get("status") == "Actual" and ident and event and expires > now:
            alerts[ident] = {
                "event": event, "severity": _text(p.get("severity"), 24),
                "area": _text(p.get("areaDesc"), 140),
                "sent": parse_time(p.get("sent")), "expires": expires,
            }
    severity = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3}
    items = sorted(alerts.values(), key=lambda a: (severity.get(a["severity"], 4), -a["sent"]))
    return items[:ALERT_LIMIT], len(items)


def fetch(area, path):
    if area not in STATES:
        raise ValueError("Enter a valid US state or territory code")
    request = Request(f"{NWS}?area={area}",
                      headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"})
    with urlopen(request, timeout=5) as response:
        if response.geturl() != request.full_url:
            raise ValueError("Unexpected NWS redirect")
        payload = response.read(MAX_FILE + 1)
    if len(payload) > MAX_FILE:
        raise ValueError("NWS response too large")
    now = int(time.time())
    alerts, total = alert_records(json.loads(payload), now)
    snapshot = {"area": area, "time": now, "alerts": alerts, "total": total}
    write(path, snapshot)
    return snapshot


def cached(path):
    raw = read(path, {})
    if (isinstance(raw, dict) and isinstance(raw.get("area"), str) and raw["area"] in STATES
            and type(raw.get("time")) is int and 0 < raw["time"] < 4102444800
            and type(raw.get("total")) is int and isinstance(raw.get("alerts"), list)):
        raw["alerts"] = [
            a for a in raw["alerts"][:ALERT_LIMIT] if isinstance(a, dict)
            and type(a.get("expires")) is int and 0 < a["expires"] < 4102444800
            and type(a.get("sent")) is int and 0 <= a["sent"] < 4102444800
            and all(isinstance(a.get(k), str) for k in ("event", "severity", "area"))
        ]
        return raw
    return None


def display_time(timestamp):
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone().strftime("%m-%d %H:%M")
