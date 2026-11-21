#!/usr/bin/env python3
"""Apply P2-2 SS2022 TCP integration to the PINNED upstream, after P1 patches.

Every replacement is strict (exactly one occurrence) to prevent silent drift.
The original yanxke repository and firmware remain untouched on devices.
"""
from pathlib import Path

ROOT = Path("upstream")
main_path = ROOT / "src/main.c"
header_path = ROOT / "src/router_config.h"
cmake_path = ROOT / "src/CMakeLists.txt"


def replace_once(text: str, old: str, new: str, path: Path) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{path}: expected 1 exact match, got {count}: {old[:90]!r}")
    return text.replace(old, new, 1)


main = main_path.read_text()
main = replace_once(main,
    '#include "transport_tcp.h"\n',
    '#include "transport_tcp.h"\n#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '#include "s3_ss2022_link.h"\n#endif\n', main_path)
main = replace_once(main,
    "static router_config_t    s_config;\n",
    "static router_config_t    s_config;\n"
    "#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n"
    "static s3_ss2022_node_t s_ss2022_node;\n"
    "#endif\n", main_path)
main = replace_once(main,
    'return transparent_mode_uses_vless() ? "transparent-vless" : "transparent-upstream";',
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '    if (s_transparent_mode == TRANSPARENT_MODE_SS2022) return "transparent-ss2022";\n'
    '#endif\n'
    '    return transparent_mode_uses_vless() ? "transparent-vless" : "transparent-upstream";', main_path)

anchor = "    initial[initial_length]       = '\\0';\n"
main = replace_once(main, anchor, anchor +
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '    if (s_transparent_mode == TRANSPARENT_MODE_SS2022)\n'
    '    {\n'
    '        /* The existing lwIP flow table is the single source of destination truth.\n'
    '           SS2022 has no direct fallback if a node or tunnel is unavailable. */\n'
    '        if (!s_has_upstream || !s3_ss2022_node_valid(&s_ss2022_node)) goto done;\n'
    '        char destination[254] = {0};\n'
    '        if (!transparent_tcp_dns_name_for_ip(flow.original_ip, destination, sizeof(destination)))\n'
    '        {\n'
    '            struct in_addr addr = {.s_addr = flow.original_ip};\n'
    '            if (!inet_ntop(AF_INET, &addr, destination, sizeof(destination))) goto done;\n'
    '        }\n'
    '        (void)s3_ss2022_relay(client, &s_ss2022_node, destination, flow.original_port,\n'
    '                              initial, (size_t)initial_length,\n'
    '                              bandwidth_record_upload, bandwidth_record_download);\n'
    '        goto done;\n'
    '    }\n'
    '#endif\n', main_path)

# Preserve original VLESS DNS and original direct mode ONLY where explicitly permitted.
old_dns = (
    '        if ((transparent_mode_uses_vless() && dns_vless_query(packet, &bytes)) ||\n'
    '            (!transparent_mode_uses_vless() && dns_direct_query(packet, &bytes)))\n'
    '        {\n'
    '            sendto(sock, packet, bytes, 0, (struct sockaddr *)&client, len);\n'
    '            continue;\n'
    '        }\n'
)
new_dns = (
    '        bool answer_ok = false;\n'
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '        if (s_transparent_mode == TRANSPARENT_MODE_SS2022)\n'
    '        {\n'
    '            /* Client DNS uses remote TCP/53 INSIDE SS2022; never direct UDP. */\n'
    '            answer_ok = s_has_upstream &&\n'
    '                s3_ss2022_dns_query(&s_ss2022_node,\n'
    '                    s_config.dns_resolver[0] ? s_config.dns_resolver : "1.1.1.1",\n'
    '                    packet, &bytes, sizeof(packet));\n'
    '            if (answer_ok) dns_cache_response_records(packet, bytes);\n'
    '        }\n'
    '        else\n'
    '#endif\n'
    '        {\n'
    '            answer_ok = (transparent_mode_uses_vless() && dns_vless_query(packet, &bytes)) ||\n'
    '                        (s_transparent_mode == TRANSPARENT_MODE_UPSTREAM &&\n'
    '                         dns_direct_query(packet, &bytes));\n'
    '        }\n'
    '        if (answer_ok)\n'
    '        {\n'
    '            sendto(sock, packet, bytes, 0, (struct sockaddr *)&client, len);\n'
    '            continue;\n'
    '        }\n'
)
main = replace_once(main, old_dns, new_dns, main_path)

# Physical serial-only secret provision. Never print the PSK or a URL containing it.
anchor = '        if (strcmp(command, "route") == 0)\n        {\n'
main = replace_once(main, anchor,
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '        if (strcmp(command, "ss2022") == 0)\n'
    '        {\n'
    '            bool ok = false;\n'
    '            if (first && !second && !rest && strcmp(first, "clear") == 0)\n'
    '            {\n'
    '                ok = s3_ss2022_node_clear();\n'
    '                if (ok) s3_ss2022_node_wipe(&s_ss2022_node);\n'
    '            }\n'
    '            else if (first && second && rest)\n'
    '            {\n'
    '                char *end = NULL;\n'
    '                long port = strtol(second, &end, 10);\n'
    '                if (end && !*end && port > 0 && port <= 65535)\n'
    '                {\n'
    '                    ok = s3_ss2022_node_store(first, (uint16_t)port, rest);\n'
    '                    if (ok) ok = s3_ss2022_node_load(&s_ss2022_node);\n'
    '                }\n'
    '                /* Physical serial provisioning: wipe parsed secret from input buffer. */\n'
    '                memset(rest, 0, strlen(rest));\n'
    '                memset(line, 0, sizeof(line));\n'
    '            }\n'
    '            ESP_LOGI(TAG, "SS2022 node %s (PSK never logged)",\n'
    '                     ok ? "saved/cleared" : "invalid or storage failed");\n'
    '            continue;\n'
    '        }\n'
    '#endif\n' + anchor, main_path)

main = replace_once(main, anchor,
    anchor +
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '            if (first && !second && strcmp(first, "ss2022") == 0)\n'
    '            {\n'
    '                if (s3_ss2022_node_valid(&s_ss2022_node))\n'
    '                    set_transparent_mode(TRANSPARENT_MODE_SS2022);\n'
    '                else ESP_LOGW(TAG, "SS2022 node missing; refusing to switch");\n'
    '                continue;\n'
    '            }\n'
    '            if (first && strcmp(first, "direct") == 0)\n'
    '            {\n'
    '                ESP_LOGW(TAG, "Direct route is disabled in TCP-only firmware");\n'
    '                continue;\n'
    '            }\n'
    '#endif\n', main_path)

main = replace_once(main,
    '    ESP_LOGI(TAG, "Serial commands: help; status; diag; route; wifi; ap; apip; vless; vless-uri; "\n',
    '    ESP_LOGI(TAG, "Serial commands: help; status; diag; route; wifi; ap; apip; vless; vless-uri; "\n', main_path) if False else main

# Add a clearly labeled local-only help line, never displaying credentials.
main = replace_once(main,
    '            ESP_LOGI(TAG, "mux <on|off>; admin <new-password>");\n',
    '            ESP_LOGI(TAG, "mux <on|off>; admin <new-password>");\n'
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '            ESP_LOGI(TAG, "ss2022 <IPv4> <port> <base64-16byte-PSK> | ss2022 clear; route ss2022");\n'
    '#endif\n', main_path)

# Existing authenticated web management may select a configured node but never
# accept a raw secret via the HTTP portal.
old_validation = (
    '    if (!form_value(body, "mode", mode, sizeof(mode)) ||\n'
    '        (strcmp(mode, "vless") != 0 && strcmp(mode, "direct") != 0))\n'
)
new_validation = (
    '    if (!form_value(body, "mode", mode, sizeof(mode)) ||\n'
    '        (strcmp(mode, "vless") != 0 && strcmp(mode, "direct") != 0\n'
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '         && strcmp(mode, "ss2022") != 0\n'
    '#endif\n'
    '         ))\n'
)
main = replace_once(main, old_validation, new_validation, main_path)
main = replace_once(main,
    '    set_transparent_mode(strcmp(mode, "direct") == 0 ? TRANSPARENT_MODE_UPSTREAM\n'
    '                                                     : TRANSPARENT_MODE_VLESS);\n',
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '    if (strcmp(mode, "direct") == 0)\n'
    '        return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Direct bypass disabled");\n'
    '    if (strcmp(mode, "ss2022") == 0)\n'
    '    {\n'
    '        if (!s3_ss2022_node_valid(&s_ss2022_node))\n'
    '            return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Configure SS2022 over physical USB first");\n'
    '        set_transparent_mode(TRANSPARENT_MODE_SS2022);\n'
    '        return send_json(req, "{\\"message\\":\\"SS2022 mode active for this boot.\\"}");\n'
    '    }\n'
    '#endif\n'
    '    set_transparent_mode(strcmp(mode, "direct") == 0 ? TRANSPARENT_MODE_UPSTREAM\n'
    '                                                     : TRANSPARENT_MODE_VLESS);\n', main_path)

main = replace_once(main,
    '    load_router_config(&s_config, TAG);\n',
    '    load_router_config(&s_config, TAG);\n'
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '    (void)s3_ss2022_node_load(&s_ss2022_node);\n'
    '#endif\n', main_path)
main = replace_once(main,
    '    ESP_ERROR_CHECK(esp_netif_init());\n',
    '    ESP_ERROR_CHECK(esp_netif_init());\n'
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '    if (!s3_ss2022_start_clock()) ESP_LOGW(TAG, "SNTP unavailable; SS2022 will fail closed");\n'
    '#endif\n', main_path)

# A 5-second BOOT factory reset must also erase the dedicated node namespace.
main = replace_once(main,
    '                vTaskDelay(pdMS_TO_TICKS(250));\n                esp_restart();\n',
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '                (void)s3_ss2022_node_clear();\n'
    '                s3_ss2022_node_wipe(&s_ss2022_node);\n'
    '#endif\n'
    '                vTaskDelay(pdMS_TO_TICKS(250));\n                esp_restart();\n', main_path)

header = header_path.read_text()
header = replace_once(header,
    '    TRANSPARENT_MODE_UPSTREAM,\n',
    '    TRANSPARENT_MODE_UPSTREAM,\n'
    '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
    '    TRANSPARENT_MODE_SS2022,\n'
    '#endif\n', header_path)

cmake = cmake_path.read_text()
cmake = replace_once(cmake,
    'REQUIRES esp_wifi esp_netif esp_event nvs_flash esp_http_server lwip esp_driver_rmt esp_driver_tsens app_update)',
    'REQUIRES esp_wifi esp_netif esp_event nvs_flash esp_http_server lwip esp_driver_rmt esp_driver_tsens app_update s3_ss2022)', cmake_path)

main_path.write_text(main)
header_path.write_text(header)
cmake_path.write_text(cmake)
print("PASS: exact source anchors verified, SS2022 TCP+DNS mode and NVS provisioning integrated")
