# Reuses Apache-2.0 SS2022 implementation from rlog/atoms3r-muse-firmware
# pinned at 57f73602e963e478e06eae5f8108d07495468031.
# BLAKE3 portable C implementation pinned via upstream at version 1.8.2.
# No ESP32-S3 networking/voice/display code is linked from the Muse project.
idf_component_register(
    SRCS
        "muse_ss2022.c"
        "s3_ss2022_link.c"
        "third_party/blake3/blake3.c"
        "third_party/blake3/blake3_dispatch.c"
        "third_party/blake3/blake3_portable.c"
    INCLUDE_DIRS "."
    REQUIRES mbedtls esp_netif nvs_flash lwip esp_hw_support
)
target_compile_definitions(${COMPONENT_LIB} PRIVATE
    BLAKE3_NO_SSE2 BLAKE3_NO_SSE41 BLAKE3_NO_AVX2
    BLAKE3_NO_AVX512 BLAKE3_USE_NEON=0)
