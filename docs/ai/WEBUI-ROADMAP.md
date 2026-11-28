> **2026-11-28 用户最终范围决定（优先级最高，覆盖本文旧阶段的任何 4B 引用）：** 当前 S3-Voice 项目**只交付网页版 AI 助手 WebUI**：独立账户与权限、网页文字和连续语音、通用 API/模型供应商切换、opencode.json 导入、iPhone/iPad/桌面浏览器适配、稳定发布与回退。
> **永久移出当前项目范围：** ESP32-S3 Touch-LCD-4B 硬件、固件、刷写、配对、设备 OTA/A04 网关、4B 音频 A07、R1/R2 透明代理，用户以后在另一个项目单独规划；本项目不以其完成/验收作为前置条件。
> **基础设施复用边界：** WebUI 可继续经已有隔离的浏览器 WSS/Opus 网关访问已经部署的音频/ASR/TTS 服务，但不以此授权修改任何 4B 设备通道或现有生产后端。旧版文档中的「4B 真机验收、A04 调试、固定模型厂商」均为历史记录，不再是当前 WebUI 交付门槛。阶段权重 10/20/25/20/15/10、原 PR 结构保留；P3 只指网页语音稳定性，P4 只验浏览器，P5 仍后置。

# S3-Voice WebUI — 低成本 AI 助手路线图 v1.0

**锁定日期：** 2026-11-26
**实施仓库：** `Jackyhuang83/s3-voice-4b-proxy` 的独立 `docs/ai/` 与 `webui/` 工作线；原 R1/R2 透明代理工程互不依赖。
**目标硬件：** 微雪 ESP32-S3 Touch-LCD-4B（16MB Flash / 8MB PSRAM）；当前已有的 4B 固件及 16MB 原厂备份均不得未经专门验收修改。
**服务器：** 现有 Debian 13、官方 XiaoZhi `server_0.9.8`、A03/A04、VoskASR、GenericGPTLLM、EdgeTTS；部署前重新做只读资源检查。
**首期预算：** 不增加按分钟计费的实时语音 API；文本 LLM/VPS 仍可能计费。严禁把 EdgeTTS 描述为无网络、永久免费或官方可用性承诺。

## 产品范围和决策

1. 第一版浏览器客户端支持文字、实时语音、会话上下文、GPT/DeepSeek 模型选择；优先支持 iPhone Safari（前台），其次 iPad/Mac。
2. 只复用官方 v0.9.8 音频/Opus/WS，音频服务继续用现有 A03；无第二套 AI/ASR/TTS、无 Manager/MySQL/Redis/新固件。
3. 语音问题 A07（句中卡顿、断音后又继续）必须归因后再修；不得把切换 WebUI 或 `tts_audio_send_delay: 60` 宣称为已修复。
4. TG、腾讯官方微信 ClawBot 是扩展阶段；WhatsApp 及原生 iOS App、锁屏常驻、GPT/Gemini/豆包实时语音计费 API 均不在首期。
5. P1/P2 的页面应与已有 A04/Cloudflare 的 **ESP32 非交互设备通道隔离**。浏览器身份与 4B 身份绝不可混用。
6. 浏览器纯文字请求优先复用现有 LLM Adapter，但**不得**默认使用会调用 TTS 的 `listen.detect` 作为无声的文字聊天协议。

## P0–P5 全阶段路线图（100 权重点；13 PR；2026-11-26 P1 修订）

