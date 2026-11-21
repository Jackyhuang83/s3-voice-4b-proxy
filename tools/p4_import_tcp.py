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

    # Keep the imported P1 TCP engine safe during AP restarts. Upstream's
    # global defaults to ENABLED and its AP output hooks are one-way.
    # This P4-only patch is exact-match and is never applied to P1/main.
    initial = "static bool                   s_enabled = true;"
    require(c_file.count(initial) == 1, "Router TCP initial state changed")
    c_file = c_file.replace(initial,
                            "static bool                   s_enabled = false;", 1)
    anchor = "void transparent_tcp_init(void)\n{"
    require(c_file.count(anchor) == 1, "Router TCP lifecycle moved")
    uninstall = (
        "/* P4-1: invoke on the lwIP core thread, after all relay workers stop. */\n"
        "bool transparent_tcp_is_reinjecting(void)\n"
        "{\n"
        "    return s_reinjecting;\n"
        "}\n\n"
        "void transparent_tcp_uninstall_ap_output(void)\n"
        "{\n"
        "    s_enabled = false;\n"
        "    if (s_ap_netif) {\n"
        "        if (s_ap_original_output &&\n"
        "            s_ap_netif->output == transparent_tcp_ap_output)\n"
        "            s_ap_netif->output = s_ap_original_output;\n"
        "        if (s_ap_original_linkoutput &&\n"
        "            s_ap_netif->linkoutput == transparent_tcp_ap_linkoutput)\n"
        "            s_ap_netif->linkoutput = s_ap_original_linkoutput;\n"
        "    }\n"
        "    s_ap_original_output = NULL;\n"
        "    s_ap_original_linkoutput = NULL;\n"
        "    s_ap_netif = NULL;\n"
        "    s_reinjecting = false;\n"
        "    transparent_tcp_init();\n"
        "}\n\n"
    )
    c_file = c_file.replace(anchor, uninstall + anchor, 1)
    header_anchor = "void transparent_tcp_install_ap_output(void);"
    require(h_file.count(header_anchor) == 1, "Router TCP header changed")
    h_file = h_file.replace(header_anchor,
        header_anchor + "\n"
        "/* P4-1 lifecycle: core-thread-only restore before AP teardown. */\n"
        "void transparent_tcp_uninstall_ap_output(void);\n"
        "bool transparent_tcp_is_reinjecting(void);", 1)
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
