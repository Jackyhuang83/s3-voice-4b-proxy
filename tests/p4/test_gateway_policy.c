/* P4-1 host regression: security-sensitive gateway permission matrix. */
#include <assert.h>
#include <stdio.h>
#include "s3_gateway_policy.h"

static s3_gateway_packet_action_t remote_tcp(const s3_gateway_policy_t *p) {
    return s3_gateway_packet_decide(p, true, false, 6, 49712, 443);
}

int main(void) {
    s3_gateway_policy_t p = S3_GATEWAY_POLICY_INIT;
    assert(s3_gateway_dhcp_destination_allowed(0xffffffffu,0xc0a80201u,0xffffff00u));
    assert(s3_gateway_dhcp_destination_allowed(0xc0a80201u,0xc0a80201u,0xffffff00u));
    assert(s3_gateway_dhcp_destination_allowed(0xc0a802ffu,0xc0a80201u,0xffffff00u));
    assert(!s3_gateway_dhcp_destination_allowed(0x08080808u,0xc0a80201u,0xffffff00u));
    assert(!s3_gateway_dhcp_destination_allowed(0xffffffffu,0u,0xffffff00u));
    assert(!s3_gateway_policy_ready(&p));
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);
    assert(s3_gateway_packet_decide(&p,false,false,6,12345,443) == S3_GW_PACKET_IGNORE);
    assert(s3_gateway_packet_decide(&p,true,false,17,68,67) == S3_GW_PACKET_LOCAL);
    assert(s3_gateway_packet_decide(&p,true,true,17,5151,53) == S3_GW_PACKET_LOCAL);
    assert(s3_gateway_packet_decide(&p,true,true,6,5151,53) == S3_GW_PACKET_LOCAL);
    assert(s3_gateway_packet_decide(&p,true,true,6,5151,80) == S3_GW_PACKET_DROP);
    assert(s3_gateway_packet_decide(&p,true,false,17,5151,53) == S3_GW_PACKET_DROP);
    assert(s3_gateway_packet_decide(&p,true,false,17,5151,443) == S3_GW_PACKET_DROP);
    assert(s3_gateway_packet_decide(&p,true,false,1,0,0) == S3_GW_PACKET_DROP);
    s3_gateway_policy_event(&p, S3_GW_ADMIN_ARM);
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);
    s3_gateway_policy_event(&p, S3_GW_STA_CONNECTED);
    s3_gateway_policy_event(&p, S3_GW_RELAY_READY); /* no node */
    s3_gateway_policy_event(&p, S3_GW_ADMIN_ARM);
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);
    s3_gateway_policy_event(&p, S3_GW_NODE_VALIDATED);
    s3_gateway_policy_event(&p, S3_GW_ADMIN_ARM);  /* no live relay */
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);
    s3_gateway_policy_event(&p, S3_GW_RELAY_READY);
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);  /* never auto-arm */
    s3_gateway_policy_event(&p, S3_GW_ADMIN_ARM);
    assert(s3_gateway_policy_ready(&p));
    assert(remote_tcp(&p) == S3_GW_PACKET_INTERCEPT);
    assert(s3_gateway_packet_decide(&p,true,false,17,5000,443) == S3_GW_PACKET_DROP);
    assert(s3_gateway_packet_decide(&p,true,false,6,5000,53) == S3_GW_PACKET_INTERCEPT);

    s3_gateway_policy_event(&p, S3_GW_STA_DISCONNECTED);
    assert(!s3_gateway_policy_ready(&p));
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);
    s3_gateway_policy_event(&p, S3_GW_STA_CONNECTED);
    s3_gateway_policy_event(&p, S3_GW_RELAY_READY);
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP); /* cannot auto-rearm */

    s3_gateway_policy_event(&p, S3_GW_ADMIN_ARM);
    assert(s3_gateway_policy_ready(&p));
    s3_gateway_policy_event(&p, S3_GW_CONFIG_ENTER);
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);
    s3_gateway_policy_event(&p, S3_GW_STA_CONNECTED);
    s3_gateway_policy_event(&p, S3_GW_RELAY_READY);
    s3_gateway_policy_event(&p, S3_GW_ADMIN_ARM);
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);
    s3_gateway_policy_event(&p, S3_GW_CONFIG_EXIT);
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);

    s3_gateway_policy_event(&p, S3_GW_STA_CONNECTED);
    s3_gateway_policy_event(&p, S3_GW_RELAY_READY);
    s3_gateway_policy_event(&p, S3_GW_ADMIN_ARM);
    assert(remote_tcp(&p) == S3_GW_PACKET_INTERCEPT);
    s3_gateway_policy_event(&p, S3_GW_NODE_INVALIDATED);
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);
    s3_gateway_policy_event(&p, S3_GW_NODE_VALIDATED);
    s3_gateway_policy_event(&p, S3_GW_RELAY_READY);
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);
    s3_gateway_policy_event(&p, S3_GW_ADMIN_ARM);
    assert(remote_tcp(&p) == S3_GW_PACKET_INTERCEPT);
    s3_gateway_policy_event(&p, S3_GW_RELAY_FAILED);
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);
    s3_gateway_policy_event(&p, S3_GW_RESET);
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);
    s3_gateway_policy_event(&p, (s3_gateway_event_t)999);
    assert(remote_tcp(&p) == S3_GW_PACKET_DROP);
    assert(!s3_gateway_policy_ready(NULL));
    assert(s3_gateway_packet_decide(NULL,true,false,6,1,443) == S3_GW_PACKET_DROP);
    puts("P4_GATEWAY_POLICY_PASS: manual arm, Wi-Fi/config/node/relay fail-closed, DHCP/DNS-only local and TCP-only external");
    return 0;
}
