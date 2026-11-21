#!/usr/bin/env python3
"""P3-2: after P1+P2+P3-1 integrations, enable ONLY STA IPv6 SLAAC.

The original downstream AP remains IPv4-only; this is not an IPv6 AP/router
implementation. Every source replacement must match exactly once.
"""
from pathlib import Path

path = Path("upstream/src/main.c")
src = path.read_text()


def once(old, new):
    global src
    n = src.count(old)
    if n != 1:
        raise AssertionError(f"P3-2 expected exactly one anchor, got {n}: {old[:90]!r}")
    src = src.replace(old, new, 1)


once('static bool               s_has_upstream;\n',
     'static bool               s_has_upstream;\n'
     '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
     'static bool               s_sta_has_ipv4;\n'
     'static bool               s_sta_has_ipv6;\n'
     '#endif\n')

once('    if (base == WIFI_EVENT && event == WIFI_EVENT_AP_START)\n',
     '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
     '    if (base == WIFI_EVENT && event == WIFI_EVENT_STA_CONNECTED)\n'
     '    {\n'
     '        /* Only STA may create an IPv6 link-local address; router\n'
     '           advertisements supply SLAAC and the default v6 route. */\n'
     '        if (s_sta_netif && esp_netif_create_ip6_linklocal(s_sta_netif) != ESP_OK)\n'
     '            ESP_LOGW(TAG, "STA IPv6 link-local setup was not ready");\n'
     '    }\n'
     '    if (base == WIFI_EVENT && event == WIFI_EVENT_STA_DISCONNECTED)\n'
     '    {\n'
     '        s_sta_has_ipv4 = false;\n'
     '        s_sta_has_ipv6 = false;\n'
     '        s_has_upstream = false;\n'
     '    }\n'
     '    if (base == IP_EVENT && event == IP_EVENT_GOT_IP6)\n'
     '    {\n'
     '        const ip_event_got_ip6_t *got = data;\n'
     '        esp_ip6_addr_t global = {0};\n'
     '        if (got && got->esp_netif == s_sta_netif && !s_configuration_mode &&\n'
     '            esp_netif_get_ip6_global(s_sta_netif, &global) == ESP_OK)\n'
     '        {\n'
     '            s_sta_has_ipv6 = true;\n'
     '            s_has_upstream = s_sta_has_ipv4 || s_sta_has_ipv6;\n'
     '            s_boot_upstream_connected = true;\n'
     '            refresh_transparent_interception_state();\n'
     '            status_led_show_mode(s_transparent_mode, s_has_upstream);\n'
     '            ESP_LOGI(TAG, "Upstream STA acquired global IPv6 via SLAAC");\n'
     '        }\n'
     '    }\n'
     '#endif\n'
     '    if (base == WIFI_EVENT && event == WIFI_EVENT_AP_START)\n')

once('        s_has_upstream            = true;\n        s_boot_upstream_connected = true;\n',
     '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
     '        s_sta_has_ipv4          = true;\n'
     '        s_has_upstream          = s_sta_has_ipv4 || s_sta_has_ipv6;\n'
     '#else\n'
     '        s_has_upstream          = true;\n'
     '#endif\n'
     '        s_boot_upstream_connected = true;\n')

once('    s_sta_netif             = esp_netif_create_default_wifi_sta();\n',
     '    s_sta_netif             = esp_netif_create_default_wifi_sta();\n'
     '    /* AP IPv6 initialization deliberately omitted. */\n')

once('    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP,\n'
     '                                                        network_event, NULL, NULL));\n',
     '    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP,\n'
     '                                                        network_event, NULL, NULL));\n'
     '#if defined(S3_PROXY_TCP_ONLY) && S3_PROXY_TCP_ONLY\n'
     '    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_GOT_IP6,\n'
     '                                                        network_event, NULL, NULL));\n'
     '#endif\n')
path.write_text(src)

sdk = Path("upstream/sdkconfig.defaults")
settings = sdk.read_text()
for key, value in (
    ("CONFIG_LWIP_IPV6", "y"),
    ("CONFIG_LWIP_IPV6_AUTOCONFIG", "y"),
    ("CONFIG_LWIP_IPV6_DHCP6", "y"),
    ("CONFIG_LWIP_IPV6_RDNSS_MAX_DNS_SERVERS", "2"),
):
    setting = f"{key}={value}"
    if setting not in settings:
        settings += "\n" + setting + "\n"
sdk.write_text(settings)
print("PASS P3-2 STA-only IPv6 SLAAC/gateway events, IPv4-or-IPv6 upstream, unchanged IPv4 AP")
