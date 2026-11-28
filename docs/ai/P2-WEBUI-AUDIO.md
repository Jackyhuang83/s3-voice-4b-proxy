# P2-1 — XiaoZhi 原始 Opus iPhone WebUI 音频实现与 A04 隔离入口前置修复

版本审计：2026-11-27。P1 已在真实 VPS 独立边车发布，iPhone Safari 基础文字聊天已实测通过；长思考/界面等生产热修复仍需与 GitHub 源码核对并同步。P2-1 功能权重 14，只有正式依赖和实机语音验收满足后才计入项目完成率。

## 复用优先：选型与锁定

- **官方小智服务器固定 v0.9.8**：`hello` / `listen start` / 原始 Opus 二进制 WS，参考 https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/digital-human/js/core/network/websocket.js 及 `core/connection.py`。语音上行：16 kHz 单声道、每帧 960 样本=60ms；服务器端输入 Opus 解码器是 16k mono。
- **编解码器不是自写**：`openclaw/libopus-wasm@v0.4.1` 为成熟发布的 ES module, 编码 + 解码 raw Opus，无 Ogg/WebM 封装：https://github.com/openclaw/libopus-wasm/releases/tag/v0.4.1。它是小型 WASM 库，不需要 OpenClaw 服务器。其源码 MIT，所链接 libopus 依 BSD，保留 LICENSE 与 THIRD_PARTY_NOTICES.md。
- **官方固定发布包 SHA-256**：`f645938adcd3381dcae9827ef71248218eaeb8308b6339bd568d1c43a64c5ef8`，`tools/ai/webui-vendor-opus.sh` 只允许从官方 npm registry 下载并验证该摘要，再复制 dist+LICENSE+第三方声明到 `webui/vendor/libopus/`。CI 和 staging 时使用；不要在生产 SSH 当前 Shell 里 source 它，不允许无校验下载。
- `webui/audio-opus.mjs` 封装上游编码器/解码器资源初始化、16k mono 960 frame 断言及整帧聚合，未实现任何自研 Opus。官方库支持 16k、60ms 和 Float32 编解码：https://libopus-wasm.dev/encoding.html。
- `webui/audio-worklet.js` 仅执行 AudioWorklet 中的 PCM 捕获/单声道重采样，输出 960 PCM 样本；`webui/audio-ui.mjs` 经 HTTPS 用户点击发起 getUserMedia、WS Hello/Listen、编码发送和语音播放。HTTP Auth/HMAC 不进入浏览器，仍经 P1-1 网关。
- 浏览器 CSP 仅对 WASM 增加 `'wasm-unsafe-eval'`，仍 `default-src 'none'` 且 JS/CSS/连接同源；WebUI 资源由自身 Caddy 显式白名单允许，不允许公开目录浏览。Safari 后台/退出页面停止麦克风。

## 生产前置修复：Issue #38

- 官方 Caddy 镜像的文件 capability 在 `cap_drop: ALL` 时可能导致启动 EPERM。新独立 Caddy 的生产模板现在按原 A04 的**既有成功基线**增加 `cap_add: [NET_BIND_SERVICE]`、`user: '1000:1000'`、no-new-privileges；合成 CI 容器 **真实启动相同权限组合**，而非只靠 `docker compose config`。
- Auth 边车移出 Cloudflare Tunnel 所连接的前端网络，仅留 A03 后端；独立 Gateway 同时连接 front+A03。无主机端口，旧 A04 Caddyfile / compose / Cloudflare Tunnel / 4B 不改。
- P1 的五 PR 上限不动，依照事先更新的路线图在 P2-1 一起交付必要的 P1 生产阻断修复。P1 真实部署和实际 Safari 验收仍不得跳过。


## 2026-11-27 P2-1 语音交互补强（仍在同一 PR #39）

