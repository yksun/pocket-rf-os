"""Read-only health and package integrity checks."""
import os
from pathlib import Path
import shutil
import subprocess
import time


def read(path, transform=int):
    try:
        return transform(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def health():
    free = read("/proc/meminfo", lambda info: {
        name: int(values.split()[0]) for row in info.splitlines()
        for name, _, values in [row.partition(":")] if name in ("MemAvailable", "MemTotal")
    }) or {}
    return {
        "time": time.strftime("%Y-%m-%d  %H:%M:%S"),
        "available": free.get("MemAvailable"),
        "total": free.get("MemTotal"),
        "disk": shutil.disk_usage("/").free,
        "temperature": read("/sys/class/thermal/thermal_zone0/temp"),
        "mhz": read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"),
        "load": os.getloadavg()[0],
    }


def package_integrity():
    try:
        report = subprocess.run(["dpkg", "--verify", "etherdeck"],
                                capture_output=True, text=True, timeout=5, check=False)
    except subprocess.TimeoutExpired:
        return "无法完成安装包校验", "校验超时"
    if report.returncode:
        return "无法完成安装包校验", (report.stderr or report.stdout).strip().split("\n")[-1][:100]
    matches = report.stdout.strip().splitlines()
    if matches:
        return f"发现 {len(matches)} 项文件差异", matches[0].split()[-1][-100:]
    return "已安装文件完整性通过", "dpkg 校验安装包记录"
