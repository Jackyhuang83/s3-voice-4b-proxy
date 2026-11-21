/* SPDX-License-Identifier: MIT
 * Minimal ESP-IDF FreeRTOS/BSD supervisor over existing SS2022 and VLESS/TLS.
 * No additional Wi-Fi manager, crypto, direct fallback, or automatic ARM.
 * WARNING: admin_arm requires a dedicated task; it makes a network probe.
 */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/socket.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_netif.h"
#include "s3_gateway_workers.h"
#include "s3_gateway_dns_udp.h"
#include "s3_gateway_dns_tcp.h"
#include "s3_gateway_dns_probe.h"
#include "s3_gateway_tcp_server.h"
#include "s3_gateway_session.h"
#include "s3_gateway_policy.h"
#include "transparent_tcp.h"

#define S3_GW_TASK_PRIORITY 2
#define S3_GW_DNS_STACK 4096
#define S3_GW_TCP_STACK 6144
#define S3_GW_RELAYS 2
#define S3_GW_STOP_POLL_MS 20

typedef struct {
    s3_ss2022_node_t ss_node;
    uint8_t uuid[16];
    char sni[254];
    char resolver[64];
    s3_gateway_dns_upstream_t cfg;
} owned_node_t;

static esp_netif_t *owner_ap;
static int udp_fd = -1, dns_fd = -1, relay_fd = -1;
static volatile uint32_t stopping = 1, live_tasks, authorized;
static bool initialized_once;
static SemaphoreHandle_t client_mutex;
static int active_clients[S3_GW_RELAYS] = {-1, -1};
static owned_node_t node_storage;
static volatile uint32_t configuration_in_progress;
static volatile uint32_t revoke_requested;

static bool is_stopping(void)
{
    return __atomic_load_n(&stopping, __ATOMIC_ACQUIRE) != 0;
}
static bool is_authorized(void)
{
    return !is_stopping() &&
           __atomic_load_n(&authorized, __ATOMIC_ACQUIRE) != 0 &&
           s3_gateway_policy_ready(s3_gateway_policy_device());
}
static void wipe(void *addr, size_t n)
{
    volatile uint8_t *p = (volatile uint8_t *)addr;
    while (n--) *p++ = 0;
}
static void cancel_clients(void)
{
    if (!client_mutex || xSemaphoreTake(client_mutex, pdMS_TO_TICKS(100)) != pdTRUE)
        return;
    for (unsigned i = 0; i < S3_GW_RELAYS; ++i)
        if (active_clients[i] >= 0) (void)shutdown(active_clients[i], SHUT_RDWR);
    xSemaphoreGive(client_mutex);
}
static bool client_event(int fd, bool entering, void *context)
{
    unsigned slot = (unsigned)(uintptr_t)context;
    if (slot >= S3_GW_RELAYS || !client_mutex) return false;
    if (xSemaphoreTake(client_mutex, portMAX_DELAY) != pdTRUE) return false;
    bool ok = false;
    if (entering) {
        if (active_clients[slot] == -1 && is_authorized()) {
            active_clients[slot] = fd;
            ok = true;
        }
    } else {
        if (active_clients[slot] == fd) active_clients[slot] = -1;
        ok = true;
    }
    xSemaphoreGive(client_mutex);
    return ok;
}
/* Dedicated revocation monitor: data plane stop is independent of DNS
 * requests (which may block on upstream timeout). The monitor has no sockets
 * of its own and only shuts down registered AP TCP client fds.
 */
