# P3-1: a tiny transport adapter over official ESP-IDF ESP-TLS and CRT bundle.
# No copied TLS implementation or hand-written certificate verifier.
idf_component_register(
    SRCS "s3_vless_tls.c"
    INCLUDE_DIRS "."
    REQUIRES esp-tls mbedtls lwip esp_hw_support
)
