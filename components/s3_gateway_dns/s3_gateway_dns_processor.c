/* SPDX-License-Identifier: MIT
 * Orchestration over the existing verified SS2022 and ESP-TLS VLESS DNS APIs.
 * No socket, raw DNS, fallback or Wi-Fi ownership in this component.
 */
#include "s3_gateway_dns_processor.h"
#include "s3_gateway_dns_codec.h"
#include "s3_gateway_policy.h"
#include "s3_vless_tls.h"
#include <stdbool.h>
#include <string.h>

size_t s3_gateway_dns_process(const s3_gateway_dns_upstream_t *upstream,
                              const uint8_t *request, size_t request_len,
                              uint8_t *answer, size_t answer_capacity) {
    size_t question_end = 0;
    if (!request || !answer || !s3_gateway_dns_question(request, request_len,
                                                         false, &question_end))
        return 0;
    size_t failure_len = s3_gateway_dns_servfail(request, request_len,
                                                  answer, answer_capacity);
    if (!failure_len || !upstream || !upstream->resolver ||
        !upstream->resolver[0] || !s3_gateway_policy_ready(s3_gateway_policy_device()))
        return failure_len;

    uint8_t tunnel_packet[S3_GATEWAY_DNS_WIRE_MAX];
    memcpy(tunnel_packet, request, request_len);
    int tunnel_length = (int)request_len;
    bool verified = false;
    switch (upstream->transport) {
        case S3_GATEWAY_DNS_SS2022:
            if (upstream->ss2022_node) {
                verified = s3_ss2022_dns_query(upstream->ss2022_node,
                           upstream->resolver, tunnel_packet,
                           &tunnel_length, sizeof(tunnel_packet));
            }
            break;
        case S3_GATEWAY_DNS_VLESS_TLS:
            if (upstream->vless_sni && upstream->vless_sni[0] &&
                upstream->vless_port && upstream->vless_uuid) {
                verified = s3_vless_tls_dns_query(upstream->vless_sni,
                           upstream->vless_port, upstream->vless_uuid,
                           upstream->resolver, tunnel_packet,
                           &tunnel_length, sizeof(tunnel_packet));
            }
            break;
        default:
            break;
    }
    /* A station disconnect may revoke permission during the encrypted call. */
    if (!verified || tunnel_length < 12 ||
        (size_t)tunnel_length > sizeof(tunnel_packet) ||
        (size_t)tunnel_length > answer_capacity ||
        !s3_gateway_policy_ready(s3_gateway_policy_device()) ||
        !s3_gateway_dns_matches(request, request_len,
                                 tunnel_packet, (size_t)tunnel_length)) {
        memset(tunnel_packet, 0, sizeof(tunnel_packet));
        return failure_len;
    }
    memcpy(answer, tunnel_packet, (size_t)tunnel_length);
    memset(tunnel_packet, 0, sizeof(tunnel_packet));
    return (size_t)tunnel_length;
}
