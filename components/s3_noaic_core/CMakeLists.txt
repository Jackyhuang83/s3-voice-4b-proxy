# R2-P1-1: upstream NOAIC portable data plane; library is compiled only.
# The original NOAIC app_main/Wi-Fi/HTTP/NVS/SOCKS5/UDP workers are NOT imported.
# Actual AP interception and encrypted relay are staged P1-2 and P2/P3.
idf_component_register(SRCS "flow_table.c" "packet_rewrite.c" "ap_clients.c"
                       INCLUDE_DIRS "." PRIV_REQUIRES freertos)
