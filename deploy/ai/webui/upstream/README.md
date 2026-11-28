# WebUI 成熟方案替换（GDGS：不自研功能）

**日期**：2026-11-28。独立迁移候选，仅使用官方发行版/已有成熟功能。**不是线上迁移完成声明**。

## 官方整套产品候选：Open WebUI slim

- 源码： https://github.com/open-webui/open-webui
- 官方文档：https://docs.openwebui.com/getting-started/quick-start/
- 官方连续语音：https://docs.openwebui.com/features/chat-conversations/chat-features/voice-mode/
- 发行版：`ghcr.io/open-webui/open-webui:v0.12.3-slim`（CI 必须确认 Docker registry 镜像存在及可拉取，部署前再记录不可变 digest）。
- 官方原生能力：浏览器聊天 UI、模型供应商、账号/历史、Standard 语音模式、TTS/打断；不复制源码、不做自研 UI/编解码。
- Pilot：`docker-compose.openwebui.pilot.yml` 完全独立项目命名，127.0.0.1:18173 独立绑定，独立数据卷，独立凭据，仅本机可访问；没有连接现有的生产 Cloudflare Tunnel/域名，不涉及 4B。
- **阻塞**：官方 Standard Voice 必须由服务器做 STT；设为 Web API 时通话按钮不可用。现有 `VoiceCore` 已有 VoskASR/EdgeTTS 但只有 XiaoZhi 私有 WSS 语音协议，不是 OpenAI `/audio/transcriptions` 标准 HTTP 服务。必须优先寻找已有、可直接使用且资源可承受的成熟 STT 接口/服务，不能自己编写 HTTP STT 适配器来重新实现已有功能。若没有实用解法，停止在 Open WebUI 上继续投入，改检查官方 XiaoZhi 完整网页客户端或其他成熟解决方案。
- **用户需求约束**：现有 `WebUI v3 + WebChat` 正在生产正常运行；禁止未经测试覆盖。新方案应以用户可以切换的通用 AI API 为模型后端；不得默认付费 Realtime API；用户授权后才能启用产生费用的语音服务。
- **正式发布门槛**：至少官方容器可启动、健康探针通过、使用现有供应商真实文字对话、独立兼容 STT/TTS、Safari 连续语音 10 分钟、回退可用、保持用户登录隔离；在全部通过前不移除生产中仍被引用的自写文件。

## 官方 XiaoZhi 原生候选（使用已有 VoiceCore 时的优先语音路线）

- 官方仓库/tag： https://github.com/xinnan-tech/xiaozhi-esp32-server/tree/v0.9.8/main/digital-human
- 自带：`audio/recorder.js`、`audio/opus-codec.js`、`audio/player.js`、`audio/stream-context.js`、`network/websocket.js`、`network/ota-connector.js`。
- 官方 README 将该目录称为**数字人音频测试客户端**，含摄像头、OTA、唤醒桥接，并非 WebAuth 用户权限应用。未经验证不能把其 OTA 设备身份凭证暴露给网页，也不能调用 4B `DeviceGateway`。先验证能否以**最小的接口/配置映射**连接已有专属 `WebAuth` 与 `VoiceCore`，不修改录音、编解码、播放、中断逻辑；若必须自写这些功能，禁止实施。
- 许可证 MIT，复用时保留版权与许可证。

## 删除与回退策略

- 现有 GitHub `main` 分支本来就没有旧自写 WebVoice 音频模块；未合并的旧开发 PR #39/#50 已关闭。它们的源代码仍可由 Git 历史追溯，不会继续开发/发布。
- 当前迁移候选分支从 `release/s3-voice-ui-v3-20261128` 创建。只在本**非生产分支**执行旧 WebVoice 源文件的删除，作为成熟替换来源的源码迁移草稿。旧 WebUI HTML/JS/CSS/WebAuth 本身仍在稳定版上运行，**必须在替代产品通过实机验收后才清理实际使用的依赖**。
- 不修改 VPS、不关闭服务、不创建公开路由、不调用付费模型、不触碰 4B 固件及设备网关。
- P0–P3 的阶段、PR 数量、权重、依赖及验收标准见 `docs/ai/WEBUI-ROADMAP.md` 新增章节。
