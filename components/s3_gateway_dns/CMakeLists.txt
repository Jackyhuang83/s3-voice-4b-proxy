# Query binding + response failure handling; no DNS listening socket.
idf_component_register(
    SRCS "s3_gateway_dns_codec.c" "s3_gateway_dns_processor.c" "s3_gateway_dns_udp.c" "s3_gateway_dns_tcp.c" "s3_gateway_dns_probe.c"
    INCLUDE_DIRS "."
    REQUIRES s3_ss2022 s3_vless_tls s3_gateway_policy esp_netif lwip esp_timer esp_hw_support
)
