#!/usr/bin/env python3
"""P3-1 post-P1/P2 injection: use VERIFIED ESP-TLS for every VLESS client TCP path.

This runs in a temporary CI checkout of the exact pinned yanxke upstream.
All edits have exactly-one-context assertions; never touches stable device image.
"""
from pathlib import Path

main_path = Path("upstream/src/main.c")
transport_path = Path("upstream/src/transport_tcp.c")
cmake_path = Path("upstream/src/CMakeLists.txt")
main = main_path.read_text()
transport = transport_path.read_text()
cmake = cmake_path.read_text()


def once(content, original, replacement, label):
    count = content.count(original)
    if count != 1:
        raise ValueError(f"Expected exactly one {label}: {count} matches")
    return content.replace(original, replacement, 1)


main = once(main,
    '#include "s3_ss2022_link.h"\n',
    '#include "s3_ss2022_link.h"\n'
    '#include "s3_vless_tls.h"\n',
    "header import")

# TCP session: prefer the existing DNS-IP mapping; if none, use the original
# IPv4 address as the *target* inside VLESS. TLS server identity must remain
# the separately configured DNS hostname (never the target client SNI).
anchor = "    initial[initial_length]       = '\\0';\n"
main = once(main, anchor, anchor +
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '    if (s_transparent_mode == TRANSPARENT_MODE_VLESS)\n'
    '    {\n'
    '        uint8_t uuid[16];\n'
    '        if (!s_has_upstream ||\n'
    '            !transport_tcp_uuid_to_bytes(s_config.vless_uuid, uuid)) goto done;\n'
    '        char target[254] = {0};\n'
    '        if (!transparent_tcp_dns_name_for_ip(flow.original_ip, target, sizeof(target)))\n'
    '        {\n'
    '            struct in_addr addr = {.s_addr = flow.original_ip};\n'
    '            if (!inet_ntop(AF_INET, &addr, target, sizeof(target))) goto done;\n'
    '        }\n'
    '        /* No TLS handshake = no VLESS bytes, no direct/legacy fallback. */\n'
    '        (void)s3_vless_tls_relay(client, s_config.vless_host, s_config.vless_port,\n'
    '                                 uuid, target, flow.original_port, initial,\n'
    '                                 (size_t)initial_length, bandwidth_record_upload,\n'
    '                                 bandwidth_record_download);\n'
    '        memset(uuid, 0, sizeof(uuid));\n'
    '        goto done;\n'
    '    }\n'
    '#endif\n',
    "transparent TCP secured VLESS branch")

# P2 DNS switch is preserved; exactly substitute VLESS only, never SS2022 and
# never direct UDP. Incorrect VLESS TLS/DNS returns to P1 SERVFAIL.
original = (
    '            answer_ok = (transparent_mode_uses_vless() && dns_vless_query(packet, &bytes)) ||\n'
    '                        (s_transparent_mode == TRANSPARENT_MODE_UPSTREAM &&\n'
    '                         dns_direct_query(packet, &bytes));\n'
)
replacement = (
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '            if (s_transparent_mode == TRANSPARENT_MODE_VLESS)\n'
    '            {\n'
    '                uint8_t uuid[16];\n'
    '                answer_ok = s_has_upstream &&\n'
    '                    transport_tcp_uuid_to_bytes(s_config.vless_uuid, uuid) &&\n'
    '                    s3_vless_tls_dns_query(s_config.vless_host, s_config.vless_port,\n'
    '                        uuid, s_config.dns_resolver[0] ? s_config.dns_resolver : "1.1.1.1",\n'
    '                        packet, &bytes, sizeof(packet));\n'
    '                memset(uuid, 0, sizeof(uuid));\n'
    '                if (answer_ok) dns_cache_response_records(packet, bytes);\n'
    '            }\n'
    '            else\n'
    '                answer_ok = false;\n'
    '#else\n'
    '            answer_ok = (transparent_mode_uses_vless() && dns_vless_query(packet, &bytes)) ||\n'
    '                        (s_transparent_mode == TRANSPARENT_MODE_UPSTREAM &&\n'
    '                         dns_direct_query(packet, &bytes));\n'
    '#endif\n'
)
main = once(main, original, replacement, "VLESS DNS secured switch")

