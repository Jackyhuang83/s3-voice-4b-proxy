/* Portable lifetime gate negatives: no credential mutation with live lease.
 * No device/FreeRTOS proof; run alongside the full integrated build.
 */
#include <assert.h>
#include <stdio.h>
#include "s3_gateway_runtime_guard.h"
int main(void)
{
    s3_gateway_runtime_guard_t g = {0};
    assert(!s3_gateway_runtime_guard_enter(&g));
    assert(s3_gateway_runtime_guard_quiescent(&g));
    s3_gateway_runtime_guard_init(&g);
    for (int n = 0; n < 1000; ++n) {
        s3_gateway_runtime_guard_allow(&g);
        assert(s3_gateway_runtime_guard_enter(&g));
        assert(s3_gateway_runtime_guard_enter(&g));
        assert(!s3_gateway_runtime_guard_quiescent(&g));
        s3_gateway_runtime_guard_revoke(&g);
        assert(!s3_gateway_runtime_guard_enter(&g));
        assert(!s3_gateway_runtime_guard_quiescent(&g));
        s3_gateway_runtime_guard_leave(&g);
        assert(!s3_gateway_runtime_guard_quiescent(&g));
        s3_gateway_runtime_guard_leave(&g);
        assert(s3_gateway_runtime_guard_quiescent(&g));
    }
    s3_gateway_runtime_guard_allow(&g);
    assert(!s3_gateway_runtime_guard_quiescent(&g));
    s3_gateway_runtime_guard_revoke(&g);
    assert(s3_gateway_runtime_guard_quiescent(&g));
    puts("P4_2_RUNTIME_GUARD_PASS no new-node reuse with in-flight DNS/TCP");
    return 0;
}
