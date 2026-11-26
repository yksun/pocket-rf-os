"""Pocket RF OS interface for the two official CardputerZero CAPs."""
from functools import lru_cache
import mmap
import os
from pathlib import Path
from queue import Empty, SimpleQueue
import select
import threading
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import device, hat, observations
from .keys import Keyboard

BG, PANEL, TEXT, DIM, LINE = "#101820", "#1b2833", "#f2f6f8", "#a9b9c5", "#3b505f"
TEAL, AMBER = "#68e1bd", "#ffc887"


def find_fb():
    preferred = os.getenv("LV_LINUX_FBDEV_DEVICE")
    if preferred:
        return preferred
    try:
        for row in Path("/proc/fb").read_text().splitlines():
            index, _, name = row.partition(" ")
            if "st7789" in name.lower():
                return "/dev/fb" + index
    except OSError:
        pass
    return "/dev/fb_lcd" if Path("/dev/fb_lcd").exists() else "/dev/fb0"


@lru_cache
def font(size):
    for name, index in (
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 2),
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
    ):
        if Path(name).is_file():
            return ImageFont.truetype(name, size, index=index)
    return ImageFont.load_default(size=size)


@lru_cache(maxsize=256)
def text_tile(value, size, limit):
    face = font(size)
    if face.getlength(value) > limit:
        while value and face.getlength(value + "…") > limit:
            value = value[:-1]
        value += "…"
    bounds = face.getbbox(value, anchor="lt")
    tile = Image.new("L", (max(1, bounds[2]), max(1, bounds[3])))
    ImageDraw.Draw(tile).text((0, 0), value, font=face, fill=255, anchor="lt")
    return tile


def wrap_alert(body):
    face = font(11)
    lines = []
    for paragraph in body.split("\n"):
        while face.getlength(paragraph) > 296:
            lo, hi = 1, len(paragraph)
            while lo + 1 < hi:
                mid = (lo + hi) // 2
                if face.getlength(paragraph[:mid]) <= 296:
                    lo = mid
                else:
                    hi = mid
            split = paragraph.rfind(" ", 0, lo + 1)
            end = split if split > 0 else lo
            lines.append(paragraph[:end])
            paragraph = paragraph[end:].lstrip()
        lines.append(paragraph)
    return lines


