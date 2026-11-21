/* SPDX-License-Identifier: MIT
 * Portable runtime lifetime/credential gate.  No OS, sockets or NVS.
 * A revoked lease cannot keep a new node's credentials mutable.
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    volatile uint32_t permitted;
    volatile uint32_t readers;
} s3_gateway_runtime_guard_t;
void s3_gateway_runtime_guard_init(s3_gateway_runtime_guard_t *g);
void s3_gateway_runtime_guard_revoke(s3_gateway_runtime_guard_t *g);
void s3_gateway_runtime_guard_allow(s3_gateway_runtime_guard_t *g);
bool s3_gateway_runtime_guard_enter(s3_gateway_runtime_guard_t *g);
void s3_gateway_runtime_guard_leave(s3_gateway_runtime_guard_t *g);
bool s3_gateway_runtime_guard_quiescent(const s3_gateway_runtime_guard_t *g);
#ifdef __cplusplus
}
#endif
