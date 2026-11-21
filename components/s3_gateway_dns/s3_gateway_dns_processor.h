/* SPDX-License-Identifier: MIT */
#pragma once
#include <stdint.h>
#include <stddef.h>
#include "s3_ss2022_link.h"

typedef enum {
    S3_GATEWAY_DNS_NONE = 0,
    S3_GATEWAY_DNS_SS2022 = 1,
    S3_GATEWAY_DNS_VLESS_TLS = 2
} s3_gateway_dns_transport_t;

typedef struct {
    s3_gateway_dns_transport_t transport;
    const s3_ss2022_node_t *ss2022_node;
    const char *vless_sni;
    uint16_t vless_port;
    const uint8_t *vless_uuid;
    /* Resolver destination *inside* an authenticated encrypted proxy. */
    const char *resolver;
} s3_gateway_dns_upstream_t;

/* Authenticated encrypted DNS response or bounded SERVFAIL. No direct DNS. */
size_t s3_gateway_dns_process(const s3_gateway_dns_upstream_t *upstream,
                              const uint8_t *request, size_t request_len,
                              uint8_t *answer, size_t answer_capacity);
