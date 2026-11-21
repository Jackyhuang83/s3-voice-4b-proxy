# S3-Voice 4B Proxy — P0–P4 PR Master Plan v1.3

> **2026-11-21 双轨治理更新（R1 恢复验证 / R2 独立研发）**  
> 本文件为 **R1 历史实现路线**的完整 P0–P4 PR 总规划；最初正文中的 “R2=STA IPv6-only 出站”是当时的功能子需求，不代表 2026-11-21 后新架构 R2 分支。**R1 继续包含已实现的 STA IPv6-only 出站候选功能**，但其真机仍待 P4 证明。  
> **R1 固定基线**：`r1/stable-p4-1@07e1584b45b270f86a6236fbd74b8ac29c92f473`（PR #14 合并点）；**R1-P4-2**：原 PR #15 单 PR 继续审查/开发/验收（旧提交只证明 S1 状态机和原版构建，不等于已运行的网关）；**R1-P4-3**：原计划安全发布 PR，不提前启动。**R2 独立分支**：`r2/development`，旧 NOAIC 新架构实验文件不进入 R1。main 暂不作为 R1 刷机来源。  
> **R1 验收口径（PR/CI 交付，不等于设备可用）**：P0=100%、P1=100%、P2=100%、P3=100%、P4=35%（P4-1 35%、P4-2 40%、P4-3 25%），整体精确 **90.25%**，对外可四舍五入为 **90%**。P4-2 未合并与真机未测均为 NOT RUN；不能把 90% 当作可刷机程度。R2 的进度单独计算，目前整体 4%。  
> **刷机硬阻断**：P4-2 中任何真机更新前，必须完成当前设备原固件、NVS、分区表/OTA 数据及资源的可核实只读备份与恢复方案；确认备份真实可用，并获得用户明确的当次刷机批准。严禁把 CI 临时生成的 merged binary 直接视为安全刷机包。实测应在所有软件侧负向矩阵达标后集中进行。P4-3 继续做加密密钥、最终恢复演练、性能和正式 Release，不得用 P4-3 的计划取代刷机前安全门槛。  
> **R1-P4-2 单 PR 内计划**：S0 源码/可移植/备份安全预检（本轮）→ S1 复用已有 epoch 状态机和 C11 负向测试 → S2 有界 FreeRTOS AP DNS/TCP workers、真实认证节点状态、无直连兜底、关闭/故障回收 → S3 确定性的配置与管理员显式启停 → S4 完整 4B CI、资源检查 → S5 原固件与 NVS 备份恢复门槛达标后的一次性集中实机验证。S0～S5 只占 **原 #15 一个 PR**；只有全部 P4-2 既定验收完成并合并才计 40%。  
> P4-3 在原路线仍为 25%，不得新增无必要 PR。完整 S0 的可追溯证据见 [R1-P4-2-PREFLIGHT](R1-P4-2-PREFLIGHT.md)；R2 的独立 GDGS 路线保存在 `r2/development:docs/R2-PLAN.md`。  

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
| P2 | [#10 / P2-3](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/10) | 固定官方 shadowsocks-rust 服务端 IPv4 TCP/DNS 互通、错误密钥/时间戳/盐重放/中断 Fail-Closed 自动测试，P2 阶段总结 | 官方服务端端到端 TCP/53、认证和故障负向测试 + 修改后 R8N16 CI；真实公网 VPS 与 4B 实测另标 NOT RUN | 30% | MERGED (#10; 31fbb815) |
| P3 | [#11 / P3-1](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/11) | 复用官方 ESP-TLS 认证标准 VLESS TCP/DNS，保留上游流表并禁止旧明文 VLESS、直接 UDP 旁路 | CA/SNI/SAN 证书验证、读写与负向安全测试、修改后 R8N16 固件构建；Reality 不属于本 PR | 40% | MERGED (#11; 43befc6c) |
| P3 | [#12 / P3-2](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/12) | 上游 STA IPv6 SLAAC、SS2022 AF_INET6/AAAA 代理节点拨号与 v1→v2 凭证兼容、VLESS 验证 TLS 的 AAAA IPv6-only 拨号 | 官方 Rust IPv6-only TCP/DNS、真实 IPv6 TLS CA/SNI、同节点 A 回退 + R8N16 全构建；AP 实机 IPv6 防泄漏留 P4 | 35% | MERGED (#12; b19c0c7f) |
| P3 | [#13 / P3-3](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/13) | 官方 SS2022 IPv4/IPv6 TCP/DNS、错误密钥/重放/过期/离线；VLESS/TLS 双栈证书及过期证书；DNS 事务 ID/QR Fail-Closed 回归；P3 退出验收 | 同一 PR Head 的双协议双地址族真实协议测试、负向故障矩阵、R8N16 全构建及历史回归全部 PASS；公网及 4B 实机留 P4 | 25% | MERGED (#13; c7f30f01) |
| P4 | [#14 / P4-1](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/14) | 微雪 4B 对应板型与小智语音/LCD/Wi-Fi 驱动资源集成、无损回退方案；代理网络组件作为**默认关闭**的可编译集成底座 | 正确板型/原始音频 LCD OTA 分区完整，单一 Wi-Fi 所有权，安全源检/负向测试及 IDF6.1 **完整 4B 单镜像构建通过**；不含 AP 实机通网 | 35% | **MERGED** (#14, 07e1584b；11/11 同提交 CI PASS)，网关运行与实机留 P4-2 |
| P4 | P4-2 / 单一 PR | 在 P4-1 默认关闭底座上接通**受监督的 APSTA / 本地 DNS / 透明 TCP 运行时**，明确授权启停、节点健康、断线 Fail-Closed；完成 4B 真机 Wi-Fi AP 客户端透明 TCP、IPv6-only VPS、DNS、防泄漏、重启及长期运行验收 | 源码及 CI 端到端负向验证、任务/资源退出与无旁路；实机日志、自动与现场验证分离；语音显示无回归 | 40% | IN PROGRESS：独立 P4-2 分支，先做失效代际防护和 CI，未进行实机验收 |
| P4 | P4-3 | 安全与性能收尾、Recovery 操作、固件 release | 可复现构建、回滚文档、实机验收证据和发布检查表 | 25% | PLANNED |

**P4-1 / P4-2 边界澄清（不新增 PR、权重不变）**：P4-1 的“集成构建”是可编译、单镜像、默认关闭的语音优先适配基线，不代表已经启动 AP、代理监听或可以刷机；P4-2 承接网络服务启动与任务监管、故障保护和全套 4B 实机验收。不得以 P4-1 的 CI 替代 P4-2 的功能/实机验收。首次刷写须有原始固件及 NVS 只读备份和可证明回滚的恢复路径。具体编译验收见 `docs/P4-1-EXIT.md`。

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

### 当前快照（2026-11-21；P0–P3 与 P4-1 全部合并并通过源码/CI 门槛；P4-2 实机及运行时待验收）

| 阶段 | 完成率 | 计算依据 |
|---|---:|---|
| P0 | **100%** | #1/#2/#3 已合并：35+35+30 |
| P1 | **100%** | #4/#5/#6/#7 已合并：15+30+25+30；仅代表 P1 源码与自动化门槛 |
| P2 | **100%** | #8/#9/#10 已合并：SIP022 向量 + 官方 ssserver-rust 实际协议 TCP/DNS 互通、错误密钥/重放/旧时间戳/离线负向测试、修改后 R8N16 编译全部 PASS；真实公网 VPS 与 4B 实机 NOT RUN |
| P3 | **100%** | #11/#12/#13 已合并（40+35+25）：标准 VLESS/ESP-TLS、SS2022 双栈 Rust 服务端、错密钥/重放/时间戳/离线、IPv4/IPv6 证书异常与过期证书、双协议 DNS ID/QR 拒绝、完整 R8N16 构建及 10 项 CI PASS；真实公网/4B 实机 NOT RUN |
| P4 | **35%** | P4-1 / PR #14 已合并；P4-2 / P4-3 尚未通过验收 |
| **整体** | **90%** | 100%×10% + 100%×25% + 100%×25% + 100%×25% + 35%×15% = 90.25%，按计划四舍五入为 90%；不代表硬件可用 |

这是一张 **PR/阶段交付管理进度表**，不代表设备现在可用。P4 的 35% 只对应已完成的 P4-1 构建；4B 真机验证尚未开始。

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
