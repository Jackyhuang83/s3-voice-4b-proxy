# UI v3 精简聊天标题与输入框焦点样式（2026-11-28）

## 范围与基线
从当前稳定发行分支 `release/s3-voice-ui-v3-20261128` 独立派生；只解决两项已确认的纯前端装饰问题：
1. 从聊天顶部移除固定文案 `私人对话` / `今天想聊些什么？`，保留模型选择与新对话按钮；
2. 移除输入框**打字/聚焦时出现的内部方形焦点轮廓**，保留真实 textarea、光标、文字输入、Enter 规则、发送和语义标签；不移除 iOS 系统输入法候选框（网页无法可靠控制）。

## 小范围 UI 修正执行路线（100% 验收权重；属于既有 UI v3 维护，集中一个 PR，避免对两处 CSS/HTML 修改拆 PR）
| 步骤 | 权重 | 依赖 | 交付 | 验收 |
|---|---:|---|---|---|
| P0 只读根因核查 | 20% | 稳定 UI v3 | 确认固定标题来自 index.html，输入框的聚焦轮廓来自 app.css 的全局 `:focus-visible` 规则；确认 app.js 仅提供输入自动增高而不创建方框 | HTML/CSS/JS 源码证实及稳定版哈希 |
| P1 只改 UI 外观 | 50% | P0 | 去掉标题 HTML 节点，保留 `chat-head` 工具栏；限制 `:focus-visible` 到其他控件、取消 textarea 内框，不动文字 JS、WebAuth、ModelAPI、WebVoice | 仅 index.html、app.css、文档、纯界面回归测试变化 |
| P2 自动化验证与可回退交付 | 30% | P1 | CI DOM/CSS/iPhone 宽度回归、源码文件哈希检查；通过后方可准备安全上线 | 无页面缺失资源、模型/文字 SSE/登录/声音模块不变；CI 真实绿色；VPS 与 Safari 需另验 |

**GDGS**：现有成熟 UI v3 直接沿用，仅改两处确实需要的 DOM/CSS；不重写功能，不扩 PR，不影响 Cloudflare、VPS、设备、模型 API 与旧语音模块。原分支及正式服务不动，发生回归可立即恢复原 UI v3 文件。

## 计划内文件边界
- `webui/index.html`: 仅移除 `.chat-title` 两句标题节点；
- `webui/app.css`: `.chat-head` 控件保持右侧排列；去掉 `textarea:focus-visible` 产生的内层矩形描边，同时保留其他可访问性焦点；
- `tests/ai/test_webui_v2.py`: 添加本次两个 UI 合约回归；
- `webui/app.js`、`webui/audio-ui.mjs`、`tools/ai/webui_text.py`、`tools/ai/webui_auth.py`、现有 Caddy/Cloudflare：**字节保持不变**。
