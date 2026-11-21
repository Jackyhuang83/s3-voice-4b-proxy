/* SPDX-License-Identifier: MIT
 * Reuse unchanged SS2022/VLESS TCP transports; no raw target socket.
 */
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdint.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#include "s3_gateway_tcp_server.h"
#include "s3_gateway_policy.h"
#include "s3_vless_tls.h"
#include "transparent_tcp.h"

static bool ap_info(esp_netif_t *ap, esp_netif_ip_info_t *info)
{
    if (!ap || !info) return false;
    const char *key = esp_netif_get_ifkey(ap);
    return key && strcmp(key, "WIFI_AP_DEF") == 0 &&
           esp_netif_get_ip_info(ap, info) == ESP_OK &&
           info->ip.addr != 0 && info->netmask.addr != 0;
}

int s3_gateway_tcp_listen(esp_netif_t *gateway_ap)
{
    esp_netif_ip_info_t info = {0};
    if (!ap_info(gateway_ap, &info)) return -1;
    int fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (fd < 0) return -1;
    struct timeval timeout = {.tv_sec = 1, .tv_usec = 0};
    if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO,
                   &timeout, sizeof(timeout)) != 0) {
        close(fd);
        return -1;
    }
    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(S3_GATEWAY_TCP_RELAY_PORT);
    addr.sin_addr.s_addr = info.ip.addr;
    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) != 0 ||
        listen(fd, 8) != 0) {
        close(fd);
        return -1;
    }
    return fd;
}

bool s3_gateway_tcp_accept_and_relay(int listener, esp_netif_t *gateway_ap,
                                     const s3_gateway_dns_upstream_t *node,
                                     s3_gateway_client_event_t client_event,
                                     void *event_arg)
{
    if (listener < 0 || !s3_gateway_policy_ready(s3_gateway_policy_device()))
        return false;
    esp_netif_ip_info_t ap = {0};
    if (!ap_info(gateway_ap, &ap)) return false;
    struct sockaddr_in peer = {0};
    socklen_t peerlen = sizeof(peer);
    int client = accept(listener, (struct sockaddr *)&peer, &peerlen);
    if (client < 0) return false;
    bool success = false;
    bool have_flow = false;
    bool registered = false;
    if (!client_event || !client_event(client, true, event_arg)) goto done;
    registered = true;
    transparent_tcp_flow_t flow = {0};
    uint32_t client_ip = peer.sin_addr.s_addr;
    uint16_t client_port = ntohs(peer.sin_port);
    if (!node || peerlen != sizeof(peer) || peer.sin_family != AF_INET ||
        (client_ip & ap.netmask.addr) != (ap.ip.addr & ap.netmask.addr) ||
        !s3_gateway_policy_ready(s3_gateway_policy_device()))
        goto done;
    have_flow = transparent_tcp_get(client_ip, client_port, &flow);
    if (!have_flow || !flow.original_port || !flow.original_ip) goto done;
    char destination[254] = {0};
    if (!transparent_tcp_dns_name_for_ip(flow.original_ip, destination,
                                          sizeof(destination))) {
        struct in_addr address = {.s_addr = flow.original_ip};
        if (!inet_ntop(AF_INET, &address, destination, sizeof(destination)))
            goto done;
    }
    if (!s3_gateway_policy_ready(s3_gateway_policy_device())) goto done;
    switch (node->transport) {
    case S3_GATEWAY_DNS_SS2022:
        if (node->ss2022_node && s3_ss2022_node_valid(node->ss2022_node))
            success = s3_ss2022_relay(client, node->ss2022_node,
                                     destination, flow.original_port,
                                     NULL, 0, NULL, NULL);
        break;
    case S3_GATEWAY_DNS_VLESS_TLS:
        if (node->vless_sni && node->vless_port && node->vless_uuid)
            success = s3_vless_tls_relay(client, node->vless_sni,
                                       node->vless_port, node->vless_uuid,
                                       destination, flow.original_port,
                                       NULL, 0, NULL, NULL);
        break;
    default:
        break;
    }
done:
    /* Unregister before close: the supervisor never closes a reused fd. */
    if (registered) (void)client_event(client, false, event_arg);
    shutdown(client, SHUT_RDWR);
    close(client);
    if (have_flow) transparent_tcp_remove(client_ip, client_port);
    return success;
}
