# R2-P0-2｜两套原版网关构建和自动化回归复现

**状态：CI 核对中，尚未选出最终移植底座。** 依照 R2-P0-1 的三项目标：优先直接移植、继承作者测试、保留小智并可恢复。此 PR 不写自定义路由器代码、不移植协议、不刷设备。

## 精确来源与原版验证方法

| 候选 | 固定原始提交 | 固定工具链 | 不修改的原始测试/构建 |
|---|---|---|---|
| A: [noaic ESP32 SOCKS5 gateway](https://github.com/noaic/esp32-socks5-gateway) | **v26.10.16** `0be56938acace1d083be746b3f6c60886259e81e` | ESP-IDF 6.1 Git `fff9895c82d744c7237be8847347bdd1b07c6643`、作者自带的 `patches/lwip-v6.1.json`+原版 `tools/prepare_lwip.py`，xtensa 官方 install.sh | 复制作者 CI 的 `apply → check → idf.py build → idf.py size → unittest discover -s tests -v → 两项原版 Node 测试`；只在 `noaic` 临时工作目录内产生构建文件 |
| B: [yanxke ESP32 VPN Transparent Proxy Router](https://github.com/yanxke/ESP32-VPN-Transparent-Proxy-Router) | `dfb04b03154cfaee1d8615e4b8942dfe737abc5d` | 原始 PlatformIO 6.1.18, espressif32@7.0.1 | **复用仓库现成** `.github/workflows/p0-upstream-build.yml` 的干净 upstream `pio run -e esp32s3_r8n16` 与 `.github/workflows/p1-upstream-quality.yml` 的原始 lint/static analysis；两者已在旧版和 #16 同一提交成功，不重复编写测试实现 |

## 安全边界与单次 CI 策略

- 在本 PR 中**将 A 的原版复现 CI 作为第二个 job 加入现存 `.github/workflows/p0-upstream-build.yml`**，不依赖新建工作流的 PR 触发注册；B 继续使用本仓库现存原始构建与质量 gate，每次 PR head 同步自动运行，不为了显示“两份测试”复制无意义的 30 分钟工作流。
- 审计脚本或 CI 仅可对 upstream clone 本身创建临时本地 `components/lwip` 覆盖，**禁止修改全局 IDF 或原小智目录**；绝不运行 `flash`、`upload`、`erase`、`esptool write_flash`。
- 只报告精确版本、原作者测试案例、退出码、构建大小和是否使用原作者固件板上运行记录。原作者的吞吐记录不是我们小智 4B 的实测。
- 如果官方 GitHub/组件仓库服务中断，记录为基础设施失败并重试原 PR，绝不通过删除测试、更换未审计版本、关闭 TLS 验证绕过。

## 移植决策：优先保留全套成熟数据面

P0-2 对两个候选按照 `docs/R2-PLAN.md` 的 100 分评分机制逐项附来源核实后决定。尤其审查：

1. **成熟可复制代码：**候选 A 的 `flow_table.c/.h`、`packet_rewrite.c/.h`、`ap_clients.c/.h`、`socks_relay.c/.h` 等，与原版对应测试，尽量不改内部逻辑。
2. **真正阻断点：**A `tcp_poc.c` 依赖特定 IDF 的 ip4.c；原小智只有其自己的 Wi-Fi 启停与 app_main，因此不能直接移植 A/B 的主程序。先证明官方 Hook 与原补丁的差异，再选最小版本化 patch/适配。
3. **加密协议边界：**A 的 SOCKS5 握手必须替换成现成 SS2022/VLESS 会话，但不应重写上游的流表/转发队列。选定的代理引擎需要支持端到端认证，而非 SOCKS5 弱加密或直连。
4. **资源预算：**小智语音/LCD 要共享有限 internal RAM/PSRAM，禁止默认照搬 A 的 64 条会话与大缓冲；不经实测只采用较保守的并发上限，之后一次集中实测调优。
5. **失败可退：**不重写小智 app_main/Wi-Fi owner/NVS 恢复，网关默认关闭，前置授权；退回原语音固件的安全路径在实机写入前核对。

**完成定义：**原始源版本/许可证验证 + 双候选构建/原版测试状态分项可证实 + 具体移植文件清单及最少适配调用点 + 确定选择（附硬性阻断解释）。此文档当前是验收模板，不能冒充测试结果。
