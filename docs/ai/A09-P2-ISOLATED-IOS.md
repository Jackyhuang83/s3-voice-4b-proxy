# S3-Voice A09-Lite P2 — Hi 小智 iOS isolated gateway

**Phase status: P2 BLOCKED until read-only real-host preflight, isolated pilot, real public Hi 小智 registration and actual audible speech.** P0 (20%) + P1 (50%) accepted based on source and CI; P2 is 30% and remains unaccepted even if new source CI is green. Original A09 Manager-Only PR #28 remains Draft and stopped.

## Purpose / reasons for two tiny containers

- Reuse existing official Python `xiaozhi-server v0.9.8`, GPT, Vosk and EdgeTTS. No second server, no Java/MySQL/Redis or model downloads.
- A09-Lite Python stdlib container generates six digits, stores owner-approved bindings in SQLite and proxies existing OTA signed HMAC tokens. A **second tiny, separate Caddy gateway** internally enforces the iPhone policy while the public hostname remains the existing `voice.cncloudx.com`. It uses the exact Caddy image currently already deployed for the 4B gateway (no new Caddy image pull).
- Both new containers publish **zero host ports**. Python memory cap **128 MiB**, Caddy **96 MiB**; total cap **224 MiB**, not predicted measured RSS. Both `restart: no`. Python has an internal network path to existing Docker `s3-voice-ai-server:8003` for OTA; Caddy reaches existing `s3-voice-ai-server:8000` for WSS; the original 4B container images and Cloudflare connector are unchanged; a strictly scoped A04 Caddy config hot reload extends two exact A09 secret paths and activation polling without restarting 4B.
- The new Caddy joins existing `s3-voice-ai-edge_front`. The preexisting `voice.cncloudx.com → http://gateway:8080` Cloudflare route and its connector stay unchanged. `tools/ai/a09-same-host.sh apply` inserts an exact iPhone path forwarder into the original A04 Caddyfile, after private backup and config validation, then hot-reloads the same Caddy process. No new Cloudflare DNS, hostname, route, connector or container image.

## Official source / security compatibility

- Official `v0.9.8` Java `OTAController.java` returns 202 before a device is bound and 200 afterward, `DeviceServiceImpl.buildActivation` emits activation code/message/challenge. A09-Lite P1 implements this compatibility contract with owner-only SQLite instead of Redis + user/agent admin modules.
- Official Python OTA `ota_handler.py` issues real signed HMAC tokens; this adapter passes them through unchanged, only changes its public WSS URL and adds an activation field. Existing real WS `AuthManager.verify_token` checks the forwarded Authorization, Device-Id and Client-Id. No bypass, no token forgery, no 4B change.
- Caddy v2 official `forward_auth` gates *before* reverse_proxy to A03 WSS. The adapter requires an exact approved Device-Id/Client-Id pair; token is also checked by original A03. A new 256-bit secret protects the dedicated OTA and WS URL. `POST /xiaozhi/ota/activate` on dedicated hostname only reports 202/200 (no approval action, no secret/token or user data); every other unspecified URL returns 403. Public `/internal/authorize-ws`, `/health`, and `/approve` are always denied.
- The App's actual activation polling path is **not yet verified**. The gateway provides official `/xiaozhi/ota/activate` and never invents Hi 小智 App behavior. If the App expects a different URL or additional payload, stop, inspect actual owner-approved redacted trace and amend the draft PR; never weaken owner approval.
- Important: 6-digit codes alone do **not** grant access; no automatic binding, no public management UI, no exposure of the six digits or private bearer URL in chat/CI logs. DB is owner/UID10001-only, Caddyfile is readable only within new private 0700 host dir, and HTTP logging discards request URI, authorization and device headers. The route secret is not hardware-backed authentication; keep it private.

## Locked P0–P2 roadmap (GDGS)

