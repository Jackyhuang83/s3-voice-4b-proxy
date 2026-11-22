# S3-Voice-AI A07 — Waveshare ESP32-S3 Touch-LCD-4B real enrollment (no flash)

Date: 2026-11-23. **Project overall 75%, P0/P1/P2 100%, P3 0%.** Existing roadmap: one A07 PR (+15% after actual device acceptance), A08 (+10% after stability/release). Depends on fully accepted A03–A06 on real Debian 13 target VPS.

## 0. Official firmware audit before touching the board

- Hardware is **Waveshare ESP32-S3 Touch-LCD-4B N16R8**, NOT the similar 4.3C/P4 board. Waveshare official tutorial lists 4B's XiaoZhi image as **v2.4.0**; current upstream 78/xiaozhi-esp32 also supports the 4B board. **Do not assume the existing factory build has the same configuration UI as v2.5.2 or v2.6.0.**
- Upstream `ota.cc` already sends `Device-Id` (MAC) and `Client-Id` (persistent client UUID) in POST to the configured OTA URL. `websocket_protocol.cc` sends those headers on WS upgrade, using the OTA-provided WSS URL and JWT.
- Where the existing board firmware exposes **Wi-Fi provisioning → Advanced → OTA URL**, it is possible to redirect to a private server without replacing the board firmware. The official Wi-Fi onboarding guide explicitly documents this option for v2.5.2. **A04 WSS url is returned from OTA; do not manually input WSS on the device.**
- If the option does not appear in the actual factory UI, STOP and report the firmware/setup screen. Do not reset NVS, erase flash, or install a different board image without a separate firmware-specific check. No blanket BOOT key sequence is asserted for this particular factory build.

Upstream references:
- https://docs.waveshare.com/ESP32-S3-Touch-LCD-4B/ESP32-AI-Tutorials
- https://docs.waveshare.com/ESP32-S3-Touch-LCD-4B/Firmware-Flashing
- https://github.com/78/xiaozhi-esp32/blob/v2.6.0/main/boards/waveshare/esp32-s3-touch-lcd-4b/README.md
- https://github.com/78/xiaozhi-esp32/blob/v2.6.0/main/ota.cc
- https://xiaozhi.dev/en/docs/usage/activation/
- https://caddyserver.com/docs/caddyfile/directives/log
- https://caddyserver.com/docs/caddyfile/directives/log_append

## 1. Why discovery is required

The already verified A04 ingress permits one **synthetic** Device-Id + Client-Id only, plus a private 256-bit path, before proxying OTA or WSS. It is not safe to add `allowed_devices` to the upstream server: v0.9.8 does not use it as a public OTA admission gate and token behavior differs. Onboarding real 4B requires the persistent MAC + UUID. Instead of asking the operator to find both in raw serial logs, A07 offers one-time discovery in **the same native Caddy gateway**.

### A07 enrollment lifecycle

