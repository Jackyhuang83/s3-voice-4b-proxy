/* SPDX-License-Identifier: MIT
 * AP-bound transparent TCP relay. P1 source owns original destination.
 */
#pragma once
#include <stdbool.h>
#include "esp_netif.h"
#include "s3_gateway_dns_processor.h"
#define S3_GATEWAY_TCP_RELAY_PORT 15001
typedef bool (*s3_gateway_client_event_t)(int client_fd, bool entering, void *arg);
int s3_gateway_tcp_listen(esp_netif_t *gateway_ap);
/* The caller publishes accepted client fd for cancellation via callback.
 * The callback must not close the socket: relay remains the sole fd owner.
 */
bool s3_gateway_tcp_accept_and_relay(int listener, esp_netif_t *gateway_ap,
                                     const s3_gateway_dns_upstream_t *node,
                                     s3_gateway_client_event_t client_event,
                                     void *event_arg);
