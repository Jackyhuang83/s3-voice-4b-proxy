/* SPDX-License-Identifier: MIT
 * Local TCP:15001 gateway relay (P1's original redirected destination).
 * AP-bound, never a direct client destination socket.
 */
#pragma once
#include <stdbool.h>
#include "esp_netif.h"
#include "s3_gateway_dns_processor.h"

#define S3_GATEWAY_TCP_RELAY_PORT 15001

/* Creates a listener ONLY on WIFI_AP_DEF, or returns -1. */
int s3_gateway_tcp_listen(esp_netif_t *gateway_ap);

/* Handles ONE accepted client synchronously; call only from bounded relay
 * worker tasks with owned upstream settings and safe task cancellation.
 * Never call this blocking function from Xiaozhi's audio/Wi-Fi event loop.
 */
bool s3_gateway_tcp_accept_and_relay(int listener, esp_netif_t *gateway_ap,
                                     const s3_gateway_dns_upstream_t *node);
