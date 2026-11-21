/* SPDX-License-Identifier: MIT
 * ESP-IDF FreeRTOS/BSD sockets; no new Wi-Fi owner or DNS crypto code.
 * NULL node: local SERVFAIL only, never a direct public DNS request.
 * The transparent TCP relay remains gated off pending cancellation.
 */
#include <stdbool.h>
#include <stdint.h>
#include <unistd.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "s3_gateway_workers.h"
#include "s3_gateway_dns_udp.h"
#include "s3_gateway_dns_tcp.h"
#include "s3_gateway_session.h"
#include "s3_gateway_policy.h"

#define S3_DNS_PRIORITY 2
#define S3_DNS_STACK_BYTES 4096

static esp_netif_t *owner_ap;
static int udp_fd = -1;
static int tcp_fd = -1;
static volatile uint32_t stopping = 1;
static volatile uint32_t live_tasks;
static bool initialized_once;

static bool stopping_now(void)
{
    return __atomic_load_n(&stopping, __ATOMIC_ACQUIRE) != 0;
}
static void worker_exit(void)
{
    __atomic_sub_fetch(&live_tasks, 1u, __ATOMIC_ACQ_REL);
    vTaskDelete(NULL);
}
static void udp_worker(void *arg)
{
    (void)arg;
    while (!stopping_now()) {
        if (!s3_gateway_dns_udp_poll(udp_fd, owner_ap, NULL))
            vTaskDelay(pdMS_TO_TICKS(20));
    }
    worker_exit();
}
static void tcp_dns_worker(void *arg)
{
    (void)arg;
    while (!stopping_now()) {
        if (!s3_gateway_dns_tcp_poll(tcp_fd, owner_ap, NULL))
            vTaskDelay(pdMS_TO_TICKS(20));
    }
    worker_exit();
}
static bool spawn(TaskFunction_t task, const char *name)
{
    __atomic_add_fetch(&live_tasks, 1u, __ATOMIC_ACQ_REL);
    if (xTaskCreate(task, name, S3_DNS_STACK_BYTES, NULL,
                    S3_DNS_PRIORITY, NULL) == pdPASS)
        return true;
    __atomic_sub_fetch(&live_tasks, 1u, __ATOMIC_ACQ_REL);
    return false;
}
void s3_gateway_workers_request_stop(void)
{
    __atomic_store_n(&stopping, 1u, __ATOMIC_RELEASE);
    s3_gateway_policy_event(s3_gateway_policy_device(), S3_GW_ADMIN_DISARM);
}
bool s3_gateway_workers_drain(uint32_t timeout_ms)
{
    s3_gateway_workers_request_stop();
    TickType_t remaining = pdMS_TO_TICKS(timeout_ms);
    TickType_t slice = pdMS_TO_TICKS(20);
    if (!slice) slice = 1;
    while (__atomic_load_n(&live_tasks, __ATOMIC_ACQUIRE) != 0 && remaining) {
        TickType_t wait = remaining < slice ? remaining : slice;
        vTaskDelay(wait);
        remaining -= wait;
    }
    if (__atomic_load_n(&live_tasks, __ATOMIC_ACQUIRE) != 0)
        return false;
    if (udp_fd >= 0) close(udp_fd);
    if (tcp_fd >= 0) close(tcp_fd);
    udp_fd = tcp_fd = -1;
    owner_ap = NULL;
    return true;
}
bool s3_gateway_workers_start_dns(esp_netif_t *ap)
{
    if (!ap || owner_ap ||
        __atomic_load_n(&live_tasks, __ATOMIC_ACQUIRE) != 0)
        return false;
    /* Never reset an epoch on an AP restart, including exhausted epochs. */
    if (!initialized_once) {
        s3_gateway_session_init(s3_gateway_session_device());
        initialized_once = true;
    }
    if (!s3_gateway_session_event(s3_gateway_session_device(),
                                  S3_SESSION_AP_READY))
        return false;
    owner_ap = ap;
    udp_fd = s3_gateway_dns_udp_open(ap);
    tcp_fd = s3_gateway_dns_tcp_listen(ap);
    if (udp_fd < 0 || tcp_fd < 0) {
        (void)s3_gateway_workers_drain(0);
        (void)s3_gateway_session_event(s3_gateway_session_device(),
                                       S3_SESSION_WORKER_FAILED);
        return false;
    }
    __atomic_store_n(&stopping, 0u, __ATOMIC_RELEASE);
    if (!spawn(udp_worker, "s3_ap_dns_udp") ||
        !spawn(tcp_dns_worker, "s3_ap_dns_tcp")) {
        s3_gateway_workers_request_stop();
        (void)s3_gateway_session_event(s3_gateway_session_device(),
                                       S3_SESSION_WORKER_FAILED);
        return false;
    }
    (void)s3_gateway_session_event(s3_gateway_session_device(),
                                   S3_SESSION_DNS_LISTENER_READY);
    return true;
}
