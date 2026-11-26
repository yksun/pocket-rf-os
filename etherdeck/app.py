"""EtherDeck's 320×170 interface and keypad navigation."""
from collections import deque
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

from . import bridge, observations
from .keys import Keyboard

NRF_CHANNELS = range(2, 81)
RADIOS = (
    ("CC", "CC1101", "Sub-GHz  ·  2-FSK",
     ("315.00 MHz", "433.92 MHz", "868.30 MHz", "915.00 MHz"), "#68e1bd"),
    ("NRF", "nRF24L01", "2.4 GHz  ·  信道活动",
     tuple(f"CH {ch:02}  /  {rate}" for rate in ("250 kbps", "1 Mbps", "2 Mbps") for ch in NRF_CHANNELS),
     "#8bbaff"),
    ("LORA", "LoRa", "SX127x  ·  点对点",
     tuple(f"{mhz} MHz  /  SF{sf}" for sf in range(7, 13) for mhz in ("433.50", "868.30", "915.00")),
     "#ffc887"),
)
ACTIONS = ("检测模块", "单次扫描", "接收测试消息", "发送测试消息", "连续观测")
BG, PANEL, TEXT, DIM, LINE = "#101820", "#1b2833", "#f2f6f8", "#a9b9c5", "#3b505f"
TEAL, AMBER = RADIOS[0][4], RADIOS[2][4]


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


def result(name, action, data):
    fields = data.split()
    if action == "PROBE" and not data:
        return "芯片响应正常", [], []
    if action == "TX" and not data:
        return "测试消息已发出", ["对端是否收到，请在接收端确认。"], []
    if action == "RX":
        if fields == ["timeout"]:
            return "5 秒内未收到测试消息", ["确认两端选择相同模块和参数。"], []
        if len(fields) == 4 and fields[0] == "packet":
            message = bytes.fromhex(fields[3]).decode("ascii")
            if not 1 <= len(message) <= 24 or not message.isprintable():
                raise ValueError("packet")
            lines = [message]
            if name != "NRF":
                lines.append(f"RSSI {int(fields[1])} dBm")
            if name == "LORA":
                lines.append(f"SNR {int(fields[2])} dB")
            return "收到测试消息", lines, []
    if action == "SCAN":
        values = [int(field) for field in fields]
        if name == "CC" and len(values) == 17 and all(-138 <= v <= -10 for v in values):
            index = values.index(max(values))
            return (f"峰值 {values[index]} dBm  /  {(index - 8) * 100:+d} kHz",
                    ["中心频率 ±800 kHz  ·  每格 100 kHz"], [v + 150 for v in values])
        if name == "NRF" and len(values) == 84 and all(0 <= v <= 8 for v in values):
            index = values.index(max(values))
            title = f"CH {index:02}  ·  {max(values)}/8 次繁忙" if max(values) else "本轮未检测到信道活动"
            return title, ["2400–2483 MHz  ·  信道活动样本"], values
        if name == "LORA" and len(values) == 2 and values[1] in (0, 1):
            return f"信号强度 {values[0]} dBm", ["检测到 LoRa 活动" if values[1] else "未检测到 LoRa 活动"], []
    raise ValueError("unexpected response")


