/* SPDX-License-Identifier: MIT
 * Local-only development NVS store for verified VLESS over TLS.
 * No Reality, no insecure TLS, no secrets in source/log output.
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef struct {
    uint32_t magic;
    uint16_t port;
    char hostname[254];
    uint8_t uuid[16];
} s3_gateway_vless_node_t;
bool s3_gateway_vless_store(const char *hostname, uint16_t port,
                             const char *uuid_text);
bool s3_gateway_vless_load(s3_gateway_vless_node_t *node);
bool s3_gateway_vless_clear(void);
void s3_gateway_vless_wipe(s3_gateway_vless_node_t *node);
