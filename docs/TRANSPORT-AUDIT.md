# P0 Transport API and Minimal-Patch Audit

Evidence date: 2026-11-21. Source inspection only; no modified firmware, IPv6-only, SS2022, TLS or 4B acceptance is claimed.

## Verified upstream reproducibility

- Original yanxke revision dfb04b03154cfaee1d8615e4b8942dfe737abc5d compiled for esp32s3_r8n16 in GitHub Actions PR #2.
- This is only an unmodified upstream build. It is NOT the 4B voice-integrated firmware.

## Real packet-to-proxy path (yanxke)

1. src/transparent_tcp.c performs lwIP IPv4 hook interception, packet tuple rewrite and flow tracking.
2. src/main.c uses recovered DNS / Host / TLS SNI when possible, then invokes transport_tcp_open_domain() or transport_tcp_open_ipv4().
3. src/transport_tcp.h exposes int socket-descriptor-returning outbound calls; src/transport_tcp.c sends a VLESS UUID + destination header and relays via select(), send(), recv().
4. src/router_config.h presently stores one VLESS host/UUID/port, Wi-Fi parameters and singmux_enabled. Runtime mode enum also exposes a direct upstream mode.

Primary source: https://github.com/yanxke/ESP32-VPN-Transparent-Proxy-Router/blob/dfb04b03154cfaee1d8615e4b8942dfe737abc5d/src/transport_tcp.h
Other source: https://github.com/yanxke/ESP32-VPN-Transparent-Proxy-Router/blob/dfb04b03154cfaee1d8615e4b8942dfe737abc5d/src/transport_tcp.c

## SS2022 reusable protocol layer (rlog)

- muse_ss2022.c exports ss2022_cipher_init, ss2022_request, ss2022_payload, ss2022_feed; uses upstream BLAKE3 and PSA AES-GCM.
- muse_proxy.c creates application-specific listeners and task bridges; dial() currently uses an AF_INET socket and IPv4 literal.
- Reuse the protocol core only and generalize its target header/connection logic. Do not copy Muse audio, app registration, or custom UI code.

Source: https://github.com/rlog/atoms3r-muse-firmware/blob/57f73602e963e478e06eae5f8108d07495468031/esp32/components/muse/muse_ss2022.c
Dial source: https://github.com/rlog/atoms3r-muse-firmware/blob/57f73602e963e478e06eae5f8108d07495468031/esp32/components/muse/muse_proxy.c

## Smallest viable implementation (PROPOSAL, not yet built)

- Keep one original lwIP IPv4 interception/flow engine. No duplicate NAT, flow table, DHCP, or DNS subsystem.
- Add a small outbound TCP stream adapter for selected VLESS+authenticated TLS or SS2022+AEAD; target domain/IP and port flow in from existing captured TCP flow.
- Outbound abstraction must own connect, read, write, close, partial I/O, errors, bounded buffers and resource cleanup.
- ESP-TLS uses authenticated TLS state, not a raw socket descriptor. Existing select/send/recv assumptions must be redesigned at the outbound boundary; pending decrypted SSL bytes must be handled.
- Add AF_INET6 VPS dialing via IPv6 literal or explicit AAAA getaddrinfo(AF_INET6). STA must have global IPv6/default route and actual TCP reachability.
- Enabling CONFIG_LWIP_IPV6 in the STA stack MUST NOT advertise/route IPv6 to the AP clients. The AP stays IPv4-only.
- Do not turn on plaintext VLESS for Internet production. Do not expose credentials through GitHub/NVS/CI.
- Exclude Internet UDP/XUDP/QUIC without breaking DHCP/local DNS or IPv6 SLAAC/router advertisements. No automatic proxy failure fallback to direct Internet.

## Remaining engineering gates

| Gate | Description | State |
|---|---|---|
| G0 | Pinned original R8N16 CI build | PASSED in PR #2 |
| G1 | Integration boundary and risks from inspected sources | DOCUMENTED here |
| G2 | Modified TCP-only firmware builds and regressions | NOT RUN |
| G3 | SS2022 independent test vectors + VPS interop | NOT RUN |
| G4 | VLESS TLS + IPv6-only VPS tests for both protocols | NOT RUN |
| G5 | Target 4B voice/display/Wi-Fi hardware acceptance | NOT RUN |

Before implementing any behavior-changing patch: search upstream issues/PRs/tests and official Espressif API docs for the exact versions, then record evidence and test/rollback plan in that PR.
