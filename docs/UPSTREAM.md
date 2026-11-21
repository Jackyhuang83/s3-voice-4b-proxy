# P0 pinned upstream ledger (2026-11-21)

The hashes below are inspection pins. No upstream source has been imported into this newly initialized repository yet.

## Main engine

Repository: https://github.com/yanxke/ESP32-VPN-Transparent-Proxy-Router
Pinned revision: dfb04b03154cfaee1d8615e4b8942dfe737abc5d
Commit: https://github.com/yanxke/ESP32-VPN-Transparent-Proxy-Router/commit/dfb04b03154cfaee1d8615e4b8942dfe737abc5d
License: MIT (preserve notices).

Confirmed upstream code:
- src/transparent_tcp.c: lwIP IPv4 packet interception, tuple rewriting, flow state.
- src/transport_tcp.c: raw TCP socket VLESS framing and relay.
- src/main.c: Wi-Fi, DNS, routing, configuration and FreeRTOS ownership.
- sdkconfig.defaults: IPv6 explicitly disabled.
- README/SECURITY: TLS, Reality, WebSocket and IPv6 unsupported; NVS encryption absent; not yet production-ready.

Strategy: reuse its IPv4 transparent TCP/DHCP/DNS/STA+AP engine. Internet UDP/XUDP/smux are non-goals; disable only with regression tests. Do NOT assume ESP-TLS is a drop-in raw socket: a TLS-aware I/O boundary is needed.

## SS2022 component

Repository: https://github.com/rlog/atoms3r-muse-firmware
Pinned revision: 57f73602e963e478e06eae5f8108d07495468031
Commit: https://github.com/rlog/atoms3r-muse-firmware/commit/57f73602e963e478e06eae5f8108d07495468031
License: Apache-2.0 (preserve notices and separate BLAKE3 attribution).

Confirmed upstream code:
- esp32/components/muse/muse_ss2022.c and .h: SIP022 TCP AEAD framing/BLAKE3/PSA AES-GCM.
- esp32/components/muse/muse_proxy.c: FreeRTOS/lwIP TCP bridge; dial currently hard-coded AF_INET with IPv4 literal.
- esp32/components/muse/PROXY.md: only 2022-blake3-aes-128-gcm, TCP-only, application-specific; no transparent routing.

Strategy: selectively import protocol core/dependencies after license and IDF version checks; adapt for general TCP targets and IPv6 outbound. Do not copy the complete Muse audio firmware.

## Official references

- Board: https://docs.waveshare.com/ESP32-S3-Touch-LCD-4B
- Board source: https://github.com/waveshareteam/ESP32-S3-Touch-LCD-4B
- ESP-IDF lwIP: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/lwip.html
- ESP-IDF Wi-Fi: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/wifi.html
- ESP-TLS: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/protocols/esp_tls.html
- SIP022: https://shadowsocks.org/doc/sip022.html

Every imported file must document original URL/path, source SHA, license/attribution and modifications. This independent new repository does not automatically inherit the original authors' Git history.
