"""Render labeled screenshots without opening the framebuffer or USB."""
from pathlib import Path
import time

from PIL import Image, ImageDraw

from etherdeck.app import App, font, result

root = Path(__file__).resolve().parent.parent
app = App()
app.usb_status, app.battery = "USB  ·  0.2.0", 76


def shot(name):
    screen = app.draw()
    draw = ImageDraw.Draw(screen)
    draw.rectangle((277, 2, 318, 12), fill="#101820")
    draw.text((280, 1), "DEMO", font=font(10), fill="#ffc887", anchor="lt")
    screen.save(root / "screenshots" / (name + ".png"))
    return screen


screens = [shot("home")]
app.go("live")
for i in range(20):
    values = [-106 + max(0, 54 - 8 * abs(col - (4 + i // 3))) for col in range(17)]
    app.scan_summary = result("CC", "SCAN", " ".join(map(str, values)))
    app.frames.append(app.scan_summary[2])
screens.append(shot("waterfall"))
app.go("history")
app.observation(app.scan_summary)
app.records = [app.sample]
screens.append(shot("history"))
app.go("alerts")
now = int(time.time())
app.alert_source = "CACHE"
app.alerts = {"area": "IL", "time": now, "total": 1, "alerts": [
    {"event": "Example Weather Advisory", "severity": "Moderate", "area": "Demo",
     "expires": now + 5400, "sent": now}
]}
screens.append(shot("alerts"))
canvas = Image.new("RGB", (660, 360), "#0a1118")
for i, screen in enumerate(screens):
    canvas.paste(screen, (5 + 330 * (i % 2), 5 + 180 * (i // 2)))
canvas.resize((1320, 720), Image.Resampling.NEAREST).save(root / "dist" / "pocket-rf-os-0.2.0-preview.png")
