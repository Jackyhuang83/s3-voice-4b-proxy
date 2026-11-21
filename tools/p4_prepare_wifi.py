#!/usr/bin/env python3
"""P4-1: pin an official Wi-Fi owner and block its independent NVS erase.

Only overlays the isolated Xiaozhi IDF build. It never modifies a user's
installed firmware, main branch, network, flash or real Wi-Fi credentials.
The vendor library remains the single owner of esp_wifi_init/stop.
"""
import argparse
import shutil
import subprocess
from pathlib import Path

WIFI_SHA = "77095063d77e7705f68e95005c43ed73582233ce"
DEST = "78__esp-wifi-connect"
NVS_ERASE = '''    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "Erasing NVS...");
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
'''
NVS_REFUSE = '''    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGE(TAG, "NVS incompatible: refusing automatic erase");
        return false;
    }
'''

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", required=True, type=Path)
    parser.add_argument("--wifi-source", required=True, type=Path)
    args = parser.parse_args()
    voice, wifi = args.voice.resolve(), args.wifi_source.resolve()
    assert voice.is_dir() and wifi.is_dir()
    sha = subprocess.check_output(["git", "-C", str(wifi), "rev-parse", "HEAD"],
                                  text=True).strip()
    require(sha == WIFI_SHA, "Refuse unpinned Wi-Fi manager source")
    manifest = (wifi / "idf_component.yml").read_text()
    require("version: 3.3.3" in manifest and "license: MIT" in manifest,
            "Wi-Fi manager component provenance changed")
    mgr = (wifi / "wifi_manager.cc").read_text()
    sta = (wifi / "wifi_station.cc").read_text()
    require(mgr.count(NVS_ERASE) == 1, "WifiManager NVS erase branch drifted")
    require(sta.count("ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));") == 1,
            "WifiStation owns STA setup differently; refuse overlay")
    require(sta.count("esp_wifi_stop();") == 1,
            "WifiStation stop lifecycle changed; refuse overlay")
    require(mgr.count("ret = esp_wifi_init(&cfg);") == 1,
            "One-owner esp_wifi_init changed")
    target = voice / "components" / DEST
    require(not target.exists(), "Refuse overwriting Wi-Fi component")
    shutil.copytree(wifi, target, ignore=shutil.ignore_patterns(".git", "dist", "tests"))
    manager = target / "wifi_manager.cc"
    manager.write_text(mgr.replace(NVS_ERASE, NVS_REFUSE, 1))
    require("nvs_flash_erase()" not in manager.read_text(),
            "Automatic NVS erase still reachable in Wi-Fi manager")
    # Keep all original station management; only insert AP startup BEFORE
    # the single owner esp_wifi_start(). An APSTA mode change after Wi-Fi
    # start would briefly broadcast an unconfigured AP.
    header_anchor = '#include "wifi_station.h"\n'
    sta_start = (
        '    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));\n'
        '    ESP_ERROR_CHECK(esp_wifi_start());\n'
    )
    sta_stop = '    esp_wifi_stop();\n'
    require(sta.count(header_anchor) == 1 and
            sta.count(sta_start) == 1 and sta.count(sta_stop) == 1,
            "Pinned Wi-Fi station start/stop signature drifted")
    modified_sta = sta.replace(header_anchor,
        header_anchor + '#include "s3_gateway_ap_runtime.h"\n', 1)
    modified_sta = modified_sta.replace(sta_start,
        '    if (!s3_gateway_ap_pre_start()) {\n'
        '        ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));\n'
        '    }\n'
        '    ESP_ERROR_CHECK(esp_wifi_start());\n'
        '    if (!s3_gateway_ap_after_start()) {\n'
        '        ESP_ERROR_CHECK(ESP_FAIL); /* DHCP failure: no service */\n'
        '    }\n', 1)
    modified_sta = modified_sta.replace(sta_stop,
        '    s3_gateway_ap_before_stop();\n'
        '    esp_wifi_stop();\n'
        '    if (!s3_gateway_ap_after_stop()) {\n'
        '        ESP_ERROR_CHECK(ESP_FAIL); /* Cannot reuse stale AP netif */\n'
        '    }\n', 1)
    # The ORIGINAL upstream file mentions esp_wifi_init() in a comment.
    # Assert no new call/string was introduced rather than rejecting its
    # existing documentation text.
    require(modified_sta.count("esp_wifi_init(") == sta.count("esp_wifi_init("),
            "Refuse added Wi-Fi initialization")
    (target / "wifi_station.cc").write_text(modified_sta)
    # The official v3.3.3 CMakeLists has one dependency list per IDF
    # major version. Add only our local AP component in both branches.
    component_cmake = target / "CMakeLists.txt"
    old_cmake = component_cmake.read_text()
    dep = '"esp_wifi" "nvs_flash"'
    require(old_cmake.count(dep) == 2,
            "Pinned Wi-Fi component dependency lists drifted")
    component_cmake.write_text(old_cmake.replace(
        dep, dep + ' "s3_gateway_ap"'))
    print("P4_WIFI_OWNER_APSTA_PRESTART: original Wi-Fi start/stop only")

    print("P4_WIFI_OWNER_PINNED 78/esp-wifi-connect 3.3.3 SHA " + sha)
    print("P4_WIFI_NVS_AUTO_ERASE_BLOCKED original STA/config AP preserved")
    print("NO APSTA activation or second Wi-Fi driver initialization")

if __name__ == "__main__":
    main()
