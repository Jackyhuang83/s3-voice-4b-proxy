# S3-Voice P1-3 — 生产只读预检与隔离试点门槛

**日期：** 2026-11-26。**权重：** P1=20；P1-1=8，P1-2=8，P1-3=4。PR #33/#34 源码和 CI 已合并，并不表示用户 VPS 和 Safari 功能通过。

## 现状及实际阻断

- GitHub/CI 可直接读取，但当前没有已授权的 SSH/VPS 执行工具；历史 RAM 快照不能替代当天状态。
- 现有 A04 Caddy 在独立 Docker 前端网络和 A03 后端网络上运行。增加边车时只能使用既有的 external 网络，不能再部署新小智、Tunnel 或 Manager。官方参考：https://docs.docker.com/compose/how-tos/networking/
- **阻断点**：原 A04 网关没有 S3_WEBUI_GATE_SECRET 环境变量，且 Caddyfile.fragment 未在实际生产 Caddy 中加载。不能复制 CI 的 Caddyfile，亦不能无回退地重启已有 4B 网关。
- P1-2 的模型账号、密钥来自 VPS 私有目录，不进入 GitHub、浏览器、PR 日志或对话记录。实际文本模型访问可能产生 Token 费用。
- 浏览器 Owner 登录和原 4B 非交互 OTA/WSS 必须隔离，禁止对原 4B 强制 Cloudflare Access 验证码。

## 一次性、只读 VPS 检查

脚本位于 tools/ai/webui_preflight.py。经过授权的 VPS 管理环境可执行：

```bash
python3 tools/ai/webui_preflight.py
```

脚本只读取 /proc、statvfs、Docker inspect、A03 OTA GET、A04 默认拒绝 GET、文件权限与指纹；不执行 Docker pull/up/stop/restart、写文件、改网络、访问真实付费模型、刷 4B 或改 Caddy。

**准入门槛**：MemAvailable 不低于 1.05GiB，/opt 空闲不低于 1GiB；A03/A04 正常运行且镜像 digest 固定，18000/18003/18080 均只绑定 127.0.0.1；共享 s3-voice-ai_default 网络且 A04 有唯一前端网络；A03 OTA GET=200、A04 默认拒绝 GET=403；A04 不记录包含密钥的请求路径，私有文件不能被其他用户读取，Manager 未运行。

发现任何不满足返回 WEBUI_P1_PREFLIGHT_BLOCKED，立即停止试点。PASS 只能证明资源/网络基线，并**不**证明 Cloudflare 映射、真实设备 OTA、模型 API 或 Safari 已通过。

## 受控部署拓扑（模板，不自动执行）

- deploy/ai/webui/docker-compose.production.example.yml：一个最多 96MiB / 0.25CPU 的 Python Owner 鉴权边车，**不发布任何新主机端口**。
- 同时连接已存在的 s3-voice-ai-edge_front 和 s3-voice-ai_default 外部网络；通过 s3-voice-ai-server:8003 获取官方 A03 签名 Token，不重用微雪 4B 的身份。
- 模板要求经验证的 immutable image digest 和 VPS root-only 配置，故不能直接 docker compose up。它不是生产安装器，也不包含任何真实或虚构固定密码。
- A04 Caddy 现有 /xiaozhi/ota/<secret> 和 /xiaozhi/v1/<secret> 保留原样，仅可能在明确受控部署时增加 /webui 路由。Caddy handle 有 matcher 排序，需检查解析后的真实路由和旧设备回归：https://caddyserver.com/docs/caddyfile/directives/handle

## 后续人工授权前的硬阻断

1. 预检通过后，在 VPS 本机 root-only 备份 A03/A04 当前 Caddy 与镜像锁文件，生成前后指纹；不得把包含秘密路径的 Caddyfile 上传到 GitHub。
2. 先在隔离网络把新授权边车及完整 Caddy 组合路由验证到：原设备 OTA 200、原 WS 101、非法设备 403；WebUI 登录成功/拒绝、Cookie/Origin/伪造请求头负向测试。
3. 针对旧 A04 的 Gateway Secret 注入和配置刷新，必须有**可逆且不丢失 4B 连接**的步骤；无法证明则 BLOCKED，不应强行重启。
4. 试点 Swap 比预检增量超过 64MiB 或 4B 断线，立即停止新增组件，恢复原 A04 并核对 A03/4B。
5. iPhone Safari 实机完成 HTTPS 登录、GPT/DeepSeek 文字流、错误恢复和模型切换；计量真实 Token 花费。P1 只有在这些真实验证后才能授予权重。

**当前验收：** 源码/CI 可自动验证；真实 VPS/Cloudflare/iPhone/4B 联合验证 NOT RUN；P1=0/20，整体=10/100。
