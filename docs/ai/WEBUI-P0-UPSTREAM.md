# S3-Voice WebUI P0-2 — 官方源码、许可证与低成本技术路线审计

**日期：** 2026-11-26；**证据等级：** 官方固定版本源码及规范核查（尚未编写 WebUI、尚未运行真实 Safari 或部署 VPS）。
**锁定上游：** [xinnan-tech/xiaozhi-esp32-server v0.9.8](https://github.com/xinnan-tech/xiaozhi-esp32-server/releases/tag/v0.9.8)，与已合并的 A03 镜像基线一致。不得把此文档的结论直接套到未来 `main` 或未经锁定的镜像。
**父阶段：** [P0-1 基线](WEBUI-P0-BASELINE.md) 与 [完整路线图](WEBUI-ROADMAP.md)。P0-1 为 5/100，P0-2 只有在本 PR 通过 CI 并合并后才增加 5/100。

## 1. 成熟代码复用矩阵（源码证实 ≠ 已在 Safari 实测）

| 功能 | 官方 v0.9.8 文件 | 复用原则 | 已证实限制 |
|---|---|---|---|
| OTA 请求 | [digital-human/js/core/network/ota-connector.js](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/digital-human/js/core/network/ota-connector.js) | 复用 OTA POST JSON 与 Device-Id/Client-Id 字段；WebUI 统一走同源入口 | 现有浏览器实现随后把 `authorization`、`device-id`、`client-id` 放进 WS URL 查询参数 |
| WS Hello / 语音信令 | [digital-human/js/core/network/websocket.js](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/digital-human/js/core/network/websocket.js) | 复用 Hello、listen、TTS/STT 状态解析及二进制帧处理 | `tts.stop` 直接调用 `audioPlayer.clearAllAudio()`，可能清掉未播放尾音（有代码路径证据，未证实是 4B 断音根因） |
| 麦克风采集与 Opus | [digital-human/js/core/audio/recorder.js](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/digital-human/js/core/audio/recorder.js)、[opus-codec.js](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/digital-human/js/core/audio/opus-codec.js) | 优先复用 AudioWorklet、PCM 分帧、Opus 编码 | 需验证 Safari 上的初始化/释放和音频格式；`ScriptProcessorNode` 后备方案已过时 |
| 流式播放 | [digital-human/js/core/audio/player.js](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/digital-human/js/core/audio/player.js)、[stream-context.js](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/digital-human/js/core/audio/stream-context.js) | 复用 Opus 解码、缓存队列与定时播放 | 播放器存在 400ms 缓冲超时、已排队帧、停止事件之间的状态竞争风险；P2 做独立回放测试 |
| 测试 UI | [digital-human/index.html](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/digital-human/index.html) | 借鉴文本框、连接状态、音频按钮；只实现轻量 HTML/CSS UI | 页面默认 OTA 为本机 `127.0.0.1:8002`，包含 Live2D、摄像头、MCP 工具与唤醒词等额外依赖，不直接整体移植 |
| 唤醒词 | [wakeword-bridge.js](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/digital-human/js/core/network/wakeword-bridge.js) | 首期全部排除 | 默认 WS 是浏览器设备本地 `ws://127.0.0.1:8006/wakeword-ws`；远端 iPhone 不可能假定存在该服务 |
| A03 原生 OTA | [xiaozhi-server/core/api/ota_handler.py](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/core/api/ota_handler.py) | 复用现有签名 Token 和 OTA 发现路径；不重新实现服务端 HMAC | 仅真实 POST + 设备字段可证明设备 OTA；浏览器 GET 健康检查不可替代 |
| A03 原生 WS | [xiaozhi-server/core/websocket_server.py](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/core/websocket_server.py) | 维持上游认证，不降低检查或复制密钥到前端 | 上游允许在无 Device-Id header 时从 URL 提取身份和 authorization，不能由此推断安全准入已经达标 |
| 纯文字问答 | [listenMessageHandler.py](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/core/handle/textHandler/listenMessageHandler.py) | 可复用已接入的 LLM Adapter / 流式生成机制 | 原生 `listen.detect` 包含 `startToChat` 和 TTS 语音答复路径，不能当作“无 TTS 文字 API”直接使用 |

官方将 digital-human 定位为 **独立的音频交互测试模块**，不是已对 iPhone Safari、主屏幕安装、生产级认证完成验收的成品。参见 [digital-human/README.md](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/digital-human/README.md)。

## 2. 许可证与二进制复用：防止“MIT 仓库=所有素材可复制”误判

- 仓库顶层 [LICENSE](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/LICENSE) 为 MIT；复制 MIT 覆盖的源文件需保留版权/许可证通知，并记录固定来源、版本和变更。
- 但 [live2dcubismcore.min.js](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/digital-human/js/live2d/live2dcubismcore.min.js) **明确声明 Live2D Inc. 版权所有且遵循独立专有授权**；首期不移植、不打包 Live2D 核心、模型、动画与关联资源。
- [digital-human/js/utils/libopus.js](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/digital-human/js/utils/libopus.js) 是生成后的 Emscripten 代码；在当前核查的文件头部未获得能完整证明整个预编译产物来源/再分发条件的 NOTICE。P2 先确认实际底层 libopus、工具链、二进制许可证，必要时复用有完整许可证的成熟发行版；**P0 不复制大型编译文件**。
- 不安装/运行唤醒词 Python Runtime，不复制数字人图形/视频依赖。首期只需轻量静态页面和已有语音服务。

## 3. 浏览器安全/协议差异：P1-1 的硬门槛

**事实 A：** 标准浏览器 `new WebSocket(url[, protocols])` API 不允许页面像 Python/Flutter IO 客户端那样任意设置 `Authorization`、`Device-Id`、`Client-Id` HTTP 请求头。

**事实 B：** v0.9.8 digital-human 的 OTA Connector 将这些值放入 WebSocket 查询串，且页面展示连接 URL。此实现适合测试，不应原样套到公开 WebUI：包含 Token 的 URL 可能出现在反向代理请求日志、浏览器调试信息和异常数据中。

**事实 C：** 现有 [PR #30](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/30) Caddy 匹配器要求 OTA/WSS **请求头** `Device-Id`、`Client-Id`；不能把普通 Safari WebSocket 当成已适配客户端。#30 目前是 A09-Lite/Hi 小智实验，不是浏览器 WebUI 产品。

**P1-1 设计方向（尚待自动化验证）：**

1. 采用同源 `https://<private-webui-host>/` + `wss://<same-host>/...`，前端通过 HTTPS/会话 Cookie 身份认证，浏览器**不保存服务端 HMAC 主密钥**。
2. 私有 Owner 登录会话与原 ESP32 A04 Device-Id/Client-Id 分离。原微雪 4B 走不需要网页验证码的既有通道；网页可以经 Access 登录，不能把 Access 的重定向强加给无浏览器 4B。
3. 使用最小同源鉴权网关（优先 Caddy 已有 `forward_auth`/可信内部服务）在 **WS 升级前**判定 Owner，并按验证后的服务端会话映射内部 identity/headers；不要求浏览器发送私密 HMAC Token 查询参数，且拒绝未授权升级。是否能不新增自定义 WS 代理，要由 P1-1 的真实 Caddy+上游集成 CI 证明，不凭文档推断。
4. 真实服务器 OTA/WSS 始终复用官方 A03 的签名与协议；A09-Lite 六位码保留给确实需要的设备/App 配对，不强制 WebUI 本身使用六位码。不得以重用原 4B 的凭据、客户端 ID 或秘密路径实现“兼容”。
5. 不在公开前端显示/记录完整 OTA Token、HTTP Authorization、设备标识、内网地址或私有入口；WS query、Cookie、鉴权中间结果均需 CI 负向用例。

**拒绝条件：** 只要需要放开 4B 原有安全策略、将 HMAC 秘钥下发给网页、公开 WS 查询串 Token，或对原 A04 做未备份修改，P1-1 直接阻断，不向生产推进。

## 4. 低成本文字+语音的两条调用路径

```text
iPhone/iPad/Mac Safari  -- HTTPS/Owner session --> WebUI BFF (minimal)
    |                                                   |
    +-- text input ---> existing GenericGPTLLM --------+--> text stream/history
    |
    +-- mic AudioWorklet/Opus --> approved WSS --> existing A03
                                                  |-- VoskASR
                                                  |-- GenericGPTLLM (GPT/DeepSeek text API)
                                                  +-- EdgeTTS --> Opus --> buffer --> speaker

Waveshare ESP32-S3 4B -- original A04 OTA/WSS --> existing A03 (unchanged)
```

- **文字模式**使用现有 OpenAI-compatible LLM Adapter 的独立受保护文本接口，省略 ASR 与 TTS；不通过伪造 `listen.detect` 达成文字-only。不同平台会话不得默认互通。
- **语音模式**维持 A03 原官方协议、16kHz PCM/Opus 的已存在逻辑，P2 建立 60ms 帧、TTS stop、队列背压、尾音和快速打断的可复现自动化测试，不在 P0 直接改播放逻辑。
- **模型选择**：仅对已在既有兼容接口验证并获得 Owner 授权的 GPT/DeepSeek 配置开放，不能在网页接受任意外部 API Base URL/密钥。
- **费用边界**：Vosk 本地 ASR不增加按分钟 API 费；EdgeTTS 通过外部在线服务访问，无独立计量语音 API 费但无永久免费/可用保证；文本 LLM Token 继续按其供应商收费。任何实时语音计费模型均在本路线首期范围之外。
- **开发/部署边界**：不得新增 Java Manager/MySQL/Redis、第二套 TTS/ASR、F50 代理服务、固件刷写或锁屏常驻。

## 5. P2 音频连续性和 Safari 验收设计

- 浏览器麦克风必须由用户手势开始，`getUserMedia` 和 `AudioWorklet` 需要安全上下文（HTTPS），处理用户拒绝、切后台、返回前台、耳机切换与网络断线。参考 [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia) 及 [AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet)。
- Cloudflare WSS 仅在握手时作为普通 HTTP 请求接受鉴权；长连接可能因静默而断开，必须有上游/浏览器会话重建策略，详见 [Cloudflare WebSockets](https://developers.cloudflare.com/network/websockets/)。
- 记录至少：`mic_pcm_frames`、`opus_out_frames`、`ws_in_audio`、`audio_queue_depth`、`underrun_count`、`first_audio_latency`、`last_packet_played`、`interrupt_latency`、`tts_stop_pending_frames`。只记录聚合计数/时间差，不记录用户声音/原始文本或 API 密钥。
- `tts.stop` **不得无条件视为“立刻清缓存”**；在普通播放结束与用户明确 abort 两种情况下分别设计终止/清队列策略，测试结束时尾帧是否真实播放。这个路径是 **WebUI 特有的潜在问题**，不能据此声称已经解释 4B 的 A07 断音。
- P2-2 验收包括 30 轮本地可重放随机延时/丢包/中断用例 + iPhone Safari 真机集中语音 >=10 分钟；P3 继续独立验证 4B 句中卡顿，不用 Safari 的 PASS 替代 4B PASS。

## 6. 阶段依赖、具体交付及验收裁决

| 下一 PR | 核心输入 | 通过条件 | 未解决即阻断 |
|---|---|---|---|
| P1-1（10%） | 旧 A04/PR#30 Caddy、A09-Lite、同源 Owner 会话 | 独立假服务 + 固定 upstream v0.9.8 OTA/WSS 200/101/403，身份错/未绑定/过期必须拒绝，回退通过 | 浏览器无法安全提供身份、需要改 4B 生产 Caddy、当前 VPS RAM/Swap 不足 |
| P1-2（10%） | 现有 A05 GenericGPTLLM + Session store | 文字-only GPT/DeepSeek 模拟流式，20 组自动化问答，无 ASR/TTS 调用，Cookie 权限测试 | 只能通过会产生 TTS 的 `listen.detect` |
| P2-1（14%） | 官方 recorder/opus/playback 可用代码 | Safari/Chrome AudioWorklet、安全 HTTPS，Opus format，自研代码最小 | 无法证明 Opus 二进制授权/格式兼容 |
| P2-2（11%） | P2-1，播放器队列/stop 状态机 | 30 轮独立重放和真实 iPhone >=10 分钟 | 用户手势、尾音/打断、权限或断线未通过 |
| P3（20%） | A07 #27 + 同步 TTS/网络/队列指标 | 真实 4B A/B 支持根因，最小修复和回归 | 仅以 CI mock 或单次 60ms 配置变更宣称断音修好 |

**P0-2 自身只验收官方源码选型、安全/授权约束、可执行的集成测试门槛以及独立 CI。此 PR 不写 WebUI 运行时代码、不改 VPS/4B、不请求付费语音 API，也不将 iPhone 实测记为通过。**
