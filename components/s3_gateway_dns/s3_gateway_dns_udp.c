/* SPDX-License-Identifier: MIT
 * Local AP DNS UDP service. No direct Internet resolver, ever.
 */
#include <errno.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include "s3_gateway_dns_udp.h"
#include "s3_gateway_dns_codec.h"

static bool ap_ip(esp_netif_t *ap, esp_netif_ip_info_t *out)
{
    if (!ap || !out) return false;
    const char *key = esp_netif_get_ifkey(ap);
    return key && strcmp(key, "WIFI_AP_DEF") == 0 &&
           esp_netif_get_ip_info(ap, out) == ESP_OK && out->ip.addr != 0 &&
           out->netmask.addr != 0;
}

int s3_gateway_dns_udp_open(esp_netif_t *gateway_ap)
{
    esp_netif_ip_info_t info = {0};
    if (!ap_ip(gateway_ap, &info)) return -1;
    int fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (fd < 0) return -1;
    struct timeval timeout = {.tv_sec = 1, .tv_usec = 0};
    if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO,
                   &timeout, sizeof(timeout)) != 0) {
        close(fd);
        return -1;
    }
    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(53);
    addr.sin_addr.s_addr = info.ip.addr;
    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) != 0) {
        close(fd);
        return -1;
    }
    return fd;
}

bool s3_gateway_dns_udp_poll(int fd, esp_netif_t *gateway_ap,
                             const s3_gateway_dns_upstream_t *upstream)
{
    if (fd < 0) return false;
    esp_netif_ip_info_t info = {0};
    if (!ap_ip(gateway_ap, &info)) return false;
    /* Allocate one extra byte so an oversize UDP packet fails closed. */
    uint8_t request[S3_GATEWAY_DNS_WIRE_MAX + 1];
    uint8_t reply[S3_GATEWAY_DNS_WIRE_MAX];
    struct sockaddr_in peer = {0};
    socklen_t peerlen = sizeof(peer);
    ssize_t got = recvfrom(fd, request, sizeof(request), 0,
                            (struct sockaddr *)&peer, &peerlen);
    if (got < 12 || got > S3_GATEWAY_DNS_WIRE_MAX ||
        peerlen != sizeof(peer) || peer.sin_family != AF_INET)
        return false;
    /* Never respond to a source outside the AP subnet (e.g. STA). */
    if ((peer.sin_addr.s_addr & info.netmask.addr) !=
        (info.ip.addr & info.netmask.addr)) return false;
    size_t n = s3_gateway_dns_process(upstream, request, (size_t)got,
                                      reply, sizeof(reply));
    if (!n) return false;
    /* sendto is ONLY the reply to this AP client, never a public resolver. */
    ssize_t sent = sendto(fd, reply, n, 0,
                          (struct sockaddr *)&peer, sizeof(peer));
    return sent == (ssize_t)n;
}
