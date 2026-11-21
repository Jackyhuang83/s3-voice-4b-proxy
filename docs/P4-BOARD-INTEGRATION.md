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

## Outstanding P4-1 implementation gates

- [ ] **Compile**: full Xiaozhi 4B build with both transport libraries under its required IDF version.
- [ ] **Runtime design**: one-owner Wi-Fi STA/AP and netif lifetime; implement selected P1 IPv4 transparent TCP flow hook without overwriting Xiaozhi voice startup.
- [ ] **Fail-closed routing**: do not let the Xiaozhi voice upstream request start a plaintext or direct bypass of a protected proxy flow. Clarify Xiaozhi server (voice) traffic vs AP client traffic.
- [ ] **Compatibility**: preserve XiaoZhi UI/audio/OTA/asset partition and require a bounded PSRAM/task/stack budget, IDF 6.x-compatible intercept.
- [ ] **Recovery**: documented read-only snapshot and independent stable firmware recovery proof before authorizing any hardware flash. No guessed factory-partition recovery.
- [ ] **Build**: end-to-end single image full integration and source checks, not a demo with inactive C libraries.

P4-2 later performs actual STA RA + public IPv6, AP client IPv4 TCP/DNS/no-leak traces, reboot, LCD/audio and load tests. P4-3 later implements NVS encryption and release-grade security and performance signoff.

**NOT RUN**: real device, battery/power cycle, real VPS, original voice baseline on user's unit, real Wi-Fi AP, NVS secret encryption, flash or eFuse changes.
