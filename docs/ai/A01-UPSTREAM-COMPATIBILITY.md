# S3-Voice-AI — A01 / P0 上游成熟度与 4B v2.6.0 兼容性审计

**核查日期：** 2026-11-22  
**性质：** 只读源码与公开资料审计，绝非 API/设备实测结论  
**阶段：** 新 AI 服务端路线 P0；A01=项目总权重 5%，A02=5%，P1=30%，P2=35%，P3=25%  
**边界：** 不修改设备固件、VPS、OTA/NVS、R1/R2 代理固件。密钥不入 Git。

## 1. 决策（Go / Conditional Go）

**Conditional Go：选用成熟的 `78/xiaozhi-esp32` 固件 + `xinnan-tech/xiaozhi-esp32-server` 单服务 Docker 架构进行 P0-A02。**

本期**不用开发新的 ESP32 固件**。4B 已由用户实测升级至小智 v2.6.0，Wi-Fi、原有语音正常，配网高级选项已出现「自定义 OTA 地址」输入框。**尚未实测自建 OTA→WebSocket→双向语音**，不得写成通过。

已有 R1/R2 仓库仅临时存储这一份 AI 独立工作线的审计；A02 决定独立 `s3-voice-ai-server` 仓库与 VPS 布局后迁移，避免混合部署/固件代码。R1 #15/#20 的 Draft 和 R2 分支不受影响。**不得将 xiaozhi-server 上游主分支直接视为稳定可用版本**。

## 2. 上游选择、成熟度与许可

| 用途 | 官方/主流来源 | 核查固定版本 | 公开元数据（审计当日） | 许可 | 复用结论 |
|---|---|---|---|---|---|
| 4B 已安装固件 | [78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) | [v2.6.0](https://github.com/78/xiaozhi-esp32/releases/tag/v2.6.0) / `4de00aed740595a8713b01f8332b9b2cf30685bc` | 33,589 stars、8,035 forks；创建于 2024-08-31 | MIT | 保留现有固件；不重新烧写 |
| 自建服务器 | [xinnan-tech/xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server) | [v0.9.8](https://github.com/xinnan-tech/xiaozhi-esp32-server/releases/tag/v0.9.8) / `8f2dda09cf18f1c1ece0f906eee4cc2fabb7fb58` | 11,365 stars、3,860 forks；创建于 2025-02-02；v0.9.8 于 2026-10-23 发布 | MIT | 单模块 Docker + `.config.yaml`；先锁定 Release/镜像摘要再部署 |
| 原配网组件 | [78/esp-wifi-connect](https://github.com/78/esp-wifi-connect) | 跟随 4B 固件锁定 | 配网页高级 OTA 配置由 `show_ota_config` 控制 | 按上游版本许可证 | 不导入、不改写 Wi-Fi/NVS |

成熟度是选择上游的**必要但不充分**条件。这里有官方/广泛部署的固件与 11k+ stars 的服务端，而不是低星实验路由器。最终 4B + v0.9.8 组合的硬件兼容性尚未由本项目实测证明。

## 3. 固件→服务端接口源码对照

| 合约 | v2.6.0 固件证据 | v0.9.8 服务端证据 | 结论 |
|---|---|---|---|
| OTA 地址保存和优先级 | [main/ota.cc](https://github.com/78/xiaozhi-esp32/blob/v2.6.0/main/ota.cc)：NVS `wifi.ota_url` 为合法 URL 时优先于内置 `CONFIG_OTA_URL` | [docs/firmware-setting.md](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/docs/firmware-setting.md)：高级选项填自建 OTA | **源码吻合，真机切换未验证** |
| OTA 请求 | `POST` 带 `Device-Id`、`Client-Id`、JSON `board` / `application.version` / `protocol.features` | [core/api/ota_handler.py](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/core/api/ota_handler.py)：`handle_post` 接收前两项，按 `board.type` 和 `application.version` 匹配 | **字段级吻合**；不得只用浏览器 GET 冒充设备 POST 验收 |
| OTA 响应选择 | 固件解析 `websocket.url/token`、`mqtt`、`firmware.version/url`、`server_time` | 服务端 `mqtt_gateway: null` 时回复 `websocket`、`firmware`、`server_time` | **可选纯 WebSocket**；不得误配 MQTT（固件优先 MQTT） |
| WebSocket 握手 | [websocket_protocol.cc](https://github.com/78/xiaozhi-esp32/blob/v2.6.0/main/protocols/websocket_protocol.cc)：发 `Protocol-Version`、`Device-Id`、`Client-Id`、可选 `Authorization`；hello 带 `transport=websocket` | [websocket_server.py](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/core/websocket_server.py)、[helloHandle.py](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/core/handle/helloHandle.py) | **握手结构有源码依据** |
| Opus 声流 | [websocket_protocol.h](https://github.com/78/xiaozhi-esp32/blob/v2.6.0/main/protocols/websocket_protocol.h)：默认 version=1；v1 二进制为原始 Opus，v2/v3 另有封装 | [connection.py](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/core/connection.py)：普通 WS 二进制按 Opus 解码，MQTT 网关则另拆 16 字节头 | **默认 v1 在源码层面匹配**，不应擅自下发 v2/v3；4B 实际语音待测 |
| 不升级固件 | 固件仅在新版本/force 且下载 URL 有效时请求并写入固件 | 服务端匹配 `data/bin` 固件，候选存在时可能返回 URL | **P1 必须确保 `data/bin` 无匹配候选、`firmware.url==""`，杜绝无授权 OTA** |

[官方 OTA 契约](https://github.com/78/xiaozhi-esp32/blob/v2.6.0/docs/ota.md) 与 [官方 WebSocket 契约](https://github.com/78/xiaozhi-esp32/blob/v2.6.0/docs/websocket.md) 用于 P1 合约回归。注意「OTA 配置入口」不等于发固件升级，**本项目只需要服务地址发现**。

## 4. 模型适配器真实能力及 2026-11 的失效风险

| 模型 | 上游已有代码 | 2026-11 审计发现 | A05 准入 |
|---|---|---|---|
| OpenAI GPT API | [core/providers/llm/openai/openai.py](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/core/providers/llm/openai/openai.py) 使用官方 `openai.OpenAI` 与流式 `chat.completions.create`，从 `base_url` 或 `url` 读取地址 | 模型须**支持 Chat Completions**，不能将 Responses-only 模型不经验证直接填入；当前上游无可直接照抄的专用 GPT 配置 | 官方列出当前可用 ID、测试实际流式中文响应、延时/成本，再定版 |
| DeepSeek API | [config.yaml](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/config.yaml) 已有 `DeepSeekLLM: type: openai`，`https://api.deepseek.com` 和 `deepseek-v4-flash` | [DeepSeek 官方更新日志](https://api-docs.deepseek.com/updates/)确认当前命名/兼容性可能变化；别使用旧 `deepseek-chat` 教程 | 真实 ChatCompletions 测试并锁定可用模型 |
| Gemini API | [core/providers/llm/gemini/gemini.py](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/core/providers/llm/gemini/gemini.py) 已有 `gemini` 类型，使用传统 `google.generativeai` SDK | 上游默认 `gemini-2.0-flash` **已停用**（[Google 官方讨论确认](https://discuss.ai.google.dev/t/project-not-active-404-error-with-aq-format-api-key/179664/2)）；较新型号与旧 SDK 的兼容性**未证实** | 先用当前 Gemini API 可用模型与原适配器测试；若失败，优先复用官方兼容 API/SDK，最小适配而非重写 |

**关键修正：上游示例 `.config.yaml` 不能原样拿来生产。** 模型 ID、SDK、地域/出口、密钥与服务端实际配额都必须逐项验证。ASR/TTS 是独立模块，换 GPT 不会自动解决语音音色或识别准确率。

## 5. 公开 Issues/PR/Release 风险记录

1. [78 固件 Issue #2134](https://github.com/78/xiaozhi-esp32/issues/2134)：v2.4.0 配网页 OTA 字段隐藏；维护者承诺恢复，Issue 已关闭；**用户 v2.6.0 已现场看见该选项**，无需重复拍图/刷机。
2. [server v0.9.8 Release](https://github.com/xinnan-tech/xiaozhi-esp32-server/releases/tag/v0.9.8) 修复 2026 年 EdgeTTS 403 及服务资源释放问题，但 2026-11 仍有后续修复，因此不能混用 v0.9.8 与 main 文档的动态假设。
3. [server PR #3557](https://github.com/xinnan-tech/xiaozhi-esp32-server/pull/3557) 后续修复旧聊天/TTS 任务影响新轮次；A02 需核对是否纳入候选镜像版本，未纳入则用回归验证风险。
4. [server Issue #3566](https://github.com/xinnan-tech/xiaozhi-esp32-server/issues/3566) 记录工具超时后可能继续执行；v1 不启用危险动作工具，避免将工具调用和基础聊天混为一谈。
5. [server Issue #3567](https://github.com/xinnan-tech/xiaozhi-esp32-server/issues/3567) 多轮语义相近场景可能重复回复；基础功能仍待验证，属 P3 用户体验验收项。
6. 两个候选仓库根许可证均为 MIT。若后续引入附加音频模型、SDK 或镜像依赖，应另核实其许可与商业使用边界。

## 6. 安全/回退：A02/P1 必须解决的高影响门槛

**阻塞公网发布：** v0.9.8 默认 `server.auth.enabled: false`。源代码还显示 `allowed_devices` 在 WebSocket 验证时主要是**免 token 例外**，不是严格禁止未知设备的访问控制；OTA 端可按请求标识签发 token。**仅把 auth 改成 true、填一条 MAC，不等于安全的用户设备白名单。** 必须设计并自动测试与现有设备相容的入口访问控制、限流和 API 费用限额；未解决前不可公网公开计费服务。

- 不把 Cloudflare Access 的浏览器邮箱验证码直接放在 4B OTA/WSS 前：设备不能执行网页交互验证。若使用 Tunnel，必须另行验证无交互的设备端鉴权链路。
- 对自建服务仅下发 `websocket`（不下发 `mqtt`）；记录/校验 `POST /xiaozhi/ota/` 响应，不依赖 GET 健康页。
- OTA `firmware.url` 默认空，固件目录不得放候选升级文件；绝不擦 NVS、刷 Flash、重置分区或改变设备固件。
- 记录当前官方 OTA 地址或清空自定义 OTA 回退机制；先备份 VPS 配置和 Docker 镜像摘要，密钥不能出现在 Git/CI 日志/公开截屏。
- DeepSeek、OpenAI、Gemini 需设 API 支出上限或厂商预算告警；关闭不必要的工具调用、视觉和自动固件更新路径。
- 由于原有 R1/R2 透明代理工作未完成硬件验收，**本次 AI 接入不从那条固件线产生刷写包**。

## 7. A01 已达到的证据分级

| 检查项 | 状态 |
|---|---|
| 公开上游的维护历史、Stars/Forks、Release、License | **SOURCE CONFIRMED** |
| v2.6.0 自定义 OTA、POST 和 WebSocket v1 的源代码契约 | **SOURCE CONFIRMED** |
| server v0.9.8 的 OTA、WebSocket、原始 Opus、三模型适配器源码 | **SOURCE CONFIRMED** |
| 官方 v2.6.0 4B 机身升级、Wi-Fi/语音、OTA 输入框 | **USER DEVICE OBSERVED**（来自已完成的前序实测记录；没有自建服务连接记录） |
| 固件 ↔ 自建 server v0.9.8 自动化接口测试 | **NOT RUN**，P1 |
| 三家付费 API 真实凭证调用、模型有效性 | **NOT RUN**，P2 |
| 4B 经过自建服务端完成语音问答、回退 | **NOT RUN**，P3 |
| 现有 Debian13 VPS 资源、端口、Docker 服务冲突 | **NOT CHECKED**，A02 |

**A01 文档结论：源码审计通过；准许开展 A02。** A01 对应 GitHub PR 必须在 CI 全绿并合并后才按 GDGS 记 5%；不能把源码兼容性推断为端到端功能通过。

## 8. A02 的明确输入（不得新增 PR）

1. 只读调查 Debian13 VPS 现有 CPU/RAM、磁盘、Docker/Compose、HomeSphere/MiniProbe、入口路径与可用端口。
2. 决定独立服务端仓库 `s3-voice-ai-server`、镜像 SHA digest、上游 v0.9.8 与 main 后续修复取舍；不使用浮动 latest 作为生产基线。
3. 确定公网 OTA/WSS 认证与流控策略（包括费用限制）、TLS/Cloudflare 转发、只允许可信设备、关闭固件自动下发；写出可自动检查的准入门槛。
4. 形成 P1 备份/部署/回滚操作与端口映射，以及 P1 的模拟 OTA POST、WS v1 Hello/Opus 自动化测试清单。
5. A02 完成并合并前不改动设备和 VPS。

### 独立 AI 工作线 GDGS 路线图（不改变原有 R1/R2）

| 阶段 | PR ID | 项目权重 | 依赖 | 阶段验收 |
|---|---|---:|---|---|
| P0 | A01(5%), A02(5%) | 10% | 无 | 兼容审计、VPS 只读基线、安全+回退设计 |
| P1 | A03(18%), A04(12%) | 30% | P0 | Compose 隔离/锁定、OTA+WS/认证自动测试 |
| P2 | A05(22%), A06(13%) | 35% | P1 | 三模型真实 API 与 ASR→LLM→TTS 自动测试 |
| P3 | A07(15%), A08(10%) | 25% | P2 | 4B 实机语音+恢复、发布验收 |

总计 **8 PR / 100%**；非关键且发生率 <20% 的扩展鲁棒性暂不开发，高影响安全与回滚门槛不可豁免。