| 阶段 | 阶段权重 | PR | 单 PR 权重 | 依赖 | 集中交付及验收 |
|---|---:|---|---:|---|---|
| P0 审计与选型 | 10 | P0-1 基线审计 | 5 | 已有 A03～A09 | 仓库/PR/CI/稳定版本清单；只读路径检查；保留旧问题 |
| P0 审计与选型 |  | P0-2 官方模块及许可证审计 | 5 | P0-1 | 版本锁定、模块复用/排除清单、OTA/WSS/音频/文字路径风险与回退设计 |
| P1 WebUI 文字 | 20 | P1-1 HTTPS/WSS 安全入口 | 8 | P0 | PR #33 已合并，CI 通过；独立身份、OTA/WSS 允许/拒绝、浏览器会话隔离；生产验收待定 |
| P1 WebUI 文字 |  | P1-2 文字聊天+模型选择 | 8 | P1-1 | PR #34 已合并，CI 通过；文本专用路径，GPT/DeepSeek，20 组模拟问答；真实 Safari 待定 |
| P1 WebUI 文字 |  | P1-3 生产只读预检/隔离试点门槛 | 4 | P1-1/P1-2 | 完成 VPS 内存/Swap/A03/A04/CF/网络/回退前置检查、独立 CI；实际部署与 Safari 验收另需实机证据 |
| P2 WebUI 音频 | 25 | P2-1 Opus 音频通信 | 14 | P1 | AudioWorklet、采集、编/解码、流式播放、Chrome/Safari 兼容性测试 |
| P2 WebUI 音频 |  | P2-2 连续语音和打断 | 11 | P2-1 | 尾音、重放、缓冲与打断自动化测试 + iPhone 实际语音 |
| P3 A07 稳定性 | 20 | P3-1 断音定位 | 10 | P2 | 先记录发送节奏/接收队列/播放时间戳，区分网络、TTS、设备因素 |
| P3 A07 稳定性 |  | P3-2 最小修复+4B 回归 | 10 | P3-1 | 证据支持的最小变更、原 4B 固件不改、真实硬件连续语音验收 |
| P4 安全及发布 | 15 | P4-1 会话安全 | 7 | P1～P3 | 账号隔离、访问控制、凭证脱敏、历史存储策略、安全负向测试 |
| P4 安全及发布 |  | P4-2 成本及正式发布 | 8 | P4-1 | Token/预算统计；iPhone 及 4B 验收；资源/回滚；稳定版 |
| P5 社交渠道 | 10 | P5-1 TG Bot | 5 | P4 | 官方 Bot API，文字/语音留言、授权名单及重连 |
| P5 社交渠道 |  | P5-2 微信 ClawBot | 5 | P4 | 优先腾讯官方渠道；OpenClaw 依赖及主机容量门槛不达标即阻塞 |

**计分规则：** 仅当对应 PR 合并且该 PR 全部适用验收门槛通过才计全额权重；源码核实/CI/模拟功能/真实设备四类证据必须分开记载。仅 PR 合并不等于实机语音通过。P0 的 10% 为源码/CI/设计验收；真实 VPS 的资源与 4B 的实测在 P1/P2/P3/P4 按各自门槛另计。不得套用旧 A09 的“70%”。

**每阶段 PR 数量：** P0=2、P1=3、P2=2、P3=2、P4=2、P5=2，总计 **13 个 PR**，单阶段 <=5。

**2026-11-26 P2-1 部署试点整合计划（本轮开发前登记）：** 在不增加任何 PR/权重的前提下，将 P1 的实际部署准备纳入现有 Draft PR #39 的可逆依赖工作：新增独立 `tools/ai/webui_pilot.py`（Python 标准库独立进程，避免再次给出可能退出 SSH 登录 shell 的命令） 支持 `plan`（只读、展示阻断）、`stage`（仅经用户明确在 VPS 授权后新建 WebUI 边车与私有目录，不改变现有 A03/A04/Cloudflare）、`verify`（验证新边车、旧 A03/A04 健康及资源/Swap）、`rollback`（只停新 WebUI）；保留 PID/镜像指纹与真实内存基线，绝不在交互式 SSH 命令中执行 `exit`。默认模型目录 `[]`，不进行付费请求，不自动新增 Cloudflare 域名；真正的 GPT/DeepSeek 私有配置、Owner 登录和 Safari 仍必须另验。必须先用 Docker Runner 在模拟现有 A03/A04 环境中完整演练 `plan→stage→verify→rollback` 以及低内存/冲突/失败阻断与会话存续。此工作属于 P2-1 PR #39 的 P1 生产前置实现补强；P1 五 PR 上限与正式阶段权重/项目 100 不变。未验证的运行脚本不交用户执行，且源码 CI PASS 不等于 VPS 实测。

