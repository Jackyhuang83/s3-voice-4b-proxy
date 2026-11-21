#!/usr/bin/env python3
"""P3-2: static audit of STA-only SLAAC, AF_INET6 proxy dialing and DNS trust.

Run after P1..P3-2 exact source injection and after clang-format.
A green build is not evidence of real Wi-Fi, RA, IPv6 default route or AP leak.
"""
from pathlib import Path
import re

main = Path("upstream/src/main.c").read_text()
cfg = Path("upstream/sdkconfig.defaults").read_text()
ss = Path("upstream/components/s3_ss2022/s3_ss2022_link.c").read_text()
tls = Path("upstream/components/s3_vless_tls/s3_vless_tls.c").read_text()

assert "IP_EVENT_GOT_IP6" in main
assert "esp_netif_get_ip6_global(s_sta_netif" in main
assert "esp_netif_create_ip6_linklocal(s_sta_netif)" in main
assert "esp_netif_create_ip6_linklocal(s_ap_netif)" not in main
assert "s_sta_has_ipv4 || s_sta_has_ipv6" in main
assert "s_sta_has_ipv4 = false" in main and "s_sta_has_ipv6 = false" in main
assert "IP_EVENT_STA_GOT_IP" in main
assert "esp_netif_create_default_wifi_ap()" in main
assert "esp_netif_create_default_wifi_sta()" in main
assert "transparent_tcp_set_ap_netif(" in main
for name in ["CONFIG_LWIP_IPV6=y", "CONFIG_LWIP_IPV6_AUTOCONFIG=y",
             "CONFIG_LWIP_IPV6_RDNSS_MAX_DNS_SERVERS=2",
             "CONFIG_LWIP_IPV6_DHCP6=y"]:
    assert name in cfg, name
assert "CONFIG_MBEDTLS_CERTIFICATE_BUNDLE=y" in cfg

assert "server_host[254]" in Path("components/s3_ss2022/s3_ss2022_link.h").read_text()
assert "getaddrinfo(node->server_host" in ss
assert "AF_INET6" in ss and "AF_INET" in ss and "AF_UNSPEC" in ss
assert "connect(fd, addr->ai_addr, addr->ai_addrlen)" in ss
assert "freeaddrinfo(addresses)" in ss
assert "s3_ss2022_node_v1_t" in ss
assert 'S3_SS2022_LEGACY_KEY "node"' in ss
assert 'S3_SS2022_KEY "node_v2"' in ss
assert "nvs_erase_key(handle, S3_SS2022_LEGACY_KEY)" in ss

assert "esp_tls_conn_new_sync(host" in tls
assert re.search(r"\.crt_bundle_attach\s*=\s*esp_crt_bundle_attach", tls)
assert re.search(r"\.common_name\s*=\s*host", tls)
assert re.search(r"\.skip_common_name\s*=\s*false", tls)
assert "s3_vless_tls_dns_query" in tls
assert "s3_vless_tls_relay" in main
assert "s3_ss2022_relay" in main

# P3-2 must not add a local IPv6 listener, IPv6 AP RA or naked TCP dial
# to the client original destination as a fallback on failed proxy.
assert "radvd" not in main and "nd6_send_ra" not in main
assert "open_direct_ipv6" not in main
print("PASS P3-2 STA IPv6-only, AA/A proxy-node dial, P2 NVS migration, VLESS TLS SNI and IPv4 AP")
