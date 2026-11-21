# P4-1 | Waveshare ESP32-S3-Touch-LCD-4B voice-first integration evidence

Status: **OPEN / partial source integration; P4-1 acceptance NOT YET MET**. This is not a flashable release.

## Pinned reuse and independent evidence (2026-11-21)

| Resource | Pinned or verified basis | Reuse decision |
| --- | --- | --- |
| Hardware | [Waveshare 4B](https://docs.waveshare.com/ESP32-S3-Touch-LCD-4B), [first-party board source](https://github.com/waveshareteam/ESP32-S3-Touch-LCD-4B), [pin audit](https://github.com/waveshareteam/ESP32-S3-Touch-LCD-4B/blob/main/hardware/pin-audit.md) | Exact board **ESP32-S3-Touch-LCD-4B**, not 4.3B/4.3C |
| Voice app, board, LCD and audio | [78/xiaozhi-esp32 at 831ffd14188553cc887408b75396ae38618538e0](https://github.com/78/xiaozhi-esp32/commit/831ffd14188553cc887408b75396ae38618538e0) | **Primary application**. Keep board initialization, display, codec, device AEC, OTA and asset code intact |
| ESP-IDF | Xiaozhi main/idf_component.yml requires **>=6.0.1**, official CI uses espressif/idf:release-v6.1 | Use an isolated IDF 6.1 CI build, **do not assume** P3 router's toolchain or ABI is compatible |
| Protocol code | Local pinned s3_ss2022 and s3_vless_tls components, already covered by P2/P3 tests | Copy and link for a **compile-only API/ABI compatibility gate**, no Wi-Fi/AP activation |
| Router source | yanxke/ESP32-VPN-Transparent-Proxy-Router at dfb04b03154cfaee1d8615e4b8942dfe737abc5d | Keep the P1 transparent IPv4 TCP model, but do not start a second Wi-Fi stack or transplant its entry-point into Xiaozhi |

## Hardware and resource boundary (from official board sources)

- **ESP32-S3-WROOM-1-N16R8**: 16 MiB Flash, 8 MiB PSRAM, 2.4 GHz Wi-Fi; 4-inch 480 x 480 ST7701 RGB screen, GT911 touch.
- ES7210 microphone front-end + ES8311 codec, 24 kHz I2S and device AEC enabled in the 4B Xiaozhi board config. MCLK=GPIO5, WS=7, BCLK=16, DIN=15, DOUT=6.
- AXP2101 PMIC, TCA9554 IO expander, shared I2C SDA=GPIO47/SCL=GPIO48, RGB display double framebuffers in PSRAM and backlight GPIO4.
- All board-specific initializers are owned by Xiaozhi. The proxy must not claim pins, initialize them independently, or overtake the voice networking tasks without a resource budget and regression.

## Critical conflict: partition layouts cannot be mixed

| | P3 proxy router proof | Official Xiaozhi voice baseline |
| --- | --- | --- |
| app slot 0/1 | 0x500000 each (5 MiB) | **0x3f0000 each (3.9375 MiB)** |
| firmware partition table | upstream router partitions.csv | Xiaozhi partitions/v2/16m.csv |
| voice assets | not part of router proof | **8 MiB SPIFFS assets starting 0x800000** |
| rollback | router dual OTA | Xiaozhi dual OTA + ESP-IDF rollback configuration |

**Never apply the P3 layout to an installed Xiaozhi board.** Even an apparently successful application-only write cannot prove OTA / assets / credential preservation. The Xiaozhi 4B board code attempts a switch to a factory partition on a key action; the pinned 16m.csv **has no factory app entry**, so that is NOT a demonstrated recovery route.

## Current PR deliverable and exact claim

1. Source preflight checks exact upstream Git SHA, board ID, LCD/audio pins, AEC selection, PMIC/touch/codec constructors, upstream IDF minimum, partition and voice source invariants.
2. Protocol C components are copied into an **ephemeral CI checkout only**; the Xiaozhi main component is linked to them via a single guarded CMake addition. Voice board source, SDK defaults, OTA layout, assets and upstream entry point remain unchanged.
3. CI must build the real selected 4B Xiaozhi variant on IDF 6.1. Build binaries remain in CI workspace and **must not be published as flashable images**.
4. If any source pin or partition invariant changes, fail early. Do not silently update to newer upstream source or change partitions merely to force a green compile.

This is **not yet a functional gateway integration**. Linking SS2022 / VLESS library code alone does not connect to the existing lwIP IPv4 flow table, DNS service, STA IPv6 events or the device Wi-Fi AP. A complete P4-1 requires the voice-first runtime adapter plus a full integrated build and documented rollback preconditions. P4-1 remains **0% until its full PR is merged**.

## Verified voice networking and credential lifecycle blockers

The pinned upstream voice source has one existing **WifiManager** in
main/boards/common/wifi_board.cc: StartNetwork() calls Initialize() / StartStation(),
while StartWifiConfigMode() uses StartConfigAp() for provisioning. **That
provisioning AP is not an Internet forwarding AP.** The proxy cannot launch
a second esp_wifi_init/esp_wifi_start owner, replace the provisioning event
callback, or keep a gateway AP running during recovery without an explicit
shared-state design. Prefer an opt-in service layered on the existing
WifiManager event lifecycles; treat configuration mode as gateway-disabled
and fail closed.

The pinned main/main.cc also calls nvs_flash_erase() if nvs_flash_init()
returns ESP_ERR_NVS_NO_FREE_PAGES or ESP_ERR_NVS_NEW_VERSION_FOUND. On an
existing voice device, never assert that an untested firmware switch
preserves credentials merely because the partition CSV stays unchanged.
P4 requires a non-destructive NVS snapshot/restore strategy and explicit
handling of schema incompatibility before any hardware operation.

References:
- https://github.com/78/xiaozhi-esp32/blob/831ffd14188553cc887408b75396ae38618538e0/main/boards/common/wifi_board.cc
- https://github.com/78/xiaozhi-esp32/blob/831ffd14188553cc887408b75396ae38618538e0/main/main.cc
- https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/wifi.html

## Follow-on source security patches (not hardware validation)

The P4-1 CI assembly now makes **two exact-match, temporary source changes** that are
not present in the pinned Xiaozhi checkout and are intentionally checked:

1. The upstream app_main() can call `nvs_flash_erase()` on NVS_NO_FREE_PAGES or
   NVS_NEW_VERSION_FOUND. The isolated integration build replaces only that
   destructive recovery branch with an error log and a halted startup. This
   **prevents automatic erasure** of old Wi-Fi credentials but is NOT yet a
   migration / backup solution. The original upstream and user's device are
   untouched.
2. ESP-IDF 6 has a documented IPv4-only `getaddrinfo(AF_UNSPEC)` case. To
   protect IPv6-only node dialing, the isolated build sets
   `CONFIG_LWIP_IPV6=y`,
   `CONFIG_LWIP_IPV6_AUTOCONFIG=y` and
   `CONFIG_LWIP_USE_ESP_GETADDRINFO=y` in its ESP32-S3 target defaults. CI
   checks the **resolved** sdkconfig, not just the presence of input text.
   Source compilation is insufficient to prove real Wi-Fi IPv6 RA, DNS AAAA,
   route selection, or ESP32-S3 network service operation.

References: [ESP-IDF lwIP API and limitations](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/lwip.html),
[ESP32-S3 STA/AP official driver mode](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/wifi-driver/overview.html).

## P1 router core compatibility gate (isolated only)

The same P4-1 PR now imports **only** `transparent_tcp.c/.h` from the
original pinned yanxke TCP engine, **after** applying the existing P1 four
patches with Git exact-context checks. The MIT license is copied with the
component, and strict source guards reject unpatched source. The ESP-IDF 6.1
Xiaozhi 4B CI compiles this core along with the existing SS2022/VLESS
components. This detects cross-IDF C API drift while keeping one voice app,
one existing WifiManager and the original OTA and resource partitions.

**Deliberate safety limit:** the lwIP input hook is not enabled, the TCP
relay server is not started, no AP forwarding configuration is modified,
and no proxy credential is added. Successfully compiling this core does
**NOT** demonstrate gateway functionality. Runtime wiring and a full
fail-closed gateway lifecycle remain mandatory *within this same PR*
before P4-1 is eligible to merge.

## P4-1 voice-owned connection lifecycle policy (host-negative-tested)

The initial compile-only proof is now augmented with a small reusable
s3_gateway_policy C11 component that consumes **the existing Xiaozhi
WifiBoard::OnNetworkEvent events**: STA connected/disconnected, provisioning
AP enter/exit. All policy mutations use 32-bit atomic compare/exchange so
asynchronous Wi-Fi notifications cannot accidentally re-arm routing.

The downstream decision matrix allows only AP-local DHCPv4 (68→67) and
AP-local DNS (53) without upstream authorization. External TCP is
intercept-eligible **only** after station online, validated node, live
relay worker and explicit administrator arm; internet UDP/QUIC, ICMP,
non-DNS AP-local management and all untrusted transitions are denied.
STA disconnect, switching to configuration mode, relay failure or node
invalidity immediately clear arm/readiness, and recovery never auto-arms.

**Crucial scope boundary**: only STA/provisioning events are wired today.
There is intentionally **no code path issuing NODE_VALIDATED, RELAY_READY
or ADMIN_ARM on the 4B**, and no AP data plane or lwIP hook starts.
This prevents premature exposure while the single-owner APSTA service
and encrypted relay wiring are developed in this same PR. Host tests
validate the policy, but no on-device isolation or forwarding has passed.

## Official ESP-IDF AP-only lwIP hook (build gate pending)

The isolated voice-first build now contains a real
`ESP_IDF_LWIP_HOOK_FILENAME` IPv4 input hook. It always returns
`0` without inspecting traffic if no gateway AP netif is explicitly bound:
Xiaozhi voice/OTA traffic on STA is unchanged. If an authorized AP is
eventually bound, malformed or fragmented IPv4, UDP/QUIC, ICMP, other
AP-local services and unauthorized external TCP are consumed and dropped.
Only AP-local DHCP/DNS traffic is passed to lwIP; authorized TCP goes
through P1's patched, bounded transparent TCP engine, never direct.

The global cold-off policy is shared between the original Xiaozhi
`WifiBoard::OnNetworkEvent` callbacks and this hook. The ESP-IDF CMake
change is limited to an *isolated CI checkout* and follows the official
component-level hook mechanism. CI must prove the lwIP compile command
actually contains the hook definition, not just that the header exists.

**Safety boundary:** nobody calls `s3_gateway_lwip_bind_ap` yet.
No AP is started, DNS listener/relay are not started, P1 AP output tuple
rewrite is not installed, and IPv6 AP suppression is not yet verified.
This is not functional Wi-Fi forwarding. There is deliberately no
device flashing, public release or modification to an existing voice unit.

Official reference: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/lwip.html

## AP DNS fail-closed source gate

The bounded, network-free `s3_gateway_dns` C11 module checks canonical
RFC1035 queries (max 512 bytes), creates SERVFAIL answers on future
upstream/relay failure, and binds encrypted replies to the exact DNS
transaction ID plus QNAME/QTYPE/QCLASS. Invalid names, compression
pointers in questions, malformed and oversized packets are rejected.
Local C11 tests passed with AddressSanitizer and UndefinedBehaviorSanitizer
and a deterministic 100,000-input stress matrix. The PR's GitHub Actions
now repeats both host tests and builds the module in IDF 6.1.

**Not yet functional DNS forwarding:** the gateway has no active AP-local
UDP/TCP :53 listener and no calls to `s3_ss2022_dns_query` or
`s3_vless_tls_dns_query`; correct DHCP DNS offer settings (explicit in
ESP-IDF 6.1), SS2022/VLESS encrypted relay, DNS cache and AP leak-proof
packet capture remain P4-1 work.

## Encrypted DNS tunnel dispatch (source only)

`s3_gateway_dns_process` now dispatches strictly to the already-tested
`s3_ss2022_dns_query` or `s3_vless_tls_dns_query` APIs. If a node/relay
has not been authorized, the selected secure transport refuses, an upstream
response fails canonical ID/question checks, or the gateway policy is
revoked *while the request is in flight*, it produces local DNS
`SERVFAIL`. There is **no direct DNS socket or UDP fallback** in this
component. The API takes explicit, nonlogged proxy-node configuration;
it never reads or writes the 4B's existing NVS itself.

A host test mocks both encrypted APIs to cover successful SS2022/VLESS
replies, invalid IDs and questions, transport failure, missing resolver,
disabled transport, unauthorized gateway and mid-request disconnect.
This is not evidence of DNS network connectivity.

Still pending: one-owner APSTA lifecycle, secure node/SSID provisioning,
UDP/TCP DNS listeners, AP DHCP DNS option, packet capture leak checks,
live encrypted DNS/VLESS handshake, and hardware voice/audio regression.

## AP restart + IPv6 no-leak protection (source gate)

The originally pinned router flow engine was not safe to transplant unchanged
into a reusable Xiaozhi APSTA lifecycle: its static `s_enabled` starts
true, its output callbacks remain installed after stopping AP, and it
reinjects rewritten packets recursively through the project's IPv4 Hook.
In the **isolated 4B build only**, source import now uses exact-match
guards to make the P1 engine start disabled, add
`transparent_tcp_uninstall_ap_output()` (restores saved AP output and
linkoutput callbacks, nulls their old pointers, and clears bounded flow
tables), and expose `transparent_tcp_is_reinjecting()` to allow only
the internally rewritten TCP packet to traverse the project's AP-local
filter. User's existing P1/P2/P3 source and stable 4B firmware are not
modified. Uninstallation must run on the lwIP core task after active
relay workers are stopped and **before** destroying the AP netif.

Espressif 6.1 also provides an IPv6 packet input hook. The 4B build
now selects `CONFIG_LWIP_HOOK_IP6_INPUT_CUSTOM=y` and compiles a
per-interface filter: **all AP IPv6 is dropped**, including NDP and
Router Advertisements, whereas STA traffic follows the official
default rule (drop only when the interface has no link-local IPv6
address). This preserves the user's outbound IPv6-only VPS feature
instead of disabling IPv6 system-wide. This is source/build-only
protection pending hardware APSTA and IPv6 packet-capture validation.

## 78/esp-wifi-connect: single owner, no automatic NVS erase

The original Xiaozhi 4B voice app uses `78/esp-wifi-connect:~3.3.3`.
The exact upstream annotated v3.3.3 tag resolves to Git commit
`77095063d77e7705f68e95005c43ed73582233ce`.
**This is the existing Wi-Fi driver owner**, not a second driver.
The official upstream Wi-Fi manager has a separate NVS corruption
recovery path that calls `nvs_flash_erase()`; patching only Xiaozhi's
`main/main.cc` does not prove zero automatic erases in every path.
The isolated CI source now overlays the same tagged Wi-Fi component
and replaces **only** that destructive branch with a fail-closed error.

The original station scan/connection, configuration AP and
`esp_wifi_init()` ownership remain untouched. The 4B build must
prove the local, patched tagged component is the one actually compiled,
rather than silently selecting a registry-managed duplicate. No
credentials are introduced into the public repository.

**APSTA has not been enabled in this change.** Official ESP-IDF Wi-Fi
documentation says the AP interface must be enabled before calling
`esp_wifi_set_config(WIFI_IF_AP)`. Simply switching a running
station to APSTA and then configuring the AP risks briefly
broadcasting an unconfigured hotspot. The follow-on integration must
configure the AP before `esp_wifi_start()` using the existing
single-owner station startup path and explicit authorization.

## Official WPA2 + DHCP DNS prerequisite (not activated)

A small `s3_gateway_ap` component now validates WPA2 AP SSID and PSK
lengths (at least 12 password characters, at most 63) and refuses
empty, oversized or control-character-bearing credentials; no
password appears in the public repo. Host C11 edge-case tests are in
CI. Another function uses the official ESP-IDF 6.1
`esp_netif_dhcps_option` + `esp_netif_set_dns_info` APIs to send
**only the already-created `WIFI_AP_DEF` interface's own IPv4** as
DHCP option 6. The caller must start the local encrypted-DNS-backed
listener first. Passing the STA interface or an unconfigured AP fails.
On DHCP configuration failure, the helper does not advertise a
potential plaintext fallback.

This is a reusable prerequisite, **not the final APSTA lifecycle**:
it never calls `esp_wifi_init`, `esp_wifi_set_mode`, or
`esp_wifi_start`; the original Wi-Fi manager retains ownership.
An authenticated, secure AP must be configured before driver startup,
with an explicit user-authorized enable path, relay and teardown.
Do not interpret source compilation as a working hotspot.

## Outstanding P4-1 implementation gates

- [ ] **Compile**: full Xiaozhi 4B build with both transport libraries under its required IDF version.
- [ ] **Runtime design**: one-owner Wi-Fi STA/AP and netif lifetime; implement selected P1 IPv4 transparent TCP flow hook without overwriting Xiaozhi voice startup.
- [ ] **Fail-closed routing**: do not let the Xiaozhi voice upstream request start a plaintext or direct bypass of a protected proxy flow. Clarify Xiaozhi server (voice) traffic vs AP client traffic.
- [ ] **Compatibility**: preserve XiaoZhi UI/audio/OTA/asset partition and require a bounded PSRAM/task/stack budget, IDF 6.x-compatible intercept.
- [ ] **Recovery**: documented read-only snapshot and independent stable firmware recovery proof before authorizing any hardware flash. No guessed factory-partition recovery.
- [ ] **Build**: end-to-end single image full integration and source checks, not a demo with inactive C libraries.

P4-2 later performs actual STA RA + public IPv6, AP client IPv4 TCP/DNS/no-leak traces, reboot, LCD/audio and load tests. P4-3 later implements NVS encryption and release-grade security and performance signoff.

**NOT RUN**: real device, battery/power cycle, real VPS, original voice baseline on user's unit, real Wi-Fi AP, NVS secret encryption, flash or eFuse changes.
