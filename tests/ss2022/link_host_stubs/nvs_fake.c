/* Host test-only fake NVS. Never shipped in ESP32 firmware. */
#include <string.h>
#include "nvs.h"
static uint8_t storage[192];
static size_t storage_size;

esp_err_t nvs_open(const char *namespace_name, int mode, nvs_handle_t *handle)
{
    (void)mode;
    if (strcmp(namespace_name, "s3ss2022")) return -1;
    *handle = 1;
    return ESP_OK;
}
esp_err_t nvs_get_blob(nvs_handle_t handle, const char *name, void *data, size_t *n)
{
    if (handle != 1 || strcmp(name, "node") || !storage_size) return ESP_ERR_NVS_NOT_FOUND;
    if (*n < storage_size) return -1;
    memcpy(data, storage, storage_size);
    *n = storage_size;
    return ESP_OK;
}
esp_err_t nvs_set_blob(nvs_handle_t handle, const char *name, const void *data, size_t n)
{
    if (handle != 1 || strcmp(name, "node") || n > sizeof(storage)) return -1;
    memcpy(storage, data, n);
    storage_size = n;
    return ESP_OK;
}
esp_err_t nvs_erase_key(nvs_handle_t handle, const char *name)
{
    if (handle != 1 || strcmp(name, "node")) return -1;
    memset(storage, 0, sizeof(storage));
    storage_size = 0;
    return ESP_OK;
}
esp_err_t nvs_commit(nvs_handle_t handle) { return handle == 1 ? ESP_OK : -1; }
void nvs_close(nvs_handle_t handle) { (void)handle; }

