# S3-Voice 4B Proxy v1.0 — Requirements

Status: requirements defined, code and hardware not yet verified.
Hardware: Waveshare ESP32-S3-Touch-LCD-4B (N16R8, 16MB Flash, 8MB PSRAM).
This is an optional module, not a replacement for the stable Xiaozhi voice firmware.

## R1 — Transparent IPv4 TCP proxy (highest priority)

- Wi-Fi clients connect to the ESP32-S3 SoftAP, obtain IPv4 by DHCP and need no proxy app or system proxy settings.
- Keep the existing upstream AP+STA, DHCP, local DNS, lwIP IPv4 TCP interception and TCP flow table wherever feasible.
- Protocols: SS2022 TCP and VLESS TCP. Only one active proxy profile is required for MVP.
- SS2022 initial algorithm: 2022-blake3-aes-128-gcm, with complete SIP022 AEAD, timestamp and response authentication.
- VLESS in production MUST use authenticated TLS with server certificate and hostname/SNI validation. Plain VLESS TCP may be used ONLY for isolated lab interoperability tests.
- Exclude Internet UDP forwarding, XUDP, QUIC and HTTP/3. Preserve infrastructure UDP needed for DHCP, DNS, and upstream IPv6 ICMPv6 operations.
- Client TCP must fail closed on proxy/authentication/tunnel failure, never silently fall back to direct Wi-Fi Internet.
- DNS must not silently leak upstream in proxy mode. Design exact local DNS behavior at P1, and test it.
- Some applications without TCP fallback may not work; do not claim full application support.

## R2 — IPv6-only VPS as upstream proxy server

- Wi-Fi STA supports IPv4/IPv6 and can acquire a global IPv6 address, default route and usable TCP connectivity.
- Both SS2022 and VLESS clients support outbound IPv6 TCP to an IPv6 literal or AAAA hostname.
- On ESP-IDF lwIP, query AF_INET6 explicitly rather than relying on AF_UNSPEC returning AAAA results.
- The downstream SoftAP remains IPv4-only: no advertised IPv6 prefix, no downstream IPv6 transparent routing, no 4B NAT64/NAT66.
- If upstream cannot reach an IPv6-only VPS, the selected proxy fails closed. A local link-local address is not proof of Internet IPv6.
- If an IPv6-only VPS must reach IPv4-only websites, solve this on the VPS with an appropriate egress mechanism; do not add it to ESP32 firmware.

## Non-goals

No Snell, Hysteria2, Trojan, Reality, XTLS Vision, WebSocket, SS2022 UDP, transparent downstream IPv6, Internet UDP/XUDP, QUIC or custom proxy web UI in v1.0.

## Reuse and safety requirements

- Use proven upstream project functions, then official ESP-IDF APIs, then minimal local adapters, and write new modules only if justified.
- Preserve upstream licenses, provenance and pinned commits. Keep secrets, SS2022 PSKs, VLESS UUIDs, Wi-Fi credentials and node URLs out of git and CI output.
- Before integrating with voice/display, develop proxy independently. When proxy is disabled, voice must still work.
- Do not flash, erase NVS, change boot partitions or overwrite stable voice firmware without a confirmed reversible procedure.

## Evidence levels

- OFFICIAL: vendor / protocol / Espressif documentation.
- UPSTREAM: inspected repository source or upstream tests.
- CI VERIFIED: tests/builds actually completed on our branch.
- 4B VERIFIED: tests actually completed on target hardware with logs.

A lower evidence level must never be described as a higher one.
