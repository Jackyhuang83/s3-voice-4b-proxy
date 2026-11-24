# S3-Voice A09 — Manager-Only pilot (2026-11-25)

> This retains the original filename for PR #28 traceability. The **full-module parallel-server proposal was superseded** after the existing VPS failed the 4GB physical-RAM guard. This revision contains **no second Python voice server**.

## Scope and safety baseline

- Existing production: official `xiaozhi-server v0.9.8` (A03), A04 Caddy/Tunnel, A07 Waveshare 4B; GPT/Vosk/EdgeTTS, `voice.cncloudx.com`, HomeSphere and MiniProbe **must not be modified or restarted**.
- New pilot: one isolated official `web_0.9.8` image (manager-api and manager-web), plus pinned MySQL 8.4 and Redis 8.0. No duplicate `xiaozhi-server` container, no extra 8000/8003 listeners, no model files or API keys.
- Manager code handles six-digit `activation.code`, `POST /ota/activate` returning 202 before binding and 200 after binding, and stock management-console device binding; MySQL stores permanent binding and Redis stores pending code.
- Only one public route exists now: **the existing 4B route**. Manager listens solely on `127.0.0.1:19002` until P2. Admin access through owner-controlled SSH tunnel only; no Cloudflare registration or admin UI exposure.
- The manager's stock HMAC-SHA256 signing routine matches the existing Python server's `AuthManager` *when the manager's `server.secret` equals the server's `server.auth_key` and Device-Id/Client-Id match*. This source-code parity is necessary but **not sufficient** to claim a real iPhone connection.
- The manager does **not** become the production voice configuration source. The existing server continues using its file-based `.config.yaml`, preserving GPT/Vosk/EdgeTTS and existing hardware.

## Revised P0–P2 plan (weights unchanged; the PR budget is the logical work-plan)

| Phase | Weight | Logical PR work packages | Dependency | Acceptance |
|---|---:|---|---|---|
| P0 official-reuse audit & readonly resource preflight | **25%** | P0-1 official activation/HMAC architecture audit **12.5%**; P0-2 readonly 3.6GiB VPS guard **12.5%** | Existing 4B healthy | Official sources confirmed and actual on-host `A09_PREFLIGHT_PASS`, with no changes |
| P1 isolated Manager-Only pilot | **40%** | P1-1 pinned 3-service Compose/isolated installer **20%**; P1-2 six-digit OTA, memory/swap and rollback **20%** | P0 passes | New manager+MySQL+Redis healthy with original container IDs unchanged, OTA 200+six digits+token, `/ota/activate` 202; resident memory and swap within guards |
| P2 original-voice linkage & real iPhone | **35%** | P2-1 explicit production-key HMAC parity bridge **17.5%**; P2-2 separately scoped public OTA + iPhone binding/voice/rollback **17.5%** | P1 passes | New manager token verified against existing voice key, public isolated OTA 200, binding 202→200, WebSocket 101, actual iPhone audio PASS and existing 4B still works |

Dedicated GitHub CI now starts the three stock containers on a disposable runner, waits for the real Java OTA and `sys_params` schema, and checks six-digit/Token/202 behavior; **CI is not production VPS installation**. A previous Docker run exposed a race where the static manager-web homepage returned HTTP 200 before Liquibase created `sys_params`; readyness now requires the Java OTA and schema. CI cleanup is confined to the disposable runner.

Code may be consolidated in **existing PR #28** to minimize PR churn. CI source/static checks do not complete a phase. The last actual deployment attempt correctly ended `A09_BLOCKED` before downloads or filesystem changes; progress must remain at the P0 read-only preflight gate until retested.

## Actual resource baseline and fail-closed limits

Measured on existing shared VPS (owner read-only output, 2026-11-25):
- `MemTotal` about **3.6GiB**, `MemAvailable` about **1.5GiB**, swap in use **103MiB** (1GiB configured); disk free **34GB**.
- Current S3 voice server about **473MiB**. HomeSphere, MiniProbe and all other services remain operational.
- Three **new container memory ceilings**, not measured usage: MySQL **384MiB**, Redis **96MiB**, Java manager/API/Web **640MiB**; total cap **1,120MiB**. JVM heap capped at 320MiB; MySQL InnoDB pool at 96MiB. These limits may cause a new pilot service to fail; this is preferable to OOM-killing the existing workload.
- A09 `preflight` is **read-only**, requiring >=3,400,000 KiB physical RAM, >=1,400,000 KiB available RAM (~1.34GiB), >=5GiB free disk, Docker Engine >=28 and free TCP 19002. It checks old containers and OTA health before pulling images or writing files.
- After new containers start, A09 aborts and **stops only the pilot** if `MemAvailable < 650,000 KiB` (~635MiB), or swap usage has risen >128MiB over the baseline; it also checks original production container IDs. Resource limits protect against worst-case memory claims but do not guarantee zero host interference. **Never increase Swap or weaken limits simply to force installation.**
- No Docker global settings, firewall, SSH, Cloudflare or production config changes.

