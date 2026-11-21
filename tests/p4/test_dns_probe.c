/* Host stubs: interface/negative testing, not real VPS protocol proof. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "s3_gateway_dns_probe.h"
#include "s3_vless_tls.h"

enum {GOOD, DOWN, BAD_ID, BAD_QUESTION, SERVFAIL, EMPTY, TRUNCATED, OVERLONG};
static int behavior;
static unsigned calls;
void esp_fill_random(void *p, size_t n) { memset(p, 0x5a, n); }
bool s3_ss2022_node_valid(const s3_ss2022_node_t *n) { return n != NULL; }
static bool answer(uint8_t *p, int *n, size_t cap)
{
    if (behavior == DOWN) return false;
    assert(*n == 29 && cap >= 45);
    size_t q = (size_t)*n;
    p[2] = 0x81; p[3] = 0x80; p[6] = 0; p[7] = 1;
    const uint8_t rr[]={0xc0,0x0c, 0,1, 0,1, 0,0,0,0, 0,4, 93,184,215,14};
    memcpy(p+q, rr, sizeof(rr));
    *n = (int)(q + sizeof(rr));
    switch (behavior) {
    case BAD_ID: p[0]^=0x10; break;
    case BAD_QUESTION: p[13]='z'; break;
    case SERVFAIL: p[3]=0x82; break;
    case EMPTY: p[7]=0; break;
    case TRUNCATED: p[2]|=0x02; break;
    case OVERLONG: *n=(int)cap+1; break;
    default: break;
    }
    return true;
}
bool s3_ss2022_dns_query(const s3_ss2022_node_t *node, const char *resolver,
                        uint8_t *p,int *n,size_t cap)
{ assert(node && resolver); ++calls; return answer(p,n,cap); }
bool s3_vless_tls_dns_query(const char *sni,uint16_t port,
                           const uint8_t uuid[16],const char *resolver,
                           uint8_t *p,int *n,size_t cap)
{ assert(sni && port && uuid && resolver); ++calls; return answer(p,n,cap); }
int main(void)
{
    s3_ss2022_node_t ss = {0};
    uint8_t uuid[16] = {0};
    s3_gateway_dns_upstream_t u = {
        .transport=S3_GATEWAY_DNS_SS2022,
        .ss2022_node=&ss, .resolver="1.1.1.1"
    };
    assert(!s3_gateway_dns_probe_node(NULL));
    u.resolver=NULL; assert(!s3_gateway_dns_probe_node(&u));
    u.resolver="1.1.1.1";
    u.ss2022_node=NULL; assert(!s3_gateway_dns_probe_node(&u));
    u.ss2022_node=&ss;
    for(behavior=GOOD;behavior<=OVERLONG;behavior++)
        assert(s3_gateway_dns_probe_node(&u)==(behavior==GOOD));
    u.transport=S3_GATEWAY_DNS_VLESS_TLS;
    u.vless_sni="proxy.example.com";u.vless_port=443;u.vless_uuid=uuid;
    behavior=GOOD; assert(s3_gateway_dns_probe_node(&u));
    u.vless_port=0; assert(!s3_gateway_dns_probe_node(&u));
    u.vless_port=443;behavior=DOWN;assert(!s3_gateway_dns_probe_node(&u));
    u.transport=S3_GATEWAY_DNS_NONE;behavior=GOOD;
    assert(!s3_gateway_dns_probe_node(&u));
    assert(calls==10);
    puts("P4_2_PROBE_PASS encrypted-only API, response binding and error matrix");
    return 0;
}
