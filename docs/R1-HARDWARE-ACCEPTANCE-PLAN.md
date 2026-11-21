# S3-Voice R1 — Waveshare ESP32-S3 Touch LCD 4B 一次性集中实机验收计划

状态：**PLANNED / hardware 0%**。仅规划，不构成刷机授权。已通过 P4-2 11/11 CI、P4-3 12/12 CI；两项硬件验证目前 NOT RUN。**固定两条 PR：P4-2 #15 → P4-3 #20，不新增开发 PR。**

## 目标与原则

- 在同一次硬件验收中检查 AP → SS2022 或证书验证的 VLESS/TLS → VPS → Internet，并确保原版 Xiaozhi 语音、LCD、触控与 Wi-Fi 没有回归。
- 优先验证可恢复路径，合理情况下仅安装一次应用测试固件；严禁直接用 merged-binary、工厂整片镜像或 erase-flash 覆盖原用户 NVS/OTA/assets。
- 由 AI 完成 GitHub、官方文档、原始芯片/板卡/分区审计、CI 和日志分析；使用者只执行必要的线下连接、只读备份与获批准后的单次固件更新。
- P4-3 原生 NVS 加密仍未启用，普通 NVS 中包含开发密钥；**本次可判定功能通过，不能在未验证原生加密前发布生产固件**。
- 不测试/新增 Reality、XUDP、QUIC/UDP 出口、下游 IPv6 透明路由；非关键低概率边缘强化移至后续迭代。

## H0-H6 全阶段路线图（100% 为本轮硬件验证百分比，与 GDGS 项目进度不同）

| 阶段 | 权重 | 前置条件 | 操作与交付 | 通过条件 | 停止条件 |
|---|---:|---|---|---|---|
| H0 原机基线 | 10% | 无 | ESP32-S3 Touch LCD 4B N16R8 实物核对、原 Xiaozhi 语音/LCD/触控/联网样本、确认 UART/USB 数据连接 | 原设备正常，不用改配置即可记录 | 型号不符、原功能异常、供电不稳定 |
| H1 只读安全与全片备份 | 20% | H0 | 只读 eFuse、Flash-ID、安全启动/加密状态；16MiB 全片读出、本地 SHA256 + 6 分区核对、离线复制 | 可验证原机固件完整备份，安全状态已知；绝不公开任何 NVS dump | 安全启动/Flash 加密状态不明、读取受限、分区不同、备份校验失败 |
| H2 更新和回退预检 | 15% | H1 | 核对活动 OTA 槽、未使用槽、bootloader/otadata、恢复机制与软件镜像校验；事先确定只更新哪个 inactive OTA app | 独立可执行的恢复路径和对应原应用镜像已确认；用户另行授权写入 | 不能判定活动槽/目标槽、没有可靠回退、固件哈希不符 |
| H3 单次受控应用更新 | 15% | H2 + 本次写入授权 | 仅经核准官方 OTA/otatool 合规流程安装一个 app-only 测试镜像；启动后先测试原语音/LCD/触控 | 设备可正常启动，原 Xiaozhi 主要功能正常，AP 默认未授权 | 启动异常、语音/LCD/触控回归、无回退路径 |
| H4 集中双协议实际功能 | 25% | H3 | 本地可信物理串口配置一次测试 AP、SS2022、VLESS/TLS；手机/Mac AP DHCP/DNS、HTTP/1.1/HTTPS、VPS 出口、可选 STA IPv6-only 上游 | 两种加密协议分别通过、网页 TCP 可用、上游 DNS 无明文直接回退 | AP 无法连接、协议证书失败、DNS 外泄、绕行 |
| H5 断线与恢复 | 10% | H4 | 物理长按停用代理、断开一次上游、一次重启、检查 UDP/QUIC/下游 IPv6/远端 DNS 不泄漏；验证可用官方 OTA 回退原版（可回退路径明确且获授权） | 故障默认阻断公网转发，STA 语音正常、原应用能恢复 | 私网语音异常、外网直连泄露、原版恢复不可行 |
| H6 证据及发布决策 | 5% | H5 | 汇总脱敏日志、结果、恢复说明；分别决定 PR #15/#20 是否可验收与合并 | 每个门槛有 PASS/FAIL/NOT RUN 真实记录 | NVS 无原生加密时不得宣布生产发布可用 |

**本轮设备进度：H0=0 H1=0 H2=0 H3=0 H4=0 H5=0 H6=0，总体 0%。** 软件 CI 绿灯不占用这里的硬件百分比。

## 第一批安全操作：H0 和 H1（不刷写）

先准备 Mac、可靠数据 USB-C 线、板卡、稳定电源；断开不必要的串口程序。微雪原板卡区分 “USB TO UART” 与 “ESP32-S3 USB” 两个接口，优先使用标识清楚的 USB TO UART；**GPIO0 BOOT 与 PWRKEY 是不同按键**。记录原版小智一次正常唤醒/对话、屏幕显示和触摸。

在 Mac 上找出正确设备端口（不要想当然使用别的设备号）：

```sh
ls /dev/cu.*
```

确认官方 esptool 和 espefuse 已安装后，使用官方只读操作：

```sh
python3 -m esptool --chip esp32s3 --port PORT flash-id
espefuse -p PORT summary
```

以上命令会连接/重启串口设备，但不应执行 Flash 写入、擦除或烧写 eFuse；**不要分享完整 MAC、eFuse 私有密钥字段、节点密钥或原机 dump**。如 Flash Encryption/Secure Boot/下载模式读取受限，则 H1 STOP，不准强行 --force。

原始分区布局确认符合官方固定 78/Xiaozhi (not just generic Waveshare factory firmware) 后，使用 PR #20 现有只读工具：

```sh
python3 tools/p4_flash_backup.py capture --port PORT --out ./s3-r1-private-backup
python3 tools/p4_flash_backup.py verify --dir ./s3-r1-private-backup
```

注意：工具要求目标目录尚不存在，且在**本地**执行；会产生含 Wi-Fi/节点/账号信息的 16MiB `fullflash-private.bin` 和 `manifest.json`。存储目录权限 0700、文件 0600；用户自行安全离线复制一份，**绝不上传任何备份到 GitHub 或聊天**。只有确认 SHA256 和原六个分区无误才能标记 H1 PASS。

## H2：实际刷写方式必须先确认，不能预先猜写入偏移

原版 16MB 分区位置：

| 标签 | 起始地址 | 容量 |
|---|---|---|
| nvs | 0x9000 | 0x4000 |
| otadata | 0xD000 | 0x2000 |
| phy_init | 0xF000 | 0x1000 |
| ota_0 | 0x20000 | 0x3F0000 |
| ota_1 | 0x410000 | 0x3F0000 |
| assets | 0x800000 | 0x800000 |

两个 OTA 分区都可能有数据；**不能仅因其中一个叫 ota_1 就假设它空闲**。需要从设备引导记录或 ESP-IDF 官方 otatool 的只读 otadata 中确定实际活动 app/boot 状态。验收脚本/候选镜像必须使用同一 commit 的可追溯 SHA，确认 app image fits OTA partition，并检查回滚配置与当前 OTA app 是否有启动资格。

Espressif 官方 OTA API 使用 esp_ota_get_running_partition、esp_ota_get_next_update_partition、esp_ota_set_boot_partition；自动回滚只有在设备 bootloader 配置明确支持时才可依赖。没有经过只读核对且批准的安装步骤就**不提供猜测性的 esptool write-flash 地址**。恢复以保留的原应用槽优先，不以微雪 FactoryXiaozhi 镜像代替私人原机备份；微雪整片厂包通常从 0x00 开始，会覆盖设备原配置。

## H3/H4：只做一轮完整功能验证

软件候选来自 PR #20 经 12/12 CI 成功的完整 4B 构建（P4-3 workflow run 44920129142）：应用 `xiaozhi.bin` 0x2c0b10 bytes；应用分区 0x3f0000 bytes（剩余约 30%）。这是未经验收候选，仅在 H2 PASS、H3 另获批准后安装。启动先核对 Xiaozhi 语音、麦克风、扬声器、AEC、LCD、触控和 STA；AP 按设计默认不自动授权代理。

