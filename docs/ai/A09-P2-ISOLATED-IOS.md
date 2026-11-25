# S3-Voice A09-Lite P2 — Hi 小智 iOS isolated gateway

**Phase status: P2 BLOCKED until read-only real-host preflight, isolated pilot, real public Hi 小智 registration and actual audible speech.** P0 (20%) + P1 (50%) accepted based on source and CI; P2 is 30% and remains unaccepted even if new source CI is green. Original A09 Manager-Only PR #28 remains Draft and stopped.

## Purpose / reasons for two tiny containers

- Reuse existing official Python `xiaozhi-server v0.9.8`, GPT, Vosk and EdgeTTS. No second server, no Java/MySQL/Redis or model downloads.
- A09-Lite Python stdlib container generates six digits, stores owner-approved bindings in SQLite and proxies existing OTA signed HMAC tokens. A **second tiny, separate Caddy gateway** presents a dedicated iPhone public hostname. It uses the exact Caddy image currently already deployed for the 4B gateway (no new Caddy image pull).
- Both new containers publish **zero host ports**. Python memory cap **128 MiB**, Caddy **96 MiB**; total cap **224 MiB**, not predicted measured RSS. Both `restart: no`. Python has an internal network path to existing Docker `s3-voice-ai-server:8003` for OTA; Caddy reaches existing `s3-voice-ai-server:8000` for WSS; original Caddy/cloudflared/container settings are unchanged.
- The new Caddy joins existing `s3-voice-ai-edge_front`. Existing Cloudflare Tunnel will later route **only** a new published app/hostname to `http://s3-voice-a09-lite-gateway:8080`, while the original 4B `voice.cncloudx.com` route keeps the original `http://gateway:8080`. This is a dashboard/account action for the owner; the script NEVER touches Cloudflare DNS/Tunnel/Access and doesn't change or reload the existing A04 gateway. No second Tunnel connector is installed.

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
| P2 separate iPhone gateway, real host and device | 30% | P2-1 (one PR) | P1 | new Docker Caddy/OTA gates CI; real host preflight; no 4B restart/change; measured memory/swap; owner's CF second hostname; Hi 小智 real OTA/202→200/WS101/Opus audible; original 4B regression; exact scoped stop and rollback |

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

**Cloudflare** owner action, once the local pilot is healthy: In the existing *S3-Voice* remotely managed Tunnel's Published Applications/Routes, create a **new hostname** `ios-voice.cncloudx.com` with service URL `http://s3-voice-a09-lite-gateway:8080`. Do not modify the existing `voice.cncloudx.com → http://gateway:8080`. Do not configure browser-based Cloudflare Access on the device hostname (the App may not support interactive Access). Do not restart the existing cloudflared. Only the 256-bit path secret is shared with the App; it remains root-only on VPS and should be entered privately (not sent in chat).

**Private Hi 小智 OTA field:** `https://ios-voice.cncloudx.com/xiaozhi/ota/<your-private-64-hex-secret>`; the adapter replies with corresponding `wss://ios-voice.cncloudx.com/xiaozhi/v1/<same-secret>`. The exact secret comes from root-only `.env`; no example or command here prints real credentials. The App's ability to use a nonstandard OTA suffix and its activation polling behavior must be verified; do not claim iOS voice from synthetic CI.

With the new app displaying the real six digits, owner's root-shell action:

```bash
sudo bash tools/ai/a09-lite-deploy.sh approve
```

Code entry is hidden and passed via stdin, not shell history or process command-line arguments. Recheck that the specific device belongs to the owner. If the App remains unbound or prompts repeatedly, do not make the endpoint publicly auto-approve; record only redacted HTTP status/missing field evidence. `revoke <MAC>` is optional after a security event; avoid printing unique identifiers in public channels.

## Rollback and success criteria

Remove/disable **only** the new Cloudflare `ios-voice.cncloudx.com` hostname; leave the 4B hostname alone. Then:

```bash
sudo bash tools/ai/a09-lite-deploy.sh stop
```

This only stops new A09-Lite containers and retains the private SQLite and keys for future diagnosis. No production A03/A04 Docker restart, reload, firmware flash, firewall, global Docker prune, `swapoff` or changes to HomeSphere/MiniProbe. Keep `/opt/s3-voice-manager` from failed PR #28 untouched.

**P2 acceptance requires all:** original 4B OTA+WSS+audible voice PASS; iPhone OTA 200 with code + HMAC token, 202→200 only after owner CLI approval, iPhone WS 101 and full microphone→Vosk→GPT→EdgeTTS→speaker, no abnormal swaps or production regressions. Until then **P2 BLOCKED** (source/CI PASS is a separate level).

Upstream sources: `xinnan-tech/xiaozhi-esp32-server@v0.9.8` Java `OTAController.java`, `DeviceServiceImpl.java`, Python `ota_handler.py`, `core/auth.py`; Caddy official `forward_auth`, `reverse_proxy`; official Caddy Docker image reload guidance. The P2 design deliberately avoids reloading original Caddy altogether.