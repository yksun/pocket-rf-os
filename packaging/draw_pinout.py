"""Render the numbered 14P pinout and interposer wiring."""
from PIL import Image, ImageDraw
from etherdeck.app import font

canvas = Image.new("RGB", (1260, 850), "#14212b")
draw = ImageDraw.Draw(canvas)
text_color, dim = "#ecf3f5", "#a9bac5"
teal, blue, orange = "#68e1bd", "#90baff", "#ffc887"


def text(x, y, value, size=19, color=text_color):
    draw.text((x, y), value, font=font(size), fill=color, anchor="lt")


def header(x, y, width, value, color):
    draw.rounded_rectangle((x, y, x + width, y + 40), 5, fill="#263b47")
    text(x + 13, y + 10, value, 21, color)


def rows(x, y, width, values):
    for i, (signal, target, color) in enumerate(values):
        yy = y + 35 * i
        if i % 2 == 0:
            draw.rectangle((x, yy, x + width, yy + 33), fill="#1b2c38")
        text(x + 12, yy + 8, signal, 18, color)
        text(x + (215 if width > 550 else 105), yy + 8, target, 17)


text(32, 23, "Micius 顶部 → JosephCGS 三合一原板", 34, teal)
text(32, 70, "有源转接原型   /   14P 物理针脚   /   未经实物验证", 20, dim)
header(32, 120, 438, "Micius → ESP32-S3", teal)
rows(32, 172, 438, [
    ("1", "USB D+ → GPIO20", teal), ("3", "USB D- → GPIO19", teal),
    ("4", "共地 GND", teal), ("6", "5VOUT，原型留空", orange), ("其余", "保持断开", dim),
])
text(43, 372, "顶部设为 USB4，原型先独立限流供电。", 19)
text(43, 406, "板侧供电脚先核对稳压器，避免反灌。", 19, orange)
text(43, 450, "14P 配对面的编号示意", 19, dim)
draw.rounded_rectangle((43, 480, 170, 737), 9, outline="#567080", width=2)
for index in range(14):
    pin = index + 1
    x, y = 55 + (index % 2) * 56, 491 + (index // 2) * 34
    accent = teal if pin in (1, 3, 4) else orange if pin in (2, 6) else dim
    draw.rounded_rectangle((x, y, x + 46, y + 27), 4, fill="#263b47", outline=accent)
    text(x + 12, y + 5, str(pin), 15, accent)
header(504, 120, 724, "JosephCGS 板物理针脚 → ESP32-S3", blue)
rows(504, 172, 724, [
    ("1   LoRa RESET", "GPIO9", blue), ("2   5VIN", "不接", orange),
    ("3   LoRa DIO0", "GPIO10", blue), ("4   GND", "共地", teal),
    ("5   其他", "不接", dim), ("6   供电位置", "先核对板上稳压器", orange),
    ("7   SPI SCK", "GPIO11", teal), ("8   nRF24 CE", "GPIO4", blue),
    ("9   SPI MOSI", "GPIO12", teal), ("10  nRF24 CSN", "GPIO5", blue),
    ("11  SPI MISO", "GPIO13", teal), ("12  CC1101 GDO0", "GPIO7", orange),
    ("13  LoRa NSS", "GPIO8", blue), ("14  CC1101 CSN", "GPIO6", orange),
])
draw.line((32, 766, 1228, 766), fill="#405766", width=2)
text(32, 787, "核对 1 号脚方向及短路。CS 上电保持高，nRF CE 保持低。", 20)
text(32, 818, "Pocket RF OS 0.3.0    /    zero-top-adapter", 16, dim)
canvas.save("docs/joseph-top-pinout.png")
