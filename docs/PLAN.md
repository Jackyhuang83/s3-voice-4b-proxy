# S3-Voice 4B Proxy P0–P4 execution plan

R1: IPv4 transparent TCP for AP clients, SS2022 TCP / VLESS authenticated TLS.
R2: STA IPv6 socket connectivity to IPv6-only VPS; downstream AP IPv4-only.
Internet UDP, XUDP, QUIC, Snell, Reality and complete downstream IPv6 routing are excluded.

| Phase | Work package | Exit gate | Current status |
|---|---|---|---|
| P0 | Read official board and IDF sources, pin/audit GitHub upstream, inventory dependencies, record requirements and set up auditable repo/CI. | Provenance, licenses, minimal-change proposal and honest CI scaffold. Code import/build still pending. | Started |
| P1 | Reproduce main upstream ESP32-S3 build; keep AP+STA, local DHCP/DNS, IPv4 transparent TCP, fail-closed; isolate or remove Internet UDP functionality safely. | Reproducible project build + host regressions; no false claim of real Wi-Fi verification. | Not started |
| P2 | Selectively import rlog SS2022 AES128/BLAKE3 TCP core, generic TCP destination adapter, time handling and negative tests. | SIP022 vectors and IPv4 VPS interoperability tests pass, errors fail closed. | Not started |
| P3 | VLESS with certificate-validated ESP-TLS; shared IPv4/IPv6 outbound socket adapter; STA IPv6 global address and route to IPv6-only VPS for both protocols. | Automated IPv4/IPv6 tests and cert rejection tests for both protocols; AP stays IPv4-only. | Not started |
| P4 | Integrate into exact 4B voice/display baseline; preserve revert path, validate wireless AP clients and memory/performance. | Real 4B logs: TCP, IPv6-only VPS, recovery, long run, and voice/display not regressed. | Not started |

## Research-before-hardware discipline

For every new task:
1. Read official vendor, Espressif and protocol documentation for the precise board/version.
2. Inspect pinned and current GitHub source, tests, issues, PRs, releases and alternative implementations.
3. Explain which evidence is OFFICIAL, UPSTREAM, CI VERIFIED, or 4B VERIFIED; do not mix them.
4. Choose existing feature > official component > small compatibility patch > new code.
5. Run host tests/CI before any user device experiment.
6. Only if necessary, request a bounded hardware check with expected output, pass/fail threshold and safe recovery.

## Development controls

- Each change goes to a feature branch and PR; main is the accepted baseline.
- CI documentation checks are not firmware build checks.
- Each PR records exact upstream SHA, file changes, why new code is necessary, license implications, real test results and rollback.
- No real credentials in files/commits/CI. No unattended flash, partition changes or NVS wipe.
- Audio/voice system must work with proxy module switched off.

Next P0: reproduce pinned main upstream N16R8 build in controlled CI; audit dependency graph, then define small TLS/SS2022/IPv6 interfaces before touching hardware.
