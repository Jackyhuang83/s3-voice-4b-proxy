/* P4-1 | Voice-owned downstream TCP policy.
 * SPDX-License-Identifier: MIT
 * No Wi-Fi API, NVS credentials, sockets or lwIP interception in this module.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    volatile uint32_t flags;
} s3_gateway_policy_t;

#define S3_GATEWAY_POLICY_INIT {0u}

typedef enum {
    S3_GW_RESET = 0,
    S3_GW_STA_CONNECTED,
    S3_GW_STA_DISCONNECTED,
    S3_GW_CONFIG_ENTER,
    S3_GW_CONFIG_EXIT,
    S3_GW_NODE_VALIDATED,
    S3_GW_NODE_INVALIDATED,
    S3_GW_RELAY_READY,
    S3_GW_RELAY_FAILED,
    S3_GW_ADMIN_ARM,
    S3_GW_ADMIN_DISARM
} s3_gateway_event_t;

typedef enum {
    S3_GW_PACKET_IGNORE = 0,    /* not from AP; keep Xiaozhi voice untouched */
    S3_GW_PACKET_LOCAL = 1,     /* AP DHCP or AP-local DNS only */
    S3_GW_PACKET_DROP = 2,      /* no direct, UDP, ICMP, IPv6 forwarding */
    S3_GW_PACKET_INTERCEPT = 3  /* external TCP through verified relay only */
} s3_gateway_packet_action_t;

/* Shared between voice station events and AP-only packet hook. */
s3_gateway_policy_t *s3_gateway_policy_device(void);
struct netif;
void s3_gateway_lwip_bind_ap(struct netif *ap);
void s3_gateway_lwip_unbind_ap(void);
struct netif *s3_gateway_lwip_current_ap(void);
void s3_gateway_policy_init(s3_gateway_policy_t *policy);
void s3_gateway_policy_event(s3_gateway_policy_t *policy, s3_gateway_event_t event);
bool s3_gateway_policy_ready(const s3_gateway_policy_t *policy);

/* Only relevant for packets positively identified as arriving on the AP
 * network interface, never for Xiaozhi's own STA voice connections. */
s3_gateway_packet_action_t s3_gateway_packet_decide(
    const s3_gateway_policy_t *policy,
    bool input_is_gateway_ap,
    bool destination_is_gateway_ap,
    uint8_t ip_proto,
    uint16_t source_port,
    uint16_t destination_port);

#ifdef __cplusplus
}
#endif
