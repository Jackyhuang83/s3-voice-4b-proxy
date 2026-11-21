/* SPDX-License-Identifier: MIT
 * ESP-IDF 6.x: DHCP option 6 is explicit and must refer to the AP itself.
 * Never advertise upstream STA resolver (which may bypass proxy policy).
 */
#include <stdint.h>
#include <string.h>
#include "s3_gateway_ap_dns.h"

esp_err_t s3_gateway_ap_offer_local_dns(esp_netif_t *gateway_ap)
{
    if (!gateway_ap) return ESP_ERR_INVALID_ARG;
    const char *key = esp_netif_get_ifkey(gateway_ap);
    if (!key || strcmp(key, "WIFI_AP_DEF") != 0) return ESP_ERR_INVALID_ARG;
    esp_netif_ip_info_t ip = {0};
    esp_err_t result = esp_netif_get_ip_info(gateway_ap, &ip);
    if (result != ESP_OK) return result;
    if (ip.ip.addr == 0) return ESP_ERR_INVALID_STATE;
    esp_netif_dns_info_t dns = {0};
    dns.ip.type = IPADDR_TYPE_V4;
    dns.ip.u_addr.ip4.addr = ip.ip.addr;
    /* A failure after stopping DHCP leaves leases unavailable: fail closed. */
    result = esp_netif_dhcps_stop(gateway_ap);
    if (result != ESP_OK && result != ESP_ERR_ESP_NETIF_DHCP_ALREADY_STOPPED)
        return result;
    uint8_t offer = DHCPS_OFFER_DNS;
    result = esp_netif_dhcps_option(gateway_ap, ESP_NETIF_OP_SET,
                                  ESP_NETIF_DOMAIN_NAME_SERVER, &offer,
                                  sizeof(offer));
    if (result != ESP_OK) return result;
    result = esp_netif_set_dns_info(gateway_ap, ESP_NETIF_DNS_MAIN, &dns);
    if (result != ESP_OK) return result;
    return esp_netif_dhcps_start(gateway_ap);
}
