/* SPDX-License-Identifier: MIT
 * Independent from AP DNS policy (which must remain locked before proof).
 * Only the existing authenticated proxy DNS functions reach the network.
 */
#include <stdint.h>
#include <string.h>
#include "esp_random.h"
#include "s3_gateway_dns_codec.h"
#include "s3_gateway_dns_probe.h"
#include "s3_vless_tls.h"

static const uint8_t query_template[] = {
    0,0, 0x01,0, 0,1, 0,0, 0,0, 0,0,
    7,'e','x','a','m','p','l','e', 3,'c','o','m',0, 0,1, 0,1
};
bool s3_gateway_dns_probe_node(const s3_gateway_dns_upstream_t *upstream)
{
    if (!upstream || !upstream->resolver || !upstream->resolver[0])
        return false;
    uint8_t request[sizeof(query_template)];
    uint8_t answer[S3_GATEWAY_DNS_WIRE_MAX] = {0};
    memcpy(request, query_template, sizeof(request));
    esp_fill_random(request, 2);
    memcpy(answer, request, sizeof(request));
    int n = (int)sizeof(request);
    bool verified = false;
    switch (upstream->transport) {
    case S3_GATEWAY_DNS_SS2022:
        if (upstream->ss2022_node &&
            s3_ss2022_node_valid(upstream->ss2022_node))
            verified = s3_ss2022_dns_query(upstream->ss2022_node,
                        upstream->resolver, answer, &n, sizeof(answer));
        break;
    case S3_GATEWAY_DNS_VLESS_TLS:
        if (upstream->vless_sni && upstream->vless_sni[0] &&
            upstream->vless_port && upstream->vless_uuid)
            verified = s3_vless_tls_dns_query(upstream->vless_sni,
                        upstream->vless_port, upstream->vless_uuid,
                        upstream->resolver, answer, &n, sizeof(answer));
        break;
    default:
        break;
    }
    /* Verified encrypted answer, same transaction and question, untruncated
     * NOERROR response with at least one answer (example.com A).
     */
    bool proven = verified && n > (int)sizeof(request) &&
                  n <= (int)sizeof(answer) &&
                  s3_gateway_dns_matches(request, sizeof(request),
                                         answer, (size_t)n) &&
                  (answer[2] & 0x82u) == 0x80u &&
                  (answer[3] & 0x0fu) == 0 &&
                  (answer[6] != 0 || answer[7] != 0);
    memset(answer, 0, sizeof(answer));
    memset(request, 0, sizeof(request));
    return proven;
}
