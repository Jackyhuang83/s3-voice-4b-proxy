# P4-2 | 4B 运行时网关与实机验收门槛

**唯一 PR、40% 阶段权重；P4 总权重 15%。** P4-1 在 #14 完成源码/构建基线；P4-2 必须在这一 PR 内实现真正的可启停加密 TCP 网关，不能把尚未完成的网络运行时伪装成成功。

## 2026-11-21 — S1/S2 增量实现（暂不验收）
- S1：实际设备 P4-1 policy 新增 epoch session 双重授权门。保留历史 policy host 测试，并新增 stale-policy/epoch 负向矩阵。未完成 S2/S3 前，device session 未初始化，AP 仍无法启用。
- S2 增量：新增 AP-only DNS-over-TCP :53 接口，复用已存在的加密 DNS processor 和 ESP-IDF socket；每连接至多处理一个 RFC 7766 帧，长度与 I/O 时限受限，未经过认证时仅可能 SERVFAIL。尚未接入 FreeRTOS 工作任务、节点联机认证或客户端取消机制。
- 以上只属于代码、host 与 IDF CI 检查对象。S3 实机与完整 Fail-Closed 依旧 NOT RUN；禁止刷写/合并。

## 2026-11-21 S2 增量：可信节点探测（未完成整机运行时）
- 用 ESP-IDF esp_fill_random 生成单次 DNS 查询 ID；直接复用既有 SS2022 加密 DNS 或证书验证的 VLESS/TLS DNS 接口；严格匹配 DNS 问题与应答、拒绝错误应答和隧道失败，无直连 fallback。**首次探测不可使用需网关 READY 的 s3_gateway_dns_process，否则产生启动循环依赖。**
- 探测仅输出布尔结果供未来的监督器调用 s3_gateway_session_node_proven(epoch)；不直接授权、没有自动 AP 启动，也不能单独视为安全或实机验收。
- 运行时启动/停止 FreeRTOS 任务、epoch 令牌对应的实际 worker 取消、真实 VPS 双协议以及硬件测试均 NOT RUN。

## S2 DNS worker 集成（待最新 HEAD CI）
已在原 4B 隔离构建源上接入 AP-only FreeRTOS UDP DNS/TCP DNS worker：
- 只有显式 NVS AP 凭据有效、原 Wi-Fi owner 启动 APSTA、配置 DHCP DNS 以后，才启动两个低优先级 DNS 服务任务。默认不启动 AP；没有代理节点时仅返回本地 SERVFAIL，不会直连。
- STA 和配网事件同时通知 P4-1 policy 与 P4-2 epoch 会话；重启 AP 不重新初始化 epoch；未提供管理员 ARM 入口。
- AP stop 先撤销 epoch 和工作任务，再限时等待退出后释放 AP netif。若超时则保留隔离的 AP netif，不再主动触发故障崩溃；需要后续实机与模拟 stop 竞态检查。
- **本项仅代表 DNS 运行任务基础接线，透明 TCP relay 工作任务、活动 socket 的有界取消、可信节点启停、资源预算和实际 4B 功能仍未验收。**

## G4 核查：ESP-IDF 6.1 AP DNS 与小智 STA DNS 隔离
- Espressif `components/esp_netif/Kconfig` 中 `ESP_NETIF_SET_DNS_PER_DEFAULT_NETIF` 默认为 `n`；默认 lwIP DNS 服务器是全局值。为了避免 AP 本地 DNS 配置覆盖小智 STA 默认解析，隔离构建明确启用 `CONFIG_ESP_NETIF_SET_DNS_PER_DEFAULT_NETIF=y`，并验证生成 `sdkconfig` 中仍为 `y`。
- 这不意味着运行时已验证 DNS 隔离；仍须后续同时观察 AP DHCP option 6 与小智 STA 正常域名解析/音频等行为，检查异常重连和默认 netif 切换。
- 官方依据：https://docs.espressif.com/projects/esp-idf/en/release-v6.1/esp32s3/api-reference/network/esp_netif_programming.html ，https://github.com/espressif/esp-idf/blob/release/v6.1/components/esp_netif/Kconfig 。

