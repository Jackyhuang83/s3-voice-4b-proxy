/* SPDX-License-Identifier: MIT
 * Bounded RFC 7766 TCP framing using ESP-IDF sockets. Upstream DNS is
 * exclusively s3_gateway_dns_process(): encrypted tunnel or SERVFAIL.
 */
#include <stdint.h>
#include <string.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#include "esp_timer.h"
#include "s3_gateway_dns_tcp.h"
#include "s3_gateway_dns_codec.h"

#define S3_TCP_DNS_IO_DEADLINE_US 3000000LL

static bool get_ap(esp_netif_t *netif, esp_netif_ip_info_t *info)
{
    if (!netif || !info) return false;
    const char *key = esp_netif_get_ifkey(netif);
    return key && strcmp(key, "WIFI_AP_DEF") == 0 &&
           esp_netif_get_ip_info(netif, info) == ESP_OK &&
           info->ip.addr && info->netmask.addr;
}

static bool set_timeout(int fd)
{
    const struct timeval timeout = {.tv_sec = 1, .tv_usec = 0};
    return setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO,
                      &timeout, sizeof(timeout)) == 0 &&
           setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO,
                      &timeout, sizeof(timeout)) == 0;
}

int s3_gateway_dns_tcp_listen(esp_netif_t *gateway_ap)
{
    esp_netif_ip_info_t ip = {0};
    if (!get_ap(gateway_ap, &ip)) return -1;
    int fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (fd < 0) return -1;
    struct sockaddr_in address = {0};
    address.sin_family = AF_INET;
    address.sin_port = htons(53);
    address.sin_addr.s_addr = ip.ip.addr;
    if (!set_timeout(fd) ||
        bind(fd, (struct sockaddr *)&address, sizeof(address)) != 0 ||
        listen(fd, 2) != 0) {
        close(fd);
        return -1;
    }
    return fd;
}

/* A trickling client cannot extend the deadline by sending one byte at
 * a time. Each socket operation also has its own one-second timeout.
 */
static bool read_exact(int fd, uint8_t *data, size_t n, int64_t until)
{
    while (n) {
        if (esp_timer_get_time() >= until) return false;
        ssize_t got = recv(fd, data, n, 0);
        if (got <= 0) return false;
        data += (size_t)got;
        n -= (size_t)got;
    }
    return true;
}

static bool write_exact(int fd, const uint8_t *data, size_t n, int64_t until)
{
    while (n) {
        if (esp_timer_get_time() >= until) return false;
        ssize_t sent = send(fd, data, n, 0);
        if (sent <= 0) return false;
        data += (size_t)sent;
        n -= (size_t)sent;
    }
    return true;
}

bool s3_gateway_dns_tcp_poll(int listener, esp_netif_t *gateway_ap,
                             const s3_gateway_dns_upstream_t *upstream)
{
    esp_netif_ip_info_t ip = {0};
    if (listener < 0 || !get_ap(gateway_ap, &ip)) return false;
    struct sockaddr_in peer = {0};
    socklen_t length = sizeof(peer);
    int fd = accept(listener, (struct sockaddr *)&peer, &length);
    if (fd < 0) return false;
    bool ok = false;
    if (length != sizeof(peer) || peer.sin_family != AF_INET ||
        (peer.sin_addr.s_addr & ip.netmask.addr) !=
        (ip.ip.addr & ip.netmask.addr) || !set_timeout(fd))
        goto cleanup;
    uint8_t header[2];
    uint8_t query[S3_GATEWAY_DNS_WIRE_MAX];
    uint8_t answer[S3_GATEWAY_DNS_WIRE_MAX];
    int64_t deadline = esp_timer_get_time() + S3_TCP_DNS_IO_DEADLINE_US;
    if (!read_exact(fd, header, sizeof(header), deadline))
        goto cleanup;
    size_t query_len = ((size_t)header[0] << 8) | header[1];
    if (query_len < 12 || query_len > sizeof(query) ||
        !read_exact(fd, query, query_len, deadline))
        goto cleanup;
    size_t answer_len = s3_gateway_dns_process(upstream, query, query_len,
                                                 answer, sizeof(answer));
    if (answer_len < 12 || answer_len > sizeof(answer)) goto cleanup;
    header[0] = (uint8_t)(answer_len >> 8);
    header[1] = (uint8_t)answer_len;
    deadline = esp_timer_get_time() + S3_TCP_DNS_IO_DEADLINE_US;
    ok = write_exact(fd, header, sizeof(header), deadline) &&
         write_exact(fd, answer, answer_len, deadline);
cleanup:
    shutdown(fd, SHUT_RDWR);
    close(fd);
    return ok;
}