- 源码发现的交互缺陷：原 AudioWorklet 在收到 `tts.start` 后仍向服务端上传麦克风帧，可将扬声器音频再次输入 ASR。现按官方 XiaoZhi Listening → Speaking 状态转换暂停麦克风；`tts.stop` 后等待已排队的最后一帧播放完毕，再在同一 WS 会话恢复麦克风。P2-2 仍负责真实延迟、抗抖动、尾音和打断系统性验收。
- 主动停止/退出时，同时结束当前 WS、释放编码器和 MediaStreamTrack、取消握手/续录定时器、终止已排队的浏览器音频；不得误操作另一个已启动会话。
- 语音按钮更新 `aria-label` / `aria-pressed` 而不覆写已有 SVG，复用当前 iPhone WebUI 的 24px 单色麦克风；小字状态栏替代大面积重复提示。
- 新增 `tests/ai/test_webui_audio_ui.mjs`：模拟 hello 鉴权确认前不上传、Opus 帧、TTS 时禁止回录、尾音后恢复、手动停止、旧会话定时器失效和 SVG 保留，零真实网络/麦克风/LLM 费用。与已有 30 帧真实 libopus-wasm 测试并行作为 P2-1 专项 CI。
- **生产部署门槛**：当前 VPS 的 `/opt/s3-voice-webui/src` 存在尚未同步到 GitHub main 的 P1 User-Agent、SSE、DOM、长思考及外观修改。绝不能直接用本 PR 的旧源树整体覆盖在线目录；部署前逐文件核对基线并备份，以增量方式合入 `audio-*.mjs`、Worklet、厂商 WASM、Auth 静态白名单/CSP 及 HTML 按钮。不得覆盖在用模型凭证或恢复旧版 HTML/CSS。
- 源码测试、CI、真实公网 WSS/Opus、iPhone 10 分钟、4B 无干扰分别记录；**目前只有源码/自动化证据，没有真实 iPhone 语音通过的证据**。

## 分级验收

| 等级 | 验收 | 证明状态 |
|---|---|---|
| 源码复用 | 官方 XiaoZhi v0.9.8 及 libopus-wasm 0.4.1、MIT/BSD | 源码核查完成 |
| 自动化编码测试 | 官方包 SHA-256、30 帧 16k mono/60ms Opus 编解码、resampler 分块不变性、内存释放 | 专用 CI 验收 |
| Caddy 真实权限 | Docker Runner 下 cap_drop ALL + cap_add NET_BIND_SERVICE 的 Caddy 实际启动；原设备模拟 OTA 200/WS 101/403、新 WebUI 101/403 | 专用 CI 验收 |
| 浏览器输入 | HTTPS 权限提示、点击启停、网络断线、后台麦克风、同源 JS/WASM | 源码检查；Safari 实测待定 |
| 真正端到端 | iPhone Safari ≥10 分钟真实音频流、正常播放到尾音、TTS stop、Codec 是否卡顿 | **NOT RUN**；P2-2 进一步自动化 30 轮抗抖动测试 |
| 设备兼容 | 微雪 4B 不受影响、原 A04 设备路由继续正常 | **NOT RUN**，只能在可回退生产试点实测 |

本 PR 暂不声称 A07 卡顿问题已修复，不把 WebUI 正常播放等同于 4B 稳定性。当前不新增任何付费实时语音 API。P1 未达到验收前 P2 的 14 分不授予，项目整体仍 10%。


## 2026-11-28 P2-1 安全上线门槛（不允许覆盖线上 P1）

以生产 VPS 上通过 iPhone Safari 真实文字聊天的目录 `/opt/s3-voice-webui/src` 为基线，先**只读**核对，不得直接 `git checkout`、`git reset` 或 `cp -a` 整个 P2 源码覆盖该目录。

