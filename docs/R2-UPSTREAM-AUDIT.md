# R2-P0-1 上游深度复用审计（第一轮可核对源码证据）

> **历史文档 / 已撤回选型（2026-11-21 R2-P0-0）**：此前“NOAIC 唯一/首选数据平面”的正式选型结论已失效；本文件保留为旧版源码/CI 记录，不得作为后续移植指令或产品成熟度证据。最新唯一有效路线参见 [R2-PLAN](R2-PLAN.md)，重新审计见 [R2-P0-0-MATURITY-AUDIT](R2-P0-0-MATURITY-AUDIT.md)。历史测试结果不被删除，亦不计入新的验收进度。

状态：**P0-1 初审已通过；P0-2 原版复现通过并已形成 NOAIC 单一数据平面选型。** 证据见 [R2-P0-2-DECISION](R2-P0-2-DECISION.md)。4B 实机尚未验证。

## 候选与固定修订

| 用途 | 来源 / 固定提交 | 许可证、确认结果 | 不能直接整套移植的原因 |
|---|---|---|---|
| **语音主固件** | [78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) `831ffd14188553cc887408b75396ae38618538e0` | 原小智主固件，4B 音频、480×480 LCD、Touch、OTA/Assets | **必须保留**为主程序，不允许路由器的 app_main 替换它 |
| **Wi-Fi owner** | [78/esp-wifi-connect](https://github.com/78/esp-wifi-connect) v3.3.3 `77095063d77e7705f68e95005c43ed73582233ce` | 已有 STA/配网所有权；原代码存在异常时自动擦除 NVS 分支，需安全回退处理 | 不能再启动另一套 esp_wifi_init/esp_wifi_start |
| **候选 A，模块化网关** | [noaic/esp32-socks5-gateway](https://github.com/noaic/esp32-socks5-gateway) Release `v26.10.16` = `0be56938acace1d083be746b3f6c60886259e81e`；后续 main `7d263167deb7b78c890ee871a513a0fa143ecf72` | **MIT**；作者提供 ESP32-S3 N16R8 板上 TCP 16.43 Mbps（单流下载）和 24.49 Mbps（四流合计下载）*历史记录*；有 host tests / 单独模块；不能当作本 4B 的实测 | SOCKS5、上游 IPv4、AP/STA 自己初始化；`CONFIG_LWIP_IPV6=n`；通过修改 **IDF 6.1 ip4.c** 获取透明重写机会；其 TCP worker 直接耦合 SOCKS5 握手。原作者明确称其为实验项目 |
| **候选 B，现有 TCP Core** | [yanxke/ESP32-VPN-Transparent-Proxy-Router](https://github.com/yanxke/ESP32-VPN-Transparent-Proxy-Router) `dfb04b03154cfaee1d8615e4b8942dfe737abc5d` | **MIT**；`src/transparent_tcp.c/.h` 处理 TCP 改写/流表，现有 P1 已移植其中一部分 | DNS/TCP 任务及网络控制主要在 `src/main.c`，不可整份复制（重叠 Wi-Fi 与生命周期）；默认启用的拦截/一向 Hook 不等于可安全卸载；原版不提供完整 SS2022、VLESS/TLS 或 STA IPv6-only |
| **现有加密协议资产** | [rlog/atoms3r-muse-firmware](https://github.com/rlog/atoms3r-muse-firmware) `57f73602e963e478e06eae5f8108d07495468031` 和本仓库 ESP-TLS/VLESS（旧 PR #8–#13） | Apache-2.0（SS2022 上游）及现有源码/向量测试；必须继续保留原作者通知 | Muse 的上游适配针对其特定音频固件；协议通过主机测试不代表新流表和 ESP32 设备上真正通网 |

## A 与 B 源文件级实际差异

**noaic：** `main/flow_table.c`（约 95 行）拥有 hashed destination table、每客户端配额、TCP 关闭保留；`main/packet_rewrite.c`（约 109 行）做独立 IPv4/TCP 长度、校验和、改写；`main/ap_clients.c` 是客户端身份与回收；`main/socks_relay.c`（约 630 行）做非阻塞 select、双向有界队列、EOF、15 秒握手、120 秒空闲、网络 epoch。对应 `tests/flow_table_harness.c`、`tests/relay_harness.c`、`tests/packet_* ` 及 CI。**这些是优先复用的候选**，不能仅抄理念而重写。

**noaic 的关键移植障碍：** [docs/development.md](https://github.com/noaic/esp32-socks5-gateway/blob/7d263167deb7b78c890ee871a513a0fa143ecf72/docs/development.md) 明确解释必须在官方 lwIP `ip4.c` 的地址接受前与发送前插钩，仓库 `patches/lwip-v6.1.json` 把 SDK 固定为 `fff9895c82d744c7237be8847347bdd1b07c6643` 和 lwIP 修订 `c6f2f878e7b0f86033214b85547d579be43351e3` 并校验文件 SHA。**不能直接让这个补丁覆盖小智的 SDK**；必须首先评估 ESP-IDF 官方 custom input Hook + AP netif output callback 是否提供等效的安全时机。若不等效，需复现具体断点、精确且可逆的 upstream patch，并对照语音/OTA 等全构建。

**yanxke：** `src/transparent_tcp.c/.h` 能直接提取较小代码面，但不是完整网关；原 `src/main.c` 包含 transparent server/task、DNS cache/server、Wi-Fi 配置和监控。现有 `tools/p4_import_tcp.py` 只导入 `transparent_tcp.c/.h`，而不是原作者的整个运行时。这是旧 P4-1 “build PASS 不等于可用”的根本证据之一。

**SS2022/VLESS：** 现有源码可继续利用，但**有界转发队列与中断/EOF/超时语义**必须使用选定上游 worker 的抽象，不能把网络调用硬嵌入音频/Wi-Fi 回调；任何新 adapter 都要说明与原 SOCKS5 或明文 VLESS 协议差异。

## 已发现的旧实现高风险点（均需 R2 重测，绝不凭推测宣布已修）

1. **无运行时证据：**旧 P4-1 仅编入 TCP/DNS 入口，没有监督式任务实际启动，AP 客户端通网 NOT RUN。
2. **未保留整个经实测工作循环：**旧工程只导入 yanxke `transparent_tcp.c/.h`，自写 DNS/TCP 入口，作者真实运行时中的监听任务、维护/回收没有跟随导入；新工程必须以**最终编入固件的文件**为复用依据。
3. **单一 Wi-Fi 生命周期：**原小智已拥有 STA/配网。APSTA 增加、错误时回退、AP netif 生命周期及 DHCP 异常回收，要与官方 Wi-Fi owner 完整兼容，而不是“能编译就安全”。
4. **潜在资源竞争：**旧入口缺多客户端资源/队列完整调度验证；小智 LCD/音频与网络共用 S3 内部 RAM/PSRAM，不能照搬 64 连接和 512 流映射上限。
5. **两种数据路径不能并用：**noaic 和 yanxke 各有流表、重写 Hook；**禁止同时启用两套拦截、流量表和出站转发**。必要时只保留一个候选的数据平面，另一候选仅借鉴具证据的模块算法。
6. **上游适用边界：**noaic 的 SOCKS5、UDP ASSOCIATE、原版 IPv4-only、独立 app_main 都不满足本项目目标；即使作者曾有硬件实测，也**不能当作 SS2022/VLESS / 微雪 4B / 小智并发测试通过**。
7. **发布与回退：**旧版编译通过但从未在 4B 验证备份、恢复和音频回归；不能据此刷写设备。

## 三目标检查表（每一个候选移植文件都必须填）

| 检查项 | 必须提供的可审计证据 | 不满足时 |
|---|---|---|
| 直接移植与速度 | 上游 SHA、源码文件、许可证、可运行原始测试、移植 diff 行数，优先整块复制 | 不写替代代码；先找官方/其他成熟实现 |
| 最少用户测试 | 原作者真实测过什么、哪些测试能在 CI 复制、哪些独立小智/SS2022/VLESS 风险仍需一轮现场检查 | CI 补齐后统一测试，禁止逐次盲试 |
| 最小侵入与回退 | 小智启动/音频/LCD/Wi-Fi/OTA diff，默认关闭路径，NVS 数据保持、可逆修改与明确回退条件 | 不合并、不刷机、不发布 |

不要求用户在 P0/P1 重复做作者已经完成的硬件吞吐试验。作者板测记录仅作为选择依据；**实际小智 4B 语音共存与加密代理互通**必须完成独立最小终验，不能用原版 SOCKS5 板测替代。

## 后续可移植判定（每项必须有证据）

| 组件 | 建议 | P0-2 必须回答的问题 |
|---|---|---|
| noaic `flow_table.c/.h`, `packet_rewrite.c/.h` | **优先原样测试/移植候选** | 原测试原样复现、保留 MAC/IP owner token、防内存泄露，调整极少配置后是否可编入小智 |
| noaic `socks_relay.c` 事件循环 | **优先保留有界调度行为** | SOCKS5 握手与双向调度能否用最小 vtable 替换为 SS2022/VLESS，加密连接是否需要异步握手与独立 TLS I/O |
| noaic `tcp_poc.c` 的 Hook | **不能直接整份移植，先做官方 Hook 对照** | 与原版固定 SDK 的 `ip4.c` 插入位置和发送时机是否一致；是否有重入/校验和/PCB 差异 |
| yanxke `transparent_tcp.c` | **保留作对照或最小备选** | 经现有 P1 修改后与原版 host/hardware 测试如何对齐，有无安全卸载与流表竞态 |
| 小智 `main` + esp-wifi-connect | **绝不替换** | APSTA 前置配置与配网切换最小插入位置；无第二 Wi-Fi owner，音频/LCD/OTA不变 |
| 现有 SS2022/VLESS | **先复用旧验证资产** | 与选定 worker 的 transport I/O 合同能否兼容、是否影响 IPv6-only 节点与证书验证 |

## 实验与停止条件

R2-P0-2 首先用独立固定工具链、相同测试说明复现两候选的 upstream host tests / 原始固件 build；记录确切 SHA/命令/退出码。只允许构建、测试、静态检查，不操作用户 VPS 或微雪板。没有足够证据选择完整流表/worker 时**停止编码，不自造替代物**。每项选择必须给出原代码路径、依赖、需要修改的行及回归保障，且确保 MIT/Apache 原许可证及 NOTICE。

不要把作者 README 的历史吞吐数字视为我们设备的性能结果。
