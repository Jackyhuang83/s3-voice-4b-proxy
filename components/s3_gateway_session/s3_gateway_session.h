/* SPDX-License-Identifier: MIT
 * P4-2 atomic, epoch-fenced gateway supervisor.
 * This component is independent of Wi-Fi, FreeRTOS, socket and NVS APIs.
 * A successful host test is not a real network or hardware validation.
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    volatile uint32_t word;
} s3_gateway_session_t;

/* Flags occupy the low byte, upper 24 bits form a monotonic epoch.
 * On epoch exhaustion, the session locks closed until physical reboot.
 */
#define S3_SESSION_STA      (1u << 0)
#define S3_SESSION_AP       (1u << 1)
#define S3_SESSION_NODE     (1u << 2)
#define S3_SESSION_DNS      (1u << 3)
#define S3_SESSION_TCP      (1u << 4)
#define S3_SESSION_HOOK     (1u << 5)
#define S3_SESSION_ARMED    (1u << 6)
#define S3_SESSION_PREREQS  (S3_SESSION_STA | S3_SESSION_AP | S3_SESSION_NODE | S3_SESSION_DNS | S3_SESSION_TCP | S3_SESSION_HOOK)

typedef enum {
    S3_SESSION_STA_ONLINE,
    S3_SESSION_AP_READY,
    S3_SESSION_DNS_LISTENER_READY,
    S3_SESSION_TCP_LISTENER_READY,
    S3_SESSION_OUTPUT_HOOK_READY,
    S3_SESSION_STA_LOST,
    S3_SESSION_AP_LOST,
    S3_SESSION_NODE_FAILED,
    S3_SESSION_WORKER_FAILED,
    S3_SESSION_ADMIN_OFF,
    S3_SESSION_CONFIG_ENTER
} s3_gateway_session_event_t;

/* Zero-initialized device session is locked off until supervisor init. */
s3_gateway_session_t *s3_gateway_session_device(void);
void s3_gateway_session_init(s3_gateway_session_t *session);
uint32_t s3_gateway_session_epoch(const s3_gateway_session_t *session);
uint32_t s3_gateway_session_flags(const s3_gateway_session_t *session);
bool s3_gateway_session_event(s3_gateway_session_t *session,
                              s3_gateway_session_event_t event);
/* Proof must come from an authenticated, checked SS2022/VLESS transaction.
 * Caller captures epoch before async verification; late completions rejected.
 */
bool s3_gateway_session_node_proven(s3_gateway_session_t *session,
                                    uint32_t started_epoch);
/* Only explicit administrator action may arm a fully proven session. */
bool s3_gateway_session_admin_arm(s3_gateway_session_t *session,
                                  uint32_t verified_epoch);
bool s3_gateway_session_ready(const s3_gateway_session_t *session);

#ifdef __cplusplus
}
#endif
