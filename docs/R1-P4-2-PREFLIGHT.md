# R1-P4-2 · S0 上线前深度预检 / 一次性 S3 实机验证门槛

> 首次审查：2026-11-21。**S0 只做源码和 CI 证据、绝不刷用户 4B。** R1 继续使用原路线，不自动接受 R2 NOAIC 导入模块。R1 稳定基线为 `07e1584b45b270f86a6236fbd74b8ac29c92f473`（#14 merged），P4-2 现有 `p4/4b-runtime-gateway-validation` 只是先行 S1 状态机；后续修复必须继续在原 PR #15，CI 失败在原 PR 修复。

## 一、已经有的真实证据（不重做）

| 项 | 固定源码/CI 证据 | 判断级别 |
|---|---|---|
| 小智 4B 原板/双麦/480x480 LCD、触控、OTA、资源与原 16MB 分区 | [P4-1 EXIT](P4-1-EXIT.md)、[BOARD](P4-BOARD-INTEGRATION.md)；`xiaozhi-esp32@831ffd14188553cc887408b75396ae38618538e0`，ESP-IDF release-v6.1 | 原版源审计 + 完整 4B **编译通过**，绝非实机语音/屏幕 PASS |
| P4-1 11/11 CI 与完整固件 | #14 merged commit `07e1584`；#14 最终 head `92c320a` 的 GitHub 11/11 success | 全镜像编译与 host 负向测试 PASS；产物不当发布镜像 |
| 既有 SS2022/VLESS TLS 与 IPv6 出站 | #8-#13 正式协议兼容/错误路径测试及 CI | 标准对端/host PASS；4B STA + 实际 VPS 尚 NOT RUN |
| P4-2 S1 可撤销 session/epoch | #15 原 HEAD `0a3d1228b506d2381dfc85a76e81e086f7a33d36` 的 `s3_gateway_session.c` 与 host tests | 原始逻辑/构建 CI PASS；**只做决策，没有可信节点探测、AP 任务/开关完整接线** |
| 原版回退/恢复 | 原分区无 factory app、原版资产和 OTA 分区不改 | **NOT VERIFIED**：独立可用原厂固件、用户实际 NVS、当前 OTA slot/otadata 和故障恢复尚未建立 |

## 二、需要修复/验证的实际阻断点（含源码位置）

