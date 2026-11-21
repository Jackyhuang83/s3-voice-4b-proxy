/* Host test-only fake NVS. Never shipped in ESP32 firmware.
 * Supports P2 legacy IPv4 "node" and P3 dual-stack "node_v2" keys.
 */
#include <string.h>
#include "nvs.h"
static uint8_t current[512];
static size_t current_size;
static uint8_t legacy[128];
static size_t legacy_size;
static int slot_for(const char *name) {
    if (!strcmp(name, "node")) return 1;
    if (!strcmp(name, "node_v2")) return 2;
    return 0;
}
esp_err_t nvs_open(const char *namespace_name, int mode, nvs_handle_t *handle)
{
    (void)mode;
    if (strcmp(namespace_name, "s3ss2022")) return -1;
    *handle = 1;
    return ESP_OK;
}
esp_err_t nvs_get_blob(nvs_handle_t handle, const char *name, void *data, size_t *n)
{
    int slot = slot_for(name);
    if (handle != 1 || !slot) return -1;
    const void *src = slot == 1 ? (const void *)legacy : (const void *)current;
    size_t len = slot == 1 ? legacy_size : current_size;
    if (!len) return ESP_ERR_NVS_NOT_FOUND;
    if (*n < len) return -1;
    memcpy(data, src, len);
    *n = len;
    return ESP_OK;
}
esp_err_t nvs_set_blob(nvs_handle_t handle, const char *name, const void *data, size_t n)
{
    int slot = slot_for(name);
    if (handle != 1 || !slot || n > (slot == 1 ? sizeof(legacy) : sizeof(current)))
        return -1;
    memcpy(slot == 1 ? legacy : current, data, n);
    if (slot == 1) legacy_size = n;
    else current_size = n;
    return ESP_OK;
}
esp_err_t nvs_erase_key(nvs_handle_t handle, const char *name)
{
    int slot = slot_for(name);
    if (handle != 1 || !slot) return -1;
    if (slot == 1) {
        if (!legacy_size) return ESP_ERR_NVS_NOT_FOUND;
        memset(legacy, 0, sizeof(legacy));
        legacy_size = 0;
    } else {
        if (!current_size) return ESP_ERR_NVS_NOT_FOUND;
        memset(current, 0, sizeof(current));
        current_size = 0;
    }
    return ESP_OK;
}
esp_err_t nvs_commit(nvs_handle_t handle) { return handle == 1 ? ESP_OK : -1; }
void nvs_close(nvs_handle_t handle) { (void)handle; }
