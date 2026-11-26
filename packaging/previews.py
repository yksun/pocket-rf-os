"""Render labeled screenshots without opening the framebuffer."""
from pathlib import Path
import time
from unittest.mock import patch

from PIL import Image, ImageDraw

from etherdeck import hat
from etherdeck.app import App, font

root = Path(__file__).resolve().parent.parent
app = App()
app.battery = 76


def shot(name):
    screen = app.draw()
    draw = ImageDraw.Draw(screen)
    draw.rectangle((277, 2, 318, 12), fill="#101820")
    draw.text((280, 1), "DEMO", font=font(10), fill="#ffc887", anchor="lt")
    screen.save(root / "screenshots" / (name + ".png"))
    return screen


app.confirmed_cap, app.home = 1, 2
with patch.object(hat, "available", return_value=True):
    screens = [shot("home")]
app.key("1", 1)
screens.append(shot("board-required"))
app.go("alerts")
now = int(time.time())
app.alert_source = "CACHE"
app.alerts = {"area": "IL", "time": now, "total": 1, "alerts": [
    {"event": "Example Weather Advisory", "severity": "Moderate", "area": "Demo",
     "expires": now + 5400, "sent": now}
]}
screens.append(shot("alerts"))
canvas = Image.new("RGB", (980, 180), "#0a1118")
for i, screen in enumerate(screens):
    canvas.paste(screen, (5 + 325 * i, 5))
(root / "dist").mkdir(exist_ok=True)
canvas.resize((1960, 360), Image.Resampling.NEAREST).save(root / "dist" / "pocket-rf-os-0.3.3-preview.png")
