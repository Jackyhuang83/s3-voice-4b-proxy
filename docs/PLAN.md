# S3-Voice 4B Proxy — P0–P4 PR Master Plan v1.2

**计划先行：所有阶段的 PR 内容、预算、验收标准在修改代码前统一规划。** 2026-11-21 制订。

需求基线：R1 = 下游 AP 仅 IPv4，透明 TCP，SS2022/VLESS，两协议均不开发互联网 UDP、XUDP、QUIC；R2 = 上游 STA 能用 IPv6 连接 IPv6-only VPS，下游 AP 不提供 IPv6。现有小智语音固件保持稳定，直到 P4 才集成。

- **总 PR 预算：16 个，上限每阶段 5 个。** P0 3 个，P1 4 个，P2/P3/P4 各 3 个。
- 功能实现、负向测试、CI 故障修复必须在已规划的 PR 内完成；不为一次编译失败额外开 PR。
- PR 编号由 GitHub 生成。未来项目以 P1-4、P2-1 等作为稳定的计划 ID，避免假定 GitHub 编号。
- 先调查官网与 GitHub 源码、Issues、PR、已验证类似工程；再选择最小改动；先自动测，再安排必须的 4B 实测。
- P0–P3 的通过不代表真机验收；实机专属验证严格在 P4。

## 1. 完整 PR 任务与权重

