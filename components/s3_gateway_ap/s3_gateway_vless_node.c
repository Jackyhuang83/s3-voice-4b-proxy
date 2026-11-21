/* SPDX-License-Identifier: MIT */
#include "s3_gateway_vless_node.h"
#include <stddef.h>
#include <string.h>
#include "nvs.h"
#define VLESS_MAGIC UINT32_C(0x5333564c)
#define VLESS_NS "s3vlesstls"
#define VLESS_KEY "node"

void s3_gateway_vless_wipe(s3_gateway_vless_node_t *n)
{
    if (!n) return;
    volatile uint8_t *p = (volatile uint8_t *)n;
    for (size_t i = 0; i < sizeof(*n); ++i) p[i] = 0;
}
static bool valid_host(const char *host)
{
    if (!host) return false;
    size_t len = strnlen(host, 254);
    if (len < 4 || len > 253 || !strchr(host, '.')) return false;
    bool letter = false;
    for (size_t i = 0; i < len; ++i) {
        char c = host[i];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'))
            letter = true;
        else if (!(c >= '0' && c <= '9') && c != '-' && c != '.')
            return false;
        if (c == '.' && (!i || i + 1 == len || host[i - 1] == '.'))
            return false;
    }
    return letter; /* Cert/SNI DNS identity, never an unverified IP. */
}
static int hex(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
static bool parse_uuid(const char *text, uint8_t out[16])
{
    if (!text || !out) return false;
    size_t length = strnlen(text, 37);
    if (length != 32 && length != 36) return false;
    unsigned nibble = 0;
    uint8_t result[16] = {0};
    for (size_t i = 0; i < length; ++i) {
        if (length == 36 && (i == 8 || i == 13 || i == 18 || i == 23)) {
            if (text[i] != '-') return false;
            continue;
        }
        int v = hex(text[i]);
        if (v < 0 || nibble >= 32) return false;
        if (!(nibble & 1u)) result[nibble / 2] = (uint8_t)(v << 4);
        else result[nibble / 2] |= (uint8_t)v;
        ++nibble;
    }
    if (nibble != 32) return false;
    uint8_t any = 0;
    for (size_t i = 0; i < sizeof(result); ++i) any |= result[i];
    if (!any) return false;
    memcpy(out, result, sizeof(result));
    return true;
}
static bool valid_node(const s3_gateway_vless_node_t *n)
{
    if (!n || n->magic != VLESS_MAGIC || !n->port ||
        !memchr(n->hostname, 0, sizeof(n->hostname)) ||
        !valid_host(n->hostname)) return false;
    uint8_t any = 0;
    for (size_t i = 0; i < sizeof(n->uuid); ++i) any |= n->uuid[i];
    return any != 0;
}
bool s3_gateway_vless_store(const char *hostname, uint16_t port,
                             const char *uuid_text)
{
    if (!port || !valid_host(hostname)) return false;
    s3_gateway_vless_node_t node = {.magic = VLESS_MAGIC, .port = port};
    memcpy(node.hostname, hostname, strlen(hostname) + 1);
    if (!parse_uuid(uuid_text, node.uuid)) {
        s3_gateway_vless_wipe(&node);
        return false;
    }
    nvs_handle_t h;
    bool ok = false;
    if (nvs_open(VLESS_NS, NVS_READWRITE, &h) == ESP_OK) {
        ok = nvs_set_blob(h, VLESS_KEY, &node, sizeof(node)) == ESP_OK &&
             nvs_commit(h) == ESP_OK;
        nvs_close(h);
    }
    s3_gateway_vless_wipe(&node);
    return ok;
}
bool s3_gateway_vless_load(s3_gateway_vless_node_t *node)
{
    if (!node) return false;
    s3_gateway_vless_wipe(node);
    nvs_handle_t h;
    if (nvs_open(VLESS_NS, NVS_READONLY, &h) != ESP_OK) return false;
    size_t size = sizeof(*node);
    esp_err_t rc = nvs_get_blob(h, VLESS_KEY, node, &size);
    nvs_close(h);
    if (rc == ESP_OK && size == sizeof(*node) && valid_node(node))
        return true;
    s3_gateway_vless_wipe(node);
    return false;
}
bool s3_gateway_vless_clear(void)
{
    nvs_handle_t h;
    if (nvs_open(VLESS_NS, NVS_READWRITE, &h) != ESP_OK) return false;
    esp_err_t rc = nvs_erase_key(h, VLESS_KEY);
    bool ok = (rc == ESP_OK || rc == ESP_ERR_NVS_NOT_FOUND) &&
              nvs_commit(h) == ESP_OK;
    nvs_close(h);
    return ok;
}