**2026-11-26 P2-1 前置缺陷处理和成熟 Opus 选型（开发前计划补充）：** P1 #33～#37 已满 5 PR、源码 CI 合并，真实 VPS 只读预检 PASS，但 WebUI 生产模板在 `cap_drop: [ALL]` 下遗漏官方 Caddy 的 `NET_BIND_SERVICE` 文件 capability（详见 #38），且 Auth 被多余连接到前端网络。为不违反 P1 5 PR 上限，**在计划中的 P2-1（原权重 14，不新增阶段或 PR）内部集中修复**：参考已有 A04 正式权限配置，增加 `cap_add: [NET_BIND_SERVICE]`，仅 Auth 连接后端网络；使用 Docker Runner 与生产等效权限运行真实 Caddy+Auth 并验证合法 WS 101/无身份 403；旧 A04 完全不改。该工作仅解除 P2 的网关源码阻断，不因此额外增加 14% 或宣布 P1 已部署。P2-1 原交付仍为 Opus 16kHz/mono/960 samples、AudioWorklet、WS 原始帧传输和 Safari/Chrome 兼容测试；优先采用已发布 `libopus-wasm@0.4.1`（MIT，libopus BSD，官方 SHA-256 `f645938adcd3381dcae9827ef71248218eaeb8308b6339bd568d1c43a64c5ef8`）；禁止再次复制不明二进制。**允许提前做隔离源码/CI 开发，但 P2-1 合并和全额验收必须等待 P1 的真实部署/浏览器准入通过；所有生产变更仍严格阻断。** P1 权重和项目 100 分不变。\n\n**2026-11-26 P1 隔离网关试点路线修订（先规划后开发）：** VPS 已返回 `WEBUI_P1_PREFLIGHT_PASS`，只证明资源、A03/A04 网络和默认拒绝准入检查通过，不代表可部署。原 P1-3 生产试点建议向旧 A04 Caddy 追加 `/webui` 路由并注入 Gateway Secret，这将要求重新创建/重启正在服务微雪 4B 的网关，有连接中断风险。因此改为 **P1-3-R2（0 权重、第五个且最后一个 P1 PR）**：新增完全独立的 WebUI Caddy+Auth 双边车，通过已有外部 Docker 网络接入 A03；原 A04 Caddyfile、容器、设备域名、Cloudflare Tunnel 容器不改。Cloudflare 仅新增独立主机名到新网关服务的映射，先做隔离 Caddy+Compose CI、回退及不扰动旧设备的试点验收。此次只是改变 P1-3 的安全实现，原 13 个功能 PR 的权重依然 100，另有 P1-3-R1/R2 两个零权重维护集成 PR，实际总 15 PR、P1 实际最多 5 PR；此后 **P1 不再新增 PR**，所有失败在 R2 原 PR 修复。未经真实 VPS/Cloudflare/iPhone 验证，P1 仍 0/20。

**2026-11-26 P1-3 预检修复登记（开发前记录）：** PR #35 已合并后，真实 VPS 报告 `A09_MANAGER_RESOURCE_ISOLATION_UNKNOWN`。源码核查证实采集函数用 `all(not running)` 却在判断时要求 `manager_active is False`，导致**无 Manager 正在运行反而 BLOCKED**。因此单独创建 **P1-3-R1：0 权重缺陷纠正 PR**（修复检测逻辑和反例回归测试）。原 13 个**功能交付 PR**不变，额外 1 个维护 PR，合计预期实际 PR 数 **14 个**；P1 实际物理 PR 数 **4 个**，仍小于每阶段 5 PR 限制。P1 权重 8+8+4=20、项目总权重 100 均不变。只有重新运行真实 VPS 只读预检后才能判断是否通过，不根据旧误判结果直接放行。CI 失败原 PR 修复；不得为小缺陷擅自新增 PR。已有 #27/#28/#30 保持独立 Draft，不得为了达成进度无条件合并。

