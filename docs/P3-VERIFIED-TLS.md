# P3-1 — VLESS TCP over official verified ESP-TLS

**Plan scope: P3 exactly 3 PRs — P3-1 40%, P3-2 35%, P3-3 25%.** No extra PR for CI repairs. P0/P1/P2 accepted baseline is pinned to `yanxke/ESP32-VPN-Transparent-Proxy-Router@dfb04b03154cfaee1d8615e4b8942dfe737abc5d` and the merged P1/P2 GitHub revisions.

## Official references and reuse

- Espressif [ESP-TLS v5.5 ESP32-S3](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s3/api-reference/protocols/esp_tls.html), including `esp_tls_init`, `esp_tls_conn_new_sync`, `esp_tls_conn_read`, `esp_tls_conn_write`, `esp_tls_conn_destroy`, `esp_tls_get_conn_sockfd` and `esp_tls_get_bytes_avail`.
- Espressif official CA certificate bundle `esp_crt_bundle_attach`, `common_name` (server SNI/peer name) and `skip_common_name=false`; `CONFIG_MBEDTLS_CERTIFICATE_BUNDLE=y` is added only to the temporary R8N16 CI checkout.
- Existing upstream `transport_tcp.c` wire format: `version 0 | UUID16 | addonlen 0 | TCP1 | target port | domain address`. We reuse upstream's `transport_tcp_uuid_to_bytes()` and the same `transparent_tcp` original destination flow table; do not import Xray/Reality/TLS code or write TLS handshake logic.
- VLESS protocol framing: [Xray-core documentation and source](https://github.com/XTLS/Xray-core); **Reality and xtls-rprx-vision are NOT supported by this P3-1 implementation**. Server must provide **standard TLS** with a publicly trusted certificate. Existing Reality nodes do not qualify.

## Implementation / security boundary

1. New `components/s3_vless_tls` module uses the official ESP-TLS stack for certificate chain trust and SNI/SAN identity. `vless_host` must be a DNS hostname whose certificate matches; do not accept a numeric IPv4 literal or allow `skip_common_name=true`. P3-2 will cover IPv6-only AAAA and any separate endpoint/SNI requirements.
2. `tools/apply_p3_vless_tls.py` inserts a TCP-only VLESS adapter at the beginning of the existing `transparent_client_task` BEFORE legacy transport and retains the original flow lookup. No TLS establishment / UUID errors lead to direct fallback.
3. VLESS DNS is sent through the same verified TLS connection and VLESS TCP/53 with TCP DNS framing, never the old unencrypted `dns_vless_query` or direct UDP. TLS/DNS failure returns existing P1 `SERVFAIL` while explicitly entered setup mode retains Captive Portal.
4. All legacy plain VLESS domain/IPv4 open functions, internal mux/raw XUDP test path and direct UDP test path are gated in TCP-only builds. The unchanged upstream default build has no such restriction.
5. Limit TLS connections to two, keep 2048-byte I/O in PSRAM, require sensible time for certificate validation, restrict handshake timeout to 10 seconds and no unlimited read/write loops. Destroy the ESP-TLS handle on ALL failure paths. No node credentials are written to logs.
6. `s3_vless_tls_dns_query` validates DNS transaction ID and QR before forwarding a TLS-authenticated reply; if any step fails, preserve original packet bytes.

## Validation tiers

- Host: compile the **real production ESP-TLS adapter C** against a minimal header-compatible host shim that delegates actual TLS crypto and CA/SNI/SAN verification to OpenSSL. A Python VLESS test peer uses freshly generated temporary certificates (never a live API key), verifies TCP response and DNS, rejects untrusted CA / wrong SAN / numeric host / invalid VLESS header / connection failure. This tests byte-level logic + PKIX on host, not ESP-TLS firmware runtime.
- Static: assert no unsafe raw VLESS/direct fallback and that both TCP and DNS select the verified TLS adapter; check P1/P2 guards intact.
- Target: compile full patched ESP32-S3 R8N16 PlatformIO/ESP-IDF firmware with certificate bundle enabled, requiring actual official ESP-TLS APIs and all P1/P2 modules to link.

## Known limitations and next PRs

- P3-1 is **standard verified TLS**, not VLESS Reality; no WARP, HY2, XUDP or unencrypted TLS exceptions.
- No physical 4B has been flashed. No true ESP32 TLS handshake, RAM high-water test, STA IPv6, IPv6-only VPS, or concurrent voice/display testing is claimed.
- P3-2: support STA IPv6 address/routing and AAAA-backed IPv6-only VPS on SS2022 and VLESS; keep AP IPv4-only, add mock IPv6-only tests.
- P3-3: dual protocol/both address families peer interoperability, expired/untrusted cert, DNS & break/fail-closed matrix, P3 phase exit.
- P4 remains production release-blocked until unencrypted SS2022 NVS credentials, Wi-Fi/AP default passwords, firmware recovery, runtime security and actual 4B/Xiaozhi integration are verified.

## Current acceptance

**PASS / MERGED（源码、真实 host TLS 功能和 ESP-IDF 固件构建）**

- [PR #11](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/11) 已 Squash Merge 到 `main`，Commit `43befc6cc0a4a13431976f79ef1114ddc41ff9fe`。
- [P3-1 GitHub Actions](https://github.com/Jackyhuang83/s3-voice-4b-proxy/actions/runs/44880564684) `success`：实际生产 C 模块通过 host OpenSSL 证书链/SNI/SAN 测试、VLESS/TCP 回显和加密 DNS；错误 CA、错误 hostname、没有服务器、无效 VLESS 响应和数字 IP hostname 均 fail-closed。
- P1 四份补丁、P2 适配器与本次 P3-1 的精确源码集成、明文路径禁用、证书校验强制断言通过；**修改后完整 ESP32-S3 R8N16 PlatformIO/ESP-IDF 固件编译成功**。
- PR #11 Head SHA 上 **8 项 CI 工作流全部 success**（包括 P0/P1/P2 完整回归）。
- **P3-1 = 40% of P3 已验收**；P3-2 IPv6-only VPS/P3-3 双协议双栈与 P4 真实 4B、NVS 加密、音频/LCD、部署安全均 NOT RUN。
