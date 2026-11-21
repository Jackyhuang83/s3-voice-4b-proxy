/* SPDX-License-Identifier: MIT
 * Optional WPA2 APSTA prestart under the original Xiaozhi Wi-Fi owner.
 * No AP enabled by default, no committed credentials or duplicate driver.
 */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "esp_wifi.h"
#include "esp_wifi_default.h"
#include "esp_netif.h"
#include "esp_netif_net_stack.h"
#include "nvs.h"
#include "lwip/netif.h"
#include "s3_gateway_ap_runtime.h"
#include "s3_gateway_ap_config.h"
#include "s3_gateway_ap_dns.h"
#include "s3_gateway_policy.h"
#include "transparent_tcp.h"

static esp_netif_t *active_ap;

static void wipe_secret(void *v, size_t n)
{
    volatile uint8_t *p = (volatile uint8_t *)v;
    while (n--) *p++ = 0;
}

/* Explicit provisioned authorization; absent/invalid NVS means STA only. */
static bool read_credentials(char ssid[33], char psk[64])
{
    nvs_handle_t h;
    if (nvs_open("s3_proxy_ap", NVS_READONLY, &h) != ESP_OK) return false;
    size_t ssid_len = 33, psk_len = 64;
    uint8_t enabled = 0;
    bool valid = nvs_get_u8(h, "enabled", &enabled) == ESP_OK &&
                 enabled == 1 &&
                 nvs_get_str(h, "ssid", ssid, &ssid_len) == ESP_OK &&
                 nvs_get_str(h, "psk", psk, &psk_len) == ESP_OK &&
                 s3_gateway_ap_credentials_valid(ssid, psk);
    nvs_close(h);
    return valid;
}

bool s3_gateway_ap_pre_start(void)
{
    if (active_ap) return false;
    char ssid[33] = {0};
    char psk[64] = {0};
    if (!read_credentials(ssid, psk)) {
        wipe_secret(ssid, sizeof(ssid));
        wipe_secret(psk, sizeof(psk));
        return false;
    }
    wifi_mode_t current = WIFI_MODE_NULL;
    if (esp_wifi_get_mode(&current) != ESP_OK ||
        (current != WIFI_MODE_NULL && current != WIFI_MODE_STA)) {
        wipe_secret(ssid, sizeof(ssid));
        wipe_secret(psk, sizeof(psk));
        return false;
    }
    esp_netif_t *ap = esp_netif_create_default_wifi_ap();
    if (!ap) {
        wipe_secret(ssid, sizeof(ssid));
        wipe_secret(psk, sizeof(psk));
        return false;
    }
    wifi_config_t cfg = {0};
    size_t n = strlen(ssid), p = strlen(psk);
    memcpy(cfg.ap.ssid, ssid, n);
    cfg.ap.ssid_len = (uint8_t)n;
    memcpy(cfg.ap.password, psk, p);
    cfg.ap.authmode = WIFI_AUTH_WPA2_PSK;
    cfg.ap.max_connection = 2;
    cfg.ap.pmf_cfg.capable = true;
    cfg.ap.pmf_cfg.required = false;
    wipe_secret(ssid, sizeof(ssid));
    wipe_secret(psk, sizeof(psk));
    /* No radio frames are sent here: the original owner has not started Wi-Fi. */
    esp_err_t result = esp_wifi_set_mode(WIFI_MODE_APSTA);
    if (result == ESP_OK)
        result = esp_wifi_set_config(WIFI_IF_AP, &cfg);
    wipe_secret(&cfg, sizeof(cfg));
    struct netif *impl = NULL;
    if (result == ESP_OK)
        impl = (struct netif *)esp_netif_get_netif_impl(ap);
    if (result != ESP_OK || !impl) {
        /* Before wifi_start, restoring STA cannot expose an open AP. */
        (void)esp_wifi_set_mode(WIFI_MODE_STA);
        esp_netif_destroy_default_wifi(ap);
        return false;
    }
    transparent_tcp_init();
    transparent_tcp_set_enabled(false);
    transparent_tcp_set_ap_netif(impl);
    s3_gateway_lwip_bind_ap(impl);
    active_ap = ap;
    return true;
}

bool s3_gateway_ap_after_start(void)
{
    /* DHCP DNS always names AP itself, never the upstream STA resolver. */
    return !active_ap || s3_gateway_ap_offer_local_dns(active_ap) == ESP_OK;
}

void s3_gateway_ap_before_stop(void)
{
    if (!active_ap) return;
    s3_gateway_policy_event(s3_gateway_policy_device(), S3_GW_ADMIN_DISARM);
    transparent_tcp_set_enabled(false);
    /* Keep AP packet filters until the original owner has stopped Wi-Fi. */
}

static esp_err_t restore_output(void *ctx)
{
    (void)ctx;
    transparent_tcp_uninstall_ap_output();
    return ESP_OK;
}

bool s3_gateway_ap_after_stop(void)
{
    if (!active_ap) return true;
    /* The original owner has stopped Wi-Fi before this function. */
    if (esp_netif_tcpip_exec(restore_output, NULL) != ESP_OK) {
        /* Do not destroy a netif with output-hook pointers still referencing it. */
        return false;
    }
    s3_gateway_lwip_unbind_ap();
    esp_netif_destroy_default_wifi(active_ap);
    active_ap = NULL;
    return true;
}