# This original hand-written mux test route never used the transport_tcp
# wrapper. Block it too in TCP-only builds (unmodified upstream builds keep it).
main = once(main,
    'static int open_vless_mux_stream(void)\n{\n',
    'static int open_vless_mux_stream(void)\n{\n'
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '    return -1; /* no plaintext VLESS/Mux test endpoint in TCP-only build */\n'
    '#endif\n',
    "standalone plain XUDP mux disabled")
main = once(main,
    'static int open_direct_udp_stream(uint32_t destination_ip, uint16_t destination_port)\n{\n',
    'static int open_direct_udp_stream(uint32_t destination_ip, uint16_t destination_port)\n{\n'
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '    return -1; /* no unproxied UDP socket path in TCP-only build */\n'
    '#endif\n',
    "direct UDP socket disabled")

# Plain VLESS helpers are invoked by SOCKS, Singmux and legacy diagnostics.
# They must be inoperable in TCP-only firmware even if invoked accidentally.
transport = once(transport,
    'int transport_tcp_open_vless_stream(const router_config_t *config, bool has_upstream,\n'
    '                                    const char *destination, uint16_t destination_port)\n{\n',
    'int transport_tcp_open_vless_stream(const router_config_t *config, bool has_upstream,\n'
    '                                    const char *destination, uint16_t destination_port)\n{\n'
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '    return -1; /* plaintext VLESS is forbidden; only ESP-TLS adapter */\n'
    '#endif\n',
    "plaintext VLESS domain function")
transport = once(transport,
    'int transport_tcp_open_vless_ipv4_stream(const router_config_t *config, bool has_upstream,\n'
    '                                         uint32_t destination_ip, uint16_t destination_port)\n{\n',
    'int transport_tcp_open_vless_ipv4_stream(const router_config_t *config, bool has_upstream,\n'
    '                                         uint32_t destination_ip, uint16_t destination_port)\n{\n'
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '    return -1; /* plaintext VLESS is forbidden */\n'
    '#endif\n',
    "plaintext VLESS IPv4 function")
transport = once(transport,
    'int transport_tcp_open_domain(transparent_mode_t mode, const router_config_t *config,\n'
    '                              bool has_upstream, const char *destination,\n'
    '                              uint16_t destination_port)\n{\n',
    'int transport_tcp_open_domain(transparent_mode_t mode, const router_config_t *config,\n'
    '                              bool has_upstream, const char *destination,\n'
    '                              uint16_t destination_port)\n{\n'
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '    return -1; /* fail closed, route/target never connect directly */\n'
    '#endif\n',
    "legacy direct domain fallback")
transport = once(transport,
    'int transport_tcp_open_ipv4(transparent_mode_t mode, const router_config_t *config,\n'
    '                            bool has_upstream, uint32_t destination_ip,\n'
    '                            uint16_t destination_port)\n{\n',
    'int transport_tcp_open_ipv4(transparent_mode_t mode, const router_config_t *config,\n'
    '                            bool has_upstream, uint32_t destination_ip,\n'
    '                            uint16_t destination_port)\n{\n'
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '    return -1; /* fail closed, legacy direct mode forbidden */\n'
    '#endif\n',
    "legacy direct IPv4 fallback")

cmake = once(cmake, 'app_update s3_ss2022)',
             'app_update s3_ss2022 s3_vless_tls)', "ESP-IDF component dependency")
main_path.write_text(main)
transport_path.write_text(transport)
cmake_path.write_text(cmake)

# TLS MUST use the official ESP-IDF certificate bundle on the real target.
sdk = Path("upstream/sdkconfig.defaults")
settings = sdk.read_text()
setting = "CONFIG_MBEDTLS_CERTIFICATE_BUNDLE=y"
if setting not in settings:
    settings += "\n" + setting + "\n"
sdk.write_text(settings)
print("PASS P3-1 exact VLESS ESP-TLS injection, DNS and plaintext fallback isolation")
