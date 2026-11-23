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

## 2.5. A07 ConnectionResetError / interrupted deployment recovery (2026-11-23)

A real target VPS reported `ConnectionResetError: [Errno 104] Connection reset by peer` during A07's first gateway deployment; the previous script entered its best-effort A04/A05/A06 restore path but did **not** verify health and left `/opt/s3-voice-ai-a07` present. This is **not** proof of a GPT provider or 4B failure. Do not repeat `stage` on a stale state and do not erase any existing snapshots.

Fix in this same PR: Docker `Started` is no longer considered gateway-ready. `gateway_restart` probes the existing A04 deny path until it returns HTTP 403, and the actual A04 OTA/WSS 200/101/403 smoke has bounded retries for transient reset/connection errors. `restore_original` only restarts a server if its configuration changed, then *must verify* the restored gateway and OTA/WSS before claiming success. Interruption snapshots remain root-only.

To reconcile the **already failed** deployment on the target VPS, first fetch/verify a CI-reviewed current A07 commit then run, in the root Shell:

```bash
# Read-only visibility (without printing any secret):
docker ps --format '{{.Names}}  {{.Status}}' | grep -E '^s3-voice-ai-(server|gateway|tunnel)\b' || true
curl --noproxy '*' -sS -o /dev/null -w 'A03_OTA_HTTP=%{http_code}\n' http://127.0.0.1:18003/xiaozhi/ota/
curl --noproxy '*' -sS -o /dev/null -w 'A04_DEFAULT_DENY_HTTP=%{http_code}\n' http://127.0.0.1:18080/
# After switching to the reviewed updated source checkout:
bash tools/ai/a07-device.sh recover
bash tools/ai/a07-device.sh preflight
```

Expected after healthy recovery: `A07_OK: verified: original A04 identity and A05/A06 configuration restored; OTA/WSS 200/101/403 PASS`, then `A07_OK: interrupted stage archived ...`, then `A07_OK: A04 synthetic ingress, A05 GPT and A06 voice baseline checked; no edits`. `recover` archives the interrupted A07 private directory under `/opt/s3-voice-ai/a07-aborted-<UTC>` (mode 0700), retains all private snapshots, and does not overwrite A05/A06 API credentials. The previous *enrollment* secret is not reused; the board must use the new private OTA URL from a fresh `stage` if it had already been entered.

If `recover` reports `A07_RECOVERY_UNVERIFIED`, STOP; collect only container statuses, redacted service logs and HTTP status codes, not secret URL/identity. Do **not** force-delete the A07 directory or rerun `stage`. A07 remains unaccepted until actual real 4B enrollment + voice is proven.

## 2.7. 4B mid-sentence interruptions: official 60 ms Opus pacing experiment

**Actual user observation (2026-11-23):** Speech intermittently breaks off **mid-word in the same sentence**, then resumes. This differs from TTS waiting between complete sentences. Recent redacted real VPS sample had CPU 1.5%, 414.8 MiB, independent fixed Edge TTS first/full 0.55/0.86s, and zero TTS errors; there was one earlier audio-send failure.

**Official upstream precedent:**
- [Upstream issue #2632](https://github.com/xinnan-tech/xiaozhi-esp32-server/issues/2632): matches mid-syllable playback breaks even with full synthesized text; maintainers acknowledge and link [#2647](https://github.com/xinnan-tech/xiaozhi-esp32-server/issues/2647). **No general confirmed universal fix.**
- [Upstream issue #3349](https://github.com/xinnan-tech/xiaozhi-esp32-server/issues/3349): **verified on ESP32-C3**, not yet on Waveshare 4B. With default `PRE_BUFFER_COUNT=5`, first Opus frames can burst within milliseconds, while 60 ms pacing from frame zero restored that reporter's device playback.
- Original pinned XiaoZhi v0.9.8 `config.yaml` already exposes `tts_audio_send_delay: 0` (default) or `60` ms (fixed pacing). Original `core/handle/sendAudioHandle.py` uses `send_delay_ms > 0` to enqueue **all** Opus packets, rather than immediate first-five burst. Therefore use **official config only**, no fork or firmware replacement.

**A07 existing-PR code:** `tools/ai/a07-audio-pacing.py status|apply|rollback` with exact comparison and root-only snapshot under `/opt/s3-voice-ai/a07-pacing`. `apply` requires A05 GenericGPTLLM, A06 VoskASR+EdgeTTS, A07 real bound hardware identity, original default `0` or absence. Changes only top-level `tts_audio_send_delay` to 60 in private A03 YAML, restarts **only** `s3-voice-ai-server`, validates original A03 OTA 200 + A04 strict identity OTA/WS/403; failed startup triggers immediate snapshot restore attempt. Does not change A04 gateway, Cloudflare, other VPS projects or device firmware. `rollback` confirms exact active trial config hash before restoring the original private YAML, restarts only A03, and verifies A03/A04. It preserves old snapshots privately.

**On actual VPS** (only after exact HEAD has passed A07 CI, and not while another deployment is applying):

```bash
cd /tmp/s3-voice-a03-src
git fetch --depth 1 origin ai/p3-a07-4b-enrollment-20261123
git checkout --detach FETCH_HEAD
# Verify HEAD matches the reviewed A07 CI SHA before changing production
python3 tools/ai/a07-audio-pacing.py status
python3 tools/ai/a07-audio-pacing.py apply
```

**Only ONE real-device A/B test:** ask 4B to speak a 2-3 sentence uninterrupted reply with the same Wi-Fi and model. Listen specifically for pauses **within words**, not normal between-sentence delays. If it still breaks, or latency worsens, execute `python3 tools/ai/a07-audio-pacing.py rollback` to restore the original config. If it is noticeably improved, leave trial active, `status` and record actual 4B acceptance as a trial result (not universal protocol proof). `rollback` is also available after success.

**Not recommended without evidence:** switch to MQTT/UDP and open new ports; rewrite firmware/audio decoder; change Opus sampling rate, Vosk, GPT or Edge TTS; raise CPU quota based on idle sampling. Upstream C3 results are a hypothesis for S3 4B until physical playback confirms.

## 3. Acceptance levels / GDGS

| Gate | Meaning |
|---|---|
| Source audit | 4B official/firmware contract; no new proxy or voice code; original Caddy and XiaoZhi used |
| CI | Real official Caddy image: unknown hardware OTA denied until explicit approval; capture only shaped identity; original A04 synthetic test remains valid; after bind known OTA 200 + WS 101, wrong identities 403; rollback restores original A05/A06 |
| VPS | `stage`, `capture`, `bind`, `public` commands PASS on actual target Cloudflare gateway with real 4B headers |
| Hardware | 4B's real firmware Wi-Fi setup accepts custom OTA URL; 4B reaches self-hosted WSS; real microphone, ASR -> own GPT -> EdgeTTS -> speaker audible response verified |

**A07 is NOT complete from CI alone.** Only after actual 4B hardware test, merge A07 and credit project +15% (75%→90%). A08 stability/release remains +10%. Preserve the currently working 4B firmware and A03–A06 baseline; do not proactively work on rare failure modes. The simple 4B voice conversation is the acceptance target.