/* SPDX-License-Identifier: MIT
 * Readers acquire a lifetime lease BEFORE touching any node pointer.
 * Supervisor may rewrite credentials only while revoked AND quiescent.
 */
#include "s3_gateway_runtime_guard.h"
void s3_gateway_runtime_guard_init(s3_gateway_runtime_guard_t *g)
{
    if (!g) return;
    __atomic_store_n(&g->permitted, 0u, __ATOMIC_RELEASE);
    __atomic_store_n(&g->readers, 0u, __ATOMIC_RELEASE);
}
void s3_gateway_runtime_guard_revoke(s3_gateway_runtime_guard_t *g)
{
    if (g) __atomic_store_n(&g->permitted, 0u, __ATOMIC_RELEASE);
}
void s3_gateway_runtime_guard_allow(s3_gateway_runtime_guard_t *g)
{
    if (g) __atomic_store_n(&g->permitted, 1u, __ATOMIC_RELEASE);
}
bool s3_gateway_runtime_guard_enter(s3_gateway_runtime_guard_t *g)
{
    if (!g) return false;
    __atomic_add_fetch(&g->readers, 1u, __ATOMIC_ACQ_REL);
    if (__atomic_load_n(&g->permitted, __ATOMIC_ACQUIRE)) return true;
    __atomic_sub_fetch(&g->readers, 1u, __ATOMIC_ACQ_REL);
    return false;
}
void s3_gateway_runtime_guard_leave(s3_gateway_runtime_guard_t *g)
{
    if (g) __atomic_sub_fetch(&g->readers, 1u, __ATOMIC_ACQ_REL);
}
bool s3_gateway_runtime_guard_quiescent(const s3_gateway_runtime_guard_t *g)
{
    return g && !__atomic_load_n(&g->permitted, __ATOMIC_ACQUIRE) &&
           !__atomic_load_n(&g->readers, __ATOMIC_ACQUIRE);
}