| Stage | Weight | Logical PR | Dependency | Acceptance |
|---|---:|---|---|---|
| P0 protocol/current-state audit | 20% | source review, no PR | existing A03–A07 | official code and prior multi-device checks confirmed |
| P1 activation state machine | 50% | PR #29, merged | P0 | Python SQLite 11/11 + GitHub Actions; accepted, not yet deployed |
| P2 same-host iPhone adapter, real host and device | 30% | P2-1 (one PR) | P1 | new Docker Caddy/OTA gates CI; real host preflight; no 4B restart/change; measured memory/swap; existing CF hostname path routing with reversible Caddy reload; Hi 小智 real OTA/202→200/WS101/Opus audible; original 4B regression; exact scoped stop and rollback |

The P2 source/CI PR **may merge after independent CI** because no host files change merely by merging. P2 stays 0% until live/private end-to-end conditions are measured and accepted.

## No-touch real-host preflight (read-only)

From reviewed GitHub checkout on the *existing* Debian 13 x86_64 VPS:

```bash
sudo bash tools/ai/a09-lite-deploy.sh preflight
```

This checks the real A03/A04 containers, their default-deny HTTP 403, OTA GET 200, Docker networks, RAM available >=1.34 GiB, disk >=5 GiB, and **no pre-existing A09-Lite path**. No image pull, no directory creation, no service restart; no old Manager-Only installation command is used. If any condition fails, STOP and preserve the status output, without deleting any existing pilot data or resetting swap. It does not assume the GitHub A04 template matches the current on-host Caddyfile. The private A04 Caddyfile should be reviewed on-host if actual prior multi-device changes are in use; never print secret paths or credentials.

## Isolated pilot only after read-only preflight PASS

```bash
# Only after separate CI review and resource preflight PASS:
sudo bash tools/ai/a09-lite-deploy.sh install
sudo bash tools/ai/a09-lite-deploy.sh status
```

`install` resolves a digest-pinned official Python slim image, reuses the existing Caddy image digest, builds private `/opt/s3-voice-a09-lite` and SQLite owned by UID 10001, generates a distinct 256-bit capability, starts only adapter/gateway and tests default deny. It does not add public host ports. If startup fails, it stops **only** two new services; private backup/data remains for diagnosis. A post-start hard guard stops the pilot if MemAvailable below ~1.05 GiB or Swap use rises by more than **64 MiB**, or original 4B/gateway/tunnel fail health/identity checks. Never bypass this gate or increase swap merely to install.

**Same-host owner action** after the isolated pilot and current-head CI PASS: use `sudo bash tools/ai/a09-same-host.sh apply`. It validates the current A04 bind mount and 4B secret, writes private backups, changes only the new A09 adapter's advertised hostname to `voice.cncloudx.com`, and gracefully reloads the original Caddy to forward *only* A09's exact secret OTA/WS paths and 202→200 activation poll. It automatically tests local and real Cloudflare public OTA (200, six digits, HMAC, correct WSS) and restores the exact original A04 Caddy config and A09 environment on any failure. **No Cloudflare dashboard or new route is required.**

**Private Hi 小智 OTA field:** `https://voice.cncloudx.com/xiaozhi/ota/<your-private-64-hex-secret>`; the new adapter supplies `wss://voice.cncloudx.com/xiaozhi/v1/<same-secret>`. Only after a successful `apply`, the owner may run `sudo bash tools/ai/a09-same-host.sh show-url` in an interactive root SSH terminal to see the exact private OTA URL once. Never send that credential in chat or screenshots. Its custom path and the App's activation polling behavior still require one genuine iPhone validation.

With the new app displaying the real six digits, owner's root-shell action:

```bash
sudo bash tools/ai/a09-lite-deploy.sh approve
```

Code entry is hidden and passed via stdin, not shell history or process command-line arguments. Recheck that the specific device belongs to the owner. If the App remains unbound or prompts repeatedly, do not make the endpoint publicly auto-approve; record only redacted HTTP status/missing field evidence. `revoke <MAC>` is optional after a security event; avoid printing unique identifiers in public channels.

