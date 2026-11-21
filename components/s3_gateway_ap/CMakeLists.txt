# AP configuration and DHCP-DNS helper only. Not a second Wi-Fi owner.
idf_component_register(
    SRCS "s3_gateway_ap_config.c" "s3_gateway_ap_dns.c"
    INCLUDE_DIRS "."
    REQUIRES esp_netif
)
