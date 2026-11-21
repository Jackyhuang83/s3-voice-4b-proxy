# Only a gateway AP, never Xiaozhi STA, can be captured by this hook.
idf_component_register(
  SRCS "s3_gateway_policy.c" "s3_gateway_ip4.c" "s3_gateway_ip6.c"
  INCLUDE_DIRS "."
  REQUIRES lwip s3_tcp_guard
)