| 编号 / 级别 | 已查到的源码事实与真实风险 | P4-2 单 PR 内关闭条件 |
|---|---|---|
| **G1 / NO-GO** | `components/s3_gateway_tcp/s3_gateway_tcp_server.c` 只公开 `s3_gateway_tcp_listen` 和同步 `s3_gateway_tcp_accept_and_relay`，`components/s3_gateway_dns/s3_gateway_dns_udp.c` 只公开 open/poll；两者尚无实际 FreeRTOS bounded worker 的启动/撤销与 AP 生命周期监督；`docs/P4-1-EXIT.md` 明确标识网关未激活 | 利用现有成熟 ESP-IDF socket/select 和原 SS2022/VLESS 传输，完成有界任务/epoch/cancel/close，不阻塞小智音频；真实协议认证才 READY。并在 CI host 模拟断线和重启 |
| **G2 / NO-GO** | `components/s3_gateway_policy/s3_gateway_ip4.c` 未绑定 AP 时返回放行以保护小智 STA；这是正常冷关闭行为，但 **不能由此证明**一旦启用 AP 或配置成 IP_FORWARD/NAPT 后仍 fail-closed。正式实现还依赖 `transparent_tcp_is_reinjecting` 和 `ip4.c`/netif 处理边界 | 静态检查 AP/STA 路由隔离、所有早退/未认证/错包/断网路径；host 负向包向量 + 4B 实机 AP/STA 双侧抓包证明**无明文 direct/UDP/IPv6/DNS 绕路**。任何 bypass 即停止硬件测试 |
| **G3 / NO-GO** | `components/s3_gateway_ap/s3_gateway_ap_runtime.c` 只在 `s3_proxy_ap` NVS 显式存在有效凭据时准备 APSTA，默认 voice STA-only；`tools/p4_prepare_wifi.py` 保留原 esp-wifi-connect 的唯一 Wi-Fi owner；但错误/重复启停后的 AP hook、netif、DHCP、socket 顺序和堆内存未在 4B 实测 | 精确记录初始化/授权/停机顺序；旧 socket 不能复活；stop 后必须恢复 netif/output Hook；配置 AP 和音频任务必须同时无回归 |
| **G4 / NO-GO** | `components/s3_gateway_dns/s3_gateway_dns_processor.c` 负向处理返回 SERVFAIL，正常 DNS 必须走 SS2022/VLESS；但 AP TCP :53 本地服务与 DHCP option 6 的全链路尚未验收，ESP-IDF `lwip.rst` 说明 DNS 服务器设置可能是全局的 | 每个 AP UDP/TCP DNS 请求只送加密代理（或明确返回 SERVFAIL）；不能污染小智 STA 默认 DNS；双栈 AAAA-only 与错误 DNS 对端测试；本机/STA/DNS 抓包不泄露 |
| **G5 / NO-GO** | 4B 原始 `partitions/v2/16m.csv` 双 OTA app 各 `0x3f0000`，assets 8MiB；`docs/P4-BOARD-INTEGRATION.md` 发现没有可依赖的 factory partition；小智和 Wi-Fi owner 原版均存在 NVS 错误时擦除路径，P4-1 仅在**隔离构建源中**阻断 | 在任何首次写入之前，对用户**实际设备**做可校验只读固件/NVS/otadata/partition/assets 备份，复核存档和可用恢复方式；须有官方/微雪适用板型恢复步骤和用户当次明确授权。**无备份=不刷** |
| **G6 / NO-GO** | 4B 编译空余约 32% app OTA 分区，不等于运行内存安全；LCD 双帧缓冲、音频 AEC 与代理 socket/TLS buffer 争 PSRAM/内部 RAM；此前编译不能证明共存 | 保持原版音频/显示优先；固件 CI resource/stack 数量，4B 集中实测记录最低 internal heap、largest block、PSRAM、并发 1/2 手机及语音质量；死锁/OOM 不可称 PASS |
| **G7 / NO-GO** | `tools/p4_prepare_voice.py` 与 `tools/p4_prepare_wifi.py` 均为 CI **临时构建 overlay**，并不自动把配置界面/节点导入/固件部署到真实设备；外部 VPS 真实节点尚未验收 | 单一可复现构建标识/测试配置方法；禁止提交密钥；两种协议分别实测；可手动禁用恢复原语音，无需刷回才可禁网关 |

## 三、执行顺序（先软件验证，后一次集中硬件验证）

1. **S0 / 本 PR 当前**：记录可信 R1 固件 SHA / 原始 CI、G1-G7 的阻断和测试定义。复用 #15 已做 S1，不创建额外功能 PR；不从 R2 移植新代码。
2. **S1-S3 / 原 #15 内**：修原 worker 缺失、严格的手动 arm、节点认证、超时/资源限制、事务撤销、APSTA 单管理器事件同步、DNS TCP/UDP 及 Fail-Closed。用官方 ESP-IDF sockets/FreeRTOS/ESP-TLS 与已有协议实现，不新写 AES/TLS、另一 Wi-Fi 管理器或另一透明数据平面。
3. **S4 / 原 #15 内**：固定来源的全 4B 编译，官方 shadowsocks-rust/验证 TLS 对端回归，CRC/hash/source provenance，错密钥、错证书、STA 掉线、AP 重连、DMA/堆和 DNS 正负向自动化测试。**CI 全绿只允许进入备份准备，不等于真机 PASS。**
4. **S5 / 一次真实设备集中操作**：先只读备份及恢复可行性审查，之后**经用户确认**才刷经过 S4 的 4B 版本；验证原声/屏/触控/配网/OTA，手机 AP DHCP→网页 HTTPS（SS2022 和 VLESS/TLS），IPv6-only VPS、DNS/UDP/IPv6 no-leak、节点故障阻断、关闭/重启恢复及长时资源。一个项目的实验性吞吐记录不得替代本板真机。
5. **P4-3 / 后续原计划 PR**：NVS 秘密加密方案、正式固件发布、稳定/恢复回归和 Release。若密钥安全影响第一次刷写，需提前把安全保护作为 P4-2 前置门，而不能拖到 P4-3。

