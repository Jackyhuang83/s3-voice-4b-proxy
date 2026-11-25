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

**Activation path compatibility:** For a client that appends `/activate` to the complete private OTA URL, A04 maps `/xiaozhi/ota/<same-secret>/activate` to the existing A09 status endpoint. The fixed `/xiaozhi/ota/activate` is also accepted. Both are read-only 202-before-approval/200-after-approval and cannot approve a device. The exact route is tested under real Docker in CI. Existing installed A09 gateway needs no upgrade/reinstall because the rewrite happens at A04. App runtime behavior remains unproven until one real iPhone check.

**Private Hi 小智 OTA field:** `https://voice.cncloudx.com/xiaozhi/ota/<your-private-64-hex-secret>`; the new adapter supplies `wss://voice.cncloudx.com/xiaozhi/v1/<same-secret>`. Only after a successful `apply`, the owner may run `sudo bash tools/ai/a09-same-host.sh show-url` in an interactive root SSH terminal to see the exact private OTA URL once. Never send that credential in chat or screenshots. Its custom path and the App's activation polling behavior still require one genuine iPhone validation.

With the new app displaying the real six digits, owner's root-shell action:

```bash
sudo bash tools/ai/a09-lite-deploy.sh approve
```

The six digits are visibly echoed in the owner's interactive SSH terminal for input confirmation; the code is read directly from `/dev/tty` and passed to the adapter via stdin, never placed in shell history or process command-line arguments. As a short-lived activation credential, do not share a screenshot containing the code. Recheck that the specific device belongs to the owner. If the App remains unbound or prompts repeatedly, do not make the endpoint publicly auto-approve; record only redacted HTTP status/missing field evidence. `revoke <MAC>` is optional after a security event; avoid printing unique identifiers in public channels.

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



## P2-D One-shot private iPhone request diagnostics (existing PR #30)

The real owner read-only SQLite summary was active=0 expired=0 approved=0.
That proves no current pending code, not the absence of a phone request. The
closed-source Hi 小智 exact HTTP handshake has NOT been verified. An
independent Flutter client omits Client-Id; do NOT assume the same of Hi 小智.
The official A03 Python OTA requires both identity headers, and no
automatic identity synthesis, auto-approval or authentication bypass is allowed.

Source: tools/ai/a09_diagnose.py. Once the reviewed latest PR head passes all
three CI jobs, the owner runs one interactive command on the already-installed
and same-host-activated VPS:

    sudo python3 tools/ai/a09_diagnose.py session

The script backs up both exact byte sequences under private mode 0600, checks
the installed A09 adapter matches the known previously accepted source, and
temporarily instruments only the A09 adapter with aggregate volatile counters.
It restarts only the NEW A09 adapter and hot-reloads original A04 Caddy without
restarting the 4B voice server, old gateway container or existing Cloudflare
connector. The original 4B matchers, secret, OTA/WS, and default deny remain
untouched. Only the separate 256-bit-secret A09 OTA route is temporarily
forwarded directly to the A09 adapter for classification. Invalid identities
are still HTTP 400 and never receive binding codes. A GET OTA request is
classified and returns HTTP 405. The public /internal/diagnostics remains 403.

The user opens Hi 小智 once, attempts a connection, returns to SSH and presses
Return. The same running command prints A09_DIAG_COUNTS and A09_DIAG_VERDICT,
then restores exact original A04 Caddy and A09 adapter bytes automatically,
with A09_DIAG_ROLLBACK_PASS. No private URL, Token, MAC, Client-Id, code,
raw body or identifying header is displayed or persisted by the diagnostics.

Possible results: NO_A09_OTA_REACHED (wrong app config/path/provider or
unobserved traffic), OTA_WRONG_METHOD (GET rather than POST),
MISSING_REQUIRED_IDENTITY, INVALID_IDENTITY_FORMAT, A03_UPSTREAM_UNAVAILABLE,
OTA_REQUEST_OR_RESPONSE_INCOMPATIBLE, A09_OTA_CODE_ISSUED.
An issued code still does not establish a real device speech session.