本地节点配置**仅使用可替换的测试密码和测试 VPS**，不把日常生产 SS2022/VLESS 密钥写入明文 NVS。当前用户可操作入口来自 P4-2：
- Waveshare 4B **PWRKEY / IO 扩展器按键**约 1.5 秒松开：打开物理 ESP-IDF 串口配置控制台；不要误用 GPIO0 BOOT 语音键，也不要长按至 4 秒 PMIC 关机档位。
- `s3_ap TEST_SSID TEST_PASSWORD` 保存 WPA2 AP（密码 12-63 字符）；需要重启生效。
- `s3_ss VPS_HOST PORT BASE64_KEY` 保存 **SS2022 2022-blake3-aes-128-gcm** 节点，16 字节密钥的 base64；节点必须支持 TCP。
- `s3_vless VALID_TLS_CERT_HOST PORT UUID` 保存 **标准 VLESS over verified TLS** 节点；不支持 Reality/跳过证书验证。
- `s3_use ss2022` / `s3_use vless` 选择协议；`s3_status` 只显示配置状态；物理按键约 2 秒松开启停，均无远程管理端口。
- 真机确认串口 echo 等隐私风险，命令中含明文口令，不在公开终端录屏/聊天或日志保存中直接展示。

先用 Mac（便于重复执行批量 curl/dig）作为 AP 客户端，再用手机 Safari 验证真实网页访问。同一镜像分别切换 SS2022 和 VLESS/TLS，无须重刷：DHCP IPv4、AP 颁发的 DNS、加密 DNS 上游解析、HTTP/1.1 和 HTTPS 正常；出口 IP 与测试 VPS 一致；原小智 STA 语音不受影响；STA IPv6-only VPS 采用已经具备 IPv6 连接的网络进行可选测试。

**设计边界：** AP 不提供外部 UDP、QUIC 或 IPv6 转发，部分仅支持 UDP/QUIC 的 App 不通属预期，不能把这类应用作为 TCP 代理成功的必要条件。

## H5：只测必要的故障/恢复

- 物理关闭代理 → AP 外网无法继续访问，而小智自身 STA 语音不受影响。
- 使测试节点不可用或 STA 断开一次 → 代理客户端不得通过明文/direct 绕过，DNS 不得明文外泄。
- 重启一次 → SS2022/VLESS 节点选择和 AP 密码持久化；管理员代理授权不应自动恢复。
- 验证原应用的恢复**实际可行**：优先保留原 OTA app，利用官方受控方式切回；如果无法在原版布局、otadata、加密状态下可靠地切回则 STOP，不强行恢复或覆盖全片 Flash。

以上优先用真实使用路径复现，不对未出现的 <20% 理论并发/极端疲劳场景增加额外测试轮次。

## H6：验收分层和进度

- H4、H5 加原 Xiaozhi 回归通过后，**可将 P4-2 的功能实机验收标记 PASS**（但 PR 合并仍依原 GDGS 审批/依赖处理）。
- P4-3 的工具、备份和恢复 **可以**通过本次硬件验证；**原生 NVS 加密未开启**，所以 P4-3 的生产安全验收持续 NOT RUN/BLOCKED，除非后来采用 Espressif 官方 HMAC-NVS 或 Flash Encryption 路线并获得用户对不可逆操作的单独批准。
- 没有设备实际回读和被批准的恢复路径就不刷写；不自动 burn eFuse、迁移 NVS、erase-flash、写入 0x00 merged binary 或发布生产固件。
- 当前项目 GDGS 记分：P0=100%、P1=100%、P2=100%、P3=100%、P4=35%、总体=90.25%。软件 CI 和本轮预先计划**不改变正式进度**。H0–H6 单独从 0% 记录。

## 官方来源

- 微雪板卡、USB/PWRKEY/BOOT：https://docs.waveshare.com/ESP32-S3-Touch-LCD-4B
- 微雪工厂整片镜像烧录（地址 0x00，**不是**本项目 app-only 更新方法）：https://docs.waveshare.com/ESP32-S3-Touch-LCD-4B/Firmware-Flashing
- esptool read-flash 与安全约束：https://docs.espressif.com/projects/esptool/en/latest/esp32s3/esptool/basic-commands.html
- espefuse summary（只读）：https://docs.espressif.com/projects/esptool/en/latest/esp32s3/espefuse/summary-cmd.html
- OTA、otadata、回滚：https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/ota.html
- 原生 NVS 加密：https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/api-reference/storage/nvs_encryption.html