static void worker_done(void);
static void revoke_monitor(void *arg)
{
    (void)arg;
    while (!is_stopping()) {
        if (__atomic_load_n(&revoke_requested, __ATOMIC_ACQUIRE) ||
            !is_authorized()) {
            cancel_clients();
            __atomic_store_n(&revoke_requested, 0u, __ATOMIC_RELEASE);
        }
        vTaskDelay(pdMS_TO_TICKS(20) ? pdMS_TO_TICKS(20) : 1);
    }
    cancel_clients();
    worker_done();
}
static void worker_done(void)
{
    __atomic_sub_fetch(&live_tasks, 1u, __ATOMIC_ACQ_REL);
    vTaskDelete(NULL);
}
static void udp_worker(void *arg)
{
    (void)arg;
    while (!is_stopping()) {
        const s3_gateway_dns_upstream_t *up =
            is_authorized() ? &node_storage.cfg : NULL;
        (void)s3_gateway_dns_udp_poll(udp_fd, owner_ap, up);
        if (!is_authorized()) cancel_clients();
        vTaskDelay(pdMS_TO_TICKS(S3_GW_STOP_POLL_MS));
    }
    cancel_clients();
    worker_done();
}
static void tcp_dns_worker(void *arg)
{
    (void)arg;
    while (!is_stopping()) {
        const s3_gateway_dns_upstream_t *up =
            is_authorized() ? &node_storage.cfg : NULL;
        (void)s3_gateway_dns_tcp_poll(dns_fd, owner_ap, up);
        if (!is_authorized()) cancel_clients();
        vTaskDelay(pdMS_TO_TICKS(S3_GW_STOP_POLL_MS));
    }
    cancel_clients();
    worker_done();
}
static void tcp_relay_worker(void *arg)
{
    unsigned slot = (unsigned)(uintptr_t)arg;
    while (!is_stopping()) {
        if (!is_authorized()) {
            cancel_clients();
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }
        uint32_t epoch = s3_gateway_session_epoch(s3_gateway_session_device());
        bool ok = s3_gateway_tcp_accept_and_relay(
            relay_fd, owner_ap, &node_storage.cfg, client_event,
            (void *)(uintptr_t)slot);
        /* Legitimate close/idle timeout is not automatically node failure;
         * revoked epochs must never authorize a newer connection.
         */
        if (!ok && is_authorized() &&
            epoch != s3_gateway_session_epoch(s3_gateway_session_device()))
            cancel_clients();
    }
    worker_done();
}
static bool spawn(TaskFunction_t task, const char *name,
                  uint32_t stack, void *arg)
{
    __atomic_add_fetch(&live_tasks, 1u, __ATOMIC_ACQ_REL);
    if (xTaskCreate(task, name, stack, arg, S3_GW_TASK_PRIORITY, NULL) == pdPASS)
        return true;
    __atomic_sub_fetch(&live_tasks, 1u, __ATOMIC_ACQ_REL);
    return false;
}
static bool copy_node(const s3_gateway_dns_upstream_t *src,
                      owned_node_t *dst)
{
    if (!src || !dst || !src->resolver) return false;
    size_t n = strnlen(src->resolver, sizeof(dst->resolver));
    if (!n || n >= sizeof(dst->resolver)) return false;
    memcpy(dst->resolver, src->resolver, n + 1);
    dst->cfg.resolver = dst->resolver;
    dst->cfg.transport = src->transport;
    if (src->transport == S3_GATEWAY_DNS_SS2022) {
        if (!src->ss2022_node ||
            !s3_ss2022_node_valid(src->ss2022_node)) return false;
        dst->ss_node = *src->ss2022_node;
        dst->cfg.ss2022_node = &dst->ss_node;
        return true;
    }
    if (src->transport != S3_GATEWAY_DNS_VLESS_TLS ||
        !src->vless_sni || !src->vless_port || !src->vless_uuid) return false;
    n = strnlen(src->vless_sni, sizeof(dst->sni));
    if (!n || n >= sizeof(dst->sni)) return false;
    memcpy(dst->sni, src->vless_sni, n + 1);
    memcpy(dst->uuid, src->vless_uuid, sizeof(dst->uuid));
    dst->cfg.vless_sni = dst->sni;
    dst->cfg.vless_port = src->vless_port;
    dst->cfg.vless_uuid = dst->uuid;
    return true;
}
static esp_err_t install_output(void *context)
{
    (void)context;
    /* Runs on lwIP core. The AP packet filter still denies external TCP
     * until both session and legacy policy authorize it.
     */
    transparent_tcp_install_ap_output();
    return transparent_tcp_ap_output_installed() ? ESP_OK : ESP_FAIL;
}
bool s3_gateway_workers_admin_arm(const s3_gateway_dns_upstream_t *src)
{
    /* Called only from a dedicated local administrator task; never from
     * Wi-Fi event callbacks or Xiaozhi audio/GUI dispatch.
     */
    if (!owner_ap || is_stopping() ||
        __atomic_load_n(&authorized, __ATOMIC_ACQUIRE) ||
        !src || relay_fd < 0)
        return false;
    bool ok = false;
    uint32_t expected = 0;
    if (!__atomic_compare_exchange_n(&configuration_in_progress, &expected,
                                     1u, false, __ATOMIC_ACQ_REL,
                                     __ATOMIC_ACQUIRE))
        return false;
    if (!client_mutex || xSemaphoreTake(client_mutex, pdMS_TO_TICKS(100)) != pdTRUE)
        goto release_configuration;
    bool busy = false;
    for (unsigned i = 0; i < S3_GW_RELAYS; ++i)
        if (active_clients[i] >= 0) busy = true;
    xSemaphoreGive(client_mutex);
    if (busy) goto release_configuration;
    uint32_t epoch = s3_gateway_session_epoch(s3_gateway_session_device());
    if (!epoch ||
        (s3_gateway_session_flags(s3_gateway_session_device()) &
         (S3_SESSION_STA | S3_SESSION_AP)) !=
         (S3_SESSION_STA | S3_SESSION_AP))
        goto done;
    /* A previous failure/administrator revocation advances the epoch and
     * clears DNS/TCP listener flags, but the real sockets are still alive.
     */
    if (!s3_gateway_session_event(s3_gateway_session_device(),
                                  S3_SESSION_DNS_LISTENER_READY))
        goto done;
    wipe(&node_storage, sizeof(node_storage));
    if (!copy_node(src, &node_storage)) goto done;
    /* Prefer Xiaozhi's own already-synchronized clock. Never initialize a
     * competing SNTP client unless the clock is still implausible.
     */
    if (node_storage.cfg.transport == S3_GATEWAY_DNS_SS2022 &&
        time(NULL) < (time_t)1700000000 &&
        !s3_ss2022_start_clock()) goto done;
    if (!s3_gateway_dns_probe_node(&node_storage.cfg)) goto done;
    if (is_stopping() ||
        !s3_gateway_session_node_proven(s3_gateway_session_device(), epoch))
        goto done;
    if (esp_netif_tcpip_exec(install_output, NULL) != ESP_OK)
        goto done;
    if (!s3_gateway_session_event(s3_gateway_session_device(),
                                  S3_SESSION_TCP_LISTENER_READY) ||
        !s3_gateway_session_event(s3_gateway_session_device(),
                                  S3_SESSION_OUTPUT_HOOK_READY))
        goto done;
    /* Legacy policy and epoch must both be ready to authorize forwarding. */
    s3_gateway_policy_event(s3_gateway_policy_device(), S3_GW_NODE_VALIDATED);
    s3_gateway_policy_event(s3_gateway_policy_device(), S3_GW_RELAY_READY);
    s3_gateway_policy_event(s3_gateway_policy_device(), S3_GW_ADMIN_ARM);
    if (!s3_gateway_session_admin_arm(s3_gateway_session_device(), epoch) ||
        !is_stopping() ||
        !s3_gateway_policy_ready(s3_gateway_policy_device()))
        goto done;
    __atomic_store_n(&revoke_requested, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&authorized, 1u, __ATOMIC_RELEASE);
    transparent_tcp_set_enabled(true);
    /* An AP/STA loss may race the last ARM instructions. Never return
     * success or leave the interception gate raised for a revoked epoch.
     */
    if (!is_authorized() ||
        epoch != s3_gateway_session_epoch(s3_gateway_session_device())) {
        s3_gateway_workers_revoke();
        goto done;
    }
    ok = true;
done:
    if (!ok) {
        __atomic_store_n(&authorized, 0u, __ATOMIC_RELEASE);
        s3_gateway_policy_event(s3_gateway_policy_device(), S3_GW_NODE_INVALIDATED);
        (void)s3_gateway_session_event(s3_gateway_session_device(),
                                       S3_SESSION_NODE_FAILED);
        transparent_tcp_set_enabled(false);
        wipe(&node_storage, sizeof(node_storage));
    }
release_configuration:
    __atomic_store_n(&configuration_in_progress, 0u, __ATOMIC_RELEASE);
    return ok;
}
bool s3_gateway_workers_admin_arm_saved_ss2022(void)
{
    /* Uses previously provisioned physical-USB NVS node, no secrets in
     * project repository; must be explicitly invoked from local UI task.
     */
    s3_ss2022_node_t node = {0};
    if (!s3_ss2022_node_load(&node)) return false;
    s3_gateway_dns_upstream_t settings = {
        .transport = S3_GATEWAY_DNS_SS2022,
        .ss2022_node = &node,
        .resolver = "1.1.1.1"
    };
    bool ok = s3_gateway_workers_admin_arm(&settings);
    s3_ss2022_node_wipe(&node);
    return ok;
}
void s3_gateway_workers_revoke(void)
{
    __atomic_store_n(&authorized, 0u, __ATOMIC_RELEASE);
    s3_gateway_policy_event(s3_gateway_policy_device(), S3_GW_NODE_INVALIDATED);
    (void)s3_gateway_session_event(s3_gateway_session_device(),
                                   S3_SESSION_ADMIN_OFF);
    transparent_tcp_set_enabled(false);
    __atomic_store_n(&revoke_requested, 1u, __ATOMIC_RELEASE);
    /* Monitor polls cancellation in bounded socket timeout interval.
     * This notification path itself avoids blocking the Wi-Fi event loop.
     */
}
void s3_gateway_workers_request_stop(void)
{
    __atomic_store_n(&stopping, 1u, __ATOMIC_RELEASE);
    s3_gateway_workers_revoke();
}
bool s3_gateway_workers_drain(uint32_t timeout_ms)
{
    s3_gateway_workers_request_stop();
    cancel_clients();
    TickType_t left = pdMS_TO_TICKS(timeout_ms);
    TickType_t step = pdMS_TO_TICKS(S3_GW_STOP_POLL_MS);
    if (!step) step = 1;
    while ((__atomic_load_n(&live_tasks, __ATOMIC_ACQUIRE) ||
            __atomic_load_n(&configuration_in_progress, __ATOMIC_ACQUIRE))
           && left) {
        TickType_t n = left < step ? left : step;
        vTaskDelay(n);
        left -= n;
        cancel_clients();
    }
    if (__atomic_load_n(&live_tasks, __ATOMIC_ACQUIRE) ||
        __atomic_load_n(&configuration_in_progress, __ATOMIC_ACQUIRE))
        return false; /* Never release AP or credentials during a probe. */
    if (udp_fd >= 0) close(udp_fd);
    if (dns_fd >= 0) close(dns_fd);
    if (relay_fd >= 0) close(relay_fd);
    udp_fd = dns_fd = relay_fd = -1;
    owner_ap = NULL;
    wipe(&node_storage, sizeof(node_storage));
    return true;
}
bool s3_gateway_workers_start_dns(esp_netif_t *ap)
{
    if (!ap || owner_ap || __atomic_load_n(&live_tasks, __ATOMIC_ACQUIRE))
        return false;
    if (!client_mutex) {
        client_mutex = xSemaphoreCreateMutex();
        if (!client_mutex) return false;
    }
    if (!initialized_once) {
        s3_gateway_session_init(s3_gateway_session_device());
        initialized_once = true;
    }
    if (!s3_gateway_session_event(s3_gateway_session_device(),
                                  S3_SESSION_AP_READY))
        return false;
    owner_ap = ap;
    udp_fd = s3_gateway_dns_udp_open(ap);
    dns_fd = s3_gateway_dns_tcp_listen(ap);
    relay_fd = s3_gateway_tcp_listen(ap);
    if (udp_fd < 0 || dns_fd < 0 || relay_fd < 0) goto failed;
    __atomic_store_n(&stopping, 0u, __ATOMIC_RELEASE);
    if (!spawn(udp_worker, "s3_dns_udp", S3_GW_DNS_STACK, NULL) ||
        !spawn(tcp_dns_worker, "s3_dns_tcp", S3_GW_DNS_STACK, NULL) ||
        !spawn(tcp_relay_worker, "s3_tcp_0", S3_GW_TCP_STACK, (void *)0) ||
        !spawn(tcp_relay_worker, "s3_tcp_1", S3_GW_TCP_STACK, (void *)1) ||
        !spawn(revoke_monitor, "s3_revoke", 3072, NULL))
        goto failed;
    (void)s3_gateway_session_event(s3_gateway_session_device(),
                                   S3_SESSION_DNS_LISTENER_READY);
    return true;
failed:
    s3_gateway_workers_request_stop();
    (void)s3_gateway_workers_drain(0);
    (void)s3_gateway_session_event(s3_gateway_session_device(),
                                   S3_SESSION_WORKER_FAILED);
    return false;
}
