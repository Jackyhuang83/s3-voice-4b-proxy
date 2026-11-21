/* Host-side regression tests compile and execute the REAL pinned upstream
 * src/transparent_tcp.c with tiny deterministic lwIP/ESP-IDF API shims.
 * No device is flashed, no external network is contacted.
 * This does not simulate Wi-Fi timing, DNS task, or actual gateway routing. */
#include <arpa/inet.h>
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "lwip/ip4.h"
#include "transparent_tcp.h"
#include "lwip_router_hook.h"

static struct netif g_ap;
static struct netif g_other;
static int g_reinjected, g_freed, g_fail_alloc, g_fail_copy, g_fail_take;
static uint32_t g_relay_dest;
static uint16_t g_relay_port;

int64_t esp_timer_get_time(void) { return 1000000000; }

struct pbuf *pbuf_alloc(int layer, uint16_t length, int type)
{
    (void)layer; (void)type;
    if (g_fail_alloc) return NULL;
    struct pbuf *p = calloc(1, sizeof(*p));
    assert(p);
    p->payload = calloc(1, length ? length : 1);
    assert(p->payload);
    p->len = p->tot_len = length;
    return p;
}

err_t pbuf_copy(struct pbuf *dest, const struct pbuf *src)
{
    if (g_fail_copy || src->tot_len > dest->tot_len) return ERR_IF;
    memcpy(dest->payload, src->payload, src->tot_len);
    return ERR_OK;
}

uint16_t pbuf_copy_partial(const struct pbuf *p, void *data, uint16_t len, uint16_t offset)
{
    if (offset >= p->tot_len) return 0;
    uint16_t avail = p->tot_len - offset;
    if (len > avail) len = avail;
    memcpy(data, p->payload + offset, len);
    return len;
}

err_t pbuf_take_at(struct pbuf *p, const void *data, uint16_t len, uint16_t offset)
{
    if (g_fail_take || (size_t)offset + len > p->tot_len) return ERR_IF;
    memcpy(p->payload + offset, data, len);
    return ERR_OK;
}

uint8_t pbuf_free(struct pbuf *p)
{
    assert(p);
    ++g_freed;
    free(p->payload);
    free(p);
    return 1;
}

uint8_t pbuf_header(struct pbuf *p, int16_t increment)
{
    (void)p; (void)increment;
    return 0; /* link output not invoked in this focused input-hook fixture */
}

err_t ip4_input(struct pbuf *p, struct netif *inp)
{
    /* A reinjected TCP packet must NOT recursively enter the redirect hook. */
    assert(transparent_tcp_ip4_input(p, inp) == 0);
    ++g_reinjected;
    memcpy(&g_relay_dest, p->payload + 16, sizeof(g_relay_dest));
    g_relay_port = ((uint16_t)p->payload[22] << 8) | p->payload[23];
    pbuf_free(p);
    return ERR_OK;
}

static uint16_t be16(const uint8_t *p)
{
    return ((uint16_t)p[0] << 8) | p[1];
}

static struct pbuf *packet(int proto, unsigned ihl, unsigned len, const char *dst,
                           unsigned source_port, unsigned destination_port, int flags, uint16_t frag)
{
    assert(ihl >= 20 && ihl <= 60 && ihl % 4 == 0 && len <= UINT16_MAX);
    struct pbuf *p = calloc(1, sizeof(*p));
    assert(p);
    p->payload = calloc(1, len ? len : 1);
    assert(p->payload);
    p->tot_len = p->len = (uint16_t)len;
    if (len >= 20) {
        p->payload[0] = 0x40 | (ihl / 4);
        p->payload[2] = (uint8_t)(len >> 8);
        p->payload[3] = (uint8_t)len;
        p->payload[6] = (uint8_t)(frag >> 8);
        p->payload[7] = (uint8_t)frag;
        p->payload[9] = (uint8_t)proto;
        uint32_t src_ip = inet_addr("192.168.4.2");
        uint32_t dst_ip = inet_addr(dst);
        memcpy(p->payload + 12, &src_ip, 4);
        memcpy(p->payload + 16, &dst_ip, 4);
    }
    if (len >= ihl + 4) {
        p->payload[ihl] = (uint8_t)(source_port >> 8);
        p->payload[ihl + 1] = (uint8_t)source_port;
        p->payload[ihl + 2] = (uint8_t)(destination_port >> 8);
        p->payload[ihl + 3] = (uint8_t)destination_port;
    }
    if (proto == 6 && len >= ihl + 14) p->payload[ihl + 13] = (uint8_t)flags;
    return p;
}

static void reset_fixture(void)
{
    g_reinjected = g_freed = g_fail_alloc = g_fail_copy = g_fail_take = 0;
    g_relay_dest = 0;
    g_relay_port = 0;
    memset(&g_ap, 0, sizeof(g_ap));
    memset(&g_other, 0, sizeof(g_other));
    g_ap.ip_addr.addr = inet_addr("192.168.4.1");
    transparent_tcp_init();
    transparent_tcp_set_ap_netif(&g_ap);
    transparent_tcp_set_enabled(true);
}

static void run(const char *name, struct pbuf *p, struct netif *netif,
                int expected_result, int expected_reinjected, int expected_freed)
{
    int result = transparent_tcp_ip4_input(p, netif);
    if (result != expected_result || g_reinjected != expected_reinjected) {
        fprintf(stderr, "%s: result=%d expected=%d reinjected=%d expected=%d\n",
                name, result, expected_result, g_reinjected, expected_reinjected);
        abort();
    }
    if (result == 0) pbuf_free(p); /* caller retains the packet */
    if (g_freed != expected_freed) {
        fprintf(stderr, "%s: pbuf_free calls=%d expected=%d\n", name, g_freed, expected_freed);
        abort();
    }
    printf("PASS %s\n", name);
}

int main(void)
{
    const char *remote = "198.51.100.7";
    const char *ap = "192.168.4.1";
    reset_fixture();
    run("short UDP 28B cannot bypass guard", packet(17,20,28,remote,52000,443,0,0), &g_ap,1,0,1);

    reset_fixture();
    run("short UDP 39B blocked", packet(17,20,39,remote,52000,443,0,0), &g_ap,1,0,1);

    reset_fixture();
    run("large QUIC UDP blocked", packet(17,20,1200,remote,52000,443,0,0), &g_ap,1,0,1);

    reset_fixture();
    run("remote UDP DNS blocked", packet(17,20,28,remote,52000,53,0,0), &g_ap,1,0,1);

    reset_fixture();
    run("local AP DNS allowed", packet(17,20,28,ap,52000,53,0,0), &g_ap,0,0,1);

    reset_fixture();
    run("local AP portal TCP allowed", packet(6,20,40,ap,52000,80,2,0), &g_ap,0,0,1);

    reset_fixture();
    run("DHCP broadcast UDP allowed", packet(17,20,28,"255.255.255.255",68,67,0,0), &g_ap,0,0,1);

    reset_fixture();
    run("broadcast non-DHCP blocked", packet(17,20,28,"255.255.255.255",50000,67,0,0), &g_ap,1,0,1);

    reset_fixture();
    run("unsupported remote IPv4 ICMP dropped", packet(1,20,28,remote,0,0,0,0), &g_ap,1,0,1);

    reset_fixture();
    run("TCP SYN intercepted and reinjected", packet(6,20,40,remote,52000,443,2,0), &g_ap,1,1,2);
    assert(g_relay_dest == g_ap.ip_addr.addr);
    assert(g_relay_port == 15001);

    reset_fixture();
    run("TCP ACK without tracked flow blocked", packet(6,20,40,remote,52000,443,16,0), &g_ap,1,0,1);

    reset_fixture();
    run("TCP options IHL=60 bounded", packet(6,60,80,remote,52000,443,2,0), &g_ap,1,1,2);

    reset_fixture();
    run("UDP options IHL=60 bounded", packet(17,60,68,remote,52000,443,0,0), &g_ap,1,0,1);

    reset_fixture();
    run("TCP initial fragment dropped", packet(6,20,40,remote,52000,443,2,0x2000), &g_ap,1,0,1);

    reset_fixture();
    run("UDP non-initial fragment dropped", packet(17,20,28,remote,52000,443,0,0x0001), &g_ap,1,0,1);

    reset_fixture();
    run("malformed truncated UDP dropped", packet(17,20,27,remote,52000,443,0,0), &g_ap,1,0,1);

    reset_fixture();
    struct pbuf *short_ip = packet(6,20,19,remote,52000,443,2,0);
    run("short IPv4 header dropped", short_ip, &g_ap,1,0,1);

    reset_fixture();
    struct pbuf *bad_total = packet(17,20,28,remote,52000,443,0,0);
    bad_total->payload[2] = 0;
    bad_total->payload[3] = 23;
    run("inconsistent IPv4 total length dropped",bad_total,&g_ap,1,0,1);

    reset_fixture();
    g_fail_alloc = 1;
    run("OOM on TCP redirect fails closed", packet(6,20,40,remote,52000,443,2,0), &g_ap,1,0,1);

    reset_fixture();
    g_fail_copy = 1;
    run("TCP rewrite copy failure fails closed", packet(6,20,40,remote,52000,443,2,0), &g_ap,1,0,2);

    reset_fixture();
    g_fail_take = 1;
    run("TCP packet rewrite failure fails closed", packet(6,20,40,remote,52000,443,2,0), &g_ap,1,0,2);

    reset_fixture();
    for (unsigned p=1000;p<1000+TRANSPARENT_TCP_MAX_FLOWS;p++) {
        transparent_tcp_flow_t flow;
        assert(transparent_tcp_create_or_get(inet_addr("192.168.4.2"),p,inet_addr(remote),443,&flow));
    }
    run("exhausted TCP flow table fails closed", packet(6,20,40,remote,52000,443,2,0), &g_ap,1,0,1);

    reset_fixture();
    run("non-AP netif not intercepted", packet(17,20,28,remote,52000,443,0,0), &g_other,0,0,1);

    /* DNS domain-to-A mapping remains owned by the original upstream cache. */
    reset_fixture();
    transparent_tcp_dns_record("example.org", inet_addr(remote));
    char name[254] = {0};
    assert(transparent_tcp_dns_name_for_ip(inet_addr(remote),name,sizeof(name)));
    assert(strcmp(name,"example.org")==0);
    printf("PASS DNS A-record cache\n");

    /* Suppress warning when a future compiler diagnoses an unused helper. */
    assert(be16((const uint8_t[]){0x12,0x34}) == 0x1234);
    printf("PASS all host input-hook regression cases\n");
    return 0;
}
