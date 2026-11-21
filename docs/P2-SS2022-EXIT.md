# P2-3 SS2022 IPv4 服务端互通 / Fail-Closed 阶段退出验收

状态：**PASS / MERGED**。P2 #8/#9/#10 共三个计划 PR 已全部合并，阶段自动化验收通过，P2 100%。

## 已调查并复用的官方实现

- 官方 SS2022 规范：<https://shadowsocks.org/doc/sip022.html>，重点是 AES-128-GCM、严格 16-byte PSK、±30 秒时间窗、服务端请求盐 60 秒重放检测及独立 AEAD 响应认证。
- 官方独立服务端：<https://github.com/shadowsocks/shadowsocks-rust>，容器 `ghcr.io/shadowsocks/ssserver-rust:v1.25.0`；严格固定官方 GHCR **Linux/amd64** 摘要：
  `sha256:1816b2b09f3db929a688e48efb1333e4ee459ba158a951f9e73c3580628ab964`
  来源：<https://github.com/shadowsocks/shadowsocks-rust/pkgs/container/ssserver-rust>。
- 不复制、不修改 Shadowsocks Rust 的源码。运行官方镜像真实服务器；设备侧沿用 P2-1 通过 Git blob pin 的 `rlog/atoms3r-muse-firmware` C 协议实现及 P2-2 的原 TCP 流表适配器。
- **服务器和目标仅监听 127.0.0.1，Docker 使用 Linux host network**，所以官方容器可以访问 CI 本机的回显服务与 TCP/53 DNS 服务；不连接任何个人生产 VPS，不使用任何真实密钥。
- 测试专用公开 PSK 是 `AAECAwQFBgcICQoLDA0ODw==`，只用于临时容器，既不提交真实密钥，也不要求用户提供节点。

## P2-3 集中验收矩阵

| 场景 | 验收结论要求 | 证据类型 |
|---|---|---|
| 编译生产 `s3_ss2022_link.c` + `muse_ss2022.c` | GCC/ASan/UBSan 与固件编译均通过 | 编译 |
| 官方 `ssserver-rust` 接收请求、连接目标 127.0.0.1 TCP | C 适配器收到认证的 `pong` | 真实独立服务端协议互通 |
| SS2022 中的 TCP/53 DNS | 正确返回 `0x8180` 响应且不使用直连 UDP | 真实独立服务端协议互通 |
| PSK 错误 | 不转发未认证明文，不宣称“成功” | 服务端拒绝 + C 侧负向测试 |
| 客户端请求盐重复 | Rust 服务端拒绝第二次握手，目标不出现第二次命中 | SIP022 服务端重放保护 |
| 请求时间戳超出 ±30 秒 | Rust 服务端拒绝，目标没有新增 TCP 连接 | SIP022 真实负向测试 |
| 服务端停止 / TCP 拒绝连接 | C 侧返回失败，无直连旁路 | 故障注入 |
| TCP EOF 发生在首个服务端认证响应前 | C 侧不得返回成功 | 修复生产适配器 + 源码断言/真实失败回归 |
| PSRAM/连接计数/NVS 释放 | 保持 P2-2 的内存与清理路径，异常关闭不占用永久连接 | 源码/host sanitizer 检查 |
| 原版、P1、P2-1/P2-2 的既有回归 | 需要在 **同一 PR HEAD** 上全部成功 | GitHub Actions |

**说明：** 本项测试属于真实的**协议服务端实现互通**，但不是通过互联网连接用户自己的公网 VPS。现阶段只有服务端运行在 CI 本机的 IPv4 回环接口；网络路径、QoS、MTU、蜂窝/酒店 Wi-Fi、4B 的 FreeRTOS 并发和内存高水位仍无法从此证明。

## P2-3 发现的故障保护修复

在 P2-2 基础上将 `s3_ss2022_relay()` 的两处收到 TCP EOF 的分支从“直接返回成功”调整为 **只有已经完整通过服务端响应认证、且首个响应帧已处理完成** 才允许报告成功（`rx->phase == 2 && !rx->failed`）。错误 PSK、服务端无响应、连接中断或异常认证时必须关闭连接，绝不回退到未加密 TCP。

不修改原版 `muse_ss2022.c` 的任何密码算法，也不新增 UDP/QUIC 功能；不修改 P1 lwIP hook 的 Fail-Closed 基线。

## 生产发布禁止条件

**当前 SS2022 凭证仍以未加密 NVS 格式保存。** 它仅用于技术验证，绝不宣称生产安全就绪。P4 必须采取可验证的 NVS 加密/安全凭证处理，或在发布门槛直接阻止实机固件对敏感节点启用。

**P3（VLESS 正规 TLS 与 IPv6-only VPS）和 P4（微雪 4B、小智语音/LCD、Wi-Fi 与硬件防泄漏）均为 NOT RUN。** 本阶段不刷写设备、不变更既有固件或生产环境。ESP32-S3 的真实硬件吞吐、PSRAM/堆压力、AP 断链场景属于 P4。

## P2 退出状态

**PASS（官方真实协议服务端互通，非公网 VPS 或 4B 实机）**： [PR #10](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/10) 已 Squash Merge，合并 SHA `31fbb815851eab6afa0af574d760f89eb85a9154`。 [官方服务器 CI run](https://github.com/Jackyhuang83/s3-voice-4b-proxy/actions/runs/44879299827) success。实际日志确认：TCP `pong`、加密 TCP/53 DNS、错误 PSK、错误 DNS 密钥、重复 Salt 拒绝、过期时间戳拒绝、服务器停机 Fail-Closed 全部 PASS。固定 PR Head SHA 上的 7 项 GitHub Actions（含 P0/P1/P2-1/P2-2）全部通过，修改后 ESP32-S3 R8N16 固件编译成功。

**NOT RUN / P3-P4 继续验收**：真实公网 VPS、4B Wi-Fi/音频/LCD、IPv6-only VPS、NVS 加密及生产安全发布。P2 的 100% 仅代表其既定源码、自动化及官方 SS2022 服务端互通门槛，不能宣称可在用户设备中安全运行。
