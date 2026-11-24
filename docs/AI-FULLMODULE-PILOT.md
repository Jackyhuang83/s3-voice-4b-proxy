# S3-Voice A09: Official full-module pilot (2026-11-24)

## Scope and immutable baseline

Preserve the existing XiaoZhi v0.9.8 A03/A04/A07 deployment and physical Waveshare ESP32-S3 4B. Do not reset, flash or migrate it. The pilot uses a separate Docker Compose project, network, database, credentials and root-owned files under `/opt/s3-voice-fullpilot`. A09 is optional; its goal is to establish whether the *Hi XiaoZhi* iOS application can use stock six-digit activation.

## Roadmap (weights fixed before deployment)

| Stage | Weight | Planned PRs | Dependencies | Acceptance |
|---|---:|---|---|---|
| P0 Audit and readonly preflight | 25% | P0-1 audit and roadmap (12.5%), P0-2 resource preflight (12.5%) | Stable A03/A04/A07 | Official source contract confirmed; target VPS resources and ports checked without changes |
| P1 Parallel full-module install | 40% | P1-1 pinned Compose/installer (20%), P1-2 isolated health/rollback (20%) | P0 | Official manager, server, MySQL, Redis locally healthy; six-digit activation.code and WebSocket token returned; old container IDs unchanged |
| P2 iPhone activation | 35% | P2-1 scoped public pilot OTA/WS (17.5%), P2-2 bind/voice/rollback (17.5%) | P1 | Public 200 + six-digit code/token; unbound activate 202, bound activate 200, WS 101, real iPhone microphone/GPT/speaker PASS |

Code review or CI green alone does not complete a phase. Live acceptance must be reported separately.

## Official implementation reused

- Official repository: https://github.com/xinnan-tech/xiaozhi-esp32-server
- Official full Docker scheme: https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/docs/Deployment_all.md
- Official OTA: `main/manager-api/src/main/java/xiaozhi/modules/device/controller/OTAController.java`
- Official activation: `main/manager-api/src/main/java/xiaozhi/modules/device/service/impl/DeviceServiceImpl.java`
- Official manager API issues `activation.code` and uses Redis plus the stock manager-web UI to bind devices. The `server.secret` in the isolated manager database is used for the pilot's server config.
- Upstream `docker-compose_all.yml` is *not* directly deployable to a shared production VPS: it contains public port publishes, mutable `latest` tags and a default database password. A09 resolves release v0.9.8 image tags to digests, creates its own password, caps resources, and binds TCP ports exclusively to 127.0.0.1.

## Deployment host decision (2026-11-25)

**Observed:** Existing S3-Voice VPS returned `A09_BLOCKED: less than ~4GB physical RAM`. This is a correctly enforced safety stop **before image downloads, directory creation or container changes**. Do not bypass by forcing limits/swap. P0 actual-vps resource gate is **BLOCKED**, not passed.

**Plan revision:** Keep the original A03/A04/A07 4B VPS unchanged. Prefer an **independent x86_64 VPS with >=4 GB physical RAM, >=2.3 GiB available RAM, >=10 GiB free disk and Docker Engine >=28**. If no such host exists, pause A09 instead of buying a server for activation alone; an open-source/updated iOS client is a less invasive alternative. P0/P1/P2 acceptance weights and PR budget remain unchanged; only the host placement is revised.

On an independent host use `preflight-remote` and `install-remote`. Remote mode **rejects any pre-existing `s3-voice-ai-{server,gateway,tunnel}` containers** and otherwise uses the same resource, loopback port, image and credentials guards. It never reaches the original VPS or attempts to migrate it. Production-host `preflight`/`install` still require all three existing containers to be running and are intentionally blocked on the undersized VPS.

## Local-only pilot

```bash
sudo bash tools/ai/a09-fullmodule.sh preflight-remote   # on independent VPS
sudo bash tools/ai/a09-fullmodule.sh install-remote     # on independent VPS
sudo bash tools/ai/a09-fullmodule.sh status
sudo bash tools/ai/a09-fullmodule.sh stop
```

The installer preflight requires x86_64, Docker Engine 28+, either the unchanged existing A03/A04/Tunnel baseline (cohost mode) or absence of all S3-Voice production containers (remote mode), >~4GB total RAM, >=~2.3GiB MemAvailable, >=10GiB free disk, and free 19000/19002/19003 loopback TCP ports. It stops rather than resizing or disabling old services. Production server, gateway, tunnel, GPT/Vosk/EdgeTTS configuration and firmware remain intact. This pilot is strictly local-only until P2; do not copy the existing 4B's private OTA path or AI credentials.

Pilot UI is loopback `127.0.0.1:19002`; pilot WebSocket `127.0.0.1:19000`; pilot health `127.0.0.1:19003`. Use an SSH tunnel from a Mac for the stock manager-web admin registration. It is deliberately **not** exposed through Cloudflare during P1.

P2 requires an isolated public hostname/strongly authenticated path and a safe OTA/WS routing rule; never expose the admin signup publicly, never reuse the current 4B private bearer path, and never paste manager or AI secrets in chat. The stock pilot's default models do not automatically inherit production GPT/Vosk/EdgeTTS.

Stop the pilot using the provided `stop` action; it does not delete its data or alter the original 4B. P2 requires actual iPhone confirmation before any production change.