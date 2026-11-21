/* P4-2: legacy policy alone cannot activate real AP forwarding. */
#include <assert.h>
#include <stdio.h>
#include "s3_gateway_policy.h"
#include "s3_gateway_session.h"

static bool ready(void) {
    return s3_gateway_policy_ready(s3_gateway_policy_device());
}
int main(void) {
    s3_gateway_policy_t *p = s3_gateway_policy_device();
    s3_gateway_session_t *s = s3_gateway_session_device();
    s3_gateway_policy_init(p);
    assert(s3_gateway_session_epoch(s) == 1);
    /* The original voice STA callback can run before AP worker creation. */
    assert(s3_gateway_session_event(s, S3_SESSION_STA_ONLINE));
    assert((s3_gateway_session_flags(s) & S3_SESSION_STA) != 0);
    assert(!ready());
    s3_gateway_policy_event(p, S3_GW_STA_CONNECTED);
    s3_gateway_policy_event(p, S3_GW_NODE_VALIDATED);
    s3_gateway_policy_event(p, S3_GW_RELAY_READY);
    s3_gateway_policy_event(p, S3_GW_ADMIN_ARM);
    assert(!ready()); /* Host-era P4-1 flags still cannot authorize. */
    s3_gateway_session_init(s);
    uint32_t e = s3_gateway_session_epoch(s);
    assert(e == 1 && !ready());
    assert(s3_gateway_session_event(s, S3_SESSION_STA_ONLINE));
    assert(s3_gateway_session_event(s, S3_SESSION_AP_READY));
    assert(s3_gateway_session_event(s, S3_SESSION_DNS_LISTENER_READY));
    assert(s3_gateway_session_event(s, S3_SESSION_TCP_LISTENER_READY));
    assert(s3_gateway_session_event(s, S3_SESSION_OUTPUT_HOOK_READY));
    assert(!ready());
    assert(s3_gateway_session_node_proven(s, e));
    assert(!ready()); /* No automatic administrator arm. */
    assert(s3_gateway_session_admin_arm(s, e));
    assert(ready());
    assert(s3_gateway_session_event(s, S3_SESSION_NODE_FAILED));
    assert(!ready()); /* Prior policy is still armed, but epoch revoked. */
    assert(!s3_gateway_session_admin_arm(s, e));
    uint32_t e2 = s3_gateway_session_epoch(s);
    assert(e2 == e + 1);
    assert(s3_gateway_session_event(s, S3_SESSION_DNS_LISTENER_READY));
    assert(s3_gateway_session_event(s, S3_SESSION_TCP_LISTENER_READY));
    assert(s3_gateway_session_event(s, S3_SESSION_OUTPUT_HOOK_READY));
    assert(s3_gateway_session_node_proven(s, e2));
    assert(!ready());
    assert(s3_gateway_session_admin_arm(s, e2));
    assert(ready());
    assert(s3_gateway_session_event(s, S3_SESSION_ADMIN_OFF));
    assert(!ready());
    assert(!s3_gateway_session_admin_arm(s, e2));
    s3_gateway_policy_event(p, S3_GW_RESET);
    assert(!ready());
    puts("P4_2_DEVICE_GATE_PASS epoch revocation fences legacy AP authorization");
    return 0;
}
