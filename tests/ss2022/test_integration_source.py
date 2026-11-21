#!/usr/bin/env python3
"""Require exact P2-2 routing and DNS safety invariants after source injection."""
from pathlib import Path

root = Path("upstream/src")
main = (root / "main.c").read_text()
config = (root / "router_config.h").read_text()
cmake = (root / "CMakeLists.txt").read_text()
link = Path("upstream/components/s3_ss2022/s3_ss2022_link.c").read_text()

task = main.split("static void transparent_client_task(void *arg)", 1)[1].split("static void transparent_maintenance_task", 1)[0]
assert task.count("s3_ss2022_relay(") == 1
assert task.index("s3_ss2022_relay(") < task.index("transport_tcp_open_domain(")
assert task.index("s3_ss2022_relay(") < task.index("transport_tcp_open_ipv4(")
assert "if (!s_has_upstream || !s3_ss2022_node_valid" in task
assert "goto done;" in task.split("s3_ss2022_relay(", 1)[1].split("#endif", 1)[0]
assert 'TRANSPARENT_MODE_SS2022' in config

dns = main.split("static void captive_dns_task(void *arg)", 1)[1].split("static void reset_transparent_transport_state", 1)[0]
assert "s3_ss2022_dns_query(" in dns and "dns_cache_response_records(packet, bytes)" in dns
assert dns.index("s3_ss2022_dns_query(") < dns.index("dns_direct_query(")
assert "s_transparent_mode == TRANSPARENT_MODE_UPSTREAM" in dns
assert "if (!s_configuration_mode)" in dns, "P1 captive DNS failure fix must stay active"

console = main.split("static void serial_console_task(void *arg)", 1)[1]
assert "s3_ss2022_node_store(" in console and "s3_ss2022_node_load(" in console
assert "memset(rest, 0, strlen(rest))" in console, "USB provisioning secret must be wiped"
assert "Direct route is disabled in TCP-only firmware" in console
assert "s3_ss2022_node_clear()" in main, "Factory reset must erase separate node namespace"
assert 'S3_PROXY_TCP_ONLY' in main and 's3_ss2022_start_clock()' in main
assert "s3_ss2022" in cmake
assert "MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT" in link
assert "S3_SS2022_MAX_RELAY 2" in link
assert "esp_netif_sntp_sync_wait" in link
assert "esp_fill_random(salt" in link
assert "s3_ss2022_node_valid(node)" in link
assert "ss2022_feed" in link and "ss2022_payload" in link
assert "return false" in link

print("PASS: P2-2 SS2022 only after node/STA gating, DNS never uses direct, PSRAM, SNTP, session caps")
