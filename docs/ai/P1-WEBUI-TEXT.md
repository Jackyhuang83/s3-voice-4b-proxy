# S3-Voice WebUI P1-2 — 低成本 GPT / DeepSeek 文字聊天

日期 2026-11-26；依赖已合并 P1-1 安全入口 [PR #33](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/33)，P0/全阶段路线图见 [WEBUI-ROADMAP.md](WEBUI-ROADMAP.md)。

## 目标 / 交付

- 自建轻量前台 `webui/index.html`、`webui/app.js`、`webui/app.css`：iPhone Safari 前台文字聊天、自适应 UI、纯文本流式回复、错误提示、Owner 登录、退出及 GPT/DeepSeek 切换。
- 重用原先已通过 A05 官方适配器的 **OpenAI-compatible Chat Completions SSE 协议**（`POST /v1/chat/completions`；`stream=true`）。A05 并没有可独立调用且无 TTS 的 HTTP WebUI 聊天端点，故在已有 P1-1 stdlib 鉴权容器里增加一个很小的文本专用 HTTPS SSE broker，**没有再启动第二套模型、TTS、ASR 或小智 Server**。
- 文字模式完全不走 Vosk ASR / EdgeTTS；既有 4B 无变化；WebUI 不调用昂贵的 GPT-Live/Gemini Live。
- 所有页面均同源 `/webui/*`；仅新的静态文件可未登录读取。`/webui/api/models` 和 `/webui/api/chat` 必须通过 P1-1 HttpOnly Cookie 登录及 POST Origin 检查。**登录密码、私有 A03 HMAC、模型 API Key 不返回给浏览器**。
- 模型名称/下游 Model ID/HTTPS API 地址由服务器自己的私有模型目录配置；浏览器仅可选择公开的模型别名，不能提供任意 Base URL、API Key、system role 或启动付费实时语音模型。

## 安全模型 / 流式协议

浏览器发 `POST /webui/api/chat`：`{"model":"GPT","messages":[{"role":"user","content":"你好"}]}`。后端验证授权、请求体/消息条数/角色、配置的模型别名及并发槽，再依据现有 A05 的 Chat Completions 格式向可信 HTTPS 模型接口发起 **单次** 流式请求。浏览器仅接收逐增量 `data: {"delta":"..."}\n\n` 和 `data: [DONE]`，无法获得上游 API Key、Host 及原始 provider body。

硬门槛：
- 原始文本与提示词只在本次浏览器内存保存，刷新立即清空；当前**不实现云端历史同步**，也不使用 localStorage 缓存用户秘密。
- Chat Completions API 路由固定 `/chat/completions`；服务器模型目录最多四种别名，允许多个模型共用已有 Provider，要求 `https://...`，不允许本地/private IP、任意端口或上游 HTTP redirect。仅 **CI 测试**可以在内存中注入本机假 Provider。
- 最大请求 32 KiB、20 条消息、每条不超 2000 字符；默认 `max_tokens=1024`，最高两路并发。此为防滥用预防措施，不能替代 P4 的费用预算/真正供应商额度限制。
- SSE 事件仅允许上游 `choices[0].delta.content` 字符串，长度受限，不透传 provider JSON，也不输出任意上游错误。中断必须失败，不能伪造成功结束符 `[DONE]`。
- 页面 `textContent` 添加模型回复，不把 LLM 输出注入 HTML（防 XSS）；CSP `default-src 'none'` + 同源 script/style/connect，禁止 iframe。
- 私有模型目录通过 root-only 模型文件 `S3_WEBUI_MODELS_FILE=/run/secrets/s3-webui-models.json` 提供，不在 PR、Caddy 环境变量或网页硬编码 Key。文件内容示例只使用假的占位值：

```json
[
  {
    "id": "GPT",
    "label": "GPT",
    "model": "provider-model-id",
    "base_url": "https://provider.example/v1",
    "api_key": "REPLACE_WITH_PRIVATE_KEY"
  },
  {
    "id": "DeepSeek",
    "label": "DeepSeek",
    "model": "provider-deepseek-id",
    "base_url": "https://provider.example/v1",
    "api_key": "REPLACE_WITH_PRIVATE_KEY"
  }
]
```

模型凭据不能从现有 A03 配置自动公开。正式 P1 部署前需要在本机 root-only 私有卷中安全配置/复用已授权的凭据，不允许贴到 GitHub、聊天记录或公开终端输出。

## 验收门槛（当前 PR 只做到代码 + 隔离功能）

| 级别 | 工作内容 | 证明与限制 |
|---|---|---|
| 源码审查 | 复用 A05 同类 Chat Completion SSE 协议；前端静态文件；不改原 A03 | 可代码核查 |
| 专用 CI | 20 组中英/Unicode/HTML 文本流、GPT/DeepSeek 选择；未授权、Origin、角色、路径、密钥泄漏、请求限流 | 不使用任何真实模型 API 或真实凭据 |
| 官方 Caddy CI | 原 P1-1 Caddy 2.11.7 的 WS 101/403 回归、HTML/CSS/JS 静态访问、未登录目录 401、CSP | 仍是临时容器 |
| 真正的模型访问 | 在实际 Debian VPS 只读资源/密钥审查后，正式 GPT/DeepSeek 各返回完整回答、错误恢复、受控费用 | **尚未执行，不是 CI PASS 的推论** |
| iPhone Safari | HTTPS 登录、文字输入、切换模型、流式回复及错误恢复 | **尚未验收** |

## 代码及实际影响

修改已合并的 `tools/ai/webui_auth.py` 仅添加模型目录读取、HTML/CSS/JS 与文字 API 路由。模型及响应处理集中在 `tools/ai/webui_text.py`，不修改小智 A03 原始配置、A04 隧道、WebSocket HMAC 或任何微雪 4B 固件。CI `test_webui_text.py` 与现有 P1-1 的所有回归检查独立运行。

**P1-2 权重为 10/100，但只有专用 CI、真实 VPS + iPhone 文字聊天均达到验收后才能计满。** P1-1 也还有生产部署验收门槛；因此现有完成率仍保持 P0=100%、P1=0%、总计 10%。下一步与 P1-1 联合部署评估时只允许只读预检及可逆试点，绝不为了增加进度跳过安全条件。
