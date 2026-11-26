# S3-Voice P1 生产隔离试点 — 安全执行、SSH 命令验收与回退

**状态**：2026-11-26，源码开发于计划内 P2-1 PR #39，尚未部署到用户 VPS。用户已返回 `WEBUI_P1_PREFLIGHT_PASS`；不要求用户重做相同只读检测。对已安装的 A03/A04、cloudflared、HomeSphere、MiniProbe、4B 原厂固件 **一律不修改**。

## 原则：操作是独立 Python 进程，不是交互式 SSH 命令片段

`tools/ai/webui_pilot.py` 通过 `argparse` 提供 4 个动作，所有 `sys.exit` 仅发生在独立 Python 子进程中；不会在 SSH 登录 Shell 中使用 `exit "$rc"`、`exec` 或加载 shell 源代码。

| 模式 | 读取/修改 | 验收界限 |
|---|---|---|
| `plan` | 只读 A03/A04 检测、Docker 元数据、磁盘和内存 | 原服务仍健康、无新项目冲突；不访问模型、不重启 |
| `stage` | 必须同时明确提供新的子域名和 `--approve-isolated-stage`；只在不存在的 `/opt/s3-voice-webui/` 创建 root 私有文件、拉官方镜像 digest、启动两个**新**容器 | 初始只限 Docker 内网，无主机端口/无 Cloudflare 新路由；失败自动停止新项目 |
| `verify` | 只读验证新容器只读/网络、Owner 登录（合成账号）、A03/A04 容器 ID、内存/Swap、本地 403/401/200 | 不调用任何真实模型；不打印 Owner 密码或原设备身份 |
| `rollback` | 仅停止并删除 `s3-voice-webui` 新项目的两个容器；保留私有配置便于复盘 | 不触碰 A03/A04/tunnel/4B；即使此前另加 Cloudflare 入口，也必须单独撤销该入口 |

**生产启动前硬门槛**：不能通过只是 GitHub PASS 推断 SSH/VPS 环境可用。CI 须先在真正 Docker Runner **实跑** `stage→verify→rollback`，且有反向验证：模拟旧服务容器 ID 突变/Swap 增量超 64MiB 必须阻断；CIDR/外部 Docker 网络和临时文件权限必须正确。

### 生产时预期拓扑（当前还未建立）

```text
已有 A03 server (不重启)      原 A04 gateway (不重启)    已有 cloudflared (不重启)
       │                              │                         │
       │                         原 4B OTA/WSS                 │
       ├── Docker a03 网络 ───────────┤                         │
       │                              │                         │
       └── 新 Auth (96MiB 限制) ── 新 WebUI Caddy (96MiB 限制) ── front 网络
                                    │
                              暂无公网路由
```

新 Auth **仅连 A03 后端网络**；新 Caddy 连接前端和 A03；不得让外部访客访问 `auth` 的私有端口。初期模型配置 `models.json=[]`，不会因此产生 GPT/DeepSeek 的新 Token 费用。

### Secret、镜像和回退

- 服务私钥由 Python 标准库 `secrets` 在 VPS 本机生成并存入 `/opt/s3-voice-webui/private`（0700）；`auth.env`、`gateway.env`、`models.json` 各 0600。Owner Secret 独立于 4B、CF Access、GitHub、模型 API Key。终端摘要只显示 PASS/阻断码，**不打印密钥、设备 ID、原配置内容**。
- 固定官方 Caddy 2.11.7 + Python 3.13 Alpine 镜像实际 `RepoDigests`；不使用浮动生产 `latest`。vendor 的 libopus-wasm npm tarball 只在 staging 源码副本执行 SHA-256 校验，保留 MIT/BSD Notices。
- `/opt/s3-voice-webui/src` 是新的只读挂载代码副本，网关以 uid1000 运行并仅保留 `NET_BIND_SERVICE` Capability；原 A04 的生产配置从不复制、覆盖或重载。
- `rollback` 停止新项目 `s3-voice-webui`，**只删除其新容器，不删除私钥/源代码，不删除既有 Docker 外部网络**。如果实际 VPS 不是完全初始状态（目录或新容器同名已存在），自动 BLOCKED 而非覆盖。
- 初始 `MemAvailable` 至少 1.05GiB；**stage 启动后的自动验收**若低于该门槛或 Swap 增量超过 64MiB，立即回退两个新增容器。之后如管理员另行执行只读 `verify` 检测到资源超限，`verify` 只返回 BLOCKED，必须再执行 `rollback` 停止 WebUI；本版本没有后台持续监控，绝不虚称自动监控已经上线。P1 预检已 PASS，stage 会自行重新检查当时基线，不要求用户另跑一次相同命令。

### 下一步真实验收，不能由 GitHub Runner 替代

1. 验证 Ubuntu Runner 的实际新容器生命周期开关已全部通过，再由用户在已授权 VPS 上执行**固定提交 SHA**的受控脚本。由于 PR #39 未合并、P1 尚未实机验收，本文件当前不提供可直接运行的生产命令。
2. 真实隔离容器通过后，只有 Owner 可通过 Cloudflare 控制台在**现有 Tunnel** 上添加**新的独立主机名**到 `http://s3-voice-webui-gateway:8080`；不许修改原 4B 的 `voice.cncloudx.com`、TV 域名或 A04 入口。新主机名示例 `webvoice.cncloudx.com` 尚未实际创建。
3. 在 VPS root-only 文件设置有权使用的 GPT 和 DeepSeek API Key，逐模型开展低成本真实文字 SSE；Cloudflare Access 仅保护浏览器新域名，不作用于 4B。
4. iPhone Safari 在 HTTPS 下完成文字+麦克风授权、原始 Opus 连续 10 分钟以上、错误恢复和停止麦克风。真实 4B 连续回归 10 分钟；P3 A07 断音另行诊断。

### 验收证据等级

| 等级 | 当前含义 |
|---|---|
| 源码确认 | 不修改 A03/A04/4B；独立新容器与私有路径 |
| CI | 旧服务合成态 + 新服务真实 Docker 生命周期、资源失败门槛、SSH 子 Shell 退出行为单测 |
| 实际 VPS | **尚未执行**；镜像 Digest、真实 Docker 网络及 Swap 冷启动需另验 |
| iPhone/4B 实机 | **尚未执行**，不得据此增加 P1/P2 正式完成率 |

严格按原 GDGS：P0=10/10，P1=0/20，P2=0/25，项目整体 10/100。