**2026-11-26 P1 计划变更记录（开发前先更新）：** PR #33/#34 已完成源码合并与专用 CI，但因无生产 VPS 终端接入，无法验证当前 4B+A03+A04 Docker 网络、Cloudflare 和可回退部署；现有 P1 恰好两 PR 都只有源码验收，没有明确负责生产预检的 PR。增加 **P1-3（4 权重点）** 将只读预检、网络拓扑、路由互不干扰和一键回退门槛集中交付。原 P1-1/P1-2 从各 10 点调整为各 8 点，P1 总权重仍是 20 点，P0～P5 阶段权重和整体 100 点均不变。这不是宣称部署已通过：目前 P1 实际验收仍 **0/20**。

## 验收阈值与停机条件

- iPhone 前台连续语音：每次集中验收 >=10 分钟；4B 真实回归 >=10 分钟；无意外尾音截断与句中断音。单轮首声目标中位数 <=4s、P95 <=8s **仅为目标，尚未验证**。
- 自动化重放：至少 30 轮，断音/重播/超时等负向工况覆盖；比真实用户体验低一级证据。
- 新增语音 API 用量费：$0；仍记录文本 LLM Token 和费用。所有平台适配默认只允许所有者。
- 部署前真实 VPS 只读预检，MemAvailable >=1.05GiB、试点 Swap 增量 <=64MiB；若不能满足，停止试点，不改资源阈值、不加 Swap。
- WebUI/OAuth/OTA/WSS 绝不能要求真实 4B 通过 Cloudflare Access 浏览器验证码；原有 A04 配置、4B NVS、Cloudflare 隧道和 HomeSphere/MiniProbe 不得被 P0 修改。
- 稳定生产服务先备份镜像摘要/私有配置（仍留 VPS 本机），后逐阶段在独立服务中试点；失败一键停新服务并验证原 A03/A04 OTA+WS。
- P5 微信必须先核实腾讯官方插件依赖/适用账号/当前资源，不因功能规划强行部署 OpenClaw；WhatsApp 只作为未来独立政策研究。

## 阶段状态（2026-11-26 审计起点）

| 阶段 | 完成 | 说明 |
|---|---:|---|
| P0 | 0/10 | 审计 PR 待验证及合并，不可提前得分 |
| P1 | 0/20 | 未提供 WebUI 文字聊天 |
| P2 | 0/25 | 未有 iPhone WebUI 音频闭环 |
| P3 | 0/20 | A07 仍存在未证实根因的句中断音 |
| P4 | 0/15 | WebUI 发布/成本验证未启动 |
| P5 | 0/10 | TG、微信均未接入 |
| **总计** | **0/100** | 旧 A03～A06 是复用资产，不折算为新增 WebUI 阶段完成 |

本路线图的百分比应在每个 PR 合并并完成适用验收后更新；实际项目完成情况以 PR/CI/实机记录为准。


## 2026-11-28 重点范围修订：WebUI 语音聊天优先，4B 项目暂停

**用户明确要求：先不处理微雪 4B 硬件/固件/配对/A04 身份网关，仅集中把浏览器语音聊天做好。** 此次先更新路线图，再在现有 P2-1 PR #39 内做修改，不另开 PR；**禁止把独立 A07 4B P3 PR #27 的安全预检失败误认为 WebUI 语音故障**。保留当前可用 UI v3、Cloudflare Access、文字 SSE 和通用供应商可切换的 API 配置。

### 完整阶段继承与在用工作线（100 权重点不变）

