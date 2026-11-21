# AP configuration and DHCP-DNS helper only. Not a second Wi-Fi owner.
idf_component_register(
    SRCS "s3_gateway_ap_config.c" "s3_gateway_ap_dns.c" "s3_gateway_ap_runtime.c" "s3_gateway_workers.c" "s3_gateway_runtime_guard.c" "s3_gateway_console.c" "s3_gateway_vless_node.c"
    INCLUDE_DIRS "."
    REQUIRES console s3_ss2022 esp_netif esp_wifi nvs_flash lwip s3_gateway_policy s3_gateway_dns s3_gateway_tcp s3_gateway_session s3_tcp_guard freertos
)
