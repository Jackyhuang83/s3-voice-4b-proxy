# S3-Voice P1-3-R2 — 独立 WebUI 网关试点（零权重，无 A04 重启）

日期 2026-11-26。依据真实 VPS 返回 `WEBUI_P1_PREFLIGHT_PASS`，在安全基线下将之前的“修改原 A04 Caddyfile”改成“独立 WebUI Caddy + Auth”。这是一项 P1-3 的落地方式纠偏，不重新部署 A03、ASR、TTS、LLM，也不改动微雪 4B 固件。

## 方案变更及为什么

旧方案需要向正在运行的 A04 配置追加 /webui，并将新的 Gateway Secret 注入 Caddy 容器的环境变量。需要重新创建既有网关容器，有短暂 OTA/WSS 断开风险；且未经生产验证。更低风险路线是只新建两个独立边车，不动现有 A04 服务。

```text
                      已存在 Cloudflare Tunnel / cloudflared
                               |                 |
                    原设备主机名 / 4B       单独的 WebUI 主机名（未来新增）
                               |                 |
                      原 A04 Caddy         新 WebUI Caddy（无主机端口）
                               |                 |
                      原 A03 小智 WS <-----Auth Cookie/OTA broker（无主机端口）
```

新的 Caddy/鉴权容器共享现有 `s3-voice-ai-edge_front` 和 `s3-voice-ai_default` 两条外部 Docker 网络。现有 Tunnel 容器已经连接前者，因此通过 Cloudflare Dashboard **新增一个独立 Published application route** 可指向 `http://s3-voice-webui-gateway:8080`。官方多路由参考：https://developers.cloudflare.com/tunnel/concepts/routing/ 。禁止覆盖原有设备主机名或更改其源服务。

新 WebUI 的最终域名目前**尚未选择、DNS 未添加、Cloudflare 未变更**。实际使用时将域名设置为服务器 `S3_WEBUI_ORIGIN=https://<批准的实际主机名>`，Cloudflare Access 可选仅 Owner 邮箱；千万不能对原 4B OTA/WSS 加 Access 交互验证。

## 生产模板与边界

- `deploy/ai/webui/Caddyfile.isolated` 是**完整独立网关**，监听容器 8080，关闭请求路径日志，只允许 `/webui/*`；对 `/xiaozhi/*` 默认 403。不得把它复制进原 A04 Caddyfile。
- `deploy/ai/webui/docker-compose.isolated.example.yml` 有且只有 **auth + gateway 两个新服务**；二者只加入已存在的 external Docker 网络，不映射宿主机端口，CPU 各不超过 0.25，内存各 96MiB，文件系统只读。
- 私有 `/opt/s3-voice-webui/private/auth.env` 供 Auth 使用，含 Owner 密码/独立设备身份/网关密钥；`gateway.env` **只含网关密钥**，不含 Owner 密码或模型 Key。`models.json` 仅供 Auth 服务使用，不能让 Caddy、Cloudflare 或真实 4B 读取。
- 镜像 `WEBUI_PYTHON_IMAGE` 和 `WEBUI_CADDY_IMAGE` 必须在真实 VPS 验证后固定 digest；生产模板仍**不能直接 `docker compose up`**，它没有创建私有目录/模型凭据/实际主机名的安装逻辑。
- Cloudflare Tunnel 只是增加新主机名到新服务；**不重启旧 A04、不生成第二个 Cloudflare Tunnel Token、不改 4B NVS/OTA/WSS**。

## 自动化证据

- `tests/ai/test_webui_isolated_gateway.py` + 仅 Runner 使用的 `docker-compose.isolated.ci.yml` 在同一隔离网络里启动**两套独立 Caddy**：旧 A04 模板（生成虚构路径/身份），新 WebUI 网关、Auth 和假 A03。
- 分别验证原 A04 正确 OTA 200/WS 101，错误身份 403；新 WebUI Owner 登录/WS 101，Guest/伪造头/跨网关路径不被放行。只证明合成环境，不是假装用户 4B 已实测。
- CI 检查正式模板无新增端口、只读、外部网络、固定镜像 digest、服务和私有环境文件相互隔离。旧的 A04 生产文件在 PR 中必须完全不被修改。

## 真正上 VPS 前还必须完成

1. 真实预检已经 PASS，但仍需确认现在 VPS 的有效 Cloudflare Tunnel 是当前 A04 的 `s3-voice-ai-tunnel`，且其 front 网络与新网关容器 DNS 可达。先读状态，不改原 Tunnel。
2. 获取并锁定两个镜像实际 digest，核对新增 192MiB 容器内存上限与已有 A03/A04/RAM/Swap 余量；Owner 密钥和模型参数只在本机 root 私有目录生成或导入，不写日志和 GitHub。
3. 先在独立私有试点路径启动新两容器并验证本地授权/模型 SSE；**没有回退镜像/配置/停止命令的验收不允许公开域名**。测试前后 4B 通道的 OTA/WS 要保持正常。
4. 通过后才在 Cloudflare Dashboard 给**原有 Tunnel 增加新主机名映射**；该动作也需要验证 Cloudflare 未修改原设备映射。关闭 WebUI 时可独立撤销新路由、停止新两容器；无需触碰 A04。
5. 在 iPhone Safari 验证真实 HTTPS、Owner 登录、GPT/DeepSeek 流式文字；P2 的语音和 P3 的 4B 断音仍未验收。

**本 PR 是新增隔离架构及 CI 验证，不执行生产部署，也不代表 P1=100%。** 正式进度仍 P0 100%、P1 0%、项目 10%，除非真实部署/浏览器/回退全部通过。

参考官方 Caddy `forward_auth`：https://caddyserver.com/docs/caddyfile/directives/forward_auth 及 Docker Compose external networks：https://docs.docker.com/compose/how-tos/networking/
