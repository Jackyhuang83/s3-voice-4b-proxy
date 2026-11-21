# P3-2 — Wi-Fi STA IPv6 SLAAC + IPv6-only VPS transport

**GDGS stage plan remains fixed: P3 exactly 3 PRs.** P3-1 40% merged; **P3-2 35%** is this PR; P3-3 25% is the final double-protocol/failure acceptance PR.

## Official docs and reused code

- ESP-IDF 5.5 [lwIP IPv6](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32s3/api-guides/lwip.html): supports SLAAC via Router Advertisement, stateless DHCPv6 DNS and RDNSS, BSD AF_INET6/getaddrinfo. **Stateful DHCPv6 is not supported**, so this stage only claims RA/SLAAC upstream networks.
- ESP-IDF [esp-netif IPv6](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32/api-reference/network/esp_netif_programming.html): `esp_netif_create_ip6_linklocal(esp_netif)`, `IP_EVENT_GOT_IP6`, `esp_netif_get_ip6_global`.
- Official [ESP-TLS](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32s3/api-reference/protocols/esp_tls.html) still owns TLS connection, DNS, certificate validation and SNI on VLESS. **Never replace ESP-TLS with a hand-written TCP+TLS handshake to force IPv6.** AAAA-only resolver output naturally selects IPv6 when lwIP IPv6 support is enabled.
- SS2022: reuse P2 unchanged pinned `rlog` BLAKE3/AES-GCM core and [official shadowsocks-rust v1.25.0 image](https://github.com/shadowsocks/shadowsocks-rust/pkgs/container/ssserver-rust). Add only `AF_UNSPEC` / `getaddrinfo` and IPv6-first address iteration in existing `s3_ss2022_link.c`.

## Upstream IPv6 state / failure logic

1. **STA only**: on `WIFI_EVENT_STA_CONNECTED` call `esp_netif_create_ip6_linklocal(s_sta_netif)`. Register `IP_EVENT_GOT_IP6`; only a **global, preferred** address confirmed by `esp_netif_get_ip6_global(s_sta_netif)` marks STA IPv6 ready. Never create an IPv6 link-local on `s_ap_netif`.
2. **IPv6-only can start the proxy**: `s_has_upstream = s_sta_has_ipv4 || s_sta_has_ipv6`. A global IPv6 without IPv4 suffices; on STA disconnect reset both state flags, leave P1 TCP interception enabled and refuse direct traffic. A link-local IPv6 alone does **not** count as an internet route.
3. Temporary ESP-IDF config enables `CONFIG_LWIP_IPV6`, `CONFIG_LWIP_IPV6_AUTOCONFIG`, `CONFIG_LWIP_IPV6_DHCP6` (stateless DNS) and 2 RDNSS servers. DNS resolver changes remain ESP-IDF/lwIP-managed. This code does not create a custom DNS64, NAT64 or RA server.
4. AP remains IPv4 DHCP/DNS/transparent TCP only, and does not advertise IPv6 prefixes. The upstream SS2022/VLESS IPv6 VPS dial is an **outbound socket owned by the device**, not a new downstream AP IPv6 router. P4 must confirm actual packets/hardware before declaring no IPv6 leakage.

## SS2022 IPv4 node migration and address policy

- Existing P2 `server_ipv4[16]` node field becomes `server_host[254]`, enabling literal IPv4, literal IPv6 (including bracket-free `::1`) or a valid DNS hostname with AAAA/A. This is a **v2 NVS schema** stored under key `node_v2`.
- `s3_ss2022_node_load` reads v2 first; if absent, reads the original `node` record into the old struct and returns a valid in-memory v2 copy **without overwriting the old credential**. A subsequent `s3_ss2022_node_store` commits v2 and erases v1 in the **same NVS transaction**, and `s3_ss2022_node_clear` clears both.
- The original physical USB serial command syntax remains `ss2022 <server IPv4|IPv6|hostname> <port> <base64 PSK>`. No production key in GitHub; the plaintext-NVS issue remains a **P4 release blocker**.
- Only the **configured proxy-node hostname** is resolved. Use `getaddrinfo`/BSD sockets `AF_UNSPEC`, prefer IPv6 candidates; if IPv6 fails but the same proxy hostname also has IPv4, attempt **that same node's A record**. Never fall back to direct client destination. IPv6-only proxy with no route fails closed.
- VLESS hostname stays a DNS certificate identity (not a raw IPv6 address), with verified ESP-TLS. The AAAA-only A/AAAA test doesn't disable SNI or certificate checks.

## CI test evidence tiers

- **Node/NVS:** host ASan/UBSan tests verify IPv6 literal, AAAA hostname, invalid host/key rejection, old IPv4 node migration, clear v1/v2, retention of PSK.
- **Real IPv6-only SS2022 service:** run fixed official `ssserver-rust` on `[::1]:18450`, connect actual production C and validate authenticated TCP echo, DNS via TCP, wrong key, server shutdown no-direct. Also run a separate v4 official server on `127.0.0.1:18449`; dual-stack `s3-dual.test` resolves both `::1` and `127.0.0.1` to verify same-proxy IPv4 fallback.
- **Real IPv6 TLS peer:** run the production VLESS C adapter linked to the host OpenSSL-backed ESP-TLS shim against an IPv6-only `[::1]` server with `vless.test` AAAA from /etc/hosts, valid ephemeral SAN chain and negative CA/SNI/TLS cases.
- **Device compile:** verify P1 patches + P2 + P3-1 + P3-2 precise source injections and build full ESP32-S3 R8N16 with SLAAC and ESP-TLS.
- **Not yet verified:** live Wi-Fi 6/4B network driver behavior, RA/default-route lifetime, VPS IPv6 public routing/GFW, AP leakage, audio, LCD, NVS encryption and device resource pressure. These cannot be substituted with localhost CI. P3-3 covers more automated dual-protocol resilience; P4 covers hardware and product security.

## Validation status

**PENDING** until PR Actions host tests and firmware compilation pass and the PR merges. No real device flashed.
