# 0.2.0 设计核对

| 报告主题 | 0.2.0 结果 |
| --- | --- |
| 硬件分层和板型 | Micius 是 Raspberry Pi CM0 Linux、320×170；ESP32-S3、240×135 对应 Cardputer 系列。此版 Micius 跑 APPLaunch，ADV 运行独立桥接固件，支持 JosephCGS 引脚。初代、v1.1、其他 PCB 型号需单独验证。 |
| RF Lab | CC1101 17 点 RSSI 扫描，nRF24 84 信道活动次数，SX127x LoRa RSSI/CAD。连续模式的 CC1101、nRF24 显示最近 20 帧瀑布，LoRa 显示当前值。三模块都保留测试消息，普通测试包接收窗口为 5 秒。 |
| Signal Explorer | 独立信号历史。按 S 保存真实观测，最多 100 项，含来源、时间、模块、参数和样本。原始测试消息不会写入历史。 |
| Public Alerts | NWS 按地区手动查询，优先级排序与去重。显示 NET / CACHE 标签、快照时间和有效期。整个数据源可离线查看上次快照。 |
| Hardware / Settings | USB 身份检查、模块检测、电池状态、固件比对和桥接 OTA。启动页给七个可用入口。 |
| 可取消和有界任务 | 连续观测单工作线程，键盘和图示继续刷新。按 ESC 或 TAB 停止安排新一轮，已发出的一轮会在返回或超时后退出。按键保留系统锁屏。HTTP 使用独立工作线程和超时。 |
| 第二阶段候选 | SX1262 需要 BUSY/DIO1 与板上扩展器验证。Meshtastic 优先接入其公开客户端协议。外部 SDR 可复用 rtl_433 JSON 或单独 FFT 服务。GPS、NFC、网络诊断、日常工具、独立 ESP32 图形界面及多板型构建仍属后续范围。 |

## 信号单位

- CC1101 是窄带调谐 RSSI，频点间隔 100 kHz。
- nRF24 显示每信道 8 个样本中的活动次数。
- LoRa CAD 只检测当前参数下的 LoRa 前导。
- 宽带 FFT、协议解码与公开广播接收需要独立接收设备和软件。

## 参考与边界

- [CardputerZero 官方说明](https://docs.m5stack.com/en/compute/cardputerzero/usage) 与 [Cardputer Mesh Kit](https://docs.m5stack.com/en/core/Cardputer_Mesh_Kit) 对照操作系统、芯片及扩展模块差别。
- [JosephCGS](https://github.com/JosephCGS/Cardputer-ADV-CC1101-NRF24L01-LoRa) 交叉核对共享 SPI 和键盘复用。 [Module Tester](https://github.com/fr4nx40/Module-Tester-Cardputer-ADV) 与 [社区讨论](https://www.reddit.com/r/CardPuter/comments/1xf48z6/cardputer_module_tester/) 对照单模块诊断和图表。
- [Flipper 官方固件](https://github.com/FlipperDevices/flipperzero-firmware) 用作模块职责参考。 [rtl_433](https://github.com/merbanan/rtl_433) 与 [Meshtastic CLI](https://meshtastic.org/docs/software/python/cli/) 用于核对外部解码及 Mesh 客户端边界。
- [NWS Web API](https://www.weather.gov/documentation/services-web-api) 提供官方气象告警查询。应用仅在用户触发时请求州或地区代码。快照用于辅助查阅。
