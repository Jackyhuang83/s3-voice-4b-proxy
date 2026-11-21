/* SPDX-License-Identifier: MIT
 * Caller must pass the *existing* official WIFI_AP_DEF esp_netif.
 * The real DNS listener and encrypted relay must be available before
 * advertising this address in DHCP. No STA, AP or Wi-Fi driver is created.
 */
#pragma once
#include "esp_netif.h"
esp_err_t s3_gateway_ap_offer_local_dns(esp_netif_t *gateway_ap);
