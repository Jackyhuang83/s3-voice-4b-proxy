#pragma once
#include <stdint.h>
typedef int esp_err_t;
#define ESP_OK 0
typedef struct { const char *server; } esp_sntp_config_t;
#define ESP_NETIF_SNTP_DEFAULT_CONFIG(host) ((esp_sntp_config_t){ .server = (host) })
static inline esp_err_t esp_netif_sntp_init(const esp_sntp_config_t *p) { return p && p->server ? ESP_OK : -1; }
static inline esp_err_t esp_netif_sntp_sync_wait(uint32_t ticks) { (void)ticks; return ESP_OK; }
