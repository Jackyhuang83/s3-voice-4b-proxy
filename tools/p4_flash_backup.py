#!/usr/bin/env python3
"""ESP32-S3 R1 READ-ONLY whole-Flash backup and original-partition audit.
PRIVATE: NVS/flash may contain Wi-Fi, VPS, and voice credentials.
No write-flash, erase-flash, or eFuse operation is implemented.
"""
import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

FLASH_SIZE = 0x1000000
TABLE_OFFSET = 0x8000
EXPECTED = {
    "nvs": (0x9000, 0x4000, 1, 2),
    "otadata": (0xd000, 0x2000, 1, 0),
    "phy_init": (0xf000, 0x1000, 1, 1),
    "ota_0": (0x20000, 0x3f0000, 0, 0x10),
    "ota_1": (0x410000, 0x3f0000, 0, 0x11),
    "assets": (0x800000, 0x800000, 1, 0x82),
}

def digest(blob):
    return hashlib.sha256(blob).hexdigest()

def inspect(blob):
    if len(blob) != FLASH_SIZE:
        raise ValueError("Expected exactly 16MiB Flash; backup truncated")
    partitions = {}
    for pos in range(TABLE_OFFSET, TABLE_OFFSET + 0x1000, 32):
        magic, kind, subkind, start, length, rawname, flags = struct.unpack_from(
            "<HBBII16sI", blob, pos)
        if magic in (0xffff, 0xebeb):
            break
        if magic != 0x50aa:
            raise ValueError("Unrecognized partition table; STOP")
        name = rawname.split(b"\0")[0].decode("ascii")
        if name in partitions or start % 0x1000 or length % 0x1000 or start + length > FLASH_SIZE:
            raise ValueError("Partition alignment/bounds/duplicate invalid")
        partitions[name] = (start, length, kind, subkind)
    if partitions != EXPECTED:
        raise ValueError("Not the pinned original 78/Xiaozhi 4B partition layout")
    if not any(blob[EXPECTED[name][0]] == 0xe9 for name in ("ota_0", "ota_1")):
        raise ValueError("No bootable-looking ESP image header in OTA slots")
    return {
        "format": "r1-private-flash-v1",
        "contains_credentials": True,
        "size": FLASH_SIZE,
        "sha256": digest(blob),
        "partitions": {name: {"offset": start, "size": length,
                              "sha256": digest(blob[start:start+length])}
                       for name, (start, length, _, _) in partitions.items()},
        "scope": "offline integrity only; actual restoration NOT VERIFIED",
    }

def verify(directory):
    expected = json.loads((directory / "manifest.json").read_text())
    current = inspect((directory / "fullflash-private.bin").read_bytes())
    if expected != current:
        raise ValueError("Backup content or per-partition digest changed")
    return current

def capture(port, directory):
    if not port or port.startswith("-") or directory.exists():
        raise ValueError("Explicit physical serial port and NEW backup folder required")
    directory.mkdir(mode=0o700)
    os.chmod(directory, 0o700)
    path = directory / "fullflash-private.bin"
    print("READ ONLY 16MiB; device backup contains PRIVATE credentials", flush=True)
    command = [sys.executable, "-m", "esptool", "--chip", "esp32s3",
               "--port", port, "read-flash", "0x0", hex(FLASH_SIZE), str(path)]
    subprocess.run(command, check=True)
    os.chmod(path, 0o600)
    snapshot = inspect(path.read_bytes())
    manifest = directory / "manifest.json"
    with manifest.open("x") as f:
        os.chmod(manifest, 0o600)
        json.dump(snapshot, f, sort_keys=True, indent=2)
    verify(directory)
    print("P4_3_BACKUP_VERIFIED_OFFLINE; NOT RESTORED; NEVER SHARE BACKUP")

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    c = sub.add_parser("capture")
    c.add_argument("--port", required=True)
    c.add_argument("--out", required=True, type=Path)
    c = sub.add_parser("verify")
    c.add_argument("--dir", required=True, type=Path)
    args = p.parse_args(argv)
    try:
        if args.action == "capture":
            capture(args.port, args.out)
        else:
            print("P4_3_BACKUP_VERIFIED_OFFLINE", verify(args.dir)["sha256"])
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError,
            UnicodeDecodeError, json.JSONDecodeError) as exc:
        print("P4_3_BACKUP_STOP:", exc, file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
