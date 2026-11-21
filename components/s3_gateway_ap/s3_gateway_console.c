/* SPDX-License-Identifier: MIT
 * P4-2: exact Espressif IDF6 console REPL, started ONLY after a local
 * physical key hold. No Wi-Fi manager, network admin, secrets in code/CI.
 * Defaults to the existing board stdio console (UART or USB per IDF).
 */
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "esp_console.h"
#include "esp_log.h"
#include "nvs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "s3_gateway_workers.h"
#include "s3_gateway_ap_config.h"
#include "s3_ss2022_link.h"
#include "s3_gateway_vless_node.h"

static volatile uint32_t console_started;
static const char *TAG = "s3_setup";

static int set_ap(int argc, char **argv)
{
    if (argc != 3 || !s3_gateway_ap_credentials_valid(argv[1], argv[2])) {
        puts("Usage: s3_ap SSID WPA2_PASSWORD (SSID 1-32, password 12-63)");
        return 1;
    }
    nvs_handle_t nvs;
    if (nvs_open("s3_proxy_ap", NVS_READWRITE, &nvs) != ESP_OK) {
        puts("NVS AP open failed"); return 1;
    }
    esp_err_t rc = nvs_set_str(nvs, "ssid", argv[1]);
    if (rc == ESP_OK) rc = nvs_set_str(nvs, "psk", argv[2]);
    if (rc == ESP_OK) rc = nvs_set_u8(nvs, "enabled", 1);
    if (rc == ESP_OK) rc = nvs_commit(nvs);
    nvs_close(nvs);
    puts(rc == ESP_OK ? "AP SAVED. Reboot to apply; proxy still OFF."
                      : "AP SAVE FAILED. Proxy stays OFF.");
    return rc == ESP_OK ? 0 : 1;
}

static int disable_ap(int argc, char **argv)
{
    (void)argv;
    if (argc != 1) return 1;
    s3_gateway_workers_revoke();
    nvs_handle_t nvs;
    if (nvs_open("s3_proxy_ap", NVS_READWRITE, &nvs) != ESP_OK) return 1;
    esp_err_t rc = nvs_set_u8(nvs, "enabled", 0);
    if (rc == ESP_OK) rc = nvs_commit(nvs);
    nvs_close(nvs);
    puts(rc == ESP_OK ? "AP DISABLED on next reboot; proxy OFF."
                      : "AP DISABLE failed.");
    return rc == ESP_OK ? 0 : 1;
}

static int set_ss(int argc, char **argv)
{
    if (argc != 4) {
        puts("Usage: s3_ss HOST PORT BASE64_16_BYTE_KEY");
        return 1;
    }
    errno = 0;
    char *end = NULL;
    unsigned long number = strtoul(argv[2], &end, 10);
    if (errno || !end || *end || !number || number > UINT16_MAX) {
        puts("Invalid port"); return 1;
    }
    bool ok = s3_ss2022_node_store(argv[1], (uint16_t)number, argv[3]);
    puts(ok ? "SS2022 NODE SAVED. Press physical key ~2s to enable."
            : "SS2022 NODE REJECTED. Check host, port and base64 key.");
    return ok ? 0 : 1;
}

static int set_vless(int argc, char **argv)
{
    if (argc != 4) {
        puts("Usage: s3_vless TLS_CERT_HOST PORT UUID");
        return 1;
    }
    errno = 0;
    char *end = NULL;
    unsigned long number = strtoul(argv[2], &end, 10);
    if (errno || !end || *end || !number || number > UINT16_MAX)
        return 1;
    bool ok = s3_gateway_vless_store(argv[1], (uint16_t)number, argv[3]);
    puts(ok ? "VLESS/TLS NODE SAVED. Use s3_use vless to select."
            : "VLESS/TLS NODE REJECTED. Requires cert hostname and valid UUID.");
    return ok ? 0 : 1;
}
static int clear_vless(int argc, char **argv)
{
    (void)argv;
    if (argc != 1) return 1;
    s3_gateway_workers_revoke();
    bool ok = s3_gateway_vless_clear();
    puts(ok ? "VLESS/TLS NODE CLEARED. Proxy OFF." : "VLESS CLEAR FAILED.");
    return ok ? 0 : 1;
}
static int select_node(int argc, char **argv)
{
    if (argc != 2) {
        puts("Usage: s3_use ss2022|vless");
        return 1;
    }
    uint8_t kind;
    if (strcmp(argv[1], "ss2022") == 0) kind = 0;
    else if (strcmp(argv[1], "vless") == 0) kind = 1;
    else return 1;
    s3_gateway_workers_revoke();
    nvs_handle_t h;
    if (nvs_open("s3_proxy_ap", NVS_READWRITE, &h) != ESP_OK) return 1;
    esp_err_t rc = nvs_set_u8(h, "node_type", kind);
    if (rc == ESP_OK) rc = nvs_commit(h);
    nvs_close(h);
    puts(rc == ESP_OK ? "NODE TYPE SAVED. Press key ~2s to activate."
                      : "NODE TYPE SAVE FAILED. Proxy OFF.");
    return rc == ESP_OK ? 0 : 1;
}