| 阶段 | 权重 | 已规划 PR 数 | 本次范围与依赖 | 阶段验收 |
|---|---:|---:|---|---|
| P0 基线/官方方案 | 10 | 2 | 重用已完成的审查；不更换协议栈 | 官方源码、现有仓库和稳定版本证实 |
| P1 WebUI 安全/文字 | 20 | 5（已达上限） | 复用现有独立 WebUI Gateway/Auth、登录、通用 API 文字 SSE | 真实 HTTPS/权限/文字访问不回退 |
| P2 WebUI 双向语音 | 25 | 2（PR #39 及原规划 P2-2） | 当前唯一主动开发；Opus 16k/60ms、Safari AudioWorklet、用户点击启用、WS Hello/Listen、尾音播放、防回声、打断；依赖 P1 | 独立源代码、CI、无设备依赖的合成音频回放；iPhone Safari 前台真人听读验证另计 |
| P3 浏览器语音稳定性 | 20 | 2（原 P3-1/2 改限定网页语音） | 只分析 WebUI 从 mic→WS→A03→WS→DAC 的延迟/中断；不改 A04 硬件网关；依赖 P2 | 30 轮自动化 + iPhone >=10 分钟无可感知句中断音/尾音丢失，记录独立服务端证据 |
| P4 安全/发布 | 15 | 2 | 只涉及 WebUI 的会话保护、凭据保密、可逆发布、预算约束；依赖 P2/P3 | 不重启 A03/A04/WebUI 稳定服务，真实 VPS + Safari 回归 |
| P5 社交扩展 | 10 | 2 | 后置，不在本轮新增聊天渠道；依赖 P4 | 按原规划逐项验收，不阻碍语音优先任务 |

**跨项目排除：** 微雪 4B 真机、固件、OTA、A04 Caddy 私有路径/设备认证、原 R1/R2 代理工程、专属设备 P3/A07 的发布均冻结，不因 WebUI 语音 PR 升级、重启或修复。原 #27 可保留 Draft 和已有证据，但不属于此轮验收。

**代码整合与发布：** 仅在已有 PR #39（P2-1，权重 14）集中修复浏览器音频生命周期，剩余 P2-2（权重 11）按原计划做连续播放和打断；CI 失败留在原 PR 修。生产稳定 WebUI v3 位于独立 release 分支，不从较旧 main 全量覆盖；只允许明确源 blob 校验、备份、独立回退的 WebUI 专属变更，绝不触碰后端通用 API 供应商配置和历史设备网关。

**进度原则：** P2 源码/CI 测试与浏览器可用性分开；任何本轮修改尚未获得真实 Safari 语音验收，不以自动化 PASS 宣称语音问题已经完全解决。P0/P1/P4/P5 既有状态沿用之前的验收证据，不因更新路线图虚增百分比。


## Unified English module names — 2026-11-28

Use **functional English names**, NOT A03/A04/A05/A06/A07/A09, in all new user-facing output and WebUI development reports. Those legacy labels are *historical milestones*, not descriptive runtime services. Existing Docker names, CLI paths, environment variables and legacy references remain untouched to protect production compatibility.

| Canonical English name | Meaning | Historical milestone | Project |
|---|---|---|---|
| `VoiceCore` | XiaoZhi speech server, WebSocket/Opus transport | A03 | shared existing backend; modifications require separate approval |
| `DeviceGateway` | 4B OTA + WSS private-device identity gateway | A04 | separate 4B project; frozen here |
| `ModelAPI` | configurable OpenAI-compatible AI model bridge | A05 | shared model connectivity, user-configured provider |
| `SpeechEngine` | Vosk ASR + Edge TTS services | A06 | existing backend, source of browser speech |
| `DeviceVoice` | real 4B mic/speaker and standby tests | A07 | separate 4B project; frozen here |
| `DeviceManager` | XiaoZhi hardware activation manager | A09 | separate 4B project; frozen here |
| `WebUI` | browser visual interface, UI v3 | — | current project |
| `WebGateway` | dedicated WebUI Caddy HTTPS/WSS reverse proxy | — | current project |
| `WebAuth` | browser owner authentication and isolated WebSocket admission | — | current project |
| `WebVoice` | browser mic, raw Opus, speech playback & continuous dialogue | P2/P3 | **current development priority** |
| `WebChat` | web text SSE and configurable model selection | P1 | existing validated functionality |

**Architecture (browser only):** `WebUI → WebGateway → WebAuth → VoiceCore → SpeechEngine ↔ ModelAPI`. Browser requests use a distinct WebGateway and authenticated session. DeviceGateway is not on the browser ingress path. Do not confuse the shared VoiceCore container name with the 4B hardware project's scope.

