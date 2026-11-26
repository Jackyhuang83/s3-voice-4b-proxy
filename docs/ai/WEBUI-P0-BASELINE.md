# S3-Voice WebUI P0-1 — 仓库基线与继承资产审计

**审计日期：** 2026-11-26
**证据类型：** GitHub 源码、PR 状态、公开工作流结果 + 既有项目历史；**未接触当前 VPS、iPhone 或 4B**。
**冻结基准：** `main` = `992c2d0d06f384c817dbc73acfeb2b37068bd859`（2026-11-25，合入 A09-Lite）。以后 PR 必须记录其 base/head，不能声称实时 VPS 状态与仓库完全一致。

## 1. 逐项状态矩阵

| 项目 | 仓库中真实存在的基线 | 达到哪一级？ | 尚未通过什么？ |
|---|---|---|---|
| A03 | `tools/ai/a03-server.sh`、`deploy/ai/a03/`、A03 文档、历史服务器试点 | 既有源码/CI；历史 VPS 本地 OTA/服务测试 | 未在本 P0 重新查询今天服务器 |
| A04 | `tools/ai/a04-edge.sh`、`deploy/ai/a04/`；隔离 Caddy、Cloudflare 规则 | 既有源码/CI；历史 HTTPS/WSS 真实校验 | 真实生产 Caddyfile/设备入口尚未本轮复核 |
| A05 | `tools/ai/a05-generic.sh`、`a05-config.py`；标准兼容 LLM | 既有源码/CI；历史真实 API 流式 | WebUI 模型切换、文字-only API 尚不存在 |
| A06 | `tools/ai/a06-voice.sh`、`a06-config.py`；VoskASR + EdgeTTS | 既有源码/CI；历史 VPS 语音链路 | EdgeTTS 持续可用性不可保证；4B 音频稳定性尚未通过 |
| A07 | [PR #27](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/27) **Draft/未合并**；原生 `tts_audio_send_delay: 60` 试验脚本在 PR 分支 | 特定 CI/源码测试可用；存在历史 4B 实机记录 | 句中停顿/断音根因和真实 4B A/B 修复结果未证实 |
| A09 Manager | [PR #28](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/28) **Draft/未合并** | 资源安全预检能阻断失败 | Swap 压力、Manager 实装未通过；禁止在当前 VPS 强行部署 |
| A09 Lite | [PR #29](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/29) **已合并**，`tools/ai/a09_lite.py` + SQLite 兼容层及测试 | P1 本地/CI 测试通过 | 真实六位码设备 OTA/绑定未通过 |
| A09 iOS 入口 | [PR #30](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/30) **Draft/未合并**，隔离 Caddy 路由/安装器/测试 | PR 专用 CI 通过 | 浏览器 OTA/WSS、实际 iPhone 和原 4B 回归均未通过 |
| WebUI | main 无独立 WebUI 页面或静态站点 | **未开发** | 所有 WebUI 文字/语音/集成测试 |

A07 的真实用户问题是“同一句话说到一半停住，随后又继续”，不得与整句 GPT->TTS 的延迟混为一谈。官方 v0.9.8 的 `tts_audio_send_delay` 有现成调节参数，但目前没有针对这块 4B 的稳定性验证。

## 2. 现有 CI 证据及遗留风险

- `main` 提交 `992c2d0` 的 GitHub Actions 执行结果中，原 R1/R2 的 **P1 upstream TCP engine source-quality gate** 和 **P0 pinned upstream ESP32-S3 R8N16 build** 为 `failure`；不是“仓库 CI 全绿”。
- 同一提交的其他多数 R1/R2 代理类工作流通过；其结果**与 WebUI 音频功能无关**。
- PR #29 专用 A09-Lite CI 成功；PR #30 专用 A09-Lite P2 CI 成功；两者不代表实际 iPhone 硬件已经完成语音。
- P0 新增仅针对 WebUI 文档/路径的专用 CI：不得修改旧 R1/R2 源码/工作流；原工作流失败保留为独立风险项。**旧失败需在原有代码工作线定位，不为它追加本 WebUI 阶段的功能 PR。**

## 3. 资源与回退基准

- A02 旧资源快照（2026-11-22）属于历史证据：3,753,804 KiB RAM，2,145,920 KiB MemAvailable；当时 18000/18003/18080 无监听。部署后状态必然已改变，不可重新当作当前空闲数据。
- 2026-11-24 的人工读数显示 3.6GiB RAM、约 1.5GiB MemAvailable、Swap 已使用、HomeSphere/MiniProbe 等容器同机；A09 Manager-Only 因 Swap 压力被自动停止。
- WebUI P1/P2 不直接修改 `/opt/s3-voice-ai`、`/opt/s3-voice-ai-edge`、`/etc/s3-voice-ai`、`/var/backups/s3-voice-ai`，除非经过单独预检和变更/回滚方案；不将现有私有凭据导入仓库。
- 保留微雪 4B 原厂完整 16MB 备份；不得用新页面功能作为刷固件、清 NVS 的理由。
- 静态资源首选同域 HTTPS/Caddy，WebUI 浏览器身份必须独立于无交互 ESP32 4B；真实入站资源、Caddyfile 和 Cloudflare 路由只在后续 P1 试点前审查。

## 4. 本 PR 的真实验收边界

| 门槛 | 可在本 PR 达到？ | 后续阻断事项 |
|---|---|---|
| 现有 GitHub 文件/PR/CI 来源核对 | 是 | 仅归档仓库证据 |
| 12 PR / 100 点规划锁定 | 是 | 后续重大范围变更先改路线图 |
| 文档/路径范围 CI | 是，待本 PR Actions 实际结果 | 专用 CI 不等于全仓库 CI |
| 当前 VPS 只读实际数据 | 否 | P1-1 部署前要确认新资源与生产配置 |
| iPhone/4B 功能验证 | 否 | P2/P3/P4 真机验收 |

**P0-1 只能在本 PR 合并且专用 CI 通过后记 5/100；未确认实时 VPS 资源必须显式留下部署门槛。** 本 PR 不包含生产安装、Caddy 改写、设备变更或付费 API 调用。

## 5. 关联规划

完整阶段权重、PR 数量、依赖、验收及成本约束：见 [WEBUI-ROADMAP.md](WEBUI-ROADMAP.md)。
