# S3-Voice WebUI P1-1 — 安全入口交付与验收边界

日期：2026-11-26。依赖：已合并 P0-1 #31、P0-2 #32。P1-1 权重 10/100。

## 为什么必须有一个浏览器鉴权层

官方小智 digital-human v0.9.8 使用 URL 查询参数传递 WebSocket authorization、Device-Id 和 Client-Id。标准浏览器 WebSocket API 不能自行添加任意 HTTP 请求头。为避免把签名 Token 放进浏览器 URL，增加一个只负责 Owner Session 和内部授权的轻量 Python stdlib 服务，不增加第二套 A03/ASR/TTS/LLM。

## 安全架构（仅为隔离原型，尚未生产部署）

1. HTTPS 上的登录界面（P1-2 才开发）向 /webui/api/login 发送 Owner 密码，服务端返回 Secure / HttpOnly / SameSite=Strict / __Host- Cookie，保存 30 分钟。仅允许正确 Origin，8 次失败/分钟后限流；最多 8 个活跃 Session。服务端仅在内存维护 Cookie，重启即失效。
2. 浏览器连接 wss://同源/webui/ws，不包含任何 HMAC Token 或设备标识。Caddy 进入 route 后先删除来自客户端的 Authorization、Device-Id、Client-Id 及 X-S3-* 可信头。
3. Caddy 在 WebSocket 升级前执行 forward_auth 内部 GET /internal/ws-auth，注入专门 Gateway Secret。授权服务同时校验 Cookie、Origin、真实路径和方法，随后使用独立 WebUI 设备身份向现有 A03 内部 OTA POST 获取上游签名 token。
4. 内部鉴权应答传回完整的 Authorization / Device-Id / Client-Id，由 Caddy 将它们覆盖到进入 A03 的 WebSocket 握手头，不传递浏览器 Cookie 或 Origin。A03 原有 HMAC 验证逻辑继续生效。
5. 严禁复用已有微雪 4B 的 Device-Id、Client-Id、私有 OTA 路径或凭证。A09-Lite 六位码仅作为另一路设备绑定实验，不属于 WebUI 登录必备。

## 官方资料与真实风险

- Caddy forward_auth：https://caddyserver.com/docs/caddyfile/directives/forward_auth
- Caddy reverse_proxy：https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
- Caddy 安全公告 GHSA-7r4p-vjf4-gxv4：https://github.com/caddyserver/caddy/security/advisories/GHSA-7r4p-vjf4-gxv4
- 标准浏览器 WS 无法指定任意 HTTP Header：https://websockets.readthedocs.io/en/stable/topics/authentication.html
- 原小智服务端固定版本 v0.9.8：https://github.com/xinnan-tech/xiaozhi-esp32-server/tree/v0.9.8

安全公告指出部分 Caddy 2.10–2.11 版本的 forward_auth copy_headers 在认证回应缺少某个头时，可能保留客户端伪造的同名请求头。因此绝不单独依赖 copy_headers；必须在有序 route 中预先显式删除原请求所有可信身份/令牌头，之后再转发内网产生的完整非空头，CI 用恶意身份注入实测。正式部署仍需锁定具体镜像 SHA 和公告修复状态。

## 文件与代码范围

| 路径 | 角色 |
|---|---|
| tools/ai/webui_auth.py | stdlib Owner Cookie、限流、Origin、内部 OTA Token 授权 |
| deploy/ai/webui/Caddyfile.ci | 官方 Caddy 的独立 CI 路由，不能覆盖生产 A04 |
| deploy/ai/webui/Caddyfile.fragment | 将来手工审查后追加的路由片段，不是自动安装器 |
| deploy/ai/webui/docker-compose.ci.yml | 只有虚构密码、身份和假 HMAC；无生产凭据 |
| tests/ai/test_webui_auth.py | 7 组 Python 单测，包含 TTL、失效、错误 OTA、强制拒绝 |
| tests/ai/test_webui_caddy.py | 真 Caddy 101/403 + 错误路径 + 跨站 Origin + 伪造 Header 防护 |
| tests/ai/webui_fake_voice.py | 测试假后端，只验证 OTA/HMAC/WS 握手，不执行语音或付费 API |

## 本 PR 完成与禁止事项

- 源码自检及专用 CI 通过属于模拟级别验收，不代表真实 A03 镜像、Safari 话筒、Cloudflare 或微雪 4B 已经通过。
- 此 PR 不包括可见 WebUI 页面、文字聊天、音频编码、完整 WS 帧的语音往返；这些属于后续 P1-2/P2。
- 禁止把整份 Caddyfile.ci 写进生产；生产部署前必须只读获取当前 VPS MemAvailable/Swap、现有 A04 Caddyfile 指纹/备份和 4B 健康状态，先验证真实 A03 200/101/403 和回退。
- 真实 VPS 上只有 A03 原容器和 A04 既有入口可以被复用，不允许重启或替换已有 HomeSphere、MiniProbe、Cloudflare Tunnel，也不能刷写/清空 4B。
- 安全阈值：可用内存至少 1.05GiB、试点 Swap 增量不超过 64MiB；不达标必须 BLOCKED。
- 注销或 Session 过期阻止新的 WS 握手，已建立的 WS 尚不能被强制终止，此功能若成为需求应在 P4 单独验收。

## 进度规则

只要尚未在真实 A03/生产资源前置检查和安全回归中完成验收，P1-1 即使源码 CI 绿也只能标记“代码已交付，部署验收待定”，不应计满 10/100 权重。当前 WebUI 仍然未能进行真实文字或语音聊天。