## Execution modes and acceptance gates

From the reviewed checkout on the **existing** Debian 13 VPS:

```bash
sudo bash tools/ai/a09-fullmodule.sh preflight   # readonly, can still block
sudo bash tools/ai/a09-fullmodule.sh install     # only after code+CI review and preflight PASS
sudo bash tools/ai/a09-fullmodule.sh status
sudo bash tools/ai/a09-fullmodule.sh bridge      # P2 only; deliberate separate operation
sudo bash tools/ai/a09-fullmodule.sh bridge-rollback
sudo bash tools/ai/a09-fullmodule.sh stop
```

The script retains its historical filename `a09-fullmodule.sh` to avoid diverging PR history; **it no longer installs a second full voice stack**. Installation creates `/opt/s3-voice-manager` (0700), root-only `.env` (0600) and private database directories; the only host-published service is `127.0.0.1:19002` on a dedicated Docker network. It pins all three images to digests after pulling exact version tags. No new service can bind a public IP.

**Gate A09-P1:** The default manager WebSocket target is deliberately `wss://manager-only-not-ready.invalid/xiaozhi/v1/` so an untested iPhone cannot accidentally talk to the old 4B service. Isolated local synthetic OTA confirms `activation.code` is a six-digit decimal, `websocket.token` exists, and `/ota/activate` returns 202 for unbound devices. This neither exercises AI nor proves real-device binding.

**Manager configuration cache:** Official `SysParamsRedis` stores system parameters in Redis hash `sys:params`; direct updates to the isolated manager database must invalidate only `server.secret`, `server.websocket`, `server.ota`, and `server.auth.enabled` fields via `HDEL`. No `FLUSHALL` or production cache operations are permitted. The bridge runs manager restart+HMAC acceptance after selective invalidation.

**Gate A09-P2:** `bridge` is explicit and reads the production `server.auth_key`, configured WSS URL and Caddy bearer from root-only existing files. It requires the configured WSS path to match the existing private 256-bit bearer and writes **only** the isolated management DB's `server.secret` and `server.websocket`. A Python HMAC check verifies that manager-issued tokens match the unchanged production server key. It does not change any production file, restart an existing container or open a public port. `bridge-rollback` restores the manager-generated secret and disabled WSS target, leaving voice untouched. Keep the pilot admin page private: its system parameter page may contain the production auth secret.

**Real iPhone acceptance still requires a separate, new, bearer-protected Caddy OTA route to Manager**; this must not replace the original 4B OTA route. The Hi 小智 client's exact OTA request and WebSocket behavior remains unverified. Use a separately scoped route and verify public 200, six digits, token, activation 202→200, WS 101, and a real voice conversation before acceptance.

## Official evidence

- Pinned official manager OTA: `main/manager-api/src/main/java/xiaozhi/modules/device/controller/OTAController.java`
- Pinned device activation/token logic: `main/manager-api/src/main/java/xiaozhi/modules/device/service/impl/DeviceServiceImpl.java`
- Pinned Python HMAC verifier: `main/xiaozhi-server/core/auth.py`
- Official Docker full example (used as source reference, **not installed**): https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/docker-compose_all.yml
- Existing production A03/A04 deployment scripts in this repository remain unchanged.

## Rollback and status discipline

- Preflight failure: zero installation changes.
- Installation failure: stop pilot containers, preserve private data and original running services; do not claim P1 PASS.
- `stop`: stop only `manager`, `mysql`, `redis`, preserve data; restart/manual cleanup only after diagnosis.
- `bridge-rollback`: revert only manager DB credentials and URL.
- Original 4B OTA/WSS and real audible response remain independent acceptance checks. No firmware flash or OTA firmware download is involved.
