#!/usr/bin/env python3
"""Verify exact upstream Git blob hashes for SS2022 production source + licenses.

This checker has no network access; expected hashes are pinned from
rlog/atoms3r-muse-firmware@57f73602e963e478e06eae5f8108d07495468031.
"""
import json
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "components/s3_ss2022/VENDOR.json").read_text())
assert manifest["upstream_commit"] == "57f73602e963e478e06eae5f8108d07495468031"
assert manifest["source_files_unmodified"]
checked = set()
for entry in manifest["files"]:
    path = root / entry["path"]
    assert entry["path"].startswith("components/s3_ss2022/")
    assert path.is_file() and path.stat().st_size > 0, entry["path"]
    assert entry["path"] not in checked, entry["path"]
    checked.add(entry["path"])
    expected = entry["git_blob_sha1"]
    assert re.fullmatch(r"[0-9a-f]{40}", expected)
    actual = subprocess.check_output(
        ["git", "hash-object", str(path)], cwd=root, text=True
    ).strip()
    assert actual == expected, f"Upstream source drift: {entry['path']}: {actual} != {expected}"
required = {
    "components/s3_ss2022/muse_ss2022.c",
    "components/s3_ss2022/muse_ss2022.h",
    "components/s3_ss2022/third_party/blake3/blake3.c",
    "components/s3_ss2022/third_party/blake3/blake3.h",
    "components/s3_ss2022/third_party/blake3/blake3_impl.h",
    "components/s3_ss2022/third_party/blake3/blake3_dispatch.c",
    "components/s3_ss2022/third_party/blake3/blake3_portable.c",
    "components/s3_ss2022/LICENSE-Apache-2.0",
    "components/s3_ss2022/NOTICE-upstream",
    "components/s3_ss2022/third_party/blake3/LICENSE_A2",
    "components/s3_ss2022/third_party/blake3/LICENSE_A2LLVM",
    "components/s3_ss2022/third_party/blake3/LICENSE_CC0",
}
assert required.issubset(checked), "Missing upstream cryptographic sources/licenses"
print(f"PASS exact vendor SHA-1 Git blob checks: {len(checked)} files")
