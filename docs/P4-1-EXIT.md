# P4-1 — 4B source and integrated-build exit evidence

Status: **GitHub CI PASS at `e395ecbe2f4435f15f7f7a14c4a08c122309d79d`**. This is a *source/CI integration* acceptance, not 4B hardware verification or a usable Internet-sharing hotspot.

## Immutable acceptance baseline

- Pull request: [#14](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/14).
- Verified workflow: [ID 44896553617](https://github.com/Jackyhuang83/s3-voice-4b-proxy/actions/runs/44896553617), conclusion `success`. Every one of the **11/11** workflows for the same code commit is `success`.
- Upstream voice pinned: `78/xiaozhi-esp32@831ffd14188553cc887408b75396ae38618538e0`.
- Original single Wi-Fi owner pinned: `78/esp-wifi-connect@77095063d77e7705f68e95005c43ed73582233ce` (v3.3.3).
- Original router core pinned: `yanxke/ESP32-VPN-Transparent-Proxy-Router@dfb04b03154cfaee1d8615e4b8942dfe737abc5d`, with existing P1 TCP-only safety patches; original author licensing retained.
- Compiler: Espressif official `espressif/idf:release-v6.1`; correct board `waveshare/esp32-s3-touch-lcd-4b`, N16R8.
- Full 4B build log: `xiaozhi.bin` **0x2b0030 bytes** in **0x3f0000** OTA app slot, **0x13ffd0 bytes (32%) free**; `merged-binary.bin` created, **0xad8f49** bytes. Compiler and linker completed without errors.
- Audio codec and LCD, voice AEC source, Xiaozhi original 16MB partition, two OTA app slots and 8MB `assets` region preserved.
- NVS auto-erase guarded, AP optional/disabled by default, 4B APSTA mode configured only before owner starts Wi-Fi, protocol libraries and AP-only hooks compiled, DNS negative/host safety tests passed, no real secrets.
- Original stable firmware not overwritten. Nothing flashed, reconfigured on VPS or published as a production image.

## Intentional P4-2 and P4-3 gates

**P4-2** must connect the AP-local UDP DNS/TCP listener and authenticated SS2022/VLESS relay into bounded FreeRTOS workers with explicit user enable, authenticated node readiness and fail-closed stop. It must then test 4B real client AP TCP, DHCP, AP IPv6 drop, outbound IPv6-only VPS, DNS leaks, restarts, and voice/LCD/audio regression. The compiled entry points in P4-1 are *not yet active*.

**P4-3** must complete encrypted credential storage, stability/security signoff, and a verified independent stable-firmware/NVS backup and recovery mechanism **before** any user's unit is flashed.

This scope matches the original `docs/PLAN.md` row: P4-1 correct hardware/driver/voice integration and full build; P4-2 complete live AP functionality and physical acceptance; P4-3 safe release. PR allocation and weights are unchanged (P4-1 35%, P4-2 40%, P4-3 25%).

Do not mistake a CI-generated merged binary for an authorized installation artifact. No user-device flash evidence exists.
