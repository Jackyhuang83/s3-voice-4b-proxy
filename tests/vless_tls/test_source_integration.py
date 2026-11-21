#!/usr/bin/env python3
"""P3-1 source-level TLS guarantees. Host TLS tests and firmware build separate."""
from pathlib import Path
import re
src = Path("upstream/src/main.c").read_text()
transport = Path("upstream/src/transport_tcp.c").read_text()
cmake = Path("upstream/src/CMakeLists.txt").read_text()
tls = Path("upstream/components/s3_vless_tls/s3_vless_tls.c").read_text()
sdk = Path("upstream/sdkconfig.defaults").read_text()

entry = src.split("static void transparent_client_task(void *arg)",1)[1].split("static void transparent_maintenance_task",1)[0]
assert "s3_vless_tls_relay(" in entry, "missing TLS client connection"
assert entry.index("s3_vless_tls_relay(") < entry.index("s3_ss2022_relay(")
assert entry.index("s3_vless_tls_relay(") < entry.index("transport_tcp_open_domain(")
assert "if (s_transparent_mode == TRANSPARENT_MODE_VLESS)" in entry
assert "if (!s_has_upstream" in entry
assert "goto done;" in entry.split("s3_vless_tls_relay(",1)[1].split("#endif",1)[0]

dns = src.split("static void captive_dns_task(void *arg)",1)[1].split("static void reset_transparent_transport_state(",1)[0]
assert "s3_vless_tls_dns_query(" in dns
assert "s3_ss2022_dns_query(" in dns
assert "packet[3] = 0x82" in dns, "P1 SERVFAIL boundary lost"
assert dns.index("s3_vless_tls_dns_query(") < dns.index("dns_direct_query(")
assert "answer_ok = false" in dns

for function in ("transport_tcp_open_vless_stream(", "transport_tcp_open_vless_ipv4_stream(",
                 "transport_tcp_open_domain(", "transport_tcp_open_ipv4("):
    snippet = transport.split(function,1)[1].split("\n}",1)[0]
    assert "S3_PROXY_TCP_ONLY" in snippet and "return -1;" in snippet
assert "no plaintext VLESS/Mux" in src and "no unproxied UDP" in src
assert 's3_vless_tls' in cmake

# ESP-TLS: a valid CA trust bundle + SNI/hostname match is mandatory.
assert re.search(r"\.crt_bundle_attach\s*=\s*esp_crt_bundle_attach", tls)
assert re.search(r"\.common_name\s*=\s*host\b", tls)
assert re.search(r"\.skip_common_name\s*=\s*false\b", tls)
assert "esp_tls_conn_new_sync(" in tls and "esp_tls_conn_destroy(" in tls
assert "esp_tls_conn_write(" in tls and "esp_tls_conn_read(" in tls
assert "response[0] == packet[0]" in tls and "response[1] == packet[1]" in tls
assert "S3_VLESS_TLS_MAX_CONCURRENT 2" in tls
assert "MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT" in tls
assert "time(NULL) < (time_t)1700000000" in tls
assert "CONFIG_MBEDTLS_CERTIFICATE_BUNDLE=y" in sdk
assert "skip_common_name = true" not in tls and "is_plain_tcp = true" not in tls

print("PASS P3-1 verified ESP-TLS VLESS only; no plaintext/domain/UDP fallback; P1/P2 guards intact")
