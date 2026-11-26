"""Build the APPLaunch icon at twice the target size before downsampling."""
from pathlib import Path
from PIL import Image, ImageDraw

image = Image.new("RGBA", (200, 200))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((7, 7, 192, 192), 38, fill="#101820", outline="#406257", width=3)
draw.rounded_rectangle((34, 114, 166, 145), 9, fill="#233b42")
for box in [(43, 40, 157, 154), (61, 59, 139, 137), (79, 78, 121, 120)]:
    draw.arc(box, 215, 325, fill="#68e1bd", width=7)
draw.ellipse((95, 103, 105, 113), fill="#68e1bd")
for x, color in ((62, "#68e1bd"), (100, "#8bbaff"), (138, "#ffc887")):
    draw.ellipse((x - 5, 125, x + 5, 135), fill=color)
image.resize((100, 100), Image.Resampling.LANCZOS).save(Path(__file__).with_name("etherdeck_100.png"))
