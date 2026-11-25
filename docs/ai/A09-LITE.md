# S3-Voice A09-Lite — Hi 小智六位码最小兼容层

**Status:** P0 source audit confirmed; P1 Python prototype/CI is NOT live VPS deployment. P2 requires isolated ingress and iPhone testing. Original Manager-Only PR #28 remains Draft/BLOCKED on the shared 3.6GiB host.

## Immutable project boundaries

- Keep the working Waveshare 4B, existing Python `server_0.9.8`, A04 Caddy/Cloudflare, GPT, Vosk, EdgeTTS, HomeSphere and MiniProbe unchanged.
- No Java manager, Redis, MySQL, second voice engine, new model downloads, firmware flashing, Swap changes, public listeners, firewall changes or auto-enrollment.
- This is **not** an official XiaoZhi management console. It implements only the small OTA/activation compatibility contract; it does not provide users, agents or general device management.
- `P1` **must not be deployed onto the production VPS** until P2 has reviewed actual host configuration, port admission, rollback and memory headroom. The prototype is Python stdlib only and CI runs with ephemeral local HTTP stubs.

## Source-verified upstream protocol (official v0.9.8)

1. `main/manager-api/src/main/java/xiaozhi/modules/device/service/impl/DeviceServiceImpl.java` — `buildActivation` emits `activation.code`, `.challenge`, `.message`; `deviceActivation` finds the code in Redis and binds a `device_id` to a user/agent. This project substitutes a **root-owned local SQLite owner approval**; no official Java users/agents are emulated.
2. `main/manager-api/src/main/java/xiaozhi/modules/device/controller/OTAController.java` — OTA POST uses `Device-Id` and `Client-Id`; POST `/ota/activate` returns HTTP **202** for unbound device and **200** when bound.
3. `main/xiaozhi-server/core/api/ota_handler.py` — existing Python OTA already issues the `websocket.url` and `websocket.token`. This adapter forwards the original local OTA response, retains its **real signed token**, substitutes a distinct *iPhone-only* WSS URL, adds `activation` only for unbound clients, and clears firmware downloads. The Python voice service is not changed.
4. `main/xiaozhi-server/core/auth.py` — WS signs `Client-Id|Device-Id|timestamp` with HMAC-SHA256. **Never invent a Token or disable this existing authentication**.

## Minimal state machine / security

- First OTA: original local voice OTA → `{websocket:{url, token}, activation:{code, message, challenge}, firmware:{url:""}}`. Six-digit code is generated with `secrets.randbelow`, stored in private SQLite, reused for the same pending identity for up to **10 minutes**. The time limit is a **Lite safety policy**, not a claim about official Redis TTL.
- Unbound `POST /xiaozhi/ota/activate` → HTTP **202**. Only the owner running local CLI `approve CODE` binds the exact device/client identity; `activate` then returns HTTP **200**. Bound OTA omits `activation`.
- Client-Id changes are rejected for already-known Device-Id; unrelated devices cannot inherit a binding. Explicit `revoke` resets it. Codes have a collision guard and expire; no password or public approval API exists. Six-digit codes are not sufficient for authorization alone.
- P2 public path must contain a dedicated high-entropy capability/secret and Caddy must check **bound identity** via loopback `GET /internal/authorize-ws` **before** proxying an iOS WebSocket. Existing WS HMAC token validation must still run in the unchanged voice server. The adapter's `/internal/authorize-ws` and `/health` must **never** be exposed publicly. Deny iPhone WSS until owner approval. Never add the iOS identity to the existing 4B route by spoofing identifiers.
- Adapter binds **only `127.0.0.1`**. Upstream OTA is pinned to `http://127.0.0.1:18003/xiaozhi/ota/`, proxy settings ignored. Default WSS points to a deliberately unusable `.invalid` domain. No token/identity/access URL/activation code is written to HTTP logs.
- On operational error return controlled HTTP 400/403/503, not a fake success; failed upstream OTA never issues an activation code.

## P0–P2 roadmap (stage weights, logical PR budget)

| Stage | Weight | PRs | Dependencies | Acceptance |
| --- | ---: | --- | --- | --- |
| P0 official audit & on-host status distinction | 20% | 0 (read-only audit) | A03–A07 prior evidence | Verified official v0.9.8 protocol and historical iOS OTA mismatch; distinguish GitHub template from actual A04 deployed state |
| P1 owner-approved six-digit compatibility | 50% | P1-1 (one concentrated PR) | P0 | Stdlib Python + SQLite; real ephemeral HTTP 200 OTA, 6 digits, HMAC token pass-through, 202→200, wrong identity/expiry/revoke, CI PASS, no production changes |
| P2 separated public ingress & iPhone | 30% | P2-1 (one concentrated PR) | P1 accepted and real host readonly preflight | Caddy path/identity security with rollback, resource measurements, original 4B OTA/WS/audio regression, real Hi 小智 binding/Opus audio, no other services altered |

**Progress rule:** P0 source work is complete. P1 local Python tests may pass without GitHub CI; do not award P1 50 points until relevant HEAD CI passes. P2 never passes until actual iPhone microphone→Vosk→GPT→EdgeTTS→speaker and original 4B acceptance.

## Local-only developer exercise (never paste credentials or actual device IDs)

The following is **only for an isolated test host**, not the currently occupied VPS:

```sh
DB="$(mktemp -d)/activation.sqlite3"
python3 tools/ai/a09_lite.py --db "$DB" init
# The app is not publicly accessible; local HTTP server talks to 127.0.0.1:18003.
# Run serve only where the existing voice OTA is intentionally accessible.
python3 tools/ai/a09_lite.py --db "$DB" serve
# Once a private, valid six-digit code has been displayed to the owner:
python3 tools/ai/a09_lite.py --db "$DB" approve 123456
# Optional: revoke a specifically enrolled device:
python3 tools/ai/a09_lite.py --db "$DB" revoke 02:11:22:33:44:55
```

**Security:** CLI approval is owner-only via filesystem access; shell history can contain the code, so use a private root shell or a temporary environment. The demonstration code/identity above is fictitious. Never publish the DB or `A09_LITE_WSS_URL` bearer path.

For CI without any local voice server:

```sh
python3 -m py_compile tools/ai/a09_lite.py
python3 -m unittest discover -s tests/ai -p test_a09_lite.py -v
```

## Deployment hard gate

P2 must first read current production `docker` state and effective Caddyfile, measure available RAM/Swap without deploying anything, preserve 4B original gateway URLs and private keys, and build a **fully reversible** separate iPhone OTA/WSS route. Do not assume the `main` branch historical single-device template equals the current on-host configuration. If this cannot be proven without putting 4B at risk, leave P2 blocked and prefer the OpenNomi direct-WS alternative. Any owner acceptance must be based on real Hi 小智 version/build behavior, not only a mocked client contract.