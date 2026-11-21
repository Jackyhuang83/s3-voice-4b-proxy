#!/usr/bin/env python3
"""P3-3 source gate complements (never substitutes for) runtime interop CI.

Run before/after clang-format on a throwaway pinned upstream R8N16 checkout.
"""
from pathlib import Path
import re

ss = Path("upstream/components/s3_ss2022/s3_ss2022_link.c").read_text()
vless = Path("upstream/components/s3_vless_tls/s3_vless_tls.c").read_text()
main = Path("upstream/src/main.c").read_text()
tcp = Path("upstream/src/transport_tcp.c").read_text()
sdk = Path("upstream/sdkconfig.defaults").read_text()
workflow = Path(".github/workflows/p3-exit-matrix.yml").read_text()

# The original request MUST remain unchanged if an authenticated remote DNS
# resolver returns a mismatched transaction ID or a non-response (QR=0).
assert re.search(r"answer\[0\]\s*!=\s*packet\[0\]", ss)
assert re.search(r"answer\[1\]\s*!=\s*packet\[1\]", ss)
assert re.search(r"!\(answer\[2\]\s*&\s*0x80\)", ss)
assert ss.index("answer[0]") < ss.index("memcpy(packet, answer, expected)")
assert re.search(r"response\[0\]\s*==\s*packet\[0\]", vless)
assert re.search(r"response\[1\]\s*==\s*packet\[1\]", vless)
assert re.search(r"\(response\[2\]\s*&\s*0x80\)", vless)

# TLS certificate/SNI/CA and no legacy plaintext VLESS/direct data paths.
assert re.search(r"\.crt_bundle_attach\s*=\s*esp_crt_bundle_attach", vless)
assert re.search(r"\.common_name\s*=\s*host\b", vless)
assert re.search(r"\.skip_common_name\s*=\s*false", vless)
assert "esp_tls_conn_new_sync(" in vless
assert "s3_vless_tls_relay(" in main and "s3_ss2022_relay(" in main
for name in ("transport_tcp_open_domain", "transport_tcp_open_ipv4",
             "transport_tcp_open_vless_stream", "transport_tcp_open_vless_ipv4_stream"):
    assert "S3_PROXY_TCP_ONLY" in tcp.split(name + "(", 1)[1].split("\n}", 1)[0]

# AP still IPv4 only; STA alone may consume an IPv6 Router Advertisement.
assert "esp_netif_create_ip6_linklocal(s_sta_netif)" in main
assert "esp_netif_create_ip6_linklocal(s_ap_netif)" not in main
assert "IP_EVENT_GOT_IP6" in main
assert "s_sta_has_ipv4 || s_sta_has_ipv6" in main
assert "CONFIG_LWIP_IPV6=y" in sdk

# SS2022 v2 storage and decoder's exact upstream provenance retained.
assert 'S3_SS2022_KEY "node_v2"' in ss
assert "getaddrinfo(node->server_host" in ss
assert "AF_INET6" in ss and "AF_INET" in ss
assert "nvs_set_blob(" in ss and "nvs_commit(" in ss
assert "psa_aead_decrypt" in Path(
    "upstream/components/s3_ss2022/muse_ss2022.c"
).read_text()
assert "node_v2" in ss

# Ensure actual tests, not just prose claims, occur on every P3-3 PR run.
for gate in ("test_link_integration.py", "test_tls_interop.py",
             "official_server_probe", "S3_P3_EXTENDED_TLS=1",
             "test_source_ipv6.py", "pio run -e esp32s3_r8n16",
             "board_build.partitions = partitions.csv"):
    assert gate in workflow, gate

# Pre-production blockers: P4 MUST supply evidence, not auto-release at P3.
report = Path("docs/P3-EXIT.md").read_text()
for blocker in ("NVS", "4B", "NOT RUN", "PSRAM", "实际公网"):
    assert blocker in report, blocker
print("PASS P3 exit source gate: both protocol DNS bindings, TLS trust, IPv4 AP and release blocks")