static int clear_ss(int argc, char **argv)
{
    (void)argv;
    if (argc != 1) return 1;
    s3_gateway_workers_revoke();
    bool ok = s3_ss2022_node_clear();
    puts(ok ? "SS2022 NODE CLEARED. Proxy OFF."
            : "SS2022 CLEAR FAILED.");
    return ok ? 0 : 1;
}

static int show_status(int argc, char **argv)
{
    (void)argv;
    if (argc != 1) return 1;
    s3_ss2022_node_t node = {0};
    bool saved_node = s3_ss2022_node_load(&node);
    s3_ss2022_node_wipe(&node);
    s3_gateway_vless_node_t vless = {0};
    bool saved_vless = s3_gateway_vless_load(&vless);
    s3_gateway_vless_wipe(&vless);
    nvs_handle_t nvs;
    uint8_t selected = 0;
    uint8_t enabled = 0;
    bool saved_ap = nvs_open("s3_proxy_ap", NVS_READONLY, &nvs) == ESP_OK;
    if (saved_ap) {
        saved_ap = nvs_get_u8(nvs, "enabled", &enabled) == ESP_OK &&
                   enabled == 1;
        (void)nvs_get_u8(nvs, "node_type", &selected);
        nvs_close(nvs);
    }
    printf("AP: %s; SS2022: %s; VLESS/TLS: %s; selected: %s\n",
           saved_ap ? "yes" : "no", saved_node ? "yes" : "no",
           saved_vless ? "yes" : "no",
           selected == 1 ? "vless" : "ss2022");
    puts("Secret values are never displayed. Restart after AP setup.");
    return 0;
}

static void setup_thread(void *arg)
{
    (void)arg;
    /* stdio REPL uses the current ESP-IDF console route. The official
     * component allocates its own task only while this physical setup
     * mode is explicitly requested.
     */
    esp_console_repl_t *repl = NULL;
    esp_console_repl_config_t cfg = ESP_CONSOLE_REPL_CONFIG_DEFAULT();
    cfg.prompt = "s3-setup>";
    cfg.max_cmdline_length = 384;
    cfg.history_save_path = NULL; /* Never persist secrets to a file. */
    cfg.task_priority = 1;
    esp_err_t rc = esp_console_new_repl_stdio(&cfg, &repl);
    if (rc == ESP_OK) {
        const esp_console_cmd_t commands[] = {
            {.command = "s3_ap", .help = "Set WPA2 AP SSID/password (reboot required)", .func = set_ap},
            {.command = "s3_ap_off", .help = "Disable gateway AP on next boot", .func = disable_ap},
            {.command = "s3_ss", .help = "Save SS2022 HOST PORT BASE64_KEY", .func = set_ss},
            {.command = "s3_ss_clear", .help = "Delete saved SS2022 node", .func = clear_ss},
            {.command = "s3_vless", .help = "Save TLS_CERT_HOST PORT UUID", .func = set_vless},
            {.command = "s3_vless_clear", .help = "Delete VLESS/TLS node", .func = clear_vless},
            {.command = "s3_use", .help = "Choose ss2022 or vless", .func = select_node},
            {.command = "s3_status", .help = "Show configured status (no secrets)", .func = show_status},
        };
        for (size_t i = 0; i < sizeof(commands)/sizeof(commands[0]); ++i) {
            rc = esp_console_cmd_register(&commands[i]);
            if (rc != ESP_OK) break;
        }
        if (rc == ESP_OK) rc = esp_console_start_repl(repl);
    }
    ESP_LOGI(TAG, "Physical serial setup: %s",
             rc == ESP_OK ? "ready; type s3_status" : "unavailable");
    if (rc != ESP_OK)
        __atomic_store_n(&console_started, 0u, __ATOMIC_RELEASE);
    vTaskDelete(NULL);
}

bool s3_gateway_console_start(void)
{
    uint32_t zero = 0;
    if (!__atomic_compare_exchange_n(&console_started, &zero, 1u,
                                     false, __ATOMIC_ACQ_REL,
                                     __ATOMIC_ACQUIRE))
        return true; /* Already opened by physical user. */
    if (xTaskCreate(setup_thread, "s3_setup_once", 4096, NULL, 1, NULL)
        != pdPASS) {
        __atomic_store_n(&console_started, 0u, __ATOMIC_RELEASE);
        return false;
    }
    return true;
}