| 阶段 | 计划 PR | 交付范围 | 合并验收门槛 | 阶段权重 | 状态 |
|---|---|---|---|---:|---|
| P0 | [#1](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/1) | 仓库、R1/R2、阶段需求、安全边界 | README、需求与计划文件、初始文档 CI | 35% | MERGED |
| P0 | [#2](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/2) | 固定透明路由上游 commit，原始 R8N16 编译 | 指定版本 PlatformIO 编译通过 | 35% | MERGED |
| P0 | [#3](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/3) | VLESS/SS2022/IPv6 接口和改动范围审计 | 源码证据与接口路径记录、质量检查 | 30% | MERGED |
| P1 | [#4](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/4) | 固定上游静态分析与代码质量基线 | clang-format、控制流、静态分析通过 | 15% | MERGED |
| P1 | [#5](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/5) | TCP-only 入口和互联网 UDP/QUIC 阻断，保留 DHCP/DNS | 补丁可应用、策略静态检查、修改后 R8N16 编译通过 | 30% | MERGED |
| P1 | [#6](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/6) | 路由直连开关隔离、STA 断开时保持截获、Fail-Closed 最小修复；同时固定本 PR 总计划 | 所有 CI 通过、仅 TCP-only 编译生效、确认不会自动选择 direct | 25% | MERGED (#6; e5b4d768) |
| P1 | [#7 / P1-4](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/7) | 集中补充源侧/宿主机回归测试：TCP、短 UDP、DHCP、AP 本地 DNS、分片异常、资源耗尽、断链及无直连旁路；P1 阶段总结 | 负向测试与修改后固件构建通过；未能模拟的真实 Wi-Fi 项目明确留至 P4 | 30% | MERGED (#7; a7692a898) |
| P2 | [#8 / P2-1](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/8) | 从 rlog 选择性导入 AES128-GCM SS2022 TCP 协议和最低必要依赖，保留许可证 | 单元编译、协议向量、密钥/时间/内存边界审核 | 30% | MERGED (#8; 4864ea768) |
| P2 | [#9 / P2-2](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/9) | 与现成透明 TCP 流表/中继接口结合：SS2022 请求封装、加密读写、连接资源生命周期 | 不复制 lwIP TCP 路由器；修改后固件编译及协议数据流测试 | 40% | MERGED (#9; 29022f735) |
| P2 | P2-3 | SS2022 IPv4 VPS 互通和认证错误/中断/错误密钥负向测试，P2 阶段总结 | 可复现的端到端 TCP 互通与 Fail-Closed 自动验收 | 30% | PLANNED |
| P3 | P3-1 | VLESS 标准 TLS + ESP-TLS，统一加密 TCP stream I/O 边界 | 证书链/主机名/SNI、TLS 错误处理及 read/write/close 测试通过 | 40% | PLANNED |
| P3 | P3-2 | 上游 STA IPv6 SLAAC/默认路由、AF_INET6/AAAA VPS 拨号，两协议接入同一个 TCP 连接层 | IPv6-only mock/远程 TCP、IPv4 fallback 规则验证；AP 仍 IPv4-only | 35% | PLANNED |
| P3 | P3-3 | SS2022 与 VLESS 对 IPv4/IPv6 VPS 的端到端互通，证书/路由中断测试，P3 总结 | 双协议双地址族验证通过；无凭证泄漏和违规直连 | 25% | PLANNED |
| P4 | P4-1 | 微雪 4B 对应板型与小智语音/LCD/Wi-Fi 驱动资源集成、无损回退方案 | 确认正确硬件版本和资源配置，不覆盖稳定镜像；完成集成构建 | 35% | PLANNED |
| P4 | P4-2 | 4B 真机 Wi-Fi AP 客户端透明 TCP、IPv6-only VPS、DHCP/DNS、防泄漏、重启及长期运行验收 | 实机日志、问题清单、自动与现场验证分离；语音显示无回归 | 40% | PLANNED |
| P4 | P4-3 | 安全与性能收尾、Recovery 操作、固件 release | 可复现构建、回滚文档、实机验收证据和发布检查表 | 25% | PLANNED |

每个阶段只能在规划的所有验收门槛满足时标为 100%。新的需求或重大安全问题必须先更新这张计划表及 PR 预算，再开始相关实现。

## 2. 进度计算，不凭印象打分

**阶段完成百分比 = 该阶段已 MERGED 且通过既定自动/源码验收的各 PR 权重之和。** Draft、Open、CI 成功但未合并一律计 0%；4B 实机专属验收只在 P4 计分。

固定整体权重：
- P0: 10%
- P1: 25%
- P2: 25%
- P3: 25%
- P4: 15%

总进度 = Σ(阶段完成百分比 × 整体阶段权重)，四舍五入到整数百分比。避免在验收标准未变的情况下主观微调数字。

### 当前快照（2026-11-21；P2-2 已验收并合并，真实 VPS 与 P4 实机尚未开始）

| 阶段 | 完成率 | 计算依据 |
|---|---:|---|
| P0 | **100%** | #1/#2/#3 已合并：35+35+30 |
| P1 | **100%** | #4/#5/#6/#7 已合并：15+30+25+30；仅代表 P1 源码与自动化门槛 |
| P2 | **70%** | #8/#9 已合并：协议向量与独立本地 TCP/DNS 互通、Fail-Closed 源码验证、完整 R8N16 固件编译 PASS；真实 IPv4 VPS 待 P2-3 |
| P3 | **0%** | 未开始 |
| P4 | **0%** | 未开始 |
| **整体** | **53%** | 100%×10% + 100%×25% + 70%×25% = 52.5%，显示 53% |

这是一张 **PR/阶段交付管理进度表**，不代表设备现在可用。特别是 P4 的 0% 表示尚未完成任何 4B 真机验收。

## 3. 每次交付的固定报告模板

**PR：** 计划 ID / GitHub 链接 / OPEN or MERGED / 具体 commit  
**源码变更：** 真实改动，复用项目与版本，是否涉及密钥和回退  
**验收：** 构建、静态检查、协议互通、4B 真机分别标注 PASS/FAIL/NOT RUN  
**进度：** P0 __%｜P1 __%｜P2 __%｜P3 __%｜P4 __%｜整体 __%  
**下一任务：** 优先处理当前阶段已规划的下一 PR，不擅自拆新 PR

## 4. 阶段运行纪律

1. **先资料**：微雪原版板型和固件、ESP-IDF 官方文档、上游固定 SHA、相关 issue/PR/测试、可借鉴的其他仓库。
2. **后编码**：最大限度复用既有透明 TCP 代码、SS2022 AEAD、ESP-TLS；只写最小适配和最必要的测试。不得发散到 XUDP、Reality、HY2、Snell 或完整 IPv6 AP。
3. **CI 在 PR 内修**：一个功能一个 PR，失败直接在该分支追加提交，不因为失败单独起 PR。
4. **门槛不造假**：原版编译、补丁编译、加密协议互通和 4B 实机结果清晰区分。
5. **阶段验收先于下一阶段**：当前阶段的剩余验收风险有明确纪录，实机不能用 CI 代替。
6. **安全与回退**：不上传密钥，不无依据地切换 direct 或擦除 NVS，不在未证明可恢复前刷写 4B。

此文件是唯一权威 PR 计划与进度计算规则；每次 PR 合并时同步更新状态、阶段百分比和总体百分比。
