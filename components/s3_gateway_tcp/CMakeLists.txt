# Local P1 transparent TCP acceptor only; no Wi-Fi owner, no direct Internet.
idf_component_register(
    SRCS "s3_gateway_tcp_server.c"
    INCLUDE_DIRS "."
    REQUIRES s3_gateway_policy s3_gateway_dns s3_ss2022 s3_vless_tls
             s3_tcp_guard esp_netif lwip
)
