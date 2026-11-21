# P3-3 — SS2022/VLESS IPv4 + IPv6 双协议退出验收

**阶段 PR 规划保持不变：P3 总计 3 个 PR，#11=P3-1（40%）、#12=P3-2（35%）、本 PR=P3-3（25%）。**

## 官方实现与规范（2026-11-21）

- SS2022：沿用固定 Git SHA 的 `rlog/atoms3r-muse-firmware` 原版 BLAKE3/AES-GCM，后端复用 [官方 shadowsocks-rust](https://github.com/shadowsocks/shadowsocks-rust) v1.25.0 镜像摘要 `sha256:1816b2b09f3db929a688e48efb1333e4ee459ba158a951f9e73c3580628ab964`；重放保护按 [SIP022](https://shadowsocks.org/doc/sip022.html) 而非手写服务端。
- VLESS：保持 [Espressif 官方 ESP-TLS](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32s3/api-reference/protocols/esp_tls.html) 及系统证书链、SNI/证书 SAN 验证；主机通过 OpenSSL shim 验证实际 C 适配器，真机使用 ESP-TLS。
- DNS：根据 [RFC 1035](https://www.rfc-editor.org/rfc/rfc1035.html)，核对回复事务 ID 和 QR 标志。**已发现并在本 PR 修正** SS2022 回包未核对这两项的防线，VLESS 既有校验保留。
- 底层依旧是 `yanxke/ESP32-VPN-Transparent-Proxy-Router@dfb04b03154cfaee1d8615e4b8942dfe737abc5d` 的 lwIP TCP 流表、官方 ESP-IDF SLAAC/STA IPv6 与 P1 Fail-Closed 补丁。绝不重写这些成熟组件。

## P3 退出测试矩阵（全部自动化）

| 协议 / IP 家族 | TCP/DNS 成功用例 | 负向及安全断言 | 证据类型 |
|---|---|---|---|
| SS2022 + IPv4 | 官方 Rust TCP echo、TCP/53 DNS | 错误 PSK、错误 DNS 密钥、重放 Salt、过期时间戳、服务端离线 | 官方独立协议服务端 |
| SS2022 + IPv6-only | 官方 Rust `::1` TCP echo、TCP/53 DNS | 错误 PSK、Salt 重放、旧时间戳、关闭后无直连回退 | 官方独立协议服务端 |
| SS2022 + A/AAAA | IPv6 优先、同一节点 IPv6 故障后尝试节点 IPv4 | 不允许连接客户端原始目的 IP；IPv4 节点 NVS v1→v2 兼容 | 生产 C 连接代码 + 系统 DNS |
| VLESS/TLS + IPv4 | OpenSSL 校验证书链和 SNI、VLESS TCP/DNS | 不受信任 CA、主机名错误、过期证书、无效 VLESS header、断线 | 生产 C 适配器 + 独立 OpenSSL TLS 服务端 |
| VLESS/TLS + IPv6-only | IPv6 AAAA-only 上同样完成 TCP/DNS | 与 IPv4 同等证书/错误和无明文回退矩阵 | 真实 IPv6 socket + OpenSSL |
| 双协议 DNS 语义 | 正确 ID 与 QR 的加密回答 | **错 DNS ID 或 QR=0 必须拒绝、原查询缓冲不变** | 独立 Python 造包 + 生产 C 解密 |
| 整合固件 | P1/P2/P3-1/P3-2 全部接入 R8N16 目标构建 | 旧明文 VLESS/Direct 不可达、Wi-Fi AP 不提供 IPv6、官方双 OTA 分区不改 | ESP-IDF/PlatformIO 全构建 + 源码检查 |

说明：正确的 TLS 握手与代理协议仍不等于真实公网网络路径成功；Host CI 不会宣称 ESP32-S3/微雪 4B 的驱动、电源、内存、语音兼容已验收。

## 脚本范围及保密控制

- 所有新增连接仅指向 GitHub CI Linux runner 的 `127.0.0.1` 和 `::1`；`/etc/hosts` 临时提供测试 AAAA/A。不会使用用户节点、真实 VPS IP、真实 UUID 或 PSK。
- 模拟造包仅用于检验负向逻辑，真实 SS2022 正向/错误密钥/重放用例仍由官方 Rust 完成。官方服务端的容器镜像固定确切摘要，临时配置只有公开测试密钥。
- 过期证书使用临时生成的**有效 CA + 已过期 leaf SAN**，以确认即便 SNI 正确也不能放行。生产 ESP-TLS 仍使用官方 bundle。
- 断线、错误 DNS 回包、认证失败均拒绝，不切换到直连或未加密传输，DNS 异常需保留原请求以返回 P1 SERVFAIL。
- SS2022 NVS 凭证**仍未加密**。不得因为本次 Host CI 全绿而删除这一发布安全阻断项。

## P3-3 验收与阶段退出

**状态：PENDING CI / PR OPEN。** 本阶段须在同一个 PR 中通过新增双栈故障矩阵、所有历史回归和修改后 **R8N16 全量固件编译**，再 Squash Merge、更新 `docs/PLAN.md` 进度。

P3=100% 仅表示 P3 的**源码、协议功能、CI 固件编译**验收完成。以下 P4 专属结果仍 **NOT RUN**：

- 微雪 4B 精确板型的供电、PSRAM、Flash/分区和稳定固件备份/恢复验证。
- 上游 STA 真实 Router Advertisement、IPv6 默认路由与用户实际公网 IPv6 VPS 连通性。
- 真实下游手机 AP IPv4 透明代理、IPv6/DNS/UDP 防泄漏抓包，断电/断链重启及长时间资源压力。
- 小智语音 + LCD + Wi-Fi 共存、音频延迟、PSRAM 高水位、双协议连接数/重连。
- 敏感凭证 NVS 加密和生产配置安全；未满足时禁止正式固件发布。

**无需用户执行任何真机测试即可完成 P3 主机/CI 验收；P4 实机验证不得由这些证据替代。**
