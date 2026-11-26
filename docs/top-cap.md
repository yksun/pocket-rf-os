# CardputerZero 顶部扩展接口

0.3.0 的原板免改方案见 [有源转接针脚图](adapter.md)。

关机后再插拔扩展板。三个入口各自对应一块板，只在顶部已安装所选型号时启动其工具。

| 扩展板 | 支持方式 |
| --- | --- |
| M5Stack Cap CC1101 U219 | 原厂 CardputerZero 应用处理 SPI、供电、RF 切换和 NFC。Pocket RF OS 打开 SubG Chat / NFC。 |
| M5Stack Cap LoRa-1262 U214 | 原厂 CardputerZero 应用处理 SX1262、BUSY / IRQ、I²C 扩展器和 GNSS。Pocket RF OS 打开 LoRa / GPS。 |
| JosephCGS ADV CC1101 / nRF24L01 / LoRa | 原板的顶部接法存在主机引脚冲突。Pocket RF OS 只读显示状态。已有独立 ADV 时可继续通过显式 USB 模式使用桥接器。 |

## JosephCGS 原板交叉核对

以下是根据两个主机的 14 针物理位置和作者 README 推导的针脚对照。Micius 通过 `pinctrl get` 核实了当前主机复用状态，未对扩展板写入。

| 三合一原板信号 | ADV GPIO | EXT 针脚 | Zero 接点 |
| --- | --- | ---: | --- |
| nRF24 CE | G8 | 8 | G2 / SDA1 |
| nRF24 CS | G9 | 10 | G3 / SCL1 |
| CC1101 CS | G15 | 14 | G14 / TXD1 |
| CC1101 GDO0 | G13 | 12 | G15 / RXD1 |
| LoRa CS | G5 | 13 | G7 / SPI0 CS1 |
| LoRa RESET | G3 | 1 | G26，在 HAT GPIO 模式 |
| LoRa DIO0 | G4 | 3 | G23，在 HAT GPIO 模式 |
| SPI SCK / MOSI / MISO | G40 / G14 / G39 | 7 / 9 / 11 | G11 / G10 / G9 |

作者的 `Wire1.end()` 示例依赖 ADV 的 ESP32 固件暂时停用其 I²C，再把 G8/G9 交给 nRF24。Zero 上这两个物理位置对应系统 I²C1，键盘、RTC、电池计和板载 I/O 扩展器等设备使用这条总线。nRF24 的片选会跟随 SCL，可能在共享 SPI 期间误选。原板需要隔离 I²C 并重新布线后才能做顶部原生驱动测试。

`/usr/share/APPLaunch/bin/etherdeck --check` 仅报告主机和已安装入口状态。显示 SPI 可访问不代表射频芯片已响应。

[JosephCGS README](https://github.com/JosephCGS/Cardputer-ADV-CC1101-NRF24L01-LoRa/blob/main/README.md) · [Cardputer ADV 针脚](https://docs.m5stack.com/en/core/Cardputer-Adv#ext-254-14p) · [CardputerZero 针脚](https://docs.m5stack.com/en/CardputerZero#ext-254-14p) · [U219](https://docs.m5stack.com/en/cap/Cap_CC1101) · [U214](https://docs.m5stack.com/en/cap/Cap_LoRa-1262)
