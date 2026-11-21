#!/usr/bin/env python3
"""P4-1: assemble an isolated, voice-first 4B compilation tree.

Never runs esptool, flashes hardware, edits the upstream clone in-place,
sets eFuses, provisions credentials, or changes Xiaozhi partitions.
This compiles proxy transport components into Xiaozhi for ABI/API evaluation;
it does NOT activate transparent forwarding or validate Wi-Fi hardware.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

VOICE_SHA = "831ffd14188553cc887408b75396ae38618538e0"
BOARD = "main/boards/waveshare/esp32-s3-touch-lcd-4b"
PARTITIONS = "partitions/v2/16m.csv"
PROTECTED = [
    "CMakeLists.txt",
    "sdkconfig.defaults",
    "main/idf_component.yml",
    "main/boards/waveshare/esp32-s3-touch-lcd-4b/config.h",
    "main/boards/waveshare/esp32-s3-touch-lcd-4b/config.json",
    "main/boards/waveshare/esp32-s3-touch-lcd-4b/esp32-s3-touch-lcd-4b.cc",
    PARTITIONS,
]
COMPONENTS = ("s3_ss2022", "s3_vless_tls", "s3_gateway_policy", "s3_gateway_dns", "s3_gateway_ap", "s3_gateway_tcp", "s3_gateway_session")
CMAKE_NEEDLE = 'set(MAIN_PRIV_REQUIRES_EXTRA "")\n'
# Exact permitted root-CMake append, never a partition or main-entry rewrite.
ROOT_HOOK_CMAKE = "\n# P4-1 official IDF6.1 lwIP hook; original project() must already exist.\n# Root CMake runs in normal configure, unlike component script discovery.\nidf_component_get_property(s3_lwip lwip COMPONENT_LIB)\ntarget_compile_options(${s3_lwip} PRIVATE \"-I${PROJECT_DIR}/components/s3_gateway_policy\")\ntarget_compile_definitions(${s3_lwip} PRIVATE \"-DESP_IDF_LWIP_HOOK_FILENAME=\\\"s3_gateway_lwip_hook.h\\\"\")\n# The hook symbol lives in a static library ordered before lwIP. Force\n# archive extraction, equivalent to -u on GNU ld; never rely on link order.\ntarget_link_options(xiaozhi.elf PRIVATE \"-Wl,--undefined=s3_gateway_ip4_input\" \"-Wl,--undefined=lwip_hook_ip6_input\")\n"


# Narrow P4-2 overlay only: unused IO-expander LONG PRESS.
# GPIO0 voice key and the short-press boot-partition behavior are untouched.
BOARD_LONG_PRESS = (
    '                } else {\n'
    '                    ESP_LOGI(TAG, "Long press detected (>1000ms), no action");\n'
    '                }\n'
)
BOARD_ARM_GESTURE = (
    '                } else if (press_duration >= 1100 && press_duration < 1800) {\n'
    '                    /* Physical-only serial provisioning; no radio UI. */\n'
    '                    if (!s3_gateway_console_start()) {\n'
    '                        ESP_LOGW(TAG, "Physical setup console unavailable");\n'
    '                    }\n'
    '                } else if (press_duration >= 1800 && press_duration < 3200) {\n'
    '                    /* Physical explicit arm/disarm, nonblocking key monitor. */\n'
    '                    if (!s3_gateway_workers_admin_button_toggle()) {\n'
    '                        ESP_LOGW(TAG, "Gateway AP/node not configured");\n'
    '                    }\n'
    '                } else {\n'
    '                    ESP_LOGI(TAG, "Long press detected, no action");\n'
    '                }\n'
)

def expected_board_overlay(original: str) -> str:
    header = '#include "config.h"\n'
    require(original.count(header) == 1, "4B board header changed")
    require(original.count(BOARD_LONG_PRESS) == 1,
            "4B physical button semantics changed")
    return (original.replace(header,
                             header + '#include "s3_gateway_workers.h"\n', 1)
            .replace(BOARD_LONG_PRESS, BOARD_ARM_GESTURE, 1))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(test: bool, message: str) -> None:
    if not test:
        raise RuntimeError(message)


def inspect(voice: Path, project: Path) -> dict[str, str]:
    require((voice / ".git").is_dir(), "Require a clean, detached Git checkout")
    sha = subprocess.check_output(
        ["git", "-C", str(voice), "rev-parse", "HEAD"], text=True
    ).strip()
    require(sha == VOICE_SHA, f"Refuse moving Xiaozhi HEAD: {sha}")
    require((project / "components").is_dir(), "Missing own proxy components")
    require(all((voice / file).is_file() for file in PROTECTED),
            "Voice board or recovery-critical file is absent")
    require(all((project / "components" / name / "CMakeLists.txt").is_file()
                for name in COMPONENTS), "Missing IDF component registration")

    board = json.loads((voice / BOARD / "config.json").read_text())
    require(board["manufacturer"] == "waveshare" and
            board["type"] == "esp32-s3-touch-lcd-4b" and
            board["target"] == "esp32s3", "Wrong board/target")
    require(len(board.get("builds", [])) == 1 and
            board["builds"][0]["name"] == "esp32-s3-touch-lcd-4b",
            "Unexpected board variant")
    opts = board["builds"][0]["sdkconfig_append"]
    require("CONFIG_USE_DEVICE_AEC=y" in opts, "Voice AEC option missing")

    pins = (voice / BOARD / "config.h").read_text()
    for expected in (
        "#define AUDIO_I2S_GPIO_MCLK GPIO_NUM_5",
        "#define AUDIO_I2S_GPIO_WS GPIO_NUM_7",
        "#define AUDIO_I2S_GPIO_BCLK GPIO_NUM_16",
        "#define AUDIO_I2S_GPIO_DIN  GPIO_NUM_15",
        "#define AUDIO_I2S_GPIO_DOUT GPIO_NUM_6",
        "#define DISPLAY_WIDTH   480",
        "#define DISPLAY_HEIGHT  480",
    ):
        require(expected in pins, "Audio/LCD pin mapping changed: " + expected)
    source = (voice / BOARD / "esp32-s3-touch-lcd-4b.cc").read_text()
    for expected in ("BoxAudioCodec", "esp_lcd_new_panel_st7701",
                     "esp_lcd_touch_new_i2c_gt911", "InitializeAxp2101",
                     "DECLARE_BOARD(WaveshareEsp32s3TouchLCD4b)"):
        require(expected in source, "Missing upstream voice/driver path: " + expected)
    manifest = (voice / "main/idf_component.yml").read_text()
    require("version: '>=6.0.1'" in manifest, "IDF 6 requirement changed")
    defaults = (voice / "sdkconfig.defaults").read_text()
    require('CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions/v2/16m.csv"' in defaults,
            "Voice partition layout unexpectedly changed")
    require("CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y" in defaults,
            "Expected 16MB Flash")
    partitions = (voice / PARTITIONS).read_text()
    for expected in (
        "ota_0,    app,  ota_0,   0x20000,   0x3f0000,",
        "ota_1,    app,  ota_1,   ,          0x3f0000,",
        "assets,   data, spiffs,  0x800000,  8M",
    ):
        require(expected in partitions, "Voice flash layout changed: " + expected)
    require(not any(line.strip().startswith("factory,") for line in
                    partitions.splitlines()), "Factory partition changed")
    voice_cmake = (voice / "CMakeLists.txt").read_text()
    require("idf_build_set_property(MINIMAL_BUILD ON)" in voice_cmake,
            "Voice root build strategy changed")
    main_cmake = (voice / "main/CMakeLists.txt").read_text()
    require(main_cmake.count(CMAKE_NEEDLE) == 1,
            "Refuse CMake modification after upstream drift")
    return {name: digest(voice / name) for name in PROTECTED}


def prepare(voice: Path, project: Path) -> None:
    before = inspect(voice, project)
    cmake_path = voice / "main/CMakeLists.txt"
    for name in COMPONENTS:
        destination = voice / "components" / name
        require(not destination.exists(), "Refuse overwrite: " + str(destination))
        shutil.copytree(project / "components" / name, destination)
    original = cmake_path.read_text()
    injected = (
        CMAKE_NEEDLE +
        "# P4-1 component dependencies only; no target_* commands in IDF script mode.\n"
        "list(APPEND MAIN_PRIV_REQUIRES_EXTRA s3_ss2022 s3_vless_tls s3_tcp_guard s3_gateway_policy s3_gateway_dns s3_gateway_ap s3_gateway_tcp s3_gateway_session)\n"
    )
    cmake_path.write_text(original.replace(CMAKE_NEEDLE, injected, 1))
    after = {name: digest(voice / name) for name in PROTECTED}
    require(before == after, "Recovery-critical voice files unexpectedly modified")
    require(all((voice / "components" / name / "CMakeLists.txt").is_file()
                for name in COMPONENTS), "Proxy components were not copied")
    # P4-2: the ONE allowed board source change, after invariant checks.
    key_board = voice / BOARD / "esp32-s3-touch-lcd-4b.cc"
    key_board.write_text(expected_board_overlay(key_board.read_text()))

    # The upstream app currently erases the ENTIRE shared NVS on certain
    # initialization errors. Replace ONLY that destructive recovery branch in
    # the ephemeral build; healthy boot and original partition remain unchanged.
    app_main = voice / "main/main.cc"
    app_text = app_main.read_text()
    old_nvs = (
        '    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {\n'
        '        ESP_LOGW(TAG, "Erasing NVS flash to fix corruption");\n'
        '        ESP_ERROR_CHECK(nvs_flash_erase());\n'
        '        ret = nvs_flash_init();\n'
        '    }\n'
    )
    safe_nvs = (
        '    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {\n'
        '        ESP_LOGE(TAG, "NVS incompatible: refusing automatic erase and boot");\n'
        '    }\n'
    )
    require(app_text.count(old_nvs) == 1, "NVS recovery implementation changed")
    require("nvs_flash_erase()" in app_text, "Expected destructive upstream branch missing")
    app_main.write_text(app_text.replace(old_nvs, safe_nvs, 1))
    require("nvs_flash_erase()" not in app_main.read_text(),
            "Unsafe automatic NVS erase remains")

    # IDF 6 lwIP getaddrinfo(AF_UNSPEC) can be IPv4-only even with AAAA DNS.
    # The official dual-stack adapter is needed for IPv6-only proxy hosts.
    # Add to the 4B isolated target defaults; NEVER overwrite voice partitions,
    # credentials, the original source repository or production firmware.
    target_cfg = voice / "sdkconfig.defaults.esp32s3"
    original_cfg = target_cfg.read_text()
    for key in ("CONFIG_LWIP_IPV6=y",
                "CONFIG_LWIP_IPV6_AUTOCONFIG=y",
                "CONFIG_LWIP_USE_ESP_GETADDRINFO=y",
                "CONFIG_LWIP_HOOK_IP6_INPUT_CUSTOM=y",
                "CONFIG_ESP_NETIF_SET_DNS_PER_DEFAULT_NETIF=y"):
        require(key.split("=")[0] + "=" not in original_cfg,
                "Upstream already sets " + key.split("=")[0])
    target_cfg.write_text(original_cfg.rstrip() +
        "\n\n# P4-1 isolated 4B outbound IPv6 / official AF_UNSPEC fix\n" +
        "\n".join(("CONFIG_LWIP_IPV6=y", "CONFIG_LWIP_IPV6_AUTOCONFIG=y",
                   "CONFIG_LWIP_USE_ESP_GETADDRINFO=y",
                   "CONFIG_LWIP_HOOK_IP6_INPUT_CUSTOM=y",
                   "CONFIG_ESP_NETIF_SET_DNS_PER_DEFAULT_NETIF=y")) + "\n")

    # Wire only the Xiaozhi-owned connection and provisioning lifecycle to
    # a locked-down policy. This does not call esp_wifi_init, create an AP,
    # send packets, or arm the proxy. It is safe to ship in a non-gateway image.
    wifi_board = voice / "main/boards/common/wifi_board.cc"
    wifi_src = wifi_board.read_text()
    def swap_once(old: str, new: str, label: str) -> None:
        nonlocal wifi_src
        require(wifi_src.count(old) == 1,
                "Xiaozhi Wi-Fi owner drifted: " + label)
        wifi_src = wifi_src.replace(old, new, 1)

    swap_once('#include "wifi_board.h"\n',
              '#include "wifi_board.h"\n#include "s3_gateway_policy.h"\n#include "s3_gateway_session.h"\n#include "s3_gateway_workers.h"\n',
              "policy header")
    swap_once('static const char *TAG = "WifiBoard";\n',
              'static const char *TAG = "WifiBoard";\n'
              '/* Voice owns station and config mode; no auto-arm on restart. */\n'
              '\n',
              "policy owner")
    swap_once('void WifiBoard::OnNetworkEvent(NetworkEvent event, const std::string& data) {\n',
              'void WifiBoard::OnNetworkEvent(NetworkEvent event, const std::string& data) {\n'
              '    /* Only lifecycle notifications. The gateway AP and relay are still off. */\n'
              '    switch (event) {\n'
              '        case NetworkEvent::Connected:\n'
              '            s3_gateway_policy_event(s3_gateway_policy_device(), S3_GW_STA_CONNECTED);\n'
              '            s3_gateway_session_event(s3_gateway_session_device(), S3_SESSION_STA_ONLINE);\n'
              '            break;\n'
              '        case NetworkEvent::Disconnected:\n'
              '            s3_gateway_policy_event(s3_gateway_policy_device(), S3_GW_STA_DISCONNECTED);\n'
              '            s3_gateway_session_event(s3_gateway_session_device(), S3_SESSION_STA_LOST);\n'
              '            s3_gateway_workers_revoke();\n'
              '            break;\n'
              '        case NetworkEvent::WifiConfigModeEnter:\n'
              '            s3_gateway_policy_event(s3_gateway_policy_device(), S3_GW_CONFIG_ENTER);\n'
              '            s3_gateway_session_event(s3_gateway_session_device(), S3_SESSION_CONFIG_ENTER);\n'
              '            s3_gateway_workers_revoke();\n'
              '            break;\n'
              '        case NetworkEvent::WifiConfigModeExit:\n'
              '            s3_gateway_policy_event(s3_gateway_policy_device(), S3_GW_CONFIG_EXIT);\n'
              '            break;\n'
              '        default:\n'
              '            break;\n'
              '    }\n',
              "network callback")
    require("esp_wifi_init(" not in wifi_src,
            "Gateway must not introduce a second Wi-Fi initialization")
    wifi_board.write_text(wifi_src)
    root = voice / "CMakeLists.txt"
    original_root = root.read_text()
    require(original_root.rstrip().endswith("project(xiaozhi)"),
            "Refuse changing root project() shape")
    root.write_text(original_root + ROOT_HOOK_CMAKE)

    print("P4_4B_SOURCE_PREFLIGHT_PASS board, voice drivers, exact SHA, pin and flash invariants")
    print("P4_4B_NVS_ERASE_BLOCKED source guard; actual NVS migration NOT RUN")
    print("P4_4B_DUAL_STACK_CONFIGURED IDF6 AF_UNSPEC adapter; real IPv6 NOT RUN")
    print("P4_4B_LIFECYCLE_WIRED voice-owned STA/config events; no auto-arm or AP start")
    print("P4_4B_COMPONENT_LINK_PREPARED under pinned Xiaozhi IDF >=6.0.1")
    print("NOT RUN: forwarding, AP/STA IPv6, voice regression on device, NVS encryption, flashing")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", type=Path, required=True)
    parser.add_argument("--project", type=Path, default=Path("."))
    parser.add_argument("--inspect-only", action="store_true")
    parser.add_argument("--verify-assembled", action="store_true")
    args = parser.parse_args()
    voice, project = args.voice.resolve(), args.project.resolve()
    if args.verify_assembled:
        original = subprocess.check_output(
            ["git", "-C", str(voice), "show", "HEAD:CMakeLists.txt"],
            text=True
        )
        require((voice / "CMakeLists.txt").read_text() == original + ROOT_HOOK_CMAKE,
                "Root CMake changed beyond allowlisted official lwIP hook")
        board = voice / BOARD / "esp32-s3-touch-lcd-4b.cc"
        pinned = subprocess.check_output(
            ["git", "-C", str(voice), "show",
             "HEAD:" + BOARD + "/esp32-s3-touch-lcd-4b.cc"],
            text=True
        )
        require(board.read_text() == expected_board_overlay(pinned),
                "Board source differs from exact physical-key overlay")
        print("P4_4B_ROOT_CMAKE_SAFE_PASS official IDF hook, no partition edits")
        print("P4_2_KEY_OVERLAY_VERIFIED GPIO0 voice key unchanged")
        return
    if args.inspect_only:
        inspect(voice, project)
        print("P4_4B_SOURCE_PREFLIGHT_PASS")
    else:
        prepare(voice, project)


if __name__ == "__main__":
    main()
