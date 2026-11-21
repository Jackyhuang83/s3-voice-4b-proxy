/* Host-only P3-2 validation of dual-stack node schema, P2 NVS v1 migration.
 * This executable is NEVER included in firmware.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "nvs.h"
#include "s3_ss2022_link.h"

#define PUBLIC_KEY "AAECAwQFBgcICQoLDA0ODw=="
#define V1_MAGIC UINT32_C(0x53333232)
typedef struct {
    uint32_t magic;
    char server_ipv4[16];
    uint16_t server_port;
    uint8_t psk[16];
} old_node_t;

int main(void)
{
    s3_ss2022_node_t modern;
    assert(!s3_ss2022_node_load(&modern));
    assert(!s3_ss2022_node_store("not a host", 443, PUBLIC_KEY));
    assert(!s3_ss2022_node_store("example..org", 443, PUBLIC_KEY));
    assert(!s3_ss2022_node_store("2001:db8::zz", 443, PUBLIC_KEY));
    assert(!s3_ss2022_node_store("2001:db8::1", 0, PUBLIC_KEY));
    assert(!s3_ss2022_node_store("::1", 443, "not-a-valid-PSK"));
    assert(s3_ss2022_node_store("2001:db8::1", 443, PUBLIC_KEY));
    assert(s3_ss2022_node_load(&modern));
    assert(!strcmp(modern.server_host, "2001:db8::1") && modern.server_port == 443);
    assert(s3_ss2022_node_store("proxy.example.org", 8443, PUBLIC_KEY));
    assert(s3_ss2022_node_load(&modern));
    assert(!strcmp(modern.server_host, "proxy.example.org"));
    assert(s3_ss2022_node_store("127.0.0.1", 8080, PUBLIC_KEY));
    assert(s3_ss2022_node_load(&modern));
    assert(!strcmp(modern.server_host, "127.0.0.1"));
    assert(s3_ss2022_node_clear());
    assert(!s3_ss2022_node_load(&modern));

    nvs_handle_t handle;
    assert(nvs_open("s3ss2022", NVS_READWRITE, &handle) == ESP_OK);
    old_node_t v1 = {.magic = V1_MAGIC, .server_port = 8844};
    memcpy(v1.server_ipv4, "192.0.2.10", sizeof("192.0.2.10"));
    for (size_t i = 0; i < 16; ++i) v1.psk[i] = (uint8_t)i;
    assert(nvs_set_blob(handle, "node", &v1, sizeof(v1)) == ESP_OK);
    assert(nvs_commit(handle) == ESP_OK);
    nvs_close(handle);
    assert(s3_ss2022_node_load(&modern));
    assert(!strcmp(modern.server_host, "192.0.2.10"));
    assert(modern.server_port == 8844 && modern.psk[15] == 15);

    /* A subsequent v2 store must retire the legacy plaintext record. */
    assert(s3_ss2022_node_store("::1", 18450, PUBLIC_KEY));
    assert(s3_ss2022_node_load(&modern));
    assert(!strcmp(modern.server_host, "::1"));
    assert(nvs_open("s3ss2022", NVS_READONLY, &handle) == ESP_OK);
    old_node_t stale = {0};
    size_t size = sizeof(stale);
    assert(nvs_get_blob(handle, "node", &stale, &size) == ESP_ERR_NVS_NOT_FOUND);
    nvs_close(handle);
    assert(s3_ss2022_node_clear());
    assert(!s3_ss2022_node_load(&modern));
    s3_ss2022_node_wipe(&modern);
    printf("PASS P3-2 IPv6 literal/AAAA hostname and P2 IPv4 NVS migration; no key log\n");
    return 0;
}
