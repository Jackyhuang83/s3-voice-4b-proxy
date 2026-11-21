# R2-P0-2 正式选型：单一 NOAIC 数据平面 + 现有加密协议

> **历史文档 / 已撤回选型（2026-11-21 R2-P0-0）**：此前“NOAIC 唯一/首选数据平面”的正式选型结论已失效；本文件保留为旧版源码/CI 记录，不得作为后续移植指令或产品成熟度证据。最新唯一有效路线参见 [R2-PLAN](R2-PLAN.md)，重新审计见 [R2-P0-0-MATURITY-AUDIT](R2-P0-0-MATURITY-AUDIT.md)。历史测试结果不被删除，亦不计入新的验收进度。

**最终候选决定（源码及原版 CI 层级）：**以 MIT 的 `noaic/esp32-socks5-gateway@0be56938acace1d083be746b3f6c60886259e81e` 作为**唯一透明 IPv4 TCP 数据平面**。先整块直接移植作者原版可独立编译、具备主机测试的 flow/packet/client 模块，保留原 LICENSE 与上游源文件哈希；不要自行重写算法。旧 `yanxke@dfb04b...` 保留为如果 lwIP SDK 阻断时的**回退候选**，不可同时启用两套 Hook 和流表。既有 P2/P3 `s3_ss2022`、`s3_vless_tls` 保留并重新做集成验收，不从头发明加密协议。

## 原版可复现依据和测试级别

- GitHub PR #17 head `5df0a05610cdd6297e0e456c6a9cd8a488f41134`：**11/11 CI PASS**。原版双构建 Run [44902851046](https://github.com/Jackyhuang83/s3-voice-4b-proxy/actions/runs/44902851046)。
- NOAIC Job `136842209402`：原版 `idf.py build` PASS，bin `0xf2ed0` bytes（独立 0x400000 app 槽）；`idf.py size` **994902** bytes；**Python 125/125 PASS**，原版 Node 管理回归 PASS，作者原版 source/tests 没有改动。其独立硬件 N16R8 吞吐历史记录**不能视为微雪 4B 实测**。
- yanxke Job `136842209188`：原版 PlatformIO 6.1.18 构建 **PASS**；原版 `pio check` 和质量测试原 CI PASS；其独立源码主要工作任务与 4450 行 `src/main.c` 耦合，缺少 A 同规模的可移植单元回归。
- 两者源代码均为 MIT；对原版改动和上游作者通知需在所有移植模块中保留并自动校验。

## 选型评价：工程判断分（非产品安全评分）

| 维度（权重） | NOAIC | yanxke | 依据 |
|---|---:|---:|---|
| 独立可复用模块（20） | 19 | 8 | A 分拆 flow/packet/AP clients/relay；B 的大量控制在 main.c |
| 小智/SDK 侵入性（20） | 7 | 15 | A 要定点 SDK ip4.c Hook；B 已有旧 4B 编译成功的内建 Hook，但实机未验证 |
| 上游原版测试（20） | 20 | 11 | A 125 Python + Node + 编译，B 为编译/静态分析 |
| 网络故障/并发回收（20） | 18 | 11 | A 有 epoch、客户端 tokens、固定队列/超时和测试；B 任务分散 |
| SS2022/VLESS 接入难度（10） | 4 | 6 | A SOCKS5 非阻塞握手深耦合；B 明文 VLESS 也需替换 |
| 小智 RAM/PSRAM 预算（10） | 4 | 5 | 两者均未测过声学/LCD 共存，A 64×2×8192=1MiB PSRAM 默认队列不可照搬 |
| **合计（100）** | **72** | **56** | 评分包含工程判断和未实机证据的保守扣分，仅用于 P0 移植选择 |

## R2-P1 可直接复制的文件与继承测试

| 直接复制文件（固定 A SHA） | 作用 | 原版已跑的回归 |
|---|---|---|
| `main/flow_table.c/.h` | hashed 四元组映射、claim/expire、quota/closing guard | `tests/test_flow_table.py` + `tests/flow_table_harness.c` |
| `main/packet_rewrite.c/.h` | TCP IPv4 报文完整性、校验和、字段改写 | `tests/test_packet_rewrite.py` |
| `main/ap_clients.c/.h` | DHCP MAC/IP token 及重连身份、资源配额 | `tests/test_ap_clients.py` + `tests/ap_clients_harness.c` |
| `main/tcp_poc.c` 输入/输出/flow 连接部分 | 原版作为初始底稿，**仅最小修改**它和小智/SDK/协议边界，不能把其诊断/HTTP/SOCKS5 整套盲拷 | 原版 Flow/Packet 回归 + 新增集成 Hook 正负向测试 |

各文件在 P1 需自动记录 `upstream SHA256 → imported SHA256 → unified diff`；不可无证据抛弃上游模块自行写同功能代码。完整拷贝后要移除不需要的 UDP/diag/SOCKS5 编译依赖，而不是让原 UDP/直连残留。

## 不能整体移植：源码证据及最小替代

**A `main/app_main.c`：不能直接移植。** 它有自己的 `esp_wifi_init`、`esp_wifi_set_mode(WIFI_MODE_APSTA)`、默认 AP/STA 双 netif、NVS 恢复等；直接覆盖会破坏 `78/xiaozhi-esp32` 音频/LCD 配网主程序。**简单方案：保持 Xiaozhi 唯一 owner `78/esp-wifi-connect`，只从其已知配网/STA 事件连接少量 AP 生命周期适配。**

**A `main/socks_relay.c`：不能原封不动作为加密 SS2022/VLESS。** 源码 `advance()` 中 `GREETING_TX/RX, REQUEST_TX/RX` 是 SOCKS5 NO AUTH 协议，后续用 raw `send()/recv()`；SS2022 需要 AES-GCM AEAD 加密会话，VLESS/TLS 需要官方 `esp_tls_conn_read/write` 和证书验证。**简单方案：先保留已验证 A 的 bounded queue/epoch/cancellation 设计及可复用处理；P2 通过单一 transport 适配边界复用项目已有 `s3_ss2022_relay` / `s3_vless_tls_relay`，不重写密码学，也不继续运行 SOCKS5 明文代理。** 如需改动事件循环的巨大主体，停止，改用作者另一候选的 per-client Task 模板并强制并发上限，须在同一既定 PR 更新源代码证据。

**A `main/tcp_poc.c` 与官方 Hook 不等价：不能直接复制绑定。** 固定 esp-lwIP `src/core/ipv4/ip4.c`：
- **官方 `LWIP_HOOK_IP4_INPUT(p,inp)` 在 521–525 行**，早于 `ip4_input` 完整 IPv4 长度、头部校验和验证，而且只有 `pbuf *` 不能把修改后 `pbuf *` 返回给调用者。
- NOAIC 作者自己的 `patches/lwip-v6.1-transparent-tcp.patch` 把 Hook 安插在**完成校验之后，local-address acceptance 之前**；`proxy_rewrite_ip4_input(&p,inp)` 接收 **`struct pbuf **`**，允许 clone 并替换原报文，出口同样有定点 Hook。官方 Hook 不提供这一安全语义。

**最低侵入方案：**优先原样复用 NOAIC 的 **project-local lwIP 组件覆盖**，pin `esp-idf@fff9895c...`、`esp-lwip@c6f2f878...` 及作者原始/目标文件 SHA256，运行原作者 `prepare_lwip.py apply/check/restore`。此补丁只存在隔离构建目录，不改系统 SDK、不刷用户设备。**停止条件：**若小智 4B 必需 SDK/音频驱动和 A 固定 SDK 不兼容，先进行上游哈希/Hook 时序对照，不允许用强制指针类型转换或跳过校验让它“编译过”；回退到 B 的已编译 Hook 数据平面，同时**只保留单流表**，必要重大计划修改先更新 R2 路线图。

**其他明确不移植：**NOAIC Web 管理、LED、另一个 OTA/partition/NVS 方案、互联网 SOCKS UDP/QUIC。下游只允许 DHCP 和加密 DNS，外网 UDP 必须禁用。原小智语音、LCD、触控、OTA 分区全部保留。

## 降低实测和资源风险

- 所有 P1/P2/P3 自动重跑 upstream 模块测试，协议回归和 Xiaomi/4B 完整 IDF 编译由 GitHub 执行，最终 **只一次集中硬件验收**（一个 AP 手机、两个协议、DNS、拔上游/恢复、原版语音/LCD/触控、关代理与原版 OTA/恢复）。无需在 P0/P1 让用户刷机或试错。
- NOAIC 原设定 64 条 TCP relay × 2 × 8192 = **1,048,576 bytes** PSRAM 队列，并占用 internal RAM metadata；小智音频/LCD 并行运行尚未量测。P1/P3 应先通过源/IDF 预算选择较低限额，**4–8 条只作为初始测试候选，不代表硬件能跑或最终吞吐**。
- 网关只许手动启用，认证节点存在之前不允许启用 Hook；无法确认状态时阻断下游代理流量，不可落到 direct NAT。小智 STA/语音应独立运行。旧稳定版 main 不覆盖；原版固件和 NVS 恢复路径验证前 **不触碰微雪设备**。

## 验收真值
- 源码/API 差异：**SOURCE VERIFIED**。
- 双原版项目固定版本构建及 A 125 Python + Node、B PIO/quality gate：**UPSTREAM CI PASS**。
- A 模块真正移植并与现有 SS2022/VLESS/Xiaozhi 联合构建：**NOT RUN（R2-P1～P3）**。
- 真机加密 TCP、DNS、fail-closed、音频/GUI 和回滚：**NOT RUN（R2-P4）**。

P0-2 关闭/合并前仍要求本决议提交的**最终 PR head** CI 全绿，不能用本段之前的 11/11 冒充最终 head PASS。
