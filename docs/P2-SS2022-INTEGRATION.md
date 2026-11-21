# P2-2 — SS2022 透明 TCP / DNS 接入与验收

**阶段计划不变：P2 仅 3 PR；本文件属于 P2-2（权重 40%）。** 当前证据以 PR #9 CI 为准；未合并前 P2 仍按 30% 计算。

## 集成方案

1. **保留上游路由器主体**：`yanxke/...@dfb04b03154cfaee1d8615e4b8942dfe737abc5d` 的 AP/STA、lwIP IPv4 hook、原目的 IP/端口流表、TCP 接收任务、DHCP、本地 DNS 服务继续复用。先应用已验收的 P1 补丁 0001～0004。
2. **只增加一个显式路由模式**：`TRANSPARENT_MODE_SS2022`。在现有 `transparent_client_task()` 取得正确 flow 后优先调用 `s3_ss2022_relay()`；出错时关闭客户端，不进入 VLESS 或 direct fallback。其他现有模式不变。
3. **协议核心完全复用 P2-1**：`muse_ss2022.{c,h}`、BLAKE3、PSA AES-GCM 及 LICENSE/NOTICE 保持原样，Git blob SHA 校验持续有效。新增的 `s3_ss2022_link.c` 只负责资源、传输、NVS、时钟和 DNS 数据流，不重写加密帧。
4. **DNS 不泄漏**：`captive_dns_task` 的 SS2022 分支调用 `s3_ss2022_dns_query()`，通过节点建立 TCP/53 并发送长度前缀的 DNS Query；出错返回原 P1 `SERVFAIL`。不得因为非 VLESS 模式误入上游直连 UDP DNS；显式配网模式仍保留原 Captive Portal。
5. **生命周期**：单连接独立 SS2022 加/解密上下文，PSRAM 分配 128 KiB RX 状态及小型 I/O 缓冲，两个客户端 TCP 连接上限，另留一个 DNS 会话；最大空闲 180 秒；8 秒建连超时、5 秒 socket I/O 超时；异常链路释放 fd/PSA 密钥/缓冲/计数。未认证的响应数据不得下发客户端。

## 节点设置（仅物理 USB 串口）

本阶段仅通过物理 USB 串口配置节点，避免在明文 HTTP 管理页面提交敏感密钥。命令：

`ss2022 <IPv4 literal> <port> <base64-encoded 16-byte PSK>`

随后 `route ss2022` 在本次启动期间切换至该模式；`ss2022 clear` 删除存储的节点。管理页面允许选择**已存在**的 SS2022 节点，但不接收密码。输出只显示保存是否成功，不打印 PSK。设备无节点时拒绝启用；删除节点后不能自动直连。P2-2 不要求用户现场操作。

**重要安全限制：** 源路由工程已知 NVS 没有加密，当前单独 `s3ss2022` namespace 仍是未加密存储。此处只能认定为开发阶段验证方案，**不允许标记为生产安全固件**。P4 必须有安全可用的凭证存储/加密或明确阻断发布。同时原工程 AP 初始密码等也需要整改。

**重启行为：** 默认仍是原 VLESS 模式；SS2022 模式只在用户明确选择时启用，不会自动改动生产网络。BOOT 长按恢复出厂会同时清除独立的 SS2022 凭证。

## 可信时钟与随机性

- 官方 `esp_netif_sntp_init` + `esp_netif_sntp_sync_wait`，时间未同步或 Unix 时间不合理时禁止 SS2022。
- 节点盐及非零 padding 由 ESP-IDF `esp_fill_random` 产生；仅在 STA/Wi-Fi 正常连接后建立代理。禁用固定 salt、默认虚构时间、无认证错误后的直连。
- SNTP 的设备自身控制面可能向时间服务器发送 NTP；这与下游 AP 客户端 UDP 阻断不同。P4 需要独立明确 DNS/NTP 控制面是否满足安全策略。

官方依据：
- <https://shadowsocks.org/doc/sip022.html>
- <https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s3/api-reference/system/system_time.html>
- <https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/random.html>
- <https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/external-ram.html>

## P2-2 CI 证据及验收门槛

- 锁定原始源码 SHA、P1 全补丁；严格应用 P2-2 脚本（匹配次数非 1 时拒绝更新）。
- 编译实际新增 C 适配层，与**独立 Python BLAKE3/AES-GCM TCP 服务器**在本地主机 127.0.0.1 上测试加密 relay、分片认证服务端响应、加密 DNS-over-TCP、NVS 错误密钥与清理。
- 源码检查必须确认：SS2022 早于旧 transport 的直连分支、DNS 无直连 fallback、STA/节点/时间/PSRAM 检查以及连接上限、释放流程。
- 在固定 ESP-IDF/PlatformIO R8N16 固件中包含已连接的 SS2022 接入分支并编译。P2-1 原有向量、P0/P1 基线 CI 继续通过。
- **不等于 P2-3**：无需用户真实 VPS，不能宣称真实 SS2022 服务端互通。P2-3 专门执行 IPv4 互通、断线、服务端重放/密钥故障验证。
- **不等于 P4**：真实 4B Wi-Fi、LCD、语音、性能、PSRAM 持续运行均待实机验证；未刷写设备。

## 可回退性

取消新 P2-2 源码注入及独立组件即可恢复 P1 原 TCP-only VLESS 基线。旧固件没有被改变；不要在缺少稳定恢复流程时覆盖实机固件。

## 验收结论

**PENDING:** 仅以 CI 实际结论和合并记录为准。CI 修复必须在本 PR 中完成。
