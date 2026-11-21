# R2-P1-1 NOAIC 透明 TCP 核心原样移植

> **历史文档 / 已撤回选型（2026-11-21 R2-P0-0）**：此前“NOAIC 唯一/首选数据平面”的正式选型结论已失效；本文件保留为旧版源码/CI 记录，不得作为后续移植指令或产品成熟度证据。最新唯一有效路线参见 [R2-PLAN](R2-PLAN.md)，重新审计见 [R2-P0-0-MATURITY-AUDIT](R2-P0-0-MATURITY-AUDIT.md)。历史测试结果不被删除，亦不计入新的验收进度。

范围严格符合 R2-PLAN：**原样移植作者已经验证的 IPv4 TCP flow、packet rewrite、AP client owner 三组源码；不开发新算法、不启用 AP、不刷机**。

## 原始出处与字节一致性

- 上游：[noaic/esp32-socks5-gateway](https://github.com/noaic/esp32-socks5-gateway)，`v26.10.16` / **`0be56938acace1d083be746b3f6c60886259e81e`**，MIT；许可证逐字节复制到 `components/s3_noaic_core/LICENSE.noaic`。
- 六个源文件 `flow_table.c/.h`、`packet_rewrite.c/.h`、`ap_clients.c/.h` 是来自这个固定 Git 提交的**未修改字节级复制**。GitHub CI 从同一 Git SHA 检出来源，逐一 `cmp -s` 和 SHA256，失败即拒绝合并。
- **唯一必要自有编译代码**：`proxy_config.h`，只包含原作者头文件要求的六个资源/配额宏（原作者 `proxy_config.h` 在 ESP 平台依赖自己的 `gateway_settings.h`、NVS 和 Wi-Fi 配置，不能直接带进小智）。资源宏先保持原版默认值确保复现测试；**不是最终音频与网关共存的并发预算**。
- `CMakeLists.txt` 注册这三组源文件成为 ESP-IDF 组件，**当前没有被 Xiaozhi 启用或链接到生产镜像**，R2-P3 才允许在原版 voice-first build 中以单一数据面接线。

## 本 PR 的原作者测试，不是自己重写

- 将作者原版 `tests/flow_table_harness.c` 直接用 **本仓库实际导入的** `flow_table.c` 编译并运行。
- 将作者原版 `tests/ap_clients_harness.c` 直接用 **本仓库实际导入的** `ap_clients.c + flow_table.c` 编译并运行。
- 将作者原版 `tests/test_packet_rewrite.py`（固定上游）再次运行；仓库导入 `packet_rewrite.c` 由逐字节 `cmp` 强约束等同于原版，避免复制或改写整套 Python 测试。
- 继续重跑原本 P0 的原版 NOAIC 125 项 Python 和 Node、yanxke 原版固件等工作流，但不以这些替代移植后的实际 C harness。
- P1-1 禁止导入第二套 hook、Socks5 明文 upstream、互联网 UDP/XUDP、web 管理、LED/NVS，不能覆盖 `78/xiaozhi-esp32` 的任何文件。

## 后续保留的安全阻断点

- 原作者 `tcp_poc.c` 及 `ip4.c` project-local 补丁的 Hook 时机差异留 **R2-P1-2**；未经等价/SDK 检测不能打开 intercept。
- SS2022/VLESS-TLS 的真实加密双向流留 **R2-P2**，保留旧版验证资产，不重写密码学。
- APSTA、唯一 Wi-Fi owner、音频/LCD/配网、代理启停及 DNS 留 **R2-P3**。
- 真实 4B 设备性能、断线防泄漏和稳定回退留 **R2-P4**；未验证真实原版固件+NVS备份前禁止烧写。

**验收：**UPSTREAM source exact，原作者 C harness against imported files，原作者 packet negative vectors，GitHub 新 head CI 全绿；但 **ESP-IDF 4B runtime、实机均 NOT RUN**。