### 预检（生产零修改）
1. 确认四容器均 Running：`s3-voice-ai-server`、`s3-voice-ai-gateway`、`s3-voice-webui-auth`、`s3-voice-webui-gateway`，记录前三者和旧 WebUI 两者的 container ID/StartedAt。
2. 以仅返回布尔结果的方式确认线上 P1 差异：后端已有 `User-Agent: S3-Voice-WebUI/1.0`、`timeout=90`、`MAX_OUTPUT_BYTES = 524288`、空 `choices` 跳过；前端 JS 仍有 `el("welcome").hidden = true`、已收到文字的错误保留；HTML 仍有 `S3-Voice AI助手`、`voiceButton` SVG；CSS 有 `S3-VOICE-MINIMAL-UI-V1` 和 `S3-MIC-OUTLINE-V1`。不要输出 `models.json`、`auth.env`、Cookie、API 密钥或 WebSocket 令牌。
3. 确认 P2 GitHub PR #39 所有相关工作流成功且未合并进 `main` 前有准确 head SHA。只有使用固定 Git commit 对应源码，才在**独立、私有、权限受限**的 stage 目录运行 `webui-vendor-opus.sh` 并核对 npm tarball SHA256。stage 源码和生产挂载目录严禁混用。
4. 在 stage 内确认 Opus WASM 及 JS 资源实际可读，且 Auth/Caddy 白名单与 CSP 仅添加必要的固定路径，禁用 CDN 和目录遍历；验证不会更改既有 A04/Cloudflare Tunnel/4B 身份。

### 集中发布（只有预检通过后）
1. 创建不可覆盖的时间戳备份：生产 P1 JS、HTML、CSS、`webui_text.py`、新 WebUI Caddyfile 和 Compose，以及既有容器身份；备份私有配置仍留 VPS，不复制到 GitHub。
2. 以增量合并方式将固定的 `audio-ui.mjs`、`audio-opus.mjs`、`audio-worklet.js` 与带许可证的官方 WASM 加到现有 WebUI 文件树；**保留**线上 P1 JS、CSS、模型与 API 密钥、SSE 超时/Usage 修复。P2 HTML 只新增带 `voiceButton` 的 module 脚本及 `voiceStatus` 状态区域，避免重复创建已经存在的 SVG。
3. 新 WebUI 的 Auth 静态白名单与 CSP/WASM 必要项同步，Gateway 仅增加受限静态路由。固定路径先用 Auth/Gateway 本地 200、Content-Type、CSP、WASM 初始化及权限负向测试验证。不得扩大对外路由，尤其不得影响 A04 原 `/xiaozhi/v1/` 设备通道。
4. 仅在所有检查 PASS 时，依次重载**独立 WebUI** Gateway/Auth（修改后端 Python 需重启 Auth，导致 WebUI 密码会话重新登录），确认旧 A03/A04 容器 ID 与启动时间保持不变。任何失败只回滚本次新 WebUI 文件及服务，不回滚或触碰旧设备；有失败时不得进入 iPhone 实测。

### 真实验收
- iPhone Safari：Access + WebUI 登录、原文字聊天、长思考回复、点击麦克风权限、WSS 101、Hello、监听/说话→ASR→TTS 有声播放、播放尾音后恢复监听、主动停止和退出、后台关闭，至少 10 分钟。
- 区分四级：源码检查、CI 通过、隔离 VPS 功能通过、iPhone/4B 真实验证通过。P2-1 未拿到最后两级之前仍为 0/14。

## 2026-11-28 语音间歇识别/首声慢诊断

用户在 iPhone Safari 验证了**至少一次完整语音往返**：有时能正常识别/回答，但识别偶发失败且答复明显慢。此证据仅证明局部功能可达，不能据此认为 P2-1 10 分钟验收完成。

当前 WebUI 实施为**半双工**：收到 `tts.start` 暂停麦克风，直到收到 `tts.stop` 且音频尾部播放完毕才恢复。正在播放的 AI 不能被语音插话打断；将它和真正的无声输入故障区分，P2-2 另行实现合法打断/回滚与自动化抗抖。

避免未经测量修改 A03 的 Vosk/EdgeTTS、`close_connection_no_voice_time`、代理和网络。P2-1 原 PR 追加**浏览器端本地小计时**，只在页面显示：
- `已发送 N 帧/输入峰值 K%`：证明浏览器将 Opus 包交给 WSS API，不等于服务端收包或 ASR。
- `已识别｜结束录音→识别约 Xs`：以最后一次有效输入帧为代理，**不是**严格的音频结束时间；无显著输入则显示未知。
- `识别→TTS启动 Xs`：该段混合了模型推理、TTS调度、服务器发送状态，不能直接指认为 LLM 耗时。
- `TTS首个音频帧 Xs / 音频 N 帧`：基于浏览器消息到达时间，不等于真实扬声器首声；若 UI 有文字而 N=0，重点查 TTS 发送链路。
- 状态内容和统计只在浏览器内存，**不记录语音文本、设备身份、凭据或音频**，不发给第三方，退出自动释放。
- 继续保留老 HTML/CSS 和已通过的长思考修复，禁止全量覆盖生产目录。新一轮 GitHub CI 与只读校验完成后才能选择是否单文件上线。
- P2-2 根据实测区分 VAD 丢话、Opus 网络发送、TTS 首帧、Web Audio 播放队列和人为半双工限制。没有分段证据前不宣称“已加速”。