## 四、集中 S3 验收脚本的人机边界

单次硬件验收时，只需要用户配合：保留现有可用原固件/已配置小智、连接可恢复的 USB 数据线、开启已确认恢复方式，并按 AI 准备好的**统一测试表**观察必要的语音/LCD/触控现象。网络代理抓包、自动协议测试、构建和排错由 CI/AI 先做；不能每改一个地方就要求重复刷写。当前没有接入用户板子，所以实机列 **NOT RUN**；不得推测备份存在或设备现在可以刷机。

## 五、双轨分支纪律与进度

- **R1 发布基线**：`r1/stable-p4-1@07e1584`，正在审查的 P4-2 只在原 `p4/4b-runtime-gateway-validation`（PR #15）上变更，目标分支必须是 R1。R1 无需重新生成 P0-P4-1。
- **R2 开发基线**：`r2/development`，P0-0 PR #19 仅合并到 R2；未来新架构所有 PR 不得面向 R1 或 main。
- 当前按照原计划：**R1 P0=100%、P1=100%、P2=100%、P3=100%、P4=35%，整体 90.25%（报告四舍五入 90%）**。这代表合并历史阶段权重，不代表 4B 客户端可用；R1 P4-2 当前 NOT ACCEPTED。R2 P0=40%，P1-P4=0%，整体=4%。
- **一票否决**：缺设备备份、未知恢复、明文/直连泄漏、音频/触控损坏、代理无法关闭、任务泄漏、证书跳验、资源耗尽，均禁止进入真实刷写/正式发布。

## 六、官方恢复资料复核（2026-11-21）

- **微雪原厂镜像确实存在**：官方 [4B Firmware Flashing](https://docs.waveshare.com/ESP32-S3-Touch-LCD-4B/Firmware-Flashing) 指向 `FirmWare/ESP32-S3-Touch-LCD-4B-FactoryXiaozhi_250807.bin`；厂商 [4B Resources](https://docs.waveshare.com/ESP32-S3-Touch-LCD-4B/Resources-And-Documents) 提供来源和下载工具。这只是**厂商原厂基线候选**，不证明与用户当前板上小智版本、MAC、NVS/OTA/asset 数据完全相同。还须核对 Flash、分区与 SHA，不可简单用原厂包覆盖用户定制状态。
- **只读备份命令有官方来源**：Espressif [esptool ESP32-S3 Basic Commands](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/esptool/basic-commands.html) 支持 `read-flash`，并可用哈希核对导出文件；但命令是否在用户板的安全设置下可用尚需 read-only 查证，**不得把可读原始 SPI flash 假定为总是可恢复的明文**。
- **双 OTA 不保证自动回退**：Espressif [OTA 参考](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/ota.html) 按 OTA image state 和 `otadata` 工作；没有 factory app、`otadata` 损坏或启动失败时应单独验证恢复路径。当前 4B 的厂商键控“factory 分区”方案不适用于已核实缺少 factory app 的 16m 布局。
- **Flash Encryption/Secure Boot 必须先调查**：Espressif [Flash Encryption](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/security/flash-encryption.html) 提醒加密状态影响原始备份读取/恢复，错误写入明文可能导致设备不能启动。首次接入时只能读取安全状态、分区和原始 Flash，不能未经批准做 erase/写 eFuse/解锁安全模式。
- **预检状态**：厂商镜像来源 SOURCE CONFIRMED；**用户设备原固件、原 NVS、当前 Flash Encryption/Secure Boot 配置、完整备份哈希与恢复演练均 NOT RUN**。以上条件达标前，一律禁止刷写，即使 GitHub 11/11 仍为绿色。

