# 成熟 WebVoice 客户端调研记录（不参与生产部署）

**2026-11-28 最终范围**：用户明确要求 **仅替换网页版语音聊天 WebVoice**；现有文字聊天 WebChat、ModelAPI、WebAuth 和 UI v3 必须原样保留。

## 候选优先级

1. **XiaoZhi 官方 digital-human**：https://github.com/xinnan-tech/xiaozhi-esp32-server/tree/v0.9.8/main/digital-human 。官方现有 `js/core/audio/recorder.js`、`opus-codec.js`、`player.js`、`stream-context.js`、`js/core/network/websocket.js` 实现浏览器语音采集、Opus、音频队列、播放和打断；优先直接复用这些成熟功能。不增加自写录音/解码/重连/打断状态机，必要接口接线受 GDGS 最小适配约束。
2. **Yang-ZhiHang/xiaozhi-webui**：https://github.com/Yang-ZhiHang/xiaozhi-webui （MIT，Vue3 + Python，语音及打断，维护/会话鉴权兼容性需核对）；若官方模块无法通过 WebAuth/Safari 兼容性验收，继续考察其他成熟网页语音客户端。
3. **Open WebUI**：https://github.com/open-webui/open-webui 。其完整网页聊天、账户及历史管理不在本次范围内，**不得以替换 WebVoice 为由更换原有 WebChat**。以前的整套部署候选及 ScribeCrate STT 双容器试点文件已从本分支删除，避免误实施全面迁移。

## 严格边界

- **不得更改**：`webui/app.js`、`webui/app.css`、`tools/ai/webui_text.py`、`tools/ai/webui_auth.py`、模型/API 配置、文字 SSE、现有 UI v3 布局、用户数据、Cloudflare、生产容器及 4B 设备。
- 旧自写 WebVoice 的 JavaScript/音频测试和 vendor 脚本在未发布迁移候选分支中已经删除；已上线稳定 UI v3 没有改变。原始源码保留于 Git 历史，以便回退。
- 当前候选分支中的 `webui/index.html` 仅暂时移除旧语音客户端的脚本与麦克风入口；此状态**不能发布**，必须等验证过的成熟语音模块恢复原有按钮交互后才能准备上线。
- 官方 digital-human 的原版 OTA 示例会经浏览器构造 Device-ID/Client-ID 并连接私有语音服务；不得泄漏已有 WebAuth 凭据或绕过独立 WebGateway/权限验证。若该问题不能在两个成熟组件之间通过最小接线处理，应继续寻找其他成熟方案。
- 完整验收：成熟代码/许可与安全审查、离线 CI、真实 VPS 隔离验证、Safari 麦克风→中文识别→现有模型 API→TTS 播放→连续对话、WebChat 全量回归、可逆备份。未通过不得合并/上线。

**本 README 是选型记录，不是生产安装指南，也不授权自研。**