**Original P0–P5 roadmap unchanged** (10%,20%,25%,20%,15%,10%; PR numbers and dependencies inherited). Current planned P2 deliverables are existing Draft PR #39 = 14 weight points for mic/Opus/browser playback and P2-2 = 11 for resilience/interruption. Acceptance remains distinct for source, CI, real VPS and real Safari; no credit for unverified live speech. Any code report should use the functional names above, with the legacy identifier only in one-time migration tables.


## 2026-11-28 P0 reused-source correction: stop custom WebVoice feature growth

**User correction (GDGS source-first):** Previous P2-1/#39 and P2-2/#50 introduced substantial self-maintained browser microphone, buffering, playback, interruption and publisher code **before comparing complete maintained upstream clients**. This violates the intended reuse-first development policy; earlier mock/CI PASS is not evidence a custom solution is preferable to mature upstream. **Suspend custom WebVoice feature additions and production publisher deployment until this upstream substitution review is resolved.** Do not run previously issued one-click publication scripts until source choice and real integration security/resource gates are settled.

**Sources verified at code level, not just project popularity:**
1. **xinnan-tech/xiaozhi-esp32-server tag v0.9.8, `main/digital-human/js/core/`**, official under MIT. It already implements an end-to-end browser WebSocket client, raw 16 kHz/60 ms Opus encoder/decoder (`audio/opus-codec.js`), AudioWorklet microphone (`audio/recorder.js`), buffered scheduled playback (`audio/player.js`, `audio/stream-context.js`), `abort` and `listen` message flow (`network/websocket.js`). **Strongest protocol compatibility with the deployed VoiceCore v0.9.8.** Caution: this is an interactive *test/digital-human* module, not a drop-in private WebUI product; its unmodified code bundles camera/Live2D/wakeword runtime and browser-incompatible `AudioContext({sampleRate:16000})` assumptions may need precise iPhone Safari validation. Importing only the media core, preserving license and an isolated WebAuth bridge is the first prototype, not an unconditional transplant.
2. **open-webui/open-webui**, public current voice-mode docs. Complete self-hosted chat platform with Standard voice mode (server STT + TTS), configurable OpenAI-compatible text APIs, voice interruption, users and histories. **Best whole-product alternative** if resources and UI replacement acceptable. Its full audio backend requires appropriate STT/TTS interfaces (existing Vosk/EdgeTTS inside XiaoZhi WSS do not automatically implement OpenAI audio HTTP endpoints). Realtime mode is a separate metered/compatible voice model and should not be enabled by default. Latest license includes branding restrictions; respect official license. Pilot it only in an isolated, reversible sidecar following real VPS MemAvailable/Swap baseline, never directly replace live UI v3.
3. **TOM88812/xiaozhi-web-client**, MIT browser Opus + WS + proxy and audio playback, but its own README says **paused maintenance** and recommends Chrome/Firefox, so it is reference-only, not primary production base.
4. **TOM88812/xiaozhi-android-client**, Apache-2.0 GitHub repo declares Flutter web/iOS/Android support, however README divides opensource, commercial V3 clients and their associated server feature set. Do not assume all promoted interruption, account management and audio capabilities are included in the freely reusable GitHub subtree; inspect actual code/license and do an isolated browser build before ranking it as substitutable.

**New mandatory P0 gate before any further P2 development:** comparative matrix using exact upstream commit/tag, license, current development activity, directly reusable source surface, iPhone Safari microphone/Opus/interrupt support, WebAuth/Cloudflare fit, resource footprint, config migration and rollback. Prefer *unmodified official Open WebUI as an isolated whole-app trial* if it satisfies STT/TTS and memory; otherwise *upstream Digital Human media core with minimal isolated adapter* to preserve existing WebUI v3 and VoiceCore. Use the existing #39/#50 PRs, no gratuitous PR proliferation. Preserve exact stable production files and credentials and never restart device gateway/4B. Do not award completion for source-only tests. The already-written custom audio code remains available for comparison/rollback but is **not the default path**.
