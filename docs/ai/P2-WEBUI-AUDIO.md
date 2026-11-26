# P2-1 — XiaoZhi 原始 Opus iPhone WebUI 音频实现与 A04 隔离入口前置修复

版本审计：2026-11-26。当前 P1 源码已合并、VPS 只读预检 PASS，但尚未真实部署、Safari 未验收。P2-1 功能权重 14，只有正式依赖和实机验收满足后才计入项目完成率。

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
