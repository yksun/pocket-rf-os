# Changelog

## 0.2.1 — 2026-11-26

- 默认改为 CardputerZero 顶部 CAP 模式。支持启动 U219 的 SubG Chat / NFC 及 U214 的 LoRa / GPS 原厂应用。
- 增加 JosephCGS 原板的只读接线诊断。保留 USB 作为独立、显式选择的 ADV 桥接模式。
- Debian 包可直接升级。旧 USB 桥接镜像仍为 0.2.0。

## 0.2.0 — 2026-11-26

- 将显示名称更新为 Pocket RF OS。Debian 包名和 USB 命令兼容 0.1.0。
- 加入连续被动观测、CC1101 和 nRF24 活动瀑布、LoRa 实时采样，以及有界的本地信号历史。
- 加入 NWS 地区气象告警、离线快照、硬件诊断和电池状态。
- 保留三模块单次扫描、点对点测试消息、Micius 锁屏键位和 USB 固件升级。更新仍以同一设备的版本读回确认成功。
- 同时提供 Debian 安装包、ESP32-S3 首刷及升级镜像、校验和与源码。

## 0.1.0 — 2026-11-26

- 初版 EtherDeck，实现 Micius 界面与 JosephCGS 三合一扩展板桥接。