## Rollback and success criteria

No Cloudflare route is removed or edited. To undo *only* the added same-host Caddy handlers and restore the exact original Caddyfile without a container restart, then stop the new iOS pilot:

```bash
sudo bash tools/ai/a09-same-host.sh rollback
sudo bash tools/ai/a09-lite-deploy.sh stop
```

This only stops new A09-Lite containers and retains the private SQLite and keys for future diagnosis. No production A03/A04 Docker restart, reload, firmware flash, firewall, global Docker prune, `swapoff` or changes to HomeSphere/MiniProbe. Keep `/opt/s3-voice-manager` from failed PR #28 untouched.

**P2 acceptance requires all:** original 4B OTA+WSS+audible voice PASS; iPhone OTA 200 with code + HMAC token, 202→200 only after owner CLI approval, iPhone WS 101 and full microphone→Vosk→GPT→EdgeTTS→speaker, no abnormal swaps or production regressions. Until then **P2 BLOCKED** (source/CI PASS is a separate level).

Upstream sources: `xinnan-tech/xiaozhi-esp32-server@v0.9.8` Java `OTAController.java`, `DeviceServiceImpl.java`, Python `ota_handler.py`, `core/auth.py`; Caddy official `forward_auth`, `reverse_proxy`; official Caddy Docker image reload guidance. The revised P2 uses a validated official graceful Caddy reload with a byte-for-byte backup, retains the original 4B matchers, and does not restart original containers.
## P2.1 same-host convergence (roadmap change, 2026-11-25)

Owner requirement updated: **reuse existing `voice.cncloudx.com` and the already-running Cloudflare Tunnel, NO new hostname, DNS, published app, or cloudflared restart.** P0 (official protocol review, 20%) and P1 (stdlib 6-digit adapter, 50%) remain 100% accepted. P2 (30%) is still 0% accepted until the real iPhone call + original Waveshare 4B speech regression succeed. Changes stay within **Draft PR #30**; no extra PR fragmentation.

P2 sequence/acceptance:
1. **P2-A, source/reuse** (8/30): inspect current `/opt/s3-voice-ai-edge/Caddyfile`, `/opt/s3-voice-a09-lite/.env` and Docker bridge membership, preserve the exact original A04 4B identity and HMAC. Zero firmware change.
2. **P2-B, path extension** (12/30): generate a narrowly-scoped extra route inside existing A04 Caddy, only for the separately secret iOS OTA/WS and standard activation poll; validate Caddy syntax before write; save private byte-for-byte original and rollback on error; gracefully reload Caddy via official `caddy reload` (no container restart). Change only the **new A09 adapter**'s WSS hostname to `voice.cncloudx.com`. Original A04 OTA and WS rules must remain identical.
3. **P2-C, integrated acceptance** (10/30): automated ephemeral Docker full install/status/same-host/rollback/stop, original 4B A04 simulator identity/route checks and negative security; target VPS local/public single-host OTA, forbidden default route, original OTA, memory/swap guard; one real Hi 小智 microphone→LLM→speaker + original ESP32 4B audio check.

CI gates are **not** real-phone proof. The closed-source App Store "Hi 小智" claims custom OTA, WebSocket and Token fields, but its handling of nonstandard OTA suffix and activation response has not been verified on-device. If final device fails, do not claim P2 accepted or automatically weaken authentication. Keep rollback command and original Caddy backup.

**Safety:** Same-host extension deliberately touches the *existing A04 Caddy configuration*, not its container image or 4B firmware. Requires a protective exact-source check, read-only template parse, a backup and immediate automatic rollback before any active config alteration. Do not edit existing Cloudflare account rules or connector; do not enable new host listener. Pilot must STOP if it cannot guarantee graceful reload and old 4B route preservation.

