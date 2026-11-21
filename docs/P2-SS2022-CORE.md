# P2-1 — SS2022 TCP protocol component: provenance and verification

**Scope:** only the SIP022 TCP subset `2022-blake3-aes-128-gcm`, using one 16-byte PSK and bounded plaintext buffers. The protocol component is not wired to Wi-Fi routing yet. No production credentials, real device or VPS endpoint are needed.

## Fixed development roadmap (unchanged)

| PR | Weight within P2 | Delivery | Acceptance |
|---|---:|---|---|
| P2-1 | 30% | Isolated upstream component, BLAKE3/PSA dependencies, licenses and reference vectors | Host tests + ESP-IDF/PlatformIO build |
| P2-2 | 40% | Join SS2022 TCP transport to existing transparent IPv4 flow/relay interfaces | Modified firmware compiles, stream lifecycle tests |
| P2-3 | 30% | IPv4 real/protocol test-server interoperability, wrong key, replay/time, interruption and fail-closed | Automated end-to-end protocol tests + P2 exit record |

## Audited source provenance

- Core: `rlog/atoms3r-muse-firmware` at exact commit `57f73602e963e478e06eae5f8108d07495468031`, source files `esp32/components/muse/muse_ss2022.{c,h}`. SPDX Apache-2.0, full `LICENSE-Apache-2.0` and root `NOTICE-upstream` copied.
- Crypto: that repository's BLAKE3 1.8.2 portable source, `blake3.{c,h}`, `blake3_impl.h`, `blake3_dispatch.c`, `blake3_portable.c`; CC0/Apache-2.0 license choices and original README copied. Original code and notices are unmodified.
- `components/s3_ss2022/VENDOR.json` pins upstream git blob SHA-1 values, checked by `tools/check_ss2022_vendor.py` every CI run. The only newly authored build glue is `CMakeLists.txt`; Muse UI, voice, boards, menu, proxy listener, and app-level configuration are deliberately not imported.
- Reference core: https://github.com/rlog/atoms3r-muse-firmware/tree/57f73602e963e478e06eae5f8108d07495468031/esp32/components/muse
- Protocol: https://shadowsocks.org/doc/sip022.html
- Official ESP-IDF PSA/MbedTLS: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/protocols/mbedtls.html
- Upstream Muse `PROXY.md` confirms client scope and documents tests; searched rlog GitHub issues/PRs for SS2022 but did not find project-specific published results. Source inspection and independent CI are used rather than assuming existing tests pass.

## Actual component API (P2-1 only)

`ss2022_cipher_init()` derives a per-direction session key using BLAKE3 KDF with PSK||salt and imports an AES-128-GCM key through PSA. `ss2022_request()` serializes the authenticated request salt/type/timestamp/destination header, `ss2022_payload()` creates AEAD TCP frame length/body pairs, and `ss2022_feed()` incrementally decrypts/authenticates server chunks. `ss2022_cipher_free()` destroys PSA keys and wipes key context.

**The host test oracle is independent:** a Python `blake3` derive-key implementation + `cryptography.AESGCM` generates deterministic SIP022 wire bytes; the built production C core must match them byte-for-byte. Fragmented responses, invalid authentication tags, wrong key/salt, timestamps beyond ±30 seconds, max TCP frames and error paths are checked. Both test libraries are version-pinned in CI.

## Component/build isolation

- CI compiles original core on Linux via MbedTLS PSA with ASan/UBSan; the same isolated component is copied into a temporary pinned P1 R8N16 ESP-IDF build and compiled with the MCU toolchain.
- P2-1 **does not** change src/main.c, transport_tcp.c, lwIP routing, credentials, NVS, upstream DNS or any deployed firmware.
- P2-2 will attach SS2022 authenticated TCP streams through the already existing transparent TCP flow table; P2-3 must independently prove real IPv4 proxy server interoperability and fail-closed behavior.

## Security, resource and remaining gaps

- **Memory:** `ss2022_rx_t` contains `wire[65551]` and `plain[65535]` (~128 KiB before overhead). This is unsuitable for scarce ESP32 internal RAM or FreeRTOS task stacks. In P2-2 allocate the RX context in PSRAM, keep a strict connection cap and monitor heap/PSRAM high-water marks before 4B voice/display integration.
- **Key:** require strictly decoded 16-byte PSK. Never log PSK or leave real keys in GitHub. Current component does not implement identity-key extensions.
- **Clock:** SIP022 requires accurate Unix epoch; P2-2 must gate request creation on SNTP success and generate unique salts with secure ESP-IDF entropy. Do not substitute fabricated timestamps.
- **No client replay pool:** server must enforce request-salt replay protection; the TCP client validates server timestamp and request-salt binding. This is not a server implementation.
- **Unsupported:** 2022 AES-256-GCM, other SS variants, Internet UDP/QUIC/XUDP, Reality, Snell, direct-bypass fallback, downstream IPv6.
- **Not yet tested:** actual outbound dial on 4B, a real SS2022 VPS, concurrent voice/LCD memory pressure, high connection load, IPv6-only VPS (P3). Do not claim these from a green P2-1 CI.

## Acceptance record

- [PR #8](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/8) merged (squash SHA `4864ea76800d220ba09c42c8210705d874a56bd8`).
- [P2-1 Actions run](https://github.com/Jackyhuang83/s3-voice-4b-proxy/actions/runs/44876562792) **success**: vendored Git blob/hash and license audit, MbedTLS PSA host compilation, independent Python BLAKE3/AES-GCM request/payload vector tests, signed timestamp/salt binding, malformed authentication and fragmented response negative tests, maximum frame and error bounds.
- Isolated SS2022 component built in pinned ESP32-S3 R8N16 PlatformIO/ESP-IDF firmware (success). It is compiled, **not selected or called** by transparent TCP routing yet.
- Existing P0/P1 CI checks on PR #8 HEAD also completed with success.
- **P2-1 acceptance = PASS (30% of P2)**; P2-2 TCP routing integration and P2-3 IPv4 server interoperability are **NOT RUN**; P4 real hardware **NOT RUN**.
