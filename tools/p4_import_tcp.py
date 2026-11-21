#!/usr/bin/env python3
"""Import the P1-guarded IPv4 TCP flow table from a pinned router checkout.

Run in an ephemeral CI clone AFTER the four original P1 patches are applied.
This is COMPILE-ONLY preparation: no lwIP hook, listener or AP starts here.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
from pathlib import Path

PIN = "dfb04b03154cfaee1d8615e4b8942dfe737abc5d"


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise RuntimeError(reason)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", type=Path, required=True)
    parser.add_argument("--voice", type=Path, required=True)
    args = parser.parse_args()
    router, voice = args.router.resolve(), args.voice.resolve()

    sha = subprocess.check_output(
        ["git", "-C", str(router), "rev-parse", "HEAD"], text=True).strip()
    require(sha == PIN, "Refuse unpinned upstream router")
    require((router / "LICENSE").read_text().startswith("MIT License"),
            "Missing original MIT grant")
    c_file = (router / "src/transparent_tcp.c").read_text()
    h_file = (router / "src/transparent_tcp.h").read_text()
    router_hook = (router / "include/lwip_router_hook.h").read_text()
    require("int transparent_tcp_ip4_input(struct pbuf *packet, struct netif *input_netif);" in router_hook,
            "Pinned P1 input hook ABI changed")

    # A raw upstream transplant is unsafe: require P1 post-patch guards.
    for expected in ("S3_PROXY_TCP_ONLY", "pbuf_free(packet);",
                     "header[9] == 17", "source_port == 68",
                     "destination_port == 67", "transparent_tcp_ip4_input"):
        require(expected in c_file, "P1 IPv4 flow guard absent: " + expected)
    require("TRANSPARENT_TCP_MAX_FLOWS" in h_file,
            "Unexpected upstream flow data structure")
    require(not (voice / "components/s3_tcp_guard").exists(),
            "Refuse overwriting existing router integration component")

    dst = voice / "components/s3_tcp_guard"
    dst.mkdir()
    (dst / "transparent_tcp.c").write_text(c_file)
    (dst / "transparent_tcp.h").write_text(h_file)
    shutil.copy2(router / "LICENSE", dst / "LICENSE.router")
    (dst / "CMakeLists.txt").write_text(
        '# Compile-only audit of the exact patched router TCP core. '
        'No Wi-Fi owner or lwIP hook installed.\n'
        'idf_component_register(SRCS "transparent_tcp.c" INCLUDE_DIRS "." '
        'REQUIRES lwip esp_timer esp_netif freertos)\n'
        'target_compile_definitions($' '{COMPONENT_LIB} PRIVATE '
        'S3_PROXY_TCP_ONLY=1)\n'
    )
    digest = hashlib.sha256(c_file.encode()).hexdigest()
    print(f"P4_ROUTER_TCP_CORE_PREPARED SHA256={digest}")
    print("PASS MIT license, pinned source, P1 TCP-only guards; NO AP runtime")


if __name__ == "__main__":
    main()
