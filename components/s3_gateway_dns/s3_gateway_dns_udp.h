/* SPDX-License-Identifier: MIT
 * AP-bound UDP DNS endpoint; all upstream requests use authenticated
 * SS2022 or TLS-verified VLESS DNS. No global/listen-on-STA socket.
 * Caller owns task life cycle, AP netif and upstream credentials.
 */
#pragma once
#include "esp_netif.h"
#include "s3_gateway_dns_processor.h"

/* Opens UDP:53 ONLY on configured WIFI_AP_DEF IPv4, or returns -1. */
int s3_gateway_dns_udp_open(esp_netif_t *gateway_ap);

/* Processes at most ONE AP-subnet datagram. Caller runs in a worker task. */
bool s3_gateway_dns_udp_poll(int fd, esp_netif_t *gateway_ap,
                             const s3_gateway_dns_upstream_t *upstream);