If mobile SSH disconnects mid-session and leaves private backup files, DO NOT
rerun session or overwrite the files. After reconnecting, execute exactly
sudo python3 tools/ai/a09_diagnose.py rollback. Never delete backups manually.
P2 remains unaccepted until actual iPhone and original 4B full-audio tests pass.

The one-shot session has a hard 180-second server-side timeout; expiration or an interactive interrupt also triggers automatic diagnostic rollback. If SSH is forcibly terminated, backups remain for the explicit rollback command above.


## P2-E Edge-level Cloudflare/Caddy read-only ingress audit

Owner confirmed Hi 小智 **already saved the full private OTA URL**; stop asking
for App screenshots or another A09 diagnostic run. The real phone one-shot
diagnostic returned all counters zero (OTA, activation polling and WSS auth).
This shows only that no request reached A09 adapter during that window.
It does NOT establish whether the request reached Cloudflare, was blocked by
WAF/Access, hit a different Tunnel route, or failed the original A04 matcher.

**Historical log limitation:** the current A04 Caddy has access logging set to
output discard, so no historical Caddy request log can be recovered. Cloudflare
Security Events focuses on mitigated requests; Security Analytics can provide
HTTP request analytics subject to plan, sampling and retention. Tunnel logs
cover connector/edge/origin activity, but may not record all individual HTTP
requests. Do NOT set cloudflared to debug: it can print private URL bearer
secrets and sensitive headers. Avoid uploading any Caddy config or OTA URL.

The VPS read-only script tools/ai/a09_edge_audit.py compares the same
deliberately invalid POST against:

1. Local http://127.0.0.1:18080/xiaozhi/ota/ plus the protected A09 secret.
2. Public https://voice.cncloudx.com/xiaozhi/ota/ plus that same secret.

The body is a valid JSON ARRAY, not an object, and is rejected by A09 with
HTTP 400 before contacting A03 or generating any activation code. This probe
uses synthetic device headers, does not contact the original 4B private route,
never operates Hi 小智 or creates a SQLite row, and cannot expose the secret
in user-visible output. It does not restart containers, write configuration,
change Cloudflare Access/WAF, open host ports, or add DNS entries.
It checks the known same-host matcher, A04 bind-mount, both running gateways,
the existing Tunnel container and their Docker front network. TLS verification
remains enabled and public redirects are not followed.

After the latest-HEAD CI passes all three jobs, execute once from the
reviewed source checkout on the VPS:

    sudo python3 tools/ai/a09_edge_audit.py

Output only the redacted lines A09_EDGE_CADDY_CONFIG, A09_EDGE_DOCKER,
A09_EDGE_LOCAL_HTTP, A09_EDGE_PUBLIC_HTTP, A09_EDGE_CLOUDFLARE_HEADERS,
A09_EDGE_VERDICT, A09_EDGE_READ_ONLY_PASS. No raw request/response body or
headers, private URL, MAC, Client-Id or token should be shared.

Interpretation:
- PUBLIC_AND_LOCAL_A09_ROUTE_PASS: this VPS-origin synthetic request reaches
  A09 via both local Caddy and public Cloudflare, but does NOT prove that the
  real iPhone uses this OTA path or sends POST. Do not modify A09 auth.
- CADDY_403_LOCAL: local A04 rejected the request; inspect the actual loaded
  Caddy routes before attributing the problem to Cloudflare.
- PUBLIC_DENIED_OR_CHALLENGED: local 400 but public 401/403/429; check CF
  Security Analytics / Security Events and hostname-specific WAF/Access
  policies without disabling them globally.
- PUBLIC_REDIRECT_OR_ACCESS_AUTH: public 3xx; check Access or redirect rules.
- PUBLIC_TUNNEL_OR_EDGE_ROUTE_ERROR: public error/route mismatch while local
  400; check the existing voice.cncloudx.com published application origin.
- PUBLIC_PROBE_UNREACHABLE_FROM_VPS: the VPS egress probe could not reach
  the public host; not proof of an iPhone failure.

This audit compares **current reachability from the VPS**, not historic
iPhone traffic. Verifying a past individual iPhone request in Cloudflare
requires authorized Cloudflare account analytics/log access, not available
from the GitHub repo. Never claim this source-level check proves the
closed-source app's routing behavior.
