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
    require((target / "wifi_station.cc").read_text() == sta,
            "Wi-Fi STA source modified without explicit review")
    print("P4_WIFI_OWNER_PINNED 78/esp-wifi-connect 3.3.3 SHA " + sha)
    print("P4_WIFI_NVS_AUTO_ERASE_BLOCKED original STA/config AP preserved")
    print("NO APSTA activation or second Wi-Fi driver initialization")

if __name__ == "__main__":
    main()
