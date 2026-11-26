# Pocket RF OS

Pocket RF OS 0.3.3 是 M5Stack CardputerZero 的官方 CAP 功能首页。U219 和 U214 各有两个工具，在系统已有的原厂工具中工作。退出工具回到 Pocket RF OS。

| 按键 | 功能 | 所需板 |
| --- | --- | --- |
| 1 | Sub-GHz 聊天 | Cap CC1101 & NFC · U219 |
| 2 | NFC 工具 | Cap CC1101 & NFC · U219 |
| 3 | LoRa 聊天 | Cap LoRa-1262 · U214 |
| 4 | GPS 定位 | Cap LoRa-1262 · U214 |
| 5 | NWS 气象告警 | 共用 |
| 6 | 顶部 SPI、GPIO 模式和供电状态 | 共用 |
| 7 | 确认当前扩展板 | 共用 |
| 8 | 内存、电量、存储、CPU 与温度 | 共用 |
| 9 | 应用文件完整性 | 共用 |

先关机再换板。开机后第一次打开对应工具时，按 **Y** 确认机身上的板并打开工具。本次运行中按数字键或 **OK** 直接打开。选择另一块板的功能时会显示所需型号。顶部接口保持 **GPIO** 模式。若原厂工具显示板未供电，检查系统 **Settings → ExtPort** 的顶部 5V 选项。 [CardputerZero 官方使用说明](https://docs.m5stack.com/en/compute/cardputerzero/usage)

**F / X** 上下移动，**Z / C** 左右移动。短按 ESC 返回，长按 ESC 退出。气象详情用 F/X 滚动、Z/C 翻页。告警可按地区手动更新并离线查看已保存快照。

## 安装

下载 [0.3.3 Debian 包](https://github.com/yksun/pocket-rf-os/releases/tag/v0.3.3)，在 CardputerZero 执行：

```bash
sudo apt install ./etherdeck_0.3.3_all.deb
systemctl --user restart APPLaunch
/usr/share/APPLaunch/bin/etherdeck --check
```

旧包可以原地升级。硬件工具使用系统已有的原厂组件。缺失时首页显示缺少工具，可从原厂发行页安装。 [功能、原厂组件和验收方法](docs/top-cap.md)

## 开发

运行 `python3 -m unittest discover -s tests`，再在 Debian 上运行 `sh packaging/build_deb.sh`。预览可用 `PYTHONPATH=. python3 packaging/previews.py` 重新生成。
