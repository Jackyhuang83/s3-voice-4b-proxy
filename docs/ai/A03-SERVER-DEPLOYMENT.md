# S3-Voice-AI A03 — XiaoZhi server v0.9.8, isolated staging and rollback

**Workstream:** AI server; A01=#21 MERGED; A02=#22 MERGED; P0 100% / overall 10%. A03=18% project weight, contingent on the target Debian 13 VPS actually running the service and all tests passing.  
**Version:** Official upstream `xinnan-tech/xiaozhi-esp32-server` release `v0.9.8` (`8f2dda09cf18f1c1ece0f906eee4cc2fabb7fb58`). Its official [Docker publication workflow](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/.github/workflows/docker-image.yml) publishes immutable release *tag* `server_0.9.8`. The official [GitHub Package Versions](https://github.com/xinnan-tech/xiaozhi-esp32-server/pkgs/container/xiaozhi-esp32-server/versions) shows `server_0.9.8` digest `sha256:cd41415f887410080dc2424b5faef651373c72fba37b3979d28e90ee548181af`. Installation **pulls only this literal immutable digest and verifies its RepoDigest**, records it in a private `.env`, then deploys by digest. No mutable `server_latest` or tag resolution at installation time.

## 1. Design acceptance (A03 vs A04/A05)

| Scope | A03 delivers | Still not accepted |
|---|---|---|
| App server | Existing upstream Python image, no code changes to ESP32 or backend; Docker Compose separate project `s3-voice-ai` | Live target host deployment until user executes approved install |
| Data/config | `/opt/s3-voice-ai`, root-only `data/.config.yaml` (generated random local auth secret); separate `/var/backups/s3-voice-ai` | Real paid API keys (A05), public auth (A04) |
| Isolation | 127.0.0.1:18000→WS 8000, 127.0.0.1:18003→OTA 8003; Docker Engine 29+ guard; 1 CPU/1024 MiB/pids 256, default seccomp; no published IPv6 or 0.0.0.0 sockets | Tunnel and dedicated public ingress on 18080 (A04) |
| Voice components | Reuse Silero VAD, OpenAI-format cloud ASR, DeepSeek LLM, Edge TTS. A03 placeholder *invalid* keys deliberately mean voice API is **not usable** until A05 | GPT/Gemini/DeepSeek real API requests, ASR/TTS stream and hardware test |
| OTA | Health GET plus synthetic device POST; must return websocket configuration, no MQTT, **firmware.url == ""** | Actual device/WSS routing and authorization (A04 and A07) |
| Recovery | `rollback` stops only `s3-voice-ai-server`, leaves private app files and backup intact | Original R1/R2 firmware never changed |

This is **local staging only**. Device enrollment and paid-model public access must not be enabled until A04 secure ingress tests. The single-server upstream OTA's `allowed_devices` is NOT a strict admission list, so `server.auth.enabled: true` is not permission to expose its ports.

## 2. Firewall & port contract (explicit request)

| Direction | Protocol | Port | Need VPS PUBLIC inbound firewall change? |
|---|---|---|---|
| Host loopback | TCP | 18000 | **NO**: local XiaoZhi WS |
| Host loopback | TCP | 18003 | **NO**: local OTA |
| Future host loopback | TCP | 18080 | **NO**: future Caddy gate, NOT started in A03 |
| Future Tunnel egress | UDP 7844 QUIC OR TCP 7844 HTTP/2 | 7844 | **Outbound only**, confirm in A04 |
| Existing public 443 | TCP | 443 | **NO CHANGE**: currently owned by existing Caddy |

Cloudflare Tunnel makes outbound connections only; do not add inbound 7844, 18000, 18003 or 18080 firewall rules. No Cloudflare Tunnel/DNS/public hostname installed by A03. Docker loopback publishing is supported with Docker 28+; the user's recorded Engine 29.9.3 meets this.

Official docs: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/ and https://docs.docker.com/engine/network/port-publishing/

## 3. Automated deployment entrypoints

Reviewed files:
- `deploy/ai/a03/docker-compose.yml`: local image by SHA256 digest, scoped resource limits, no seccomp override, no new privileged flags.
- `tools/ai/a03-server.sh`: `preflight`, `install`, `status`, `rollback`.

The script refuses any installation when port 18000/18003/**reserved future 18080** is already listening, insufficient free RAM (<1,300,000 KiB) or disk (<6 GiB), Docker inaccessible/older than 28, or `/opt/s3-voice-ai` already exists. Repeated installation does **not** overwrite state. No firewall, DNS, existing Caddy or other Docker Compose project is touched. Current A02 host snapshot passed these planning thresholds; A03 rechecks at execution time.

**One controlled invocation on the actual Debian 13 VPS**, after reviewing PR and confirming the branch commit:

~~~bash
git clone --depth 1 --branch ai/p1-a03-isolated-server-20261122 \
  https://github.com/Jackyhuang83/s3-voice-4b-proxy.git \
  /tmp/s3-voice-a03-src \
  && cd /tmp/s3-voice-a03-src \
  && sudo bash tools/ai/a03-server.sh install
~~~

This invokes Docker and starts a **new local-only** server, so it is deliberately not part of A02. It downloads the official image **by published digest**; no Node or ESP firmware build on VPS. Copy just the last `A03_OK` lines or the non-sensitive failure lines for acceptance, **not raw Docker logs** (they may contain IDs). No API keys/real device identifiers needed.

To verify or stop independently:

~~~bash
cd /tmp/s3-voice-a03-src
sudo bash tools/ai/a03-server.sh status
sudo bash tools/ai/a03-server.sh rollback
~~~

The rollback command stops only the new service, leaving the original HomeSphere/MiniProbe/Caddy/SSH ports unchanged. It preserves data so recoverability remains possible and does not delete Docker objects.

## 4. Source reuse and startup constraints

- Official xiaozhi-server Dockerfile-server uses the already published `server-base` and copies the exact application source for release builds. No new image build is required on the user VPS.
- `config/config_loader.py` requires `data/.config.yaml`; A03 writes a minimal override, merges with upstream defaults and chooses remote ASR to avoid the large SenseVoiceSmall `model.pt` mount. The initial keys are explicitly nonfunctional placeholders.
- An upstream server may initialize a small VAD model at startup; max 1024 MiB prevents it from consuming the entire shared VPS. If startup exhausts the cap, A03 fails without changing the original workloads. Do not silently remove the cap.
- The OTA GET is merely a health probe. A03 sends a **synthetic** OTA POST with `Device-Id`/`Client-Id`, verifies `websocket.url` is loopback, JWT token present, `mqtt` absent, and empty firmware update URL. No hardware/flashing performed.
- The data/bin directory is created empty; A03 smoke checks no firmware .bin is present to prevent unintended automatic update. A04 later denies firmware download routes at public ingress.

## 5. Evidence-level checklist

| Evidence | Requirement | Result |
|---|---|---|
| Official source / image tagged release | Pinned v0.9.8 tag, published package digest and upstream publishing workflow | SOURCE VERIFIED |
| Port / resource / rollback design | Static Compose and script checks | **PASS — GitHub CI** |
| CI ephemeral Docker image start and OTA contract | Dedicated `S3-Voice-AI A03 local server smoke` | **PASS — GitHub CI, including CI rollback** |
| **Actual target VPS local server running** | Target root Shell output from reviewed install script: container Started; OTA GET/POST PASS; official pinned image | **PASS — user-supplied live host output** |
| User HomeSphere/MiniProbe unchanged in running-container snapshot | Installer compares known container names before/after | **PASS — installer reached final success; full app health not separately tested** |
| Public WSS / device auth / cloud billing | A04/A05, not included | **NOT RUN** |
| Real Waveshare 4B voice dialog | A07, not included | **NOT RUN** |

**A03 target-host staging deployed:** CI on prior head was 12/12 PASS, and the target VPS install and OTA contract are now verified. This documentation change must pass its **new final HEAD CI** before A03 PR #23 may merge. Only after merge should A03 +18% be counted (P0=100%, P1=60%, P2/P3=0%, project=28%). Actual host rollback was NOT requested or run; its behavior was tested in CI. No public WSS or real paid-model/hardware validation has been performed.


## 6. Target Debian 13 VPS live install evidence

User supplied terminal output from the reviewed `bash tools/ai/a03-server.sh install` on the host previously inventoried by A02 (Debian 13/x86_64, 2 cores, Docker 29.9.3). Output included:

```text
[+] up 2/2
Network s3-voice-ai_default Created
Container s3-voice-ai-server Started
A03_OK: OTA GET/POST smoke PASS; MQTT absent; firmware.url empty; WebSocket config loopback-only
A03_OK: real device + paid API calls NOT tested (A04 / A05 / A07)
A03_OK: installed official server_0.9.8 pinned digest, with 1024 MiB and 1 CPU cap; private backup created
A03_OK: no firewall changes, no Cloudflare Tunnel, no original Docker services touched
```

**Evidence boundary:** Source code establishes that the final `A03_OK` message is printed only after `check_local` and comparison of the existing known running containers. Real OTA POST smoke with a **synthetic** device identifier was run. No actual Waveshare 4B was connected, no new public TCP/UDP ingress allowed, no provider API credential used, no independent HomeSphere/MiniProbe HTTP functional probe performed. Running containers are not equivalent to functional app test. Service availability may change after the snapshot; A04 must recheck before introducing Tunnel ingress. The CLI did not output the private full image digest but used the literal pinned digest from the reviewed installer.
