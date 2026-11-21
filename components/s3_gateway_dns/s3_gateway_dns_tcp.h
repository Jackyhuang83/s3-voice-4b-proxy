/* SPDX-License-Identifier: MIT
 * AP-only TCP/53 RFC 7766 endpoint; never launched automatically.
 * Caller owns all socket and task lifecycle, upstream and credentials.
 */
#pragma once
#include <stdbool.h>
#include "esp_netif.h"
#include "s3_gateway_dns_processor.h"

/* Listen only on WIFI_AP_DEF IPv4 address, -1 on failure. */
int s3_gateway_dns_tcp_listen(esp_netif_t *gateway_ap);

/* One request per accepted AP client. May block; must only run in a
 * supervised FreeRTOS worker, never in voice or Wi-Fi event callbacks.
 */
bool s3_gateway_dns_tcp_poll(int listener, esp_netif_t *gateway_ap,
                             const s3_gateway_dns_upstream_t *upstream);