1. `stage`: Verify A05 generic GPT, A06 VoskASR+EdgeTTS, A04 existing synthetic gate. Back up only A03 private YAML and A04 identity/Caddyfile into `/opt/s3-voice-ai-a07` (0700). Generate a **new random 256-bit private enrollment path**. In the Caddy gateway add a match for exact POST private path plus well-formed `Device-Id`/`Client-Id`. During enrollment it **always returns HTTP 403**: no unauthenticated OTA token is minted, no AI requests or speech generated. Original A04 test route still works.
2. `show-url`: Prints the new private OTA URL **only in the owner-controlled VPS terminal**; user copies into the existing 4B firmware's Wi-Fi provisioning Advanced → OTA URL. Never send this URL to chat, screenshots, console logs, GitHub, or Cloudflare Access. Set up in a trusted area. Cloudflare Access with browser email OTP must stay OFF for headless XiaoZhi.
3. `capture`: Caddy uses its official access log `log_append` fields but deletes the entire `request` object and response headers, keeping only the candidate MAC/UUID and non-sensitive status. Log file is in container `/config` **tmpfs**, mode 0600; only valid matching OTA requests receive identity fields, all other paths still 403. Script copies and sanitizes it into a transient private root-only VPS file, accepts exactly one distinct well-formed pair and stores only that pair in `/opt/s3-voice-ai-a07/candidate.json` (0600). The private URL path and headers are never logged together. A07 status prints only identifier suffixes, not full UUID/MAC or path.
4. `bind`: Only after the user confirms they just configured their own board and types `BIND` does the tool generate the **original A04 strict Caddyfile** bound to that MAC + UUID + the new private path. It swaps the A04 identity file and changes only the A03 `server.websocket` URL to the matching WSS path. The rest of A05/A06 YAML, API keys, model and ASR/TTS selection remain byte-for-byte unchanged. Then only Caddy gateway and A03 server are recreated/restarted, followed by A04 OTA/WS 200/101/403 regression. Enrollment logging is gone.
5. `public`: Re-executes A04 real HTTPS/WSS admission tests through dedicated Cloudflare Tunnel. This is still a synthetic *protocol* probe using the now-bound real headers; it is **not** proof microphone/speaker work.
6. Actual 4B OTA reconnect and conversational test: 4B should query its configured private URL, receive OTA metadata WSS URL and JWT, upgrade WSS, capture user's Mandarin speech, transmit audio, receive GPT response and play reply. If the board was offline during binding, reboot the board normally **without factory reset** to retry. Actual mic/speaker and audible response must be observed by owner.

## 2. Target VPS commands (AFTER GitHub CI passes and exact reviewed SHA is specified)

Root Shell on the same Debian 13 VPS:

```bash
cd /tmp/s3-voice-a03-src
git fetch --depth 1 origin ai/p3-a07-4b-enrollment-20261123
git checkout --detach FETCH_HEAD
# VERIFY: git rev-parse HEAD matches the reviewed A07 CI SHA
bash tools/ai/a07-device.sh preflight
bash tools/ai/a07-device.sh stage
bash tools/ai/a07-device.sh show-url  # PRIVATE; NEVER share the URL
```

On the 4B, only if current firmware exposes its existing setup Advanced OTA URL, enter that private URL (copy exactly; no trailing whitespace). It is **expected** to receive 403 before binding. Return to VPS:

```bash
bash tools/ai/a07-device.sh capture
# If this says no OTA captured, check 4B setup then retry; don't flash firmware.
bash tools/ai/a07-device.sh bind  # type BIND after confirming it was YOUR board
bash tools/ai/a07-device.sh public
bash tools/ai/a07-device.sh status
```

Full path secrets, A05 provider credentials, real MAC/UUID and Cloudflare tunnel token must never leave the VPS/board private setup. After successful binding, do not expose the full returned URL. User's ordinary board Wi-Fi connection may require reconfiguration to enter AP setup; follow actual firmware menu, do not infer button map.

Scoped restoration at any time:

```bash
bash tools/ai/a07-device.sh rollback
```

Rollback stops only A07 changes, restores A03 config and A04 original identity/Caddyfile, restarts only A03 and the A04 gateway; other VPS projects and tunnel container remain intact. The real board's new OTA URL will stop working until it is reconfigured, because rollback intentionally restores the synthetic-only gate. No firmware writing is performed.

## 3. Acceptance levels / GDGS

| Gate | Meaning |
|---|---|
| Source audit | 4B official/firmware contract; no new proxy or voice code; original Caddy and XiaoZhi used |
| CI | Real official Caddy image: unknown hardware OTA denied until explicit approval; capture only shaped identity; original A04 synthetic test remains valid; after bind known OTA 200 + WS 101, wrong identities 403; rollback restores original A05/A06 |
| VPS | `stage`, `capture`, `bind`, `public` commands PASS on actual target Cloudflare gateway with real 4B headers |
| Hardware | 4B's real firmware Wi-Fi setup accepts custom OTA URL; 4B reaches self-hosted WSS; real microphone, ASR -> own GPT -> EdgeTTS -> speaker audible response verified |

**A07 is NOT complete from CI alone.** Only after actual 4B hardware test, merge A07 and credit project +15% (75%→90%). A08 stability/release remains +10%. Preserve the currently working 4B firmware and A03–A06 baseline; do not proactively work on rare failure modes. The simple 4B voice conversation is the acceptance target.