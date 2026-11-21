# R2-P0-0 · 成熟实现重新选型审计（第一轮，未决议）

> 采集日期：2026-11-21。此文为可复查的 **P0-0 第一轮 GitHub/官方源码核查**，不是最终选型，也不是软件可靠性认证。旧“NOAIC 72/100 主方案”已撤回。原版 4B 未刷写、未实机测试。P0-0 在补齐代码/许可证/可复现性门槛及 CI 前维持 OPEN / NOT ACCEPTED。

## 1. 已核对的仓库活跃与社区证据

| 候选 | 创建时间（UTC） | Stars / forks（采集时） | 维护/Release/问题记录 | 暂定角色 |
|---|---|---:|---|---|
| [Espressif esp-idf](https://github.com/espressif/esp-idf) | 2016-08-17 | 19,559 / 8,614 | 官方组件，v6.1.1 于 2026-11-16 发布；持续更新 | **优先使用官方网络与 TLS API，不自动等同透明网关可用** |
| [Espressif esp-iot-bridge](https://github.com/espressif/esp-iot-bridge) | 2021-05-11 | 241 / 89 | 乐鑫维护；已有 v1.0.0 2022 release、v1.1.0 registry，支持 ESP32-S3 / Wi-Fi router | **官方 AP/STA/netif/DHCP/NAT 案例；需确认 Wi-Fi owner 与补丁边界** |
| [martin-ger esp32_nat_router](https://github.com/martin-ger/esp32_nat_router) | 2020-02-17 | 2,280 / 522 | 多年迭代、wiki/安全/资源文档、ESP32-S3 固件；缺少整机统一许可证核对 | **成熟路由器行为/防火墙/故障控制参考；不是现成加密透明代理** |
| [noaic esp32-socks5-gateway](https://github.com/noaic/esp32-socks5-gateway) | 2026-10-06 | **0 / 0** | 仅 v26.10.16 一次正式 release；2026-10-17 最后推送；当时 GitHub issues 列表为空 | **实验候选**：源码整洁/测试可复用，但无长期外部部署证据 |
| [yanxke ESP32-VPN-Transparent-Proxy-Router](https://github.com/yanxke/ESP32-VPN-Transparent-Proxy-Router) | 2026-08-16 | **6 / 0** | 无 GitHub release；最近源码推送 2026-08-24；Issues #1–#5 都集中于 2026-08-19~24 | **实验候选**：旧版已有构建经验，不视为长期实证 |
| [AliAkrami1375 DRouter-Firmware](https://github.com/AliAkrami1375/DRouter-Firmware) | 2026-07-27 | 4 / 0 | 项目描述宣称透明代理但发布/运维证据不足 | **候补探索，不纳入成熟主要候选** |

数据来自 GitHub repository REST metadata（created_at, pushed_at, stargazers_count, forks_count, release/issue endpoints），是当时快照，会变化；**0 Issues 不代表 0 缺陷，Stars 高也不证明产品安全**。检索时尚未找到有多年外部应用证明、同时完整提供 ESP32-S3 AP 透明 SS2022/VLESS-TLS/IPv6-only 出站/Fail-Closed 的仓库；这是本轮搜索结果范围，不是不存在的证明。

## 2. 源码层面查实的适配障碍

### 官方 esp-iot-bridge：不能不经分析就移植整套

- [官方 wifi_router 示例](https://github.com/espressif/esp-iot-bridge/blob/master/examples/wifi_router/README.md) 明确支持 ESP32-S3 的 SoftAP→STA NAT；[官方 User_Guide](https://github.com/espressif/esp-iot-bridge/blob/master/components/iot_bridge/User_Guide.md) 声称 IDF 5.3 到 6.2 的 SDK 范围。
- [bridge_wifi.c](https://github.com/espressif/esp-iot-bridge/blob/master/components/iot_bridge/src/bridge_wifi.c) 的 `esp_bridge_wifi_init()` 实际包含 `esp_wifi_init()`、`esp_wifi_set_mode(WIFI_MODE_NULL)`、`esp_wifi_start()`；原小智已有 Wi-Fi owner，故**不能直接调用整个初始化链**。
- [iot_bridge/CMakeLists.txt](https://github.com/espressif/esp-iot-bridge/blob/master/components/iot_bridge/CMakeLists.txt) 将 `customer_lwip_hook.h` 注入 lwIP，并调用 `apply_patches_from_list()`；官方项目**同样存在 SDK Hook/补丁集成风险**，P0-1 必须精确审查其 SDK/具体 Kconfig/patch，而不是用“官方”掩盖侵入。
- `bridge_wifi.c`、`bridge_lwip_hook.c` 文件头写明 `SPDX-License-Identifier: Apache-2.0`，但集成前仍须检查逐文件及第三方依赖许可证、固定对应 commit/tag。
- 官方 router 默认 NAT 是 **direct forwarding** 语义；若直接启用，可能绕过 SS2022/VLESS。必须评估先 Drop、后允许的隔离安全边界，不能照搬 NAT 当透明加密代理。

### martin-ger：网络功能成熟，但协议与复制许可证仍需审计

- [README](https://github.com/martin-ger/esp32_nat_router/blob/master/README.md) 明确 AP→STA/ETH NAT、可选 WireGuard、ACL、防火墙、ESP32-S3 固件及网络资源提示；[Security Wiki](https://github.com/martin-ger/esp32_nat_router/wiki/Security) 描述运维安全配置。
- [Issue #267](https://github.com/martin-ger/esp32_nat_router/issues/267)（2026-09-23，仍 open）直接说明项目当前是 IP-level NAT，**不支持直接把 AP 用户的上游流量透明送入 SOCKS5/HTTP/HTTPS 代理**；因此不能把成熟 NAT 模块当作已实现 SS2022/VLESS 的证明。
- README 的 License 部分明确写了 **WireGuard submodule 的条款**；仓库根目录缺少独立 LICENSE（GitHub API repo license 返回 null）。未经逐文件许可证核对，**不能直接复制所有 router 核心**；仅在安全许可明确后选择可复用文件。
- 原始完整 router 的 `esp_wifi_init`/netif 逻辑属于独立固件架构，不得代替小智 app_main。

### NOAIC/yanxke：此前 CI 的真实证明范围

- 历史 PR #17 对 NOAIC 固定 SHA `0be56938acace1d083be746b3f6c60886259e81e` 原版固件、125/125 Python 单元回归、Node 管理测试、yanxke 固定 SHA `dfb04b03154cfaee1d8615e4b8942dfe737abc5d` 的原版 PlatformIO build 验证成功；PR #18 对 NOAIC `flow_table`、`packet_rewrite`、`ap_clients` 六文件原样拷贝和原作者 C harness 验证成功。
- **这些证明导入文件来源一致、对应单元逻辑在测试中成立；没有证明作者数月/数年的现场运行、S3-4B 音频同时工作、协议适配或真正 fail-closed。**
- NOAIC 作者 [ip4.c 局部补丁](https://github.com/noaic/esp32-socks5-gateway/blob/0be56938acace1d083be746b3f6c60886259e81e/patches/lwip-v6.1-transparent-tcp.patch) 需要在校验后 `pbuf **` 更换及输出前重写，无法直接等同官方普通 hook；其 `app_main` 另有 Wi-Fi 初始化，`socks_relay` 是 SOCKS5 NO-AUTH/原生 socket，不是 SS2022/VLESS。
- yanxke 的原透明入口经验只作对照；主任务与 DNS/Wi-Fi 强耦合，不得导入另一数据平面与 NOAIC 双运行。

## 3. 本轮 P0-0 的准入矩阵（没有证据就不选）

| 准入维度 | 可接受证据 | 不可接受的替代品 | 状态 |
|---|---|---|---|
| 生命周期与外部实证 | 多年维护/release、真实用户/Issue 修复、真实硬件日志及长期记录 | 单次 README 测速、刚建仓库、单人单次 CI | 官方与 martin 较强；A/B 不足 |
| 源码许可 | 固定 tag/SHA、逐文件和依赖 LICENSE/SPDX 清单 | “GitHub 是公开的就能复制” | **待 P0-1 补完** |
| 正确网络语义 | AP 仅 TCP 透明、DNS 加密，普通 direct/NAT 无逃逸，断线 Drop | 仅原版 NAT 通网 | **尚无整体可复用证据** |
| 小智保护 | 唯一 Wi-Fi owner / 不动 app_main/音频/LCD/OTA/NVS；安全卸载 | 将 router app_main、Wi-Fi 初始化整份复制 | **官方 bridge 也需适配** |
| SDK/资源边界 | ESP-IDF6.1 lwIP 实际 Hook 时序、可逆补丁、4B RAM/PSRAM 与 PSRAM DMA 共存测试 | 能在独立 N16R8 编译就认为 4B 稳定 | **未验收** |
| 协议与验证 | SS2022 标准服务端互通、VLESS TLS 严格验证、IPv6-only VPS、错误密钥/断链阻断 | 上游 SOCKS5 可转发或旧单测成功 | **未验收** |

## 4. 下一项具体调查清单（本 PR 内执行）

1. 固定官方 ESP-IoT-Bridge 真实 release/commit 与 esp-idf v6.1.x，审查 `bridge_lwip_hook.c`、所有 lwIP patch/注册路径、只借用 AP/netif/DHCP 组件时如何避免第二 Wi-Fi owner；源码证据列到接口级。
2. 以 martin-ger 为路由行为参考：进一步检查 netif/ACL/断线保护、脚本和测试能否作为纯模块直接复用；先核对许可证，不跨界复制。
3. 将 NOAIC、yanxke、DRouter 等实验项目标记 `reference-only until proven`；为每项写“可直接移植的现成实现 / 不可移植的实际原因 / 替代功能成熟度 / 自动化测试证据”。
4. 搜索成熟的 TCP transport/async event loop、ESP-IDF 网络服务及已验证 SS2022/TLS client 组件，比较“官方 Wi-Fi 适配 + 最小透明数据平面”与“成熟 router 隔离子模块”两条路线；补充真实缺口。
5. 不满足上述门槛则保持 P0-0 OPEN，不创建或推进功能性 PR，不刷微雪板。

## 5. 当前真值与约束

- **SOURCE REVIEW：首轮证据已记录；MATURE FULL PROXY ARCHITECTURE：UNVERIFIED**。
- **CI：本 PR 尚待 GitHub Actions；P0-0 尚未合并；真实 4B 设备、DNS/IPv6、双协议 Fail-Closed：NOT RUN**。
- **P0/P1/P2/P3/P4 均 0%；整体 0%（重置后的新验收口径）**。从旧 PR 中复用测试成果，不重新重复已通过的无关工作；若需检查其有效性，仅重新确认固定 SHA 与兼容性。
- 明确禁止新建仓库、删除历史 PR、强推 main、独立初始化第二套 Wi-Fi、自动修改用户 VPS/实机固件及绕过 TLS 证书验证。

## 6. 第二轮：固定来源和可移植边界证据（2026-11-21）

本轮检查不再把 Stars 排名作为替代源码的证据；对长期维护的官方组件，也逐项注明**可沿用和不能直接沿用的调用链**。来源 SHA 是进一步 P0-1 选定冻结版本的调查快照，而不是声称这些版本已经与 XiaoZhi 固件兼容。

| 候选/代码快照 | 已确认的可直接借鉴部分 | 决定性阻断与定位 | 本阶段判定 |
|---|---|---|---|
| `espressif/esp-idf@fff9895c82d744c7237be8847347bdd1b07c6643` 与 esp-lwip `c6f2f878e7b0f86033214b85547d579be43351e3` | `esp_netif` DHCP、BSD sockets、IPv6、`esp_tls`；官方文档含 `protocols/sockets/non_blocking`、`tcp_transport_client` 和 `protocols/dns_over_https` 示例 | 官方 [ip4.c](https://github.com/espressif/esp-lwip/blob/c6f2f878e7b0f86033214b85547d579be43351e3/src/core/ipv4/ip4.c) 中 `LWIP_HOOK_IP4_INPUT(p,inp)` 位于 IPv4 头长度及 checksum 验证**之前**；按这个接口只能消费/放行传入的 `pbuf *`，不能返回新的 `pbuf *` 给 `ip4_input`。没有等价的透明 TCP 完整实现。 | **成熟官方基本库，优先复用**；还需单独处理透明重定向的 hook/packet ownership |
| `espressif/esp-iot-bridge@5b848ef836bcf5c07e17143989f0eb16a0dee003` | 官方 [wifi_router](https://github.com/espressif/esp-iot-bridge/blob/5b848ef836bcf5c07e17143989f0eb16a0dee003/examples/wifi_router/README.md)、Apache-2.0 [组件许可证](https://github.com/espressif/esp-iot-bridge/blob/5b848ef836bcf5c07e17143989f0eb16a0dee003/components/iot_bridge/license.txt)；[User_Guide](https://github.com/espressif/esp-iot-bridge/blob/5b848ef836bcf5c07e17143989f0eb16a0dee003/components/iot_bridge/User_Guide.md) 支持 ESP32-S3 与 IDF6.1 | [patches.list](https://github.com/espressif/esp-iot-bridge/blob/5b848ef836bcf5c07e17143989f0eb16a0dee003/components/iot_bridge/patches/patches.list) 实际含 `dhcp.patch` / `dhcpserver.patch` / `ip4_napt.patch` / `lwip_napt.patch`，作用于 NAT/DHCP，**不是** NOAIC 所需的 `ip4.c` 校验后 TCP pbuf 替换点；`bridge_wifi.c::esp_bridge_wifi_init()` 自行 `esp_wifi_init`/`start`，违反小智唯一 Wi-Fi owner。且 `esp_bridge_wifi_set*()` 使用 `%s` 打印 SSID/密码，整份移植会引入不必要的日志泄露风险。 | **官方参考，不整套移植**；最小所有权适配必须在 P0-1 先核对 |
| `martin-ger/esp32_nat_router@96e6ce483e6f95567860a6d146976f76f1c38ad3` | 成熟维护的 [netif_hooks.c](https://github.com/martin-ger/esp32_nat_router/blob/96e6ce483e6f95567860a6d146976f76f1c38ad3/main/netif_hooks.c) 展示 AP/STA `netif->input/linkoutput` hook、拦截 ACL、故障监控的行为；可用作独立设计审查参照 | 通过 `esp_netif_get_netif_impl()` 取得内部 netif，并修改原有 function pointers；并非公共安全透明代理 API。全项目是 NAT + 可选 WireGuard；[Issue #267](https://github.com/martin-ger/esp32_nat_router/issues/267) 仍请求 SOCKS5/HTTP 透明出口。GitHub repo license=null、根目录无统一 LICENSE，`main/netif_hooks.c` 与 `components/acl/acl.c` 未发现明确 SPDX/授权头（仅抽查），逐文件许可未获证实。 | **长期运行实践参考，暂不复制源码**；先许可澄清，再判定可复用片段 |
| `shadowsocks/shadowsocks-rust`（长期主线） | 成熟、持续维护的 SIP022 / `aead-cipher-2022`，官方协议端到端行为与跨平台服务端、错误路径 | 基于 Rust/大量桌面 OS 运行时，不是现成 ESP-IDF6.1/FreeRTOS 客户端；移植编译和资源成本未证实 | **SS2022 对照实现 / 标准互通测试 oracle**，不要搬整套 runtime |
| `shadowsocks/shadowsocks-c@50f1ae54f737aa66f8edba05bdbf7250ff7f8a60` | 2012 起的 C 代码历史，CI/跨平台互通与部分 SIP022 行为可参考；项目文档记录 2026 年从 libev 迁移 libuv | 当前 README 依赖 libuv；`docs/modernization.md` 还记录 **C++20 核心迁移**，不能笼统说为 ESP32-S3 可直接移植的纯 C 协议库；`LICENSE` 为 GPL-3.0，直接并入本项目有重大许可证评估/合规成本；README 的透明重定向依赖 Linux iptables | **协议测试/实现参考，不作为直接移植候选** |
| `espressif/esp-protocols` + `78/esp-wifi-connect` | 前者为乐鑫长期维护的 `net_connect`、`sock_utils` 等官方组件；后者为小智原有 STA/配网 owner（2024-09 起维护） | 前者的 `net_connect` 是独立连接管理范式而非透明网关；后者必须继续保留唯一 Wi-Fi owner，禁止另加路由器 `app_main` 或第二次 Wi-Fi 初始化 | **优先审查其函数级复用**，列入 P0-1 源码矩阵 |

### 6.1 必须解决的两项新增风险

1. **ESP-IDF DNS 配置是全局的，不按 AP/STA 分离。** 固定 IDF 源码 [lwip.rst](https://github.com/espressif/esp-idf/blob/fff9895c82d744c7237be8847347bdd1b07c6643/docs/en/api-guides/lwip.rst) 明确提醒在多网卡下 DHCP 获取 DNS 可能改写全局 DNS。P0-1/P3 应设计隔离的下游 DNS 应答与加密出口验证，而不能凭 DHCP AP DNS 设置就宣称防泄漏。
2. **Fail-Closed 与 Hook 不是同一个问题。** 上述成熟 NAT 项目默认可以从 AP 经 STA direct；禁用代理或 Hook 仍可能直接上网。P0-1 必须证明存在靠得住的独立 deny/禁止 IP_FORWARD/NAPT 的配置策略（仅允许 DHCP、必要受保护 DNS 本地入口），并设计故障负向测试；在证明前禁止开启 AP 路由。

### 6.2 成熟度与可复用性的两张分开的成绩单

- **成熟且直接可复用**：官方 esp-netif / ESP-IDF BSD sockets / esp_tls / FreeRTOS 与原小智 esp-wifi-connect owner；其具体 4B 组合仍需 P0-1/P0-2 CI。
- **成熟但仅可参考**：Espressif ESP-IoT-Bridge 的完整 router、martin-ger NAT Router、shadowsocks-rust 的 SIP022 行为、shadowsocks-c 的跨平台测试。没有一个已证实可整套满足 AP transparent SS2022/VLESS。
- **较新且已做原版 CI**：NOAIC、yanxke，保留测试/源文件，但不能充当“成熟产品实测”的替代品。
- **明确待定**：局部重定向 Hook 的最终安全抽象、公开许可允许直接复制的网关代码、加密传输与固定 4B 内存预算的组合证据。**这些保留给 P0-1/P0-2，不得在 P0-0 伪造 PASS。**

## 7. P0-0 关闭判定

P0-0 的目标是客观筛选、识别缺口与冻结下一步调查路径，**不是在本 PR 确立永久主实现**。本轮已有：成熟/实验候选分级；多个独立官方源码的函数/补丁/许可证风险定位；阶段与 PR 全路线；历史主选型撤回。只在最新 HEAD 的 GitHub CI 全绿且审计文档一致后，才可合并并计 P0 内 40%（项目 4%）。

下一 PR **P0-1** 要继续深入至接口级：精确复用列表、输入输出 Hook 可行性、真正的 Fail-Closed/服务隔离、SS2022/VLESS 的 transport + DNS 合约及被证实的资源预算，不以高 Stars 替代这些验收。无法找到相应成熟组件时应 STOP，记录风险并重新评估路线，而不偷用实验代码。
