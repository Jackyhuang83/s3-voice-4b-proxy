# P4-2 | 4B 运行时网关与实机验收门槛

**唯一 PR、40% 阶段权重；P4 总权重 15%。** P4-1 在 #14 完成源码/构建基线；P4-2 必须在这一 PR 内实现真正的可启停加密 TCP 网关，不能把尚未完成的网络运行时伪装成成功。

## 任务顺序与依赖

1. **S1：可证明撤销的监督状态机（前置安全门）** — 不允许自动 ARM，节点健康必须来自真实认证 SS2022/VLESS 回合；失效、STA 掉线、AP 停止、配网切换均撤销旧 token；旧任务返回后不能恢复转发。源侧与主机负向矩阵、ESP-IDF 6.1 编译 PASS。
2. **S2：FreeRTOS 有界服务** — 现有单 Wi-Fi owner 的 APSTA，绑定 AP-only UDP DNS :53 和 TCP :15001；启动前完成 DNS/TCP listener 与节点健康验证，限制并发、内存/栈、超时、重启退避；安全安装原 P1 AP output Hook。失败必须原子停止截获并关闭 client/worker socket，不得直连旁路；不得阻塞 Xiaozhi 音频事件。
3. **S3：可授权配置与真实协议** — 不在仓库写入密码；默认不启动代理 AP。明确提供启用/停止与节点配置/状态检查，验证 SS2022 与标准证书验证 VLESS/TLS；STA 可使用 IPv6-only VPS，下游 AP 仅 IPv4 TCP + 加密 DNS。
4. **S4：验收矩阵** — CI 宿主机负向测试/IDF 整镜像/资源预算；4B 上 AP 连接、DHCP/DNS、TCP 访问、错误密钥、节点断线、UDP/QUIC/DNS/IPv6 不泄露、反复断连与语音/LCD/触控不回归。没有实机记录必须标注 **NOT RUN**。

### 责任与不触及范围

- 此 PR 不负责 P4-3 NVS 加密、正式镜像发布、eFuse 或恢复刷写；但任何实机刷写前都需独立可靠的原版备份和可验证恢复方案，不得根据猜测刷固件。
- 复用 pinned Espressif ESP-IDF 6.1、`78/xiaozhi-esp32`、`78/esp-wifi-connect 3.3.3`、P1 原透明 TCP 与本仓库 P2/P3 已验证传输。APSTA 由单一 Wi-Fi owner 管理。官方文档：<https://docs.espressif.com/projects/esp-idf/en/release-v6.1/esp32s3/api-guides/wifi-driver/overview.html>、<https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/network/esp_netif.html>。
- P4-2 不验收前 P4 保持 35%、整体 90%；通过 CI 不等于实机 PASS。
