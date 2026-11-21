/* SPDX-License-Identifier: MIT
 * P4-1 minimal, fail-closed, concurrent-safe 4B gateway permission state.
 * State changes are atomic; no Wi-Fi, netif, secrets, timers or side effects.
 */
#include "s3_gateway_policy.h"

static s3_gateway_policy_t device_policy = S3_GATEWAY_POLICY_INIT;
s3_gateway_policy_t *s3_gateway_policy_device(void) { return &device_policy; }

bool s3_gateway_dhcp_destination_allowed(uint32_t dst,
                                         uint32_t ap_ip, uint32_t netmask)
{
    if (!ap_ip || !netmask) return false;
    return dst == UINT32_MAX || dst == ap_ip ||
           dst == ((ap_ip & netmask) | ~netmask);
}

#define S3_F_STA    (1u << 0)
#define S3_F_NODE   (1u << 1)
#define S3_F_RELAY  (1u << 2)
#define S3_F_ARMED  (1u << 3)
#define S3_F_CONFIG (1u << 4)
#define S3_F_ALLOW (S3_F_STA | S3_F_NODE | S3_F_RELAY | S3_F_ARMED)

void s3_gateway_policy_init(s3_gateway_policy_t *policy) {
    if (policy) {
        __atomic_store_n(&policy->flags, 0u, __ATOMIC_RELEASE);
    }
}

void s3_gateway_policy_event(s3_gateway_policy_t *policy, s3_gateway_event_t event) {
    if (!policy) return;
    uint32_t old_flags;
    uint32_t next;
    do {
        old_flags = __atomic_load_n(&policy->flags, __ATOMIC_ACQUIRE);
        next = old_flags;
        switch (event) {
            case S3_GW_RESET:
                next = 0u;
                break;
            case S3_GW_STA_CONNECTED:
                if (!(old_flags & S3_F_CONFIG)) next |= S3_F_STA;
                break;
            case S3_GW_STA_DISCONNECTED:
                next &= ~(S3_F_STA | S3_F_RELAY | S3_F_ARMED);
                break;
            case S3_GW_CONFIG_ENTER:
                next |= S3_F_CONFIG;
                next &= ~(S3_F_STA | S3_F_RELAY | S3_F_ARMED);
                break;
            case S3_GW_CONFIG_EXIT:
                next &= ~S3_F_CONFIG;
                break;
            case S3_GW_NODE_VALIDATED:
                if (!(old_flags & S3_F_CONFIG)) next |= S3_F_NODE;
                break;
            case S3_GW_NODE_INVALIDATED:
                next &= ~(S3_F_NODE | S3_F_RELAY | S3_F_ARMED);
                break;
            case S3_GW_RELAY_READY:
                if ((old_flags & (S3_F_STA | S3_F_NODE | S3_F_CONFIG)) ==
                    (S3_F_STA | S3_F_NODE)) next |= S3_F_RELAY;
                break;
            case S3_GW_RELAY_FAILED:
                next &= ~(S3_F_RELAY | S3_F_ARMED);
                break;
            case S3_GW_ADMIN_ARM:
                if ((old_flags & (S3_F_STA | S3_F_NODE | S3_F_RELAY | S3_F_CONFIG)) ==
                    (S3_F_STA | S3_F_NODE | S3_F_RELAY)) next |= S3_F_ARMED;
                else next &= ~S3_F_ARMED;
                break;
            case S3_GW_ADMIN_DISARM:
                next &= ~S3_F_ARMED;
                break;
            default:
                /* Unknown inputs cannot change or arm state. */
                break;
        }
        if (next == old_flags) return;
    } while (!__atomic_compare_exchange_n(&policy->flags, &old_flags, next,
                                           false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE));
}

bool s3_gateway_policy_ready(const s3_gateway_policy_t *policy) {
    if (!policy) return false;
    uint32_t flags = __atomic_load_n(&policy->flags, __ATOMIC_ACQUIRE);
    return (flags & (S3_F_ALLOW | S3_F_CONFIG)) == S3_F_ALLOW;
}

s3_gateway_packet_action_t s3_gateway_packet_decide(
    const s3_gateway_policy_t *policy, bool input_is_gateway_ap,
    bool destination_is_gateway_ap, uint8_t ip_proto,
    uint16_t source_port, uint16_t destination_port) {
    if (!input_is_gateway_ap) return S3_GW_PACKET_IGNORE;
    /* DHCPv4 to the local interface is permitted even when the proxy is
     * disabled, but only the client->server port pair. */
    if (ip_proto == 17u && source_port == 68u && destination_port == 67u)
        return S3_GW_PACKET_LOCAL;
    /* Only the AP-owned DNS endpoint may answer AP requests. Remote DNS UDP
     * is always blocked: DNS must use encrypted proxy TCP upstream. */
    if (destination_is_gateway_ap &&
        (ip_proto == 17u || ip_proto == 6u) && destination_port == 53u)
        return S3_GW_PACKET_LOCAL;
    if (destination_is_gateway_ap || ip_proto != 6u)
        return S3_GW_PACKET_DROP;
    return s3_gateway_policy_ready(policy)
        ? S3_GW_PACKET_INTERCEPT : S3_GW_PACKET_DROP;
}
