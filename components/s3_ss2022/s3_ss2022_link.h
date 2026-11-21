/* SPDX-License-Identifier: Apache-2.0
 * New S3-Voice adapter around rlog's unchanged SS2022 production C core.
 * TCP-only and IPv4 SS2022 server endpoint until the P3 IPv6 adapter.
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef void (*s3_ss2022_bandwidth_cb)(size_t bytes);
typedef struct {
    uint32_t magic;
    char server_ipv4[16];
    uint16_t server_port;
    uint8_t psk[16];
} s3_ss2022_node_t;

/* Physical USB serial provisioning only; credentials must never be logged. */
bool s3_ss2022_node_store(const char *ip, uint16_t port, const char *key_b64);
bool s3_ss2022_node_load(s3_ss2022_node_t *out);
bool s3_ss2022_node_clear(void);
bool s3_ss2022_node_valid(const s3_ss2022_node_t *node);
void s3_ss2022_node_wipe(s3_ss2022_node_t *node);

/* Must be called once after esp_netif_init, before Wi-Fi comes online. */
bool s3_ss2022_start_clock(void);

/* Caller owns client fd, request initial bytes; relay closes ONLY server fd. */
bool s3_ss2022_relay(int client, const s3_ss2022_node_t *node, const char *destination,
                     uint16_t port, const uint8_t *initial, size_t initial_length,
                     s3_ss2022_bandwidth_cb upload, s3_ss2022_bandwidth_cb download);

/* Uses the SAME SS2022 TCP encryption for RFC 7766 TCP DNS (length + packet).
 * Device control-plane DNS MUST NOT fallback to direct UDP if this fails.
 */
bool s3_ss2022_dns_query(const s3_ss2022_node_t *node, const char *resolver,
                          uint8_t *packet, int *length, size_t capacity);
