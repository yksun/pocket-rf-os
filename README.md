# Pocket RF OS

Pocket RF OS 是 CardputerZero 的 APPLaunch 应用。0.2.1 默认操作顶部 CAP 接口。

| 顶部板 | 主页入口 |
| --- | --- |
| M5Stack Cap CC1101（U219） | 1 → SubG Chat 或 NFC。调用已安装的原厂原生应用。 |
| M5Stack Cap LoRa-1262（U214） | 2 → LoRa 或 GPS。调用已安装的原厂原生应用。 |
| JosephCGS ADV 三合一板 | 3 → 接线诊断。原板与 Zero 有 I²C 和 UART 引脚冲突，运行射频功能需先重新布线。 |

先关机，再更换顶部扩展板。启动原厂工具前确认机身上的板与选择一致。Pocket RF OS 使用原厂应用现有的启动权限和驱动，原厂工具退出后返回 APPLaunch。原厂工具及驱动请从 CardputerZero 软件商店或其发行页安装。 [U219 SubG Chat](https://github.com/CardputerZero/Cap-CC1101-SubG-Chat/releases) · [U214 LoRa](https://github.com/CardputerZero/Cap-LoRa-1262/releases)

[顶部接口兼容性与实测引脚](docs/top-cap.md)

## 可选的 ADV USB 桥接模式

已有独立 ADV 桥接器时，在 Micius 本机终端运行 `/usr/share/APPLaunch/bin/etherdeck --transport usb`。以下三模块功能适用于这个模式。

| 模块 | 可用操作 |
| --- | --- |
| CC1101 | 芯片检测、四个中心频率的 17 点 RSSI 扫描、2-FSK 测试消息和接收 RSSI。315 MHz 预设仅接收。其余预设为 433.92、868.30、915.00 MHz。 |
| nRF24L01 / nRF24L01+ | 芯片检测、2400–2483 MHz 信道活动柱状图、CH 02–80 测试消息。支持 1 和 2 Mbps，Plus 芯片另支持 250 kbps。活动图显示每个信道 8 次采样中检测到活动的次数。 |
| LoRa（SX127x） | 芯片检测、RSSI 和 LoRa 信道活动检测、点对点测试消息、接收 RSSI / SNR。可选 433.50、868.30、915.00 MHz 和 SF7–12，带宽 125 kHz、编码率 4/5。 |

发射前按模块铭牌、天线和当地规定选择频段。三个收发器一次只操作一个。测试消息最长 24 个 ASCII 字符，需要输入后按 Y 确认。接收窗口为 5 秒，识别 EtherDeck 测试消息。当前 LoRa 驱动面向参考引脚的 DIO0 型 SX127x。这一 USB 桥接模式使用 SX127x。顶部 U214 的 SX1262 使用上面的原厂入口。

## 观测和告警

USB 模式的三个模块都有「连续观测」。CC1101 和 nRF24 使用最近 20 帧画瀑布，LoRa 显示当前信号强度和信道活动。按 ESC 停止，按 S 保存最近一次测量到信号历史。历史保留最近 100 项，可以从主页用 **4** 浏览。

主页 **5** 是 NWS 气象告警。按 C 输入美国州或地区代码，按 OK 查询。随后可以用 R 刷新。NET 表示当次请求成功，CACHE 表示从本地快照读取，超出 15 分钟会标记为旧。记录显示有效期，辅助查阅时请以官方通告为准。告警和历史存于 `$XDG_STATE_HOME/etherdeck`，默认是 `~/.local/state/etherdeck`。

[功能对照和硬件范围](docs/design.md) · [版本记录](CHANGELOG.md) · [许可证](THIRD_PARTY.md)

## 在 Micius 上安装

从 [v0.2.1 Release](https://github.com/yksun/pocket-rf-os/releases/tag/v0.2.1) 下载 Debian 包。在能 SSH 到 Micius 的 Mac 上运行。Micius 重启后，先在机身上解锁，Tailscale 才会启动。

```bash
stage=$(ssh micius 'd=$(mktemp -d /tmp/pocket-rf.XXXXXXXX) && chmod 755 "$d" && printf "%s" "$d"')
scp etherdeck_0.2.1_all.deb "micius:$stage/" &&
ssh -t micius "chmod 644 '$stage/etherdeck_0.2.1_all.deb' && sudo apt install '$stage/etherdeck_0.2.1_all.deb' && /usr/share/APPLaunch/bin/etherdeck --version && systemctl --user restart APPLaunch"
```

启动器中选择 **Pocket RF OS**。默认显示顶部扩展板入口；可选 USB 模式须显式启动。

## 可选 USB 桥接器的 ADV 首次刷写

先确认连接的是你的 **8 MB ESP32-S3 Cardputer ADV** 和与 JosephCGS 引脚相符的扩展板。刷写会替换 ADV 上当前引导和应用固件，先备份。整个过程只接一台 ESP32-S3 USB 设备，使用可传数据的 USB 线连接 Micius 的 USB 主机端。CC1101、LoRa 射频型号和频段以你的板子为准。

1. 在 ADV 按住 **G0** 再按 **RST**（或按住 G0 开机）进入下载模式。
2. 打开 `ssh -t micius`，在 Micius 上安装首次刷写工具并确定 USB 路径。

   ```bash
   sudo apt install esptool
   python3 -m serial.tools.list_ports -v
   ls -l /dev/serial/by-id/
   ```

3. 把示例 `/dev/ttyACM0` 改成上一步确认的 ADV 端口。脚本会验证安装包随附的引导镜像、读取 8 MB 备份，备份成功后才写入。这个阶段保持两台设备供电。

   ```bash
   port=/dev/ttyACM0
   firmware=/usr/share/APPLaunch/apps/etherdeck/bridge-firmware
   (
     set -eu
     cd "$firmware"
     python3 -c 'import hashlib,json,pathlib; m=json.loads(pathlib.Path("manifest.json").read_text()); assert m["profile"] == "joseph-adv" and hashlib.sha256(pathlib.Path("bootstrap.bin").read_bytes()).hexdigest() == m["bootstrap_sha256"]'
     umask 077
     backup=$(mktemp -d "$HOME/etherdeck-adv-backup.XXXXXX")
     python3 -m esptool --chip esp32s3 --port "$port" --before no_reset --after no_reset read_flash 0x0 0x800000 "$backup/adv-original.bin"
     test "$(wc -c < "$backup/adv-original.bin")" -eq 8388608
     printf 'ADV backup saved: %s\n' "$backup/adv-original.bin"
     python3 -m esptool --chip esp32s3 --port "$port" --before no_reset --after no_reset write_flash 0x0 bootstrap.bin
   )
   ```

4. 在 ADV 上按 **RST** 正常启动。回到 Micius 运行以下检测，或在应用主页按 R。先逐个模块做「检测模块」，再试扫描和两台之间的测试消息。

   ```bash
   /usr/share/APPLaunch/bin/etherdeck --transport usb --check
   ```

恢复旧固件时，在同一台 ADV 上重新进入下载模式，用保存的 **8 MB 原机备份**替换上述写入命令里的 `bootstrap.bin`，再按 RST。备份可能含有原设备的配置，请放在本机保管。

## 可选 USB 桥接固件更新

装好含有新版桥接固件的 EtherDeck 应用包后，连接同一台 ADV 并启动 USB 模式。主页按 **U** 查看版本，按 **OK** 进入确认页，再按 **Y**。应用校验包内镜像 SHA-256、核对板型和设备身份，写入 ESP32 的备用应用分区。桥接端验证收到的镜像后才切换启动分区。程序重新连接并读到同一台设备的目标版本时才显示成功。正在运行 0.1.0 的桥接板可从 0.2.0 应用内升级。若应用包内版本已经与板上版本一致，界面仅显示版本。固件文件随应用包分发。

## 键位

- **F / X** 或 **Fn+F / Fn+X** 上下选择，主页也可用 **1–7**。**OK** 打开或执行。
- **Z / C** 或 **Fn+Z / Fn+C** 调整频率或信道，**B** 切换 nRF24 速率或 LoRa 扩频因子。
- **短按 ESC** 返回，**长按 ESC** 退出。TAB 后再按 OK 保留给 Micius 的锁屏操作。
- **R** 在主页重连，**H** 查看信号历史，**A** 打开气象告警，**D** 查看当前接口状态。USB 模式下 **U** 打开桥接固件。

## 开发与参考

- Micius 的部署、320×170 framebuffer、evdev 键盘和 APPLaunch 结构来自 [官方 CardputerZero 文档](https://docs.m5stack.com/en/compute/cardputerzero/usage) 与 [官方 AppBuilder](https://github.com/CardputerZero/AppBuilder)。
- JosephCGS 的参考板使用独立片选共享 SPI（SCK 40、MISO 39、MOSI 14）。CC1101 CS/GDO0 为 15/13，nRF24 CS/CE 为 9/8，LoRa CS/RESET/DIO0 为 5/3/4。nRF24 两个引脚在 ADV 上与键盘复用，因此桥接固件由 Micius 接管输入。 [JosephCGS 参考板说明](https://github.com/JosephCGS/Cardputer-ADV-CC1101-NRF24L01-LoRa)
- Module Tester 的分模块诊断与活动图、论坛里的引脚与扩展芯片讨论，以及官方 LoRa 套件的 SX1262 型号差异提供了功能与界面参考。 [Module Tester](https://github.com/fr4nx40/Module-Tester-Cardputer-ADV) · [r/CardPuter 讨论](https://www.reddit.com/r/CardPuter/comments/1xf48z6/cardputer_module_tester/) · [官方 Mesh Kit](https://docs.m5stack.com/en/core/Cardputer_Mesh_Kit)
- 桥接端使用 [RadioLib 7.4.0](https://github.com/jgromes/RadioLib/tree/7.4.0) 与 [RF24 1.5.0](https://github.com/nRF24/RF24/tree/v1.5.0)，通过 Espressif 的 [OTA 分区接口](https://docs.espressif.com/projects/esp-idf/en/v5.1/esp32s3/api-reference/system/ota.html) 写入备用分区。应用和桥接源码均在本目录。
- 在 Mac 上运行 `packaging/build_firmware.sh` 生成 ESP32 镜像。用 Debian 的 `sh packaging/build_deb.sh` 打包。应用测试命令为 `python3 -m unittest discover -s tests -v`。
