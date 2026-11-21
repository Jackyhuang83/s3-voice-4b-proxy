#!/usr/bin/env python3
"""Production release evidence blocker. No flashing, eFuse, OTA or publish."""
import argparse
import json
import re
import sys
from pathlib import Path

FIELDS = ("device_restore_verified", "xiaozhi_voice_lcd_verified",
          "both_protocols_vps_verified", "dns_udp_ipv6_leak_verified",
          "credential_encryption_verified", "operator_approved")

def missing(e):
    absent = []
    h = e.get("private_fullflash_sha256")
    if not isinstance(h, str) or not re.fullmatch("[0-9a-f]{64}", h):
        absent.append("private_fullflash_sha256")
    for key in FIELDS:
        if e.get(key) is not True:
            absent.append(key)
    if not isinstance(e.get("board_serial"), str) or not e["board_serial"].strip():
        absent.append("board_serial")
    return absent

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args(argv)
    if not args.evidence:
        print("P4_3_PRODUCTION_RELEASE_BLOCKED: no real device evidence")
        return 2
    try:
        values = json.loads(args.evidence.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print("P4_3_PRODUCTION_RELEASE_BLOCKED:", exc)
        return 2
    failures = missing(values)
    if failures:
        print("P4_3_PRODUCTION_RELEASE_BLOCKED:", ", ".join(failures))
        return 2
    print("P4_3_DOCUMENTATION_GATE_PASS: independent physical audit still required.")
    print("NO deploy, eFuse burn, flash or release performed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
