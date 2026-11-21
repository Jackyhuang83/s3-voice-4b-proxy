/* SPDX-License-Identifier: MIT
 * Official ESP-IDF lwIP input hook: inert until gateway AP is bound.
 */
#pragma once
#include "lwip/netif.h"
#include "lwip/pbuf.h"
#ifdef __cplusplus
extern "C" {
#endif
int s3_gateway_ip4_input(struct pbuf *packet, struct netif *input_netif);
#ifdef __cplusplus
}
#endif
#ifdef LWIP_HOOK_IP4_INPUT
#error "Another component already owns LWIP_HOOK_IP4_INPUT"
#endif
#define LWIP_HOOK_IP4_INPUT(packet, netif) s3_gateway_ip4_input((packet), (netif))
