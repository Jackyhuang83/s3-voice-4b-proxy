/* SPDX-License-Identifier: MIT
 * AP-only fail-closed IPv4 input. Xiaozhi STA/voice remains untouched.
 * No AP or listener is ever started by this component.
 */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "lwip/netif.h"
#include "lwip/pbuf.h"
#include "lwip/ip4_addr.h"
#include "s3_gateway_policy.h"
#include "transparent_tcp.h"
/* Pinned to router/include/lwip_router_hook.h; do not import its conflicting Hook macro. */
int transparent_tcp_ip4_input(struct pbuf *packet, struct netif *input_netif);

static struct netif * volatile bound_ap;
void s3_gateway_lwip_bind_ap(struct netif *ap) {
    __atomic_store_n(&bound_ap, ap, __ATOMIC_RELEASE);
}
void s3_gateway_lwip_unbind_ap(void) {
    __atomic_store_n(&bound_ap, NULL, __ATOMIC_RELEASE);
}
struct netif *s3_gateway_lwip_current_ap(void) {
    return __atomic_load_n(&bound_ap, __ATOMIC_ACQUIRE);
}
static int drop(struct pbuf *packet) {
    pbuf_free(packet);
    return 1;
}
int s3_gateway_ip4_input(struct pbuf *packet, struct netif *netif) {
    struct netif *ap = __atomic_load_n(&bound_ap, __ATOMIC_ACQUIRE);
    if (!ap || netif != ap) return 0; /* Never affect the voice STA. */
    /* P1 reinjects the rewritten TCP segment with destination AP:15001.
     * Suppress ONLY that internal recursion; arbitrary AP-local :15001
     * packets still follow the drop policy. */
    if (transparent_tcp_is_reinjecting()) return 0;
    if (!packet) return 1;
    if (packet->tot_len < 20) return drop(packet);
    uint8_t hdr[20];
    if (pbuf_copy_partial(packet, hdr, sizeof(hdr), 0) != sizeof(hdr))
        return drop(packet);
    unsigned ihl = (unsigned)(hdr[0] & 15u) * 4u;
    if ((hdr[0] >> 4) != 4 || ihl < 20 || ihl > 60 ||
        packet->tot_len < ihl || (hdr[6] & 0x3fu) || hdr[7])
        return drop(packet);
    uint16_t total = (uint16_t)(((unsigned)hdr[2] << 8) | hdr[3]);
    if (total < ihl || total > packet->tot_len) return drop(packet);
    uint32_t dest;
    memcpy(&dest, hdr + 16, sizeof(dest));
    bool local = (dest == ip4_addr_get_u32(netif_ip4_addr(ap)));
    uint8_t proto = hdr[9];
    uint16_t sport = 0, dport = 0;
    if (proto == 6 || proto == 17) {
        uint8_t ports[4];
        if (total < ihl + 4 || pbuf_copy_partial(packet, ports, 4, ihl) != 4)
            return drop(packet);
        sport = (uint16_t)(((unsigned)ports[0] << 8) | ports[1]);
        dport = (uint16_t)(((unsigned)ports[2] << 8) | ports[3]);
    }
    /* DHCP client port 68->67 is NOT an exemption for arbitrary WAN IP.
     * Only the AP interface address or broadcast destinations are local. */
    if (proto == 17 && sport == 68 && dport == 67 &&
        !s3_gateway_dhcp_destination_allowed(dest,
             ip4_addr_get_u32(netif_ip4_addr(ap)),
             ip4_addr_get_u32(netif_ip4_netmask(ap))))
        return drop(packet);
    s3_gateway_packet_action_t action = s3_gateway_packet_decide(
        s3_gateway_policy_device(), true, local, proto, sport, dport);
    if (action == S3_GW_PACKET_LOCAL) return 0; /* Local DHCP/DNS. */
    if (action != S3_GW_PACKET_INTERCEPT || proto != 6 ||
        total < ihl + 20) return drop(packet);
    /* P1 validated transparent core; never allow direct fallback. */
    if (transparent_tcp_ip4_input(packet, netif)) return 1;
    return drop(packet);
}
