# P1 minimum TCP-only ingress patch — evidence and limitations

Status: proposed patch in PR; **CI or 4B packet-level result not yet established**.

## Source reuse

- Pinned original router commit: dfb04b03154cfaee1d8615e4b8942dfe737abc5d, MIT.
- Original IPv4 TCP intercept/reply tuple handling remains in src/transparent_tcp.c, plus the Wi-Fi/STA/AP/DHCP/local DNS architecture.
- The added patch only changes the existing packet ingress hook; no new TCP protocol/router implementation and no new node UI.
- CI clones the exact original revision, verifies and applies the patch, enables S3_PROXY_TCP_ONLY=1 for esp32s3_r8n16, then compiles; original upstream source remains unmodified in its repository.

## Intended packet behavior when S3_PROXY_TCP_ONLY=1

| AP packet | Intended behavior |
|---|---|
| IPv4 TCP to a remote host | Preserve existing transparent TCP handling |
| IPv4 UDP to the AP gateway (local DNS and services) | Preserve local handling |
| DHCP request from source UDP/68 to destination UDP/67 | Preserve AP lease handling |
| Other AP-sourced UDP, including QUIC to Internet UDP/443 | Drop before XUDP association creation |
| IPv6 packets from AP clients | Not supported; downstream stays IPv4-only |
| IPv6 control-plane of upstream Wi-Fi STA | Not processed by this IPv4 AP packet hook |

## Short UDP packet correction

The original upstream hook required a minimum 40-byte packet before interception. A valid IPv4 UDP header can be only 28 bytes (20 IP + 8 UDP), so the minimal TCP-only patch changes initial IPv4 header copy to bounded 20–40 bytes and preserves UDP destination-port parsing. This avoids the obvious 28–39-byte bypass of the UDP guard.

## Explicit limitations / future tests

- The gate intercepts AP IPv4 ingress only. A successful patched build and static source assertions do **not** prove no UDP leakage under all AP/STA conditions.
- UDP/XUDP/smux code may remain compiled and configured but is unreachable for normal non-local AP-originated UDP packets in TCP-only mode; full removal is not required for MVP and would raise regression risk.
- Original code still has edge cases requiring P1 review: IPv4 header options, fragment handling, malformed packet policy, enabled/disabled mode and fail-closed on outage. Do not announce security proof without packet-level tests.
- Local DNS service and DHCP must be tested with a real AP client later. No Internet UDP proxying is in scope.
- The patch does not implement SS2022, VLESS TLS, IPv6 VPS entry, nor S3-Voice integration.

## Next acceptance gate

1. Patch applies to pinned source with zero fuzz and builds under PlatformIO.
2. Source quality check passes; inspect the precise diff and ensure DHCP/local DNS control flow remains before the drop.
3. Add host tests covering synthetic short/normal UDP packets, DHCP and AP-local DNS if feasible with a lwIP test fixture.
4. Later, actual 4B packet capture/behavior test proves TCP works, Internet UDP/QUIC fails closed, and local DNS/DHCP work.

Never force a device flash or remove a stable firmware to prove a capability already checkable by source/CI.

## PR #6: fail-closed route-mode follow-up

- Audited upstream `src/main.c` at pinned SHA and confirmed direct/upstream mode can be selected via a physical BOOT short press, authenticated management POST and serial command.
- An additive compile-guarded patch in `patches/0002-tcp-only-enforce-no-direct-route.patch` rejects selections of `TRANSPARENT_MODE_UPSTREAM` in `S3_PROXY_TCP_ONLY` builds.
- When upstream STA disconnects, TCP-only build keeps the AP ingress interception enabled rather than switching the packet hook off; local DHCP/AP services remain allowed by the existing hook.
- The release-mode guard deliberately does not alter the original upstream project or its default builds.
- Compilation/static checks do not certify the end-to-end kill switch: unhandled IPv4 fragments, flow table exhaustion, DNS behavior, and all physical Wi-Fi packet paths still require dedicated review/tests.
- This patch remains a P1 safety improvement; it adds neither SS2022, encrypted VLESS, IPv6 VPS support nor flashing instructions.