## R1-P4-2 运行时撤销增强（待 CI / 未实机）
- 撤销 monitor 为第五个低优先级 FreeRTOS 任务，独立于可能被网络调用阻塞的 DNS 和 relay worker，每 20 ms 轮询失效状态并在互斥保护下 shutdown 当前 AP 客户端 socket；不主动关闭其他任务拥有的 fd，避免重用 fd 被误关。
- 真实 Xiaozhi STA disconnect 和配网进入事件现在明确发送 revoke（修正早先缺失的事件接线），而不仅是更新 policy；每次重新授权都要求重新对节点加密探测。全部 worker 停止前 AP netif 继续保留，不能保证此前持有的上游 TLS fd 在断网时立即回收。
- 修复 epoch 被撤销后 DNS 监听标志不会自动恢复的问题：管理员再次明确授权时，核对现存监听器并重新记录 DNS ready，而非允许旧任务重新授权。
- 当前 API 仍需上层明确调用管理员 arm，尚缺最终安全的本地节点配置/按键 UI/实机资源记录。不能把“源码实现”和“可供用户直接操作”混淆。

## S2/S3 节点准备与硬件时间
- SS2022 时间戳机制改为优先复用小智已有的系统时间；只有系统时钟仍不可信时才尝试启动现成 Espressif SNTP。避免重复起一套 SNTP 影响小智。
- 提供两种显式管理员入口：内存中传入经验证的 VLESS/TLS 或 SS2022 参数，以及加载原 P2 物理 USB 已保存 SS2022 NVS 节点。所有入口均不会自动 ARM；尚待在确认可用的触控/UI 路径接线。
- 管理员异步操作互斥；旧活动 TCP 客户端未退出不得替换节点密钥；失败清除策略并拒绝直连。
- **仍缺完整设备 UI/串口授权入口、上游 TLS socket 在所有取消边界的有界回收证据、客户端真实互联网互通与原版备份。不得宣称实机就绪。**

## G2/G3 钩子安装回读（待 CI）
- 原 P1 `transparent_tcp_install_ap_output` 返回 void。现在利用固定来源的 P4-only overlay 添加只读已安装检测函数，要求 AP netif 的 IPv4 output 与 linkoutput 指针均确实指向透明 TCP Hook，才会设置 P4-2 `OUTPUT_HOOK_READY`。若部分或完全安装失败，一律拒绝授权，无 direct 回退。
- 只校验已安装；仍需真实 4B 在关闭和 AP 重启时验证 Hook 原始指针恢复。

## 任务顺序与依赖

1. **S1：可证明撤销的监督状态机（前置安全门）** — 不允许自动 ARM，节点健康必须来自真实认证 SS2022/VLESS 回合；失效、STA 掉线、AP 停止、配网切换均撤销旧 token；旧任务返回后不能恢复转发。源侧与主机负向矩阵、ESP-IDF 6.1 编译 PASS。
2. **S2：FreeRTOS 有界服务** — 现有单 Wi-Fi owner 的 APSTA，绑定 AP-only UDP DNS :53 和 TCP :15001；启动前完成 DNS/TCP listener 与节点健康验证，限制并发、内存/栈、超时、重启退避；安全安装原 P1 AP output Hook。失败必须原子停止截获并关闭 client/worker socket，不得直连旁路；不得阻塞 Xiaozhi 音频事件。
3. **S3：可授权配置与真实协议** — 不在仓库写入密码；默认不启动代理 AP。明确提供启用/停止与节点配置/状态检查，验证 SS2022 与标准证书验证 VLESS/TLS；STA 可使用 IPv6-only VPS，下游 AP 仅 IPv4 TCP + 加密 DNS。
4. **S4：验收矩阵** — CI 宿主机负向测试/IDF 整镜像/资源预算；4B 上 AP 连接、DHCP/DNS、TCP 访问、错误密钥、节点断线、UDP/QUIC/DNS/IPv6 不泄露、反复断连与语音/LCD/触控不回归。没有实机记录必须标注 **NOT RUN**。

### 责任与不触及范围

- 此 PR 不负责 P4-3 NVS 加密、正式镜像发布、eFuse 或恢复刷写；但任何实机刷写前都需独立可靠的原版备份和可验证恢复方案，不得根据猜测刷固件。
- 复用 pinned Espressif ESP-IDF 6.1、`78/xiaozhi-esp32`、`78/esp-wifi-connect 3.3.3`、P1 原透明 TCP 与本仓库 P2/P3 已验证传输。APSTA 由单一 Wi-Fi owner 管理。官方文档：<https://docs.espressif.com/projects/esp-idf/en/release-v6.1/esp32s3/api-guides/wifi-driver/overview.html>、<https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/network/esp_netif.html>。
- P4-2 不验收前 P4 保持 35%、整体 90%；通过 CI 不等于实机 PASS。
