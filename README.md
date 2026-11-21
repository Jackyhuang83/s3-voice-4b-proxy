# S3-Voice 4B Proxy

Optional ESP-IDF/FreeRTOS **IPv4 transparent TCP proxy** gateway for the Waveshare ESP32-S3-Touch-LCD-4B. This project prioritizes reuse of existing GitHub implementations and keeps the original S3-Voice/Xiaozhi voice firmware intact until independent acceptance.

**Required:** SS2022 TCP, VLESS with authenticated TLS, and outbound IPv6 connectivity to IPv6-only VPS nodes. The Wi-Fi AP for phones and laptops stays IPv4-only.

**Not included in v1.0:** transparent Internet UDP, XUDP, QUIC/HTTP3, full downstream IPv6 router, Snell, HY2, Reality/Vision or a new custom UI.

## Current status

P0–P3 **completed (13 merged PRs; protocol security regression and ESP32-S3 R8N16 build passing)**. P4 remains unaccepted: the existing router build is **not** a Waveshare 4B Xiaozhi voice firmware, the actual 4B has not been flashed/tested, and production-safe NVS encryption is not yet implemented. The planned P4-1 voice-first integration preflight and compile gate are documented in [P4 board integration](docs/P4-BOARD-INTEGRATION.md); it is not a deployable transparent gateway until the voice/AP runtime adapter and end-to-end build pass.

## Project baseline

- [Requirements R1/R2](docs/REQUIREMENTS.md)
- [P0–P4 plan](docs/PLAN.md)
- [Pinned upstream source ledger and licenses](docs/UPSTREAM.md)
- [Research evidence and unresolved risks](docs/RESEARCH.md)

## Upstream code to be reused

1. Main router: https://github.com/yanxke/ESP32-VPN-Transparent-Proxy-Router (MIT, pinned revision in UPSTREAM.md).
2. SS2022 TCP protocol: https://github.com/rlog/atoms3r-muse-firmware (Apache-2.0, pinned revision in UPSTREAM.md).
3. Board/IDF official source: see UPSTREAM.md.

## Development policy

Each work item must inspect official docs, exact upstream code/tests and similar implementations before requesting device testing. Use official APIs and small adapters instead of rebuilding protocol/router functionality. All changes through feature PRs with provenance and honest CI results. Never commit VPS credentials, erase NVS or flash a stable voice device without a verified recovery path.