### 本次阶段审计
P0=10/10，P1 尚未完成既定正式阶段验收，P2=0/25（P2-1 在实机验证中），P3/P4/P5 各 0；正式项目总计 10/100。源码 PR、CI、真实 VPS 和 iPhone 不互相替代。

## 2026-11-28 AI 处理状态可视化

用户反馈「不知道 AI 有没有在思考」。保持 P2-1 独立 JS+CSS 语音 UI，不改变 P1 模型、音频协议或 A03 处理链路：

1. 浏览器收到服务端 `stt` 后显示 **「AI 思考中 · 已等待 N 秒」**，从该消息到达开始以秒更新；这只是端到端**等待回复**的前端推断，不证明模型内部正执行推理，也不应包含服务端隐私数据。
2. `tts.start` 立刻结束计时并显示 **「AI 正在准备语音」**；收到本轮首个 Opus 数据包后显示 **「AI 语音已到达，正在播放」**；`tts.stop` 等尾音播完恢复 **「可继续说话」**。
3. 独立监控栏持续保留帧数/峰值，录音帧周期更新不得覆盖「AI 思考中」；退出、断线和手动停止需清理计时器。
4. 如果没有收到 STT 就不能显示「AI 思考中」：那可能是 ASR/VAD 未生成识别结果。测试须覆盖未识别不能虚报、计时更新、收到 TTS 取消计时、音频首包/退出清理。
5. 当前未发布到 VPS：只能在最新 CI 全部 PASS、保留原文件备份并校验固定源码 Git Blob 后通过单文件更新。真实 Safari 验收仍是 P2-1 必须的独立门槛。


## 2026-11-28 WebUI 语音尾音修复 + 单文件发布验收

**范围**：用户已将 ESP32-S3 4B 项目完全移出当前 S3-Voice。此工作仅更新 WebUI 浏览器音频模块，不修 4B 设备 A04 私有身份网关，不修改 A03/A04、Cloudflare、UI v3 HTML/CSS/JS、模型或凭据。

- **问题机制**：WebUI 旧版收到 `tts.stop` 后，按预计的 `AudioContext.currentTime + 80ms` 恢复录音，而 Web Audio 实际播放队列可能尚未完成，存在收回声和尾音被误当成输入的风险。依据 Web Audio 标准，新的 `audio-ui.mjs` 在 `AudioBufferSourceNode.onended` 确认所有本轮排队的音频源确实播放结束后恢复麦克风；手动停止仍立即终止音频/WS 和释放资源。保留已有的 16k/60ms Opus、AudioWorklet、语音阶段指标及 UI v3 视觉交互。
- **安全隔离**：新 `tools/ai/webui_voice_publish.py` 只原子替换 `/opt/s3-voice-webui/src/webui/audio-ui.mjs`。发布源锁定 GitHub 不可变提交 `9daabddb90f817c3ad4f418089f07f85dd1e5588`，Git blob SHA-1 为 `f8bf11ca3a852b1474dd827c250d2b654ade53a5`。仅在原文件匹配 UI v3 稳定版 blob `65d2dfc95000f84c67d6b121955cf9801dc1400a` 时部署；线上存在本地修改即停止。
- **保护及回退**：读取 4 个已运行容器的 ID/StartedAt，验证 WebUI Auth 的只读源码挂载，无公开 host ports；所有其他 WebUI 文件哈希保持不变。发布前从现有独立 WebUI Gateway/Auth 内部验证 UI、文字脚本、会话 API 和未登录 WebSocket 拒绝状态；保存私有原文件备份后原子更新，再读取 HTTP 实际响应 SHA-256 验证，无容器重启。任何应用/验证失败自动恢复原始字节；可单独执行 `rollback` 并留下审计快照。
- **CI**：`tests/ai/test_webui_voice_publish.py` 覆盖正常应用、重复执行、人工回滚、发布后检查失败自动回滚；`tests/ai/test_webui_audio_ui.mjs` 覆盖结束事件驱动、未播完不恢复收音、手动停止。Docker/网络均由 mock 代替，不触发生产 VPS。
- **真实验收门槛**：GitHub 最新 CI 通过 + 在 VPS 成功执行只更改音频前端模块 + Safari 实际连续对话。上述任何一项未完成，不得标注生产声音已修复。4B 安全诊断与 WebUI 语音无关，不可成为前端发布绕过条件，亦不在此 PR 修改。


## WebVoice P2-2 (2026-11-28): Native abort, 30 rounds, single-file guarded release

**User-facing module names:** WebUI (visual UI), WebVoice (browser speech), WebGateway (Caddy), WebAuth (browser auth), WebChat (text), VoiceCore (shared existing XiaoZhi service), SpeechEngine (ASR/TTS), ModelAPI (user-changeable model API). Historical A-number labels are not used for new user-facing work. DeviceGateway, DeviceVoice and DeviceManager are outside this project.

**Mature protocol reused:** XiaoZhi v0.9.8 `core/handle/abortHandle.py` natively handles `{"type":"abort","session_id":...,"reason":"user_interruption"}`, cancels ongoing LLM/TTS queues and emits `{"type":"tts","state":"stop"}`. Its `listenMessageHandler.py` handles `{"type":"listen","state":"start","mode":"auto",...}` to reset current audio capture state. No server protocol modification.

**WebVoice interaction:** When AI speaks, tapping the existing microphone control sends abort + listen-start on the **same authenticated WSS session**, immediately stops local queued audio, reopens the mic, suppresses stale binary packets even after the abort acknowledgement until a genuine new TTS start, and ignores the abort acknowledgement's duplicate TTS stop. During normal listening, the same button still stops the session. Normal TTS finishes only via actual `AudioBufferSourceNode.onended` across all pending buffers, not an estimated delay. Browser UI exposes different accessible names for interrupt vs stop, preserves the existing SVG and current WebUI v3.

**Testing performed:** The actual GitHub source `webui/audio-ui.mjs` and `tests/ai/test_webui_audio_ui.mjs` were executed in an isolated JavaScript V8 browser mock; output `WEBVOICE_P2_2_AUDIO_PASS` covered thirty consecutive completed audio turns, mic pause/after-actual-tail resume, native abort+listen, stale packet rejection, second click stop and delayed logout. This is **mocked functional evidence only**, not iPhone audio proof or GitHub CI. The GitHub workflow additionally runs pinned real libopus-wasm 0.4.1 encode/decode, isolated WebGateway test and source publisher tests when scheduled.

**Single copy-paste VPS publisher (source prepared, not yet authorized):** `tools/ai/webui_voice_publish.py` hash-pins the completed P2-1+P2-2 audio source at immutable commit `b7e777f352dbf4fef8036b8d39257f43b1ace3d9`. Accepts *either* unmodified stable UI v3 WebVoice (blob `65d2dfc95000f84c67d6b121955cf9801dc1400a`) or previously applied P2-1 WebVoice (blob `f8bf11ca3a852b1474dd827c250d2b654ade53a5`); rejects any other custom files. Only atomic replacement of `/opt/s3-voice-webui/src/webui/audio-ui.mjs`, no HTML/CSS, model keys, Cloudflare routing or container restarts. Private snapshot and strict HTTP/unchanged-container hashes, auto rollback on failed checks, explicit manual rollback. P2-1 and P2-2 CI must both pass before use. Reusing a single publisher avoids asking the owner to perform two sequential updates.

**Pending acceptance:** no production VPS release, no real browser continuous voice test, no user confirmation of stable playback; do not mark the P2-2 11 points complete. Existing UI v3 text and owner login remain protected.