class App:
    def __init__(self, storage=None):
        self.page = "home"
        self.home = 0
        self.confirmed_cap = None
        self.required_cap = 0
        self.pending_tool = None
        self.launch_target = None
        self.notice = ""
        self.hat_data = self.system_info = self.integrity = None
        self.storage = storage or observations.state_dir()
        self.alert_file = self.storage / "nws-alerts.json"
        self.alerts = None
        self.alert_source = "NWS"
        self.area = ""
        self.list_index = self.alert_scroll = 0
        self.alert_lines = []
        self.battery = None
        self.next_battery = 0
        self.esc_down = self.tab_down = None
        self.lock_until = 0
        self.job = None
        self.reply = SimpleQueue()
        self.running = self.dirty = True

    def go(self, page):
        self.page, self.dirty, self.notice = page, True, ""

    def start(self, task, operation):
        if self.job:
            return
        self.job, self.dirty = task, True

        def work():
            try:
                self.reply.put((True, operation()))
            except (OSError, ValueError) as exc:
                self.reply.put((False, str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def open_alerts(self):
        self.alerts = observations.cached(self.alert_file)
        self.alert_source = "CACHE" if self.alerts else "NWS"
        self.area = self.alerts["area"] if self.alerts else ""
        self.list_index = 0
        self.go("alerts")

    def refresh_alerts(self):
        if self.area not in observations.STATES:
            self.go("area")
            return
        area = self.area
        self.start("alerts", lambda: observations.fetch(area, self.alert_file))

    def poll(self):
        try:
            ok, value = self.reply.get_nowait()
        except Empty:
            return
        task, self.job = self.job, None
        self.dirty = True
        if task == "system":
            self.system_info = value if ok else None
        elif task == "integrity":
            self.integrity = value if ok else ("校验不可用", str(value))
        elif task == "hat":
            self.hat_data = value if ok else None
        elif task == "alerts":
            if ok:
                self.alert_source, self.alerts, self.list_index = "NET", value, 0
                self.notice = ""
            else:
                self.alert_source = "CACHE" if self.alerts else "NWS"
                self.notice = "刷新失败，请核对网络"

    def tool(self, index):
        self.required_cap = index // 2
        if self.confirmed_cap != self.required_cap:
            self.pending_tool = index
            self.go("cap-confirm" if self.confirmed_cap is None else "cap-required")
            return
        if hat.port_mode() != "GPIO":
            self.notice = "请在 ExtPort 确认顶部 GPIO 模式"
        else:
            _, command = hat.tool(index)
            error = hat.tool_error(command)
            if error:
                self.notice = error
            else:
                self.launch_target = command
                self.running = False
        self.dirty = True

    def key(self, key, now):
        if key == "TAB_DOWN":
            self.tab_down = now
            self.lock_until = now + 1.2
        elif key == "TAB_UP":
            if self.tab_down is not None and now - self.tab_down < 0.5:
                self.lock_until = now + 1.2
            self.tab_down = None
        elif key == "ESC_DOWN":
            self.esc_down = now
        elif key == "ESC_UP":
            if self.esc_down is not None and now - self.esc_down >= 0.8:
                self.running = False
            elif self.esc_down is not None and not self.job:
                if self.page == "area" and self.alerts:
                    self.area = self.alerts["area"]
                parent = {"alert-detail": "alerts", "area": "alerts"}
                self.go(parent.get(self.page, "home"))
                self.pending_tool = None
            self.esc_down = None
        elif self.job or (key == "ENTER" and (self.tab_down is not None or now < self.lock_until)):
            return
        elif self.page == "area":
            if key == "ENTER" and self.area in observations.STATES:
                self.go("alerts")
                self.refresh_alerts()
            elif key in ("BACKSPACE", "DELETE"):
                self.area = self.area[:-1]
            elif len(key) == 1 and key.isascii() and key.isalpha() and len(self.area) < 2:
                self.area += key.upper()
            self.dirty = True
        else:
            self.navigate(key.lower())

    def navigate(self, key):
        step = 1 if key in ("down", "x") else -1 if key in ("up", "f") else 0
        move_x = 1 if key in ("right", "c") else -1 if key in ("left", "z") else 0
        if self.page == "home":
            if step or move_x:
                row, col = divmod(self.home, 3)
                self.home = min(2, max(0, row + step)) * 3 + min(2, max(0, col + move_x))
                self.notice = ""
                self.dirty = True
            elif key == "enter" or key in "123456789" and len(key) == 1:
                if key != "enter":
                    self.home = int(key) - 1
                if self.home < 4:
                    self.tool(self.home)
                elif self.home == 4:
                    self.open_alerts()
                elif self.home == 5:
                    self.go("hat")
                    self.start("hat", hat.status)
                elif self.home == 6:
                    self.go("cap-settings")
                elif self.home == 7:
                    self.go("system")
                    self.start("system", device.health)
                else:
                    self.go("integrity")
                    self.start("integrity", device.package_integrity)
        elif self.page == "cap-settings" and key in ("1", "2"):
            self.required_cap = int(key) - 1
            self.pending_tool = None
            self.go("cap-confirm" if self.confirmed_cap in (None, self.required_cap) else "cap-required")
        elif self.page == "cap-confirm" and key == "y":
            if hat.port_mode() != "GPIO":
                self.notice = "请在 ExtPort 确认顶部 GPIO 模式"
                self.dirty = True
                return
            self.confirmed_cap = self.required_cap
            index, self.pending_tool = self.pending_tool, None
            self.go("home")
            if index is not None:
                self.tool(index)
        elif self.page == "alerts":
            items = self.alerts["alerts"] if self.alerts else []
            if step and items:
                self.list_index = (self.list_index + step) % len(items)
                self.dirty = True
            elif key == "enter" and items:
                self.go("alert-detail")
                self.alert_scroll = 0
                item = items[self.list_index]
                issued = observations.display_time(item["sent"]) if item["sent"] else "未知"
                body = (f"发布 {issued}\n范围 {item['area']}\n\n" +
                        (observations.alert_text(item) or "这份快照没有正文。返回后按 R 重新获取。"))
                self.alert_lines = wrap_alert(body)
            elif key == "r":
                self.refresh_alerts()
            elif key == "c":
                self.area = ""
                self.go("area")
        elif self.page == "alert-detail" and (step or move_x):
            self.alert_scroll = min(max(0, len(self.alert_lines) - 5),
                                    max(0, self.alert_scroll + (step or 5 * move_x)))
            self.dirty = True
        elif key == "r":
            if self.page == "hat":
                self.start("hat", hat.status)
            elif self.page == "system":
                self.start("system", device.health)
            elif self.page == "integrity":
                self.start("integrity", device.package_integrity)

    def draw(self):
        im = Image.new("RGB", (320, 170), BG)
        draw = ImageDraw.Draw(im)

        def text(x, y, value, size=13, color=TEXT, right=308):
            tile = text_tile(value, size, right - x)
            im.paste(color, (x, y, x + tile.width, y + tile.height), tile)

        def lines_at(y, lines):
            for i, line in enumerate(lines):
                text(12, y + 19 * i, line, 13, DIM)

        def listing(items, field):
            start = self.list_index // 3 * 3
            for i, item in enumerate(items[start:start + 3], start):
                y = 60 + (i - start) * 26
                if i == self.list_index:
                    draw.rounded_rectangle((10, y, 309, y + 23), 4, fill=PANEL, outline=TEAL)
                text(17, y + 5, field(item), 13)

        footer = self.notice or "ESC 返回"
        if self.page == "home":
            text(12, 7, "Pocket RF OS", 22, TEAL)
            cap = "选择 CAP" if self.confirmed_cap is None else hat.CAP_IDS[self.confirmed_cap]
            text(211, 13, cap, 11, DIM)
            if self.battery is not None:
                text(278, 13, f"{self.battery}%", 11, DIM)
            labels = [(hat.tool(i)[0], hat.CAP_IDS[i // 2]) for i in range(4)]
            labels += [("气象告警", "NWS"), ("硬件检测", "SPI"), ("扩展板", "CAP"),
                       ("设备状态", "日常"), ("完整性", "诊断")]
            for i, (label, detail) in enumerate(labels):
                x, y = 10 + i % 3 * 102, 35 + i // 3 * 36
                draw.rounded_rectangle((x, y, x + 95, y + 31), 4, fill=PANEL if i == self.home else BG,
                                       outline=TEAL if i == self.home else LINE)
                text(x + 5, y + 4, label, 13, TEXT, x + 92)
                if i < 4:
                    detail = "就绪" if self.confirmed_cap == i // 2 and hat.available(hat.tool(i)[1]) else "需 " + detail
                text(x + 5, y + 19, f"{i + 1}  {detail}", 10, DIM, x + 92)
            footer = self.notice or "1–9 打开   F/X 上下   Z/C 左右   长按 ESC 退出"
        elif self.page in ("cap-confirm", "cap-required"):
            name, detail, _ = hat.CAPS[self.required_cap]
            text(12, 8, name, 20, TEAL)
            text(12, 37, detail, 13, DIM)
            if self.page == "cap-confirm":
                lines_at(63, ["确认本次开机已安装这块板。", "更换顶部板之前请关机。"])
                footer = self.notice or "Y 确认    ESC 返回"
            else:
                lines_at(63, [f"此功能需要 {hat.CAP_IDS[self.required_cap]}。",
                              f"本次已确认 {hat.CAP_IDS[self.confirmed_cap]}。",
                              "请关机换板，再开机确认。"])
        elif self.page == "cap-settings":
            text(12, 8, "扩展板", 20, TEAL)
            selected = "未确认" if self.confirmed_cap is None else hat.CAP_IDS[self.confirmed_cap]
            lines_at(43, ["1  U219：Sub-GHz 聊天 / NFC", "2  U214：LoRa 聊天 / GPS",
                          "本次：" + selected, "关机后再换板。"])
            footer = "1 / 2 选择    ESC 返回"
        elif self.page == "hat":
            text(12, 8, "顶部接口检测", 20, TEAL)
            lines_at(42, hat.summary(self.hat_data) if self.hat_data is not None else ["正在读取主机状态…"])
            footer = "R 刷新    ESC 返回"
        elif self.page == "system":
            text(12, 8, "设备状态", 20, TEAL)
            stats = self.system_info
            if stats:
                available = stats["available"]
                mem = f"{available // 1024}/{stats['total'] // 1024} MiB" if available and stats["total"] else "未知"
                frequency = f"{stats['mhz'] / 1000:.0f} MHz" if stats["mhz"] else "未知"
                temperature = f"{stats['temperature'] / 1000:.1f} °C" if stats["temperature"] is not None else "未知"
                lines_at(37, [stats["time"], f"CPU {frequency}  ·  {temperature}  ·  负载 {stats['load']:.2f}",
                              f"可用内存 {mem}", f"存储剩余 {stats['disk'] / 2**30:.1f} GiB",
                              f"电量 {self.battery}%" if self.battery is not None else "电量未知"])
            else:
                text(12, 40, "正在读取设备状态…" if self.job else "设备状态不可用", 13, DIM)
            footer = "R 刷新    ESC 返回"
        elif self.page == "integrity":
            text(12, 8, "应用文件完整性", 20, TEAL)
            lines_at(42, self.integrity or ("正在校验…",))
            footer = "R 重新校验    ESC 返回"
        elif self.page in ("alerts", "alert-detail", "area"):
            text(12, 8, "NWS 气象告警", 20, AMBER)
            if self.page == "area":
                lines_at(44, ["输入美国州或地区代码，如 IL", f"地区  {self.area or '__'}"])
                footer = "OK 请求    DEL 删除    ESC 返回"
            elif self.page == "alert-detail":
                item = self.alerts["alerts"][self.list_index]
                text(12, 32, item["event"], 14)
                expired = "  已过期" if item["expires"] <= time.time() else ""
                text(12, 50, f"{self.alert_source}  {item['severity']}  至 {observations.display_time(item['expires'])}{expired}", 11, AMBER)
                rows = self.alert_lines[self.alert_scroll:self.alert_scroll + 5]
                for i, line in enumerate(rows):
                    text(12, 67 + 14 * i, line, 11)
                footer = f"F/X 滚动  Z/C 翻页  {self.alert_scroll + 1}/{len(self.alert_lines)}  ESC 返回"
            else:
                footer = "R 刷新    C 地区    OK 详情    ESC 返回"
                if self.alerts:
                    tag = self.alert_source
                    if time.time() - self.alerts["time"] > 900:
                        tag = "CACHE 旧"
                    text(12, 36, f"{tag} · {self.alerts['area']}  {observations.display_time(self.alerts['time'])}"
                                  f"  ·  {self.alerts['total']} 条", 12, DIM)
                    if self.alerts["alerts"]:
                        listing(self.alerts["alerts"], lambda item: (
                            ("[过期] " if item["expires"] <= time.time() else "") + item["event"]))
                    else:
                        lines_at(66, ["此快照未列出有效告警。"])
                else:
                    lines_at(48, ["选择地区后手动查询。", "来源：美国国家气象局"])
                if self.job == "alerts":
                    footer = "正在请求 NWS…"
        draw.line((10, 145, 309, 145), fill=LINE)
        text(12, 153, self.notice or footer, 11, DIM)
        return im

    def run(self):
        keyboard = Keyboard()
        try:
            if not keyboard.fds:
                raise OSError("CardputerZero keyboard missing or inaccessible")
            with open(find_fb(), "r+b", buffering=0) as dev:
                with mmap.mmap(dev.fileno(), 320 * 170 * 2) as display:
                    while self.running:
                        self.poll()
                        now = time.monotonic()
                        if now >= self.next_battery:
                            self.next_battery = now + 15
                            battery = device.read("/sys/class/power_supply/bq27220-0/capacity")
                            if battery != self.battery or self.page in ("alerts", "alert-detail"):
                                self.battery, self.dirty = battery, True
                        if self.dirty:
                            pixels = np.asarray(self.draw(), dtype=np.uint16)
                            packed = ((pixels[:, :, 0] >> 3) << 11 |
                                      (pixels[:, :, 1] >> 2) << 5 | pixels[:, :, 2] >> 3)
                            display[:] = packed.astype("<u2").tobytes()
                            self.dirty = False
                        ready, _, _ = select.select(keyboard.fds, [], [], 0.05)
                        now = time.monotonic()
                        for key in keyboard.read(ready):
                            self.key(key, now)
                            if not self.running:
                                break
                        if self.esc_down is not None and now - self.esc_down >= 0.8:
                            self.running = False
                    display[:] = bytes(len(display))
        finally:
            for fd in keyboard.fds:
                os.close(fd)
