#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "s3_gateway_session.h"

int main(void)
{
    s3_gateway_session_t s = {0};
    assert(!s3_gateway_session_ready(&s));
    assert(!s3_gateway_session_event(&s,S3_SESSION_STA_ONLINE));
    assert(!s3_gateway_session_admin_arm(&s,1));
    s3_gateway_session_init(&s);
    uint32_t e = s3_gateway_session_epoch(&s);
    assert(e == 1 && !s3_gateway_session_ready(&s));
    assert(!s3_gateway_session_event(&s,S3_SESSION_TCP_LISTENER_READY));
    assert(!s3_gateway_session_event(&s,S3_SESSION_DNS_LISTENER_READY));
    assert(!s3_gateway_session_event(&s,S3_SESSION_OUTPUT_HOOK_READY));
    assert(s3_gateway_session_event(&s,S3_SESSION_AP_READY));
    assert(s3_gateway_session_event(&s,S3_SESSION_STA_ONLINE));
    assert(s3_gateway_session_event(&s,S3_SESSION_DNS_LISTENER_READY));
    assert(s3_gateway_session_event(&s,S3_SESSION_TCP_LISTENER_READY));
    assert(s3_gateway_session_event(&s,S3_SESSION_OUTPUT_HOOK_READY));
    assert(!s3_gateway_session_admin_arm(&s,e)); /* Proof missing. */
    assert(!s3_gateway_session_node_proven(&s,e+1));
    assert(s3_gateway_session_node_proven(&s,e));
    assert(!s3_gateway_session_ready(&s)); /* No auto arm. */
    assert(s3_gateway_session_admin_arm(&s,e));
    assert(s3_gateway_session_ready(&s));
    assert(s3_gateway_session_event(&s,S3_SESSION_STA_LOST));
    assert(!s3_gateway_session_ready(&s));
    uint32_t new_epoch = s3_gateway_session_epoch(&s);
    assert(new_epoch == e+1);
    assert(!s3_gateway_session_node_proven(&s,e));
    assert(!s3_gateway_session_admin_arm(&s,e));
    assert(s3_gateway_session_event(&s,S3_SESSION_STA_ONLINE));
    assert(!s3_gateway_session_admin_arm(&s,new_epoch));
    assert(!s3_gateway_session_node_proven(&s,e));
    assert(s3_gateway_session_event(&s,S3_SESSION_DNS_LISTENER_READY));
    assert(s3_gateway_session_event(&s,S3_SESSION_TCP_LISTENER_READY));
    assert(s3_gateway_session_event(&s,S3_SESSION_OUTPUT_HOOK_READY));
    assert(s3_gateway_session_node_proven(&s,new_epoch));
    assert(s3_gateway_session_admin_arm(&s,new_epoch));
    assert(s3_gateway_session_ready(&s));
    assert(s3_gateway_session_event(&s,S3_SESSION_ADMIN_OFF));
    assert(!s3_gateway_session_ready(&s));
    assert(!s3_gateway_session_admin_arm(&s,new_epoch));
    assert(s3_gateway_session_event(&s,S3_SESSION_AP_LOST));
    assert(!s3_gateway_session_ready(&s));
    assert(s3_gateway_session_event(&s,S3_SESSION_CONFIG_ENTER));
    assert(s3_gateway_session_flags(&s)==0);
    assert(!s3_gateway_session_event(&s,(s3_gateway_session_event_t)999));
    assert(!s3_gateway_session_ready(NULL));
    assert(!s3_gateway_session_node_proven(NULL,1));
    assert(!s3_gateway_session_admin_arm(NULL,1));

    /* Failure epoch never wraps into a stale authorization token. */
    s.word = (uint32_t)(0x00ffffffu << 8);
    assert(s3_gateway_session_event(&s,S3_SESSION_NODE_FAILED));
    assert(s3_gateway_session_epoch(&s)==0);
    assert(!s3_gateway_session_event(&s,S3_SESSION_STA_ONLINE));
    assert(!s3_gateway_session_ready(&s));

    /* Deterministic interleaved stale responses and reconnection failures. */
    s3_gateway_session_init(&s);
    for (unsigned k=0;k<10000;k++) {
        uint32_t before=s3_gateway_session_epoch(&s);
        assert(s3_gateway_session_event(&s,S3_SESSION_STA_ONLINE));
        assert(s3_gateway_session_event(&s,S3_SESSION_AP_READY));
        assert(s3_gateway_session_event(&s,S3_SESSION_NODE_FAILED));
        assert(!s3_gateway_session_node_proven(&s,before));
        assert(!s3_gateway_session_admin_arm(&s,before));
        assert(!s3_gateway_session_ready(&s));
    }
    puts("P4_2_SESSION_PASS epoch-fenced proof, manual-arm, STA/AP loss, replay and 10000 revocations");
    return 0;
}