class App:
    def __init__(self, port=None, storage=None):
        self.port = port
        self.storage = storage or observations.state_dir()
        self.history_file = self.storage / "rf-history.json"
        self.alert_file = self.storage / "nws-alerts.json"
        self.cancel_scan = threading.Event()
        self.scan_slot = threading.Event()
        self.frames = deque(maxlen=20)
        self.scan_summary = None
        self.sample = None
        self.notice = ""
        self.home = 0
        self.list_index = 0
        self.records = []
        self.alerts = None
        self.alert_source = "NWS"
        self.area = ""
        self.battery = None
        self.next_battery = 0
        self.page = "home"
        self.selected = self.action = 0
        self.profiles = [1, len(NRF_CHANNELS), 0]
        self.message = ""
        self.usb = None
        self.usb_status = "正在检查 USB"
        self.esc_down = self.tab_down = None
        self.esc_stopping_scan = False
        self.lock_until = 0
        self.view = ("", [], [])
        self.hardware = []
        self.hardware_note = ""
        self.job = None
        self.progress = 0
        self.reply = SimpleQueue()
        self.running = True
        self.dirty = True

    def go(self, page):
        self.page, self.dirty, self.notice = page, True, ""

    def start(self, task, operation):
        if self.job:
            return
        self.job, self.progress, self.dirty = task, 0, True

        def work():
            try:
                self.reply.put(("done", operation()))
            except (OSError, ValueError, bridge.BridgeError) as exc:
                self.reply.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def discover(self):
        def check():
            with bridge.Bridge(self.port) as link:
                return link.port, link.identity, link.version

        self.start("discover", check)

    def operate(self, action):
        if action == "RX":
            self.go("waiting")
        name = RADIOS[self.selected][0]
        profile, message = self.profiles[self.selected], self.message if action == "TX" else ""

        def run():
            data = bridge.radio(self.port, name, action, profile, message)
            return action, result(name, action, data)

        self.start("radio", run)

    def observation(self, view):
        _, title, _, profiles, _ = RADIOS[self.selected]
        heading, lines, samples = view
        self.sample = observations.record(title, profiles[self.profiles[self.selected]],
                                          heading, lines[0], samples)

    def live_scan(self):
        self.frames.clear()
        self.scan_summary = self.sample = None
        self.cancel_scan.clear()
        self.scan_slot.set()
        self.go("live")
        name = RADIOS[self.selected][0]
        profile = self.profiles[self.selected]

        def scan():
            with bridge.Bridge(self.port) as link:
                while not self.cancel_scan.is_set():
                    if not self.scan_slot.wait(0.2) or self.cancel_scan.is_set():
                        continue
                    self.scan_slot.clear()
                    data = result(name, "SCAN", link.ask(f"{name} SCAN {profile}", timeout=3))
                    self.reply.put(("sample", data))
                    self.cancel_scan.wait(0.22)

        self.start("live", scan)

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
        while True:
            try:
                status, value = self.reply.get_nowait()
            except Empty:
                return
            self.dirty = True
            if status == "progress":
                self.progress = value
                continue
            if status == "sample":
                self.observation(value)
                self.scan_summary = value
                self.frames.append(value[2])
                self.scan_slot.set()
                continue
            task, self.job = self.job, None
            if task == "live":
                self.go("live-result")
                self.notice = str(value) if status == "error" else "扫描已停止"
                continue
            if task == "save":
                self.notice = "已保存到信号历史" if status == "done" else "保存失败"
                continue
            if task == "hardware":
                if status == "done":
                    self.hardware = value
                else:
                    self.hardware_note = str(value)
                continue
            if task == "alerts":
                if status == "done":
                    self.alert_source, self.alerts, self.list_index = "NET", value, 0
                    self.notice = ""
                else:
                    self.alert_source = "CACHE" if self.alerts else "NWS"
                    self.notice = "刷新失败，请核对网络"
                continue
            if task == "discover":
                self.usb = value if status == "done" else None
                self.usb_status = f"USB  ·  {value[2]}" if self.usb else "USB 未就绪"
                self.usb_detail = "" if self.usb else value
            elif status == "error":
                self.view = ("操作未完成", [value], [])
                self.go("firmware-result" if task == "update" else "result")
            elif task == "update":
                self.usb = (*self.usb[:2], value)
                self.usb_status = f"USB  ·  {value}"
                self.view = ("固件已更新", [f"已重连并核对版本 {value}"], [])
                self.go("firmware-result")
            else:
                action, self.view = value
                self.sample = None
                if action == "SCAN":
                    self.observation(self.view)
                self.go("result")

    def key(self, key, now):
        if key == "TAB_DOWN":
            self.tab_down = now
            if self.job == "live":
                self.cancel_scan.set()
            self.lock_until = now + 1.2
        elif key == "TAB_UP":
            if self.tab_down is not None and now - self.tab_down < 0.5:
                self.lock_until = now + 1.2
            self.tab_down = None
        elif key == "ESC_DOWN":
            self.esc_down = now
            self.esc_stopping_scan = self.job == "live"
            if self.esc_stopping_scan:
                self.cancel_scan.set()
                self.dirty = True
        elif key == "ESC_UP":
            if self.esc_down is not None and now - self.esc_down >= 0.8 and self.job != "update":
                self.running = False
            elif self.esc_down is not None and not self.job and not self.esc_stopping_scan:
                parent = {"radio": "home", "result": "radio", "compose": "radio",
                          "send": "compose", "firmware": "home", "confirm-update": "firmware",
                          "firmware-result": "firmware", "live-result": "radio",
                          "history-detail": "history", "alert-detail": "alerts", "area": "alerts"}
                if self.page == "area" and self.alerts:
                    self.area = self.alerts["area"]
                self.go(parent.get(self.page, "home"))
            self.esc_down = None
            self.esc_stopping_scan = False
        elif self.job or (key == "ENTER" and (self.tab_down is not None or now < self.lock_until)):
            return
        elif self.page == "area":
            if key == "ENTER" and self.area in observations.STATES:
                self.go("alerts")
                self.refresh_alerts()
            elif key == "BACKSPACE":
                self.area = self.area[:-1]
            elif len(key) == 1 and key.isascii() and key.isalpha() and len(self.area) < 2:
                self.area += key.upper()
            self.dirty = True
        elif self.page == "compose":
            if key == "ENTER" and self.message.strip():
                self.go("send")
            elif key == "BACKSPACE":
                self.message = self.message[:-1]
            elif len(key) == 1 and 32 <= ord(key) <= 126 and len(self.message) < 24:
                self.message += key
            self.dirty = True
        else:
            self.navigate(key.lower())

    def navigate(self, key):
        step = 1 if key in ("down", "x") else -1 if key in ("up", "f") else 0
        if self.page == "home":
            if step:
                self.home = (self.home + step) % 7
                self.dirty = True
            elif key in ("left", "right", "z", "c"):
                self.home = (self.home + (3 if key in ("right", "c") else -3)) % 7
                self.dirty = True
            elif key in ("1", "2", "3", "4", "5", "6", "7", "enter", "u", "h", "a", "d"):
                shortcuts = {"h": 3, "a": 4, "d": 5, "u": 6}
                if key in shortcuts:
                    self.home = shortcuts[key]
                elif key.isdigit():
                    self.home = int(key) - 1
                if self.home < 3:
                    self.selected, self.action = self.home, 0
                    self.go("radio")
                elif self.home == 3:
                    self.records = observations.history(self.history_file)
                    self.list_index = 0
                    self.go("history")
                elif self.home == 4:
                    self.open_alerts()
                elif self.home == 5:
                    self.go("hardware")
                    self.diagnose()
                else:
                    self.go("firmware")
                    self.discover()
            elif key == "r":
                self.discover()
        elif self.page == "radio":
            if step:
                self.action = (self.action + step) % len(ACTIONS)
                self.dirty = True
            elif key in ("left", "right", "z", "c"):
                position = self.profiles[self.selected]
                slots = (4, len(NRF_CHANNELS), 3)[self.selected]
                first = position - position % slots
                delta = 1 if key in ("right", "c") else -1
                self.profiles[self.selected] = first + (position + delta) % slots
                self.dirty = True
            elif key == "b" and self.selected:
                slots = len(NRF_CHANNELS) if self.selected == 1 else 3
                count = len(RADIOS[self.selected][3])
                self.profiles[self.selected] = (self.profiles[self.selected] + slots) % count
                self.dirty = True
            elif key == "enter":
                if self.action < 3:
                    self.operate(("PROBE", "SCAN", "RX")[self.action])
                elif self.action == 4:
                    self.live_scan()
                elif self.selected == 0 and self.profiles[0] == 0:
                    self.view = ("315 MHz 仅接收", ["使用其他参数进行测试发送。"], [])
                    self.go("result")
                else:
                    self.message = ""
                    self.go("compose")
        elif self.page in ("result", "live-result") and key == "s" and self.sample:
            sample = self.sample
            self.start("save", lambda: observations.save(self.history_file, sample))
        elif self.page in ("history", "alerts"):
            items = self.records if self.page == "history" else self.alerts["alerts"] if self.alerts else []
            if step and items:
                self.list_index = (self.list_index + step) % len(items)
                self.dirty = True
            elif key == "enter" and items:
                self.go("history-detail" if self.page == "history" else "alert-detail")
            elif self.page == "alerts" and key == "r":
                self.refresh_alerts()
            elif self.page == "alerts" and key == "c":
                self.area = ""
                self.go("area")
        elif self.page == "hardware" and key == "r":
            self.diagnose()
        elif self.page == "send" and key == "y":
            self.operate("TX")
        elif self.page == "firmware":
            if key == "r":
                self.discover()
            elif key == "enter" and self.update_available():
                self.go("confirm-update")
        elif self.page == "confirm-update" and key == "y":
            args = self.usb
            self.go("updating")
            self.start("update", lambda: bridge.update(
                *args, lambda p: self.reply.put(("progress", p)) if p % 2 == 0 else None))

    def diagnose(self):
        self.hardware = []
        self.hardware_note = ""

        def check():
            results = []
            with bridge.Bridge(self.port) as link:
                for index, (name, label, *_) in enumerate(RADIOS):
                    try:
                        link.ask(f"{name} PROBE {self.profiles[index]}")
                    except bridge.BridgeError as exc:
                        results.append((label, str(exc)))
                    else:
                        results.append((label, "模块响应正常"))
            return results

        self.start("hardware", check)

    def bundled_version(self):
        try:
            return bridge.pack()[0]
        except bridge.BridgeError:
            return None

    def update_available(self):
        bundled = self.bundled_version()
        return (bool(self.usb and bundled) and
                bridge.version_tuple(bundled) > bridge.version_tuple(self.usb[2]))

    def draw(self):
        im = Image.new("RGB", (320, 170), BG)
        draw = ImageDraw.Draw(im)

        def text(x, y, value, size=13, color=TEXT, right=308):
            face = font(size)
            if draw.textlength(value, font=face) > right - x:
                while value and draw.textlength(value + "…", font=face) > right - x:
                    value = value[:-1]
                value += "…"
            draw.text((x, y), value, font=face, fill=color, anchor="lt")

        def cards(labels):
            for i, (label, detail, tint) in enumerate(labels):
                x, y = 10 + i % 3 * 102, 35 + i // 3 * 36
                draw.rounded_rectangle((x, y, x + 95, y + 31), 4,
                                       fill=PANEL if i == self.home else BG,
                                       outline=tint if i == self.home else LINE)
                text(x + 5, y + 4, label, 13, TEXT, x + 92)
                text(x + 5, y + 19, detail, 10, DIM, x + 92)

        def listing(items, field):
            start = self.list_index // 3 * 3
            for i, item in enumerate(items[start:start + 3], start=start):
                y = 60 + (i - start) * 26
                if i == self.list_index:
                    draw.rounded_rectangle((10, y, 309, y + 23), 4, fill=PANEL, outline=TEAL)
                text(17, y + 5, field(item), 13)

        def lines_at(y, lines):
            for i, line in enumerate(lines):
                text(12, y + 19 * i, line, 13, DIM)

        name, title, _, profiles, color = RADIOS[self.selected]
        profile = profiles[self.profiles[self.selected]]
        footer = "ESC 返回"
        if self.page == "home":
            text(12, 7, "Pocket RF OS", 22, TEAL)
            text(184, 13, self.usb_status, 11, DIM, 278)
            if self.battery is not None:
                text(278, 13, f"{self.battery}%", 11, DIM)
            cards([(label, f"{i + 1}  {band}", tint)
                   for i, ((_, label, _, _, tint), band) in
                   enumerate(zip(RADIOS, ("Sub-GHz", "2.4 GHz", "SX127x")))] +
                  [("信号历史", "4  RF", TEAL), ("气象告警", "5  NWS", TEAL),
                   ("硬件检测", "6  USB", TEAL), ("桥接固件", "7  OTA", TEAL)])
            footer = "1–7 打开    F/X 选择    R 重连    长按 ESC 退出"
        elif self.page == "radio":
            text(12, 8, title, 20, color)
            text(135, 12, "<  " + profile + "  >", 14, TEXT)
            for index, label in enumerate(ACTIONS):
                y = 34 + 21 * index
                if index == self.action:
                    draw.rounded_rectangle((10, y, 309, y + 19), 5, fill=PANEL, outline=color)
                text(22, y + 3, label)
            footer = ("F/X 选项    Z/C 频率    OK 执行    ESC 返回" if name == "CC" else
                      "F/X 选项    Z/C 频率    B " + ("速率" if name == "NRF" else "SF") + "    OK 执行")
        elif self.page in ("compose", "send"):
            text(12, 9, "测试消息" if self.page == "compose" else "确认单次发送", 19, color)
            text(12, 38, f"{title}  ·  {profile}", 13, DIM)
            draw.rounded_rectangle((10, 62, 309, 96), 5, fill=PANEL, outline=LINE)
            text(19, 73, self.message or "输入 ASCII 文本", 14)
            if self.page == "compose":
                text(12, 109, f"{len(self.message)} / 24", 13, DIM)
                footer = "OK 继续    DEL 删除    ESC 返回"
            else:
                text(12, 109, "确保已连接匹配频段的天线。", 13, DIM)
                footer = "Y 发送    ESC 返回"
        elif self.page == "waiting":
            text(12, 9, "正在接收", 20, color)
            text(12, 53, f"{title}  ·  {profile}", 14)
            text(12, 83, "等待另一台 Pocket RF OS 发送  ·  5 秒", 13, DIM)
            footer = "长按 ESC 退出"
        elif self.page in ("live", "live-result"):
            text(12, 8, "连续观测", 19, color)
            text(125, 12, f"{title}  {profile}", 12, DIM)
            if self.scan_summary is not None:
                heading, details, bars = self.scan_summary
                text(12, 36, heading, 14)
                text(12, 55, details[0], 11, DIM)
                if bars:
                    maximum = 140 if name == "CC" else 8
                    for i, frame in enumerate(reversed(self.frames)):
                        y = 76 + 3 * i
                        for j, value in enumerate(frame):
                            if value:
                                x = 12 + j * 296 // len(frame)
                                end = 11 + (j + 1) * 296 // len(frame)
                                level = min(1, value / maximum)
                                draw.rectangle((x, y, end, y + 2), fill=(
                                    int(36 + 180 * level), int(61 + 105 * level), int(83 - 47 * level)))
                else:
                    text(12, 82, f"最近 {len(self.frames)} 次观测", 13, DIM)
            else:
                text(12, 45, self.notice or "等待真实采样…", 13, DIM)
            footer = ("正在停止…" if self.cancel_scan.is_set() else "ESC 停止观测") if self.page == "live" else (
                "S 保存最后一帧    ESC 返回" if self.sample else "ESC 返回")
        elif self.page in ("history", "history-detail"):
            text(12, 8, "信号历史", 20, TEAL)
            if self.page == "history-detail" and self.records:
                entry = self.records[self.list_index]
                text(12, 38, entry["title"], 15)
                lines_at(63, [f"RF  {entry['radio']}  {entry['profile']}",
                              entry["detail"], observations.display_time(entry["time"])])
            elif self.records:
                text(12, 37, f"RF  ·  已保存 {len(self.records)} 项", 12, DIM)
                listing(self.records, lambda e: f"{e['radio']}  {e['title']}")
                footer = "F/X 浏览    OK 详情    ESC 返回"
            else:
                lines_at(46, ["尚无观测记录", "在扫描结果页按 S 保存。"])
        elif self.page in ("alerts", "alert-detail", "area"):
            text(12, 8, "NWS 气象告警", 20, AMBER)
            if self.page == "area":
                lines_at(44, ["输入美国州或地区代码，如 IL", f"地区  {self.area or '__'}"])
                footer = "OK 请求    DEL 删除    ESC 返回"
            elif self.page == "alert-detail":
                item = self.alerts["alerts"][self.list_index]
                text(12, 37, item["event"], 15)
                expired = "  已过期" if item["expires"] <= time.time() else ""
                lines_at(59, [f"{self.alert_source}  ·  {item['severity'] or 'Unknown'}{expired}",
                              item["area"], f"发布  {observations.display_time(item['sent'])}" if item["sent"] else "发布时间未知",
                              f"有效至  {observations.display_time(item['expires'])}"])
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
        elif self.page == "hardware":
            text(12, 8, "硬件检测", 20, TEAL)
            text(12, 37, "ADV / JosephCGS  ·  USB CDC", 13, DIM)
            for i, (label, detail) in enumerate(self.hardware):
                text(12, 64 + i * 22, label, 14)
                text(112, 66 + i * 22, detail, 12, DIM)
            if not self.hardware:
                text(12, 65, self.hardware_note or "正在检查模块…", 13, DIM)
            footer = "R 重新检测    ESC 返回"
        elif self.page in ("result", "firmware-result"):
            heading, lines, bars = self.view
            text(12, 8, title if self.page == "result" else "桥接固件", 19, color)
            text(12, 39, heading, 16)
            for i, item in enumerate(lines):
                text(12, 65 + 20 * i, item, 13, DIM)
            if bars:
                maximum = 140 if name == "CC" else 8
                baseline = 137
                draw.line((12, baseline, 307, baseline), fill=LINE)
                for i, sample in enumerate(bars):
                    x = 12 + i * 296 // len(bars)
                    end = 11 + (i + 1) * 296 // len(bars)
                    height = max(0, min(44, round(sample * 44 / maximum)))
                    if height:
                        draw.rectangle((x, baseline - height, max(x, end - 1), baseline - 1), fill=color)
        else:
            text(12, 9, "桥接固件", 20, TEAL)
            text(12, 37, "Cardputer ADV  /  JosephCGS 三合一板", 13, DIM)
            if self.page == "firmware":
                text(12, 65, f"USB 版本  {self.usb[2] if self.usb else '未连接'}", 14)
                bundled = self.bundled_version()
                text(12, 88, f"随应用版本  {bundled or '不可用'}", 14)
                if not self.usb and not self.job:
                    detail = getattr(self, "usb_detail", "")
                    text(12, 113, detail or "接入已刷好桥接固件的 ADV。", 12, AMBER)
                footer = ("OK 检查更新    R 重连    ESC 返回" if self.update_available()
                          else "R 重连    ESC 返回")
            elif self.page == "confirm-update":
                text(12, 69, f"{self.usb[2]}  →  {self.bundled_version()}", 18)
                text(12, 106, "保持 USB 连接并给 Micius 接上电源。", 14, AMBER)
                footer = "Y 开始更新    ESC 返回"
            else:
                text(12, 69, f"正在更新  {self.progress}%", 18)
                draw.rounded_rectangle((12, 103, 308, 111), 3, fill=PANEL)
                if self.progress:
                    draw.rectangle((12, 103, 12 + self.progress * 296 // 100, 111), fill=TEAL)
                footer = "保持 USB 连接  ·  完成后检查版本"
        if self.job == "radio" and self.page != "waiting":
            footer = "正在与模块通信…"
        if self.sample and self.page == "result":
            footer = "S 保存观测    ESC 返回"
        if self.notice and self.page in ("result", "live-result", "alerts"):
            footer = self.notice + ("    ESC 返回" if len(self.notice) < 15 else "")
        draw.line((10, 145, 309, 145), fill=LINE)
        text(12, 153, footer, 11, DIM)
        return im

    def run(self):
        keyboard = Keyboard()
        try:
            if not keyboard.fds:
                raise OSError("CardputerZero keyboard missing or inaccessible")
            with open(find_fb(), "r+b", buffering=0) as dev:
                with mmap.mmap(dev.fileno(), 320 * 170 * 2) as display:
                    self.discover()
                    while self.running:
                        self.poll()
                        now = time.monotonic()
                        if now >= self.next_battery:
                            self.next_battery = now + 15
                            try:
                                battery = int(Path("/sys/class/power_supply/bq27220-0/capacity").read_text())
                            except (OSError, ValueError):
                                battery = None
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
                        if (self.esc_down is not None and now - self.esc_down >= 0.8
                                and self.job != "update"):
                            self.running = False
                    display[:] = bytes(len(display))
        finally:
            self.cancel_scan.set()
            for fd in keyboard.fds:
                os.close(fd)
