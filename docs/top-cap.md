# 官方 CAP 功能

| 板型 | 原厂工具 | 验收 |
| --- | --- | --- |
| U219 | [Sub-GHz 聊天](https://github.com/CardputerZero/Cap-CC1101-SubG-Chat)、[NFC](https://github.com/CardputerZero/Cap-CC1101-NFC) | 聊天界面打开并显示射频状态。用自有兼容标签检查 NFC。 |
| U214 | [LoRa 聊天](https://github.com/CardputerZero/Cap-LoRa-1262)、[GPS](https://github.com/CardputerZero/Cap-LoRa-1262-GPS) | LoRa 打开并显示射频状态。GPS 打开并检查 NMEA/卫星状态，首次定位可能需要开阔天空。 |

Pocket RF OS 切换到系统已有的官方工具，关闭工具后回到原会话。板型由用户在本次运行中确认，程序读取 GPIO 模式和供电状态来帮助诊断。官方说明要求关机换板。

- 安装 U219 后按 **1** 或 **2**，随后按 **Y**。按 **3** 或 **4** 时提示 U214。
- 安装 U214 后按 **3** 或 **4**，随后按 **Y**。按 **1** 或 **2** 时提示 U219。

可用 `/usr/share/APPLaunch/bin/etherdeck --check` 核对 GPIO 模式和已安装工具。工具安装存在和 SPI 可访问各是独立检查，实际芯片状态以原厂工具里报告为准。

[M5Stack U219](https://docs.m5stack.com/en/cap/Cap_CC1101) · [M5Stack U214](https://docs.m5stack.com/en/cap/Cap_LoRa-1262) · [CardputerZero 使用说明](https://docs.m5stack.com/en/compute/cardputerzero/usage)
