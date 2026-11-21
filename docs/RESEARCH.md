# P0 source and compatibility evidence register

Date: 2026-11-21. Research only; no firmware build or 4B hardware tests performed.

| ID | Finding | Evidence | Source | Remaining validation |
|---|---|---|---|---|
| E01 | Board is ESP32-S3 N16R8 with 16 MB flash and 8 MB PSRAM. | OFFICIAL | https://docs.waveshare.com/ESP32-S3-Touch-LCD-4B | Exact firmware version, partitions, audio/LCD memory on target. |
| E02 | ESP-IDF lwIP supports IPv6 SLAAC and IPv6 sockets; AF_UNSPEC getaddrinfo may return IPv4 only, so AF_INET6 query is important. | OFFICIAL | https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/lwip.html | Test actual selected ESP-IDF release and STA gateway route. |
| E03 | AP+STA is officially supported, with Wi-Fi channel sharing constraints. | OFFICIAL | https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/wifi.html | Long-term stability on 4B. |
| E04 | yanxke has IPv4 TCP interception and plain VLESS TCP; TLS and IPv6 are absent, and NVS encryption is absent. | UPSTREAM | https://github.com/yanxke/ESP32-VPN-Transparent-Proxy-Router/blob/dfb04b03154cfaee1d8615e4b8942dfe737abc5d/README.md | Controlled build and regression tests. |
| E05 | rlog SS2022 is AES-128-GCM TCP, FreeRTOS sockets, application-specific, presently IPv4-only dial. | UPSTREAM | https://github.com/rlog/atoms3r-muse-firmware/blob/57f73602e963e478e06eae5f8108d07495468031/esp32/components/muse/PROXY.md | Reproducible SIP022 tests and VPS interoperability. |
| E06 | VLESS TLS via ESP-TLS with verified certificate and hostname is a plausible official-API design, not yet implemented. | DESIGN | https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/protocols/esp_tls.html | Complete TLS-aware I/O and negative certificate tests. |
| E07 | IPv6-only VPS connectivity is independent of downstream IPv6 address assignment. | REQUIREMENT | docs/REQUIREMENTS.md | Verify global route, socket reachability and fail-closed. |

## Engineering risks

- Main router source uses ordinary socket descriptors and send/recv/select; encrypted VLESS TLS I/O is not a transparent swap and requires proper TLS object lifecycle, read/write/close, timeouts and error handling.
- Main source currently disables IPv6 in sdkconfig; enabling lwIP IPv6 is not permission to route IPv6 to AP clients.
- SS2022 requires accurate clock, random salts/nonces and authenticated response framing.
- UDP-based DHCP and DNS are still needed even though Internet UDP forwarding is out of scope.
- Transparent TCP for Wi-Fi clients is not the same as a fully proven general VPN: check DNS leaks, packet flow, TLS fallback and untrusted portal concerns.
- ESP32-S3 8MB PSRAM must also serve LCD/voice tasks; no resource claims before target testing.

## Research process for every PR

Review primary documents, inspect source and test cases, search relevant issues/PRs and comparable solutions, record source SHA and smallest patch, run CI and host/protocol tests, and only then request narrowly specified real-device evidence. No repeated blind changes, Wi-Fi resets or irreversible flashing.

## Open items

1. Select and pin ESP-IDF/PlatformIO version from upstream and 4B voice firmware compatibility.
2. Reproduce pinned yanxke build in automated environment.
3. Confirm module interfaces for transport TLS, AEAD TCP and AF_INET6 dial.
4. Define a documented recovery approach before any hardware programming.
