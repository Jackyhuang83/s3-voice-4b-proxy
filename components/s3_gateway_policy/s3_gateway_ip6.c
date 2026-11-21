/* SPDX-License-Identifier: MIT
 * Per-interface IPv6 input filter on official ESP-IDF 6.1 custom hook.
 * Preserve the IDF default no-link-local guard for STA (voice/OTA/IPv6 VPS).
 * Drop ALL IPv6 on the proxy AP, including router advertisements and NDP.
 */
#include "lwip/netif.h"
#include "lwip/ip6_addr.h"
#include "lwip/pbuf.h"
#include "s3_gateway_policy.h"

int lwip_hook_ip6_input(struct pbuf *packet, struct netif *input_netif)
{
    if (!packet || !input_netif) {
        if (packet) pbuf_free(packet);
        return 1;
    }
    struct netif *ap = s3_gateway_lwip_current_ap();
    if ((ap && input_netif == ap) ||
        ip6_addr_isany(netif_ip6_addr(input_netif, 0))) {
        pbuf_free(packet);
        return 1;
    }
    return 0; /* Preserve stock ESP-IDF STA IPv6 behavior. */
}
