/* SPDX-License-Identifier: Apache-2.0
 * Added by S3-Voice: bounded, fail-closed ESP32-S3 SS2022 TCP transport.
 * Production AEAD/KDF code in muse_ss2022.c is unchanged from pinned upstream.
 */
#include "s3_ss2022_link.h"
#include "muse_ss2022.h"

#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <stdio.h>
#include <netdb.h>
#include <unistd.h>
#include <sys/select.h>
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_netif_sntp.h"
#include "nvs.h"
#include "mbedtls/base64.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "freertos/FreeRTOS.h"

#define S3_SS2022_MAGIC UINT32_C(0x53333232)
#define S3_SS2022_NAMESPACE "s3ss2022"
#define S3_SS2022_KEY "node_v2"
#define S3_SS2022_LEGACY_KEY "node"
#define S3_SS2022_IO_SIZE 2048
#define S3_SS2022_WIRE_SIZE (S3_SS2022_IO_SIZE + 1200)
#define S3_SS2022_MAX_RELAY 2
#define S3_SS2022_MAX_DNS 1

typedef struct {
    int fd;
    ss2022_cipher_t tx;
    ss2022_rx_t *rx;
    uint8_t *io;
    uint8_t *wire;
    bool rx_ready;
    bool tx_ready;
    bool slot;
    bool dns;
} s3_ss2022_session_t;

static const char *TAG = "s3_ss2022";
static portMUX_TYPE s_guard = portMUX_INITIALIZER_UNLOCKED;
static unsigned s_relays;
static unsigned s_dns;
static bool s_sntp_started;
static bool s_sntp_synced;

static void wipe(void *ptr, size_t n)
{
    volatile uint8_t *p = ptr;
    while (n--) *p++ = 0;
}

void s3_ss2022_node_wipe(s3_ss2022_node_t *node)
{
    if (node) wipe(node, sizeof(*node));
}

typedef struct {
    uint32_t magic;
    char server_ipv4[16];
    uint16_t server_port;
    uint8_t psk[16];
} s3_ss2022_node_v1_t;

/* Verify the server endpoint before DNS and before saving secrets. Client
   destinations are never passed to getaddrinfo() for the proxy transport. */
static bool valid_node_host(const char *host)
{
    if (!host) return false;
    size_t n = strnlen(host, 254);
    if (!n || n > 253) return false;
    struct in6_addr v6;
    struct in_addr v4;
    if (inet_pton(AF_INET6, host, &v6) == 1 ||
        inet_pton(AF_INET, host, &v4) == 1) return true;
    if (n < 4 || !strchr(host, '.')) return false;
    for (size_t i = 0; i < n; ++i) {
        char c = host[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '-' || c == '.')) return false;
        if (c == '.' && (i == 0 || i == n - 1 || host[i - 1] == '.')) return false;
    }
    return true;
}

bool s3_ss2022_node_valid(const s3_ss2022_node_t *node)
{
    if (!node || node->magic != S3_SS2022_MAGIC || !node->server_port ||
        !memchr(node->server_host, '\0', sizeof(node->server_host)) ||
        !valid_node_host(node->server_host)) return false;
    uint8_t sum = 0;
    for (size_t i = 0; i < sizeof(node->psk); ++i) sum |= node->psk[i];
    return sum != 0;
}

bool s3_ss2022_node_load(s3_ss2022_node_t *out)
{
    if (!out) return false;
    s3_ss2022_node_wipe(out);
    nvs_handle_t handle;
    if (nvs_open(S3_SS2022_NAMESPACE, NVS_READONLY, &handle) != ESP_OK) return false;
    size_t size = sizeof(*out);
    esp_err_t err = nvs_get_blob(handle, S3_SS2022_KEY, out, &size);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        /* Old P2 serial config is a v1 IPv4-only blob. Preserve it as an
           in-memory v2 object without writing or erasing credentials. */
        s3_ss2022_node_v1_t old = {0};
        size = sizeof(old);
        err = nvs_get_blob(handle, S3_SS2022_LEGACY_KEY, &old, &size);
        if (err == ESP_OK && size == sizeof(old) &&
            old.magic == S3_SS2022_MAGIC &&
            memchr(old.server_ipv4, '\0', sizeof(old.server_ipv4))) {
            struct in_addr ipv4;
            if (inet_pton(AF_INET, old.server_ipv4, &ipv4) == 1) {
                out->magic = old.magic;
                out->server_port = old.server_port;
                memcpy(out->server_host, old.server_ipv4,
                       strnlen(old.server_ipv4, sizeof(old.server_ipv4)) + 1);
                memcpy(out->psk, old.psk, sizeof(old.psk));
                size = sizeof(*out);
            }
        }
        wipe(&old, sizeof(old));
    }
    nvs_close(handle);
    if (err != ESP_OK || size != sizeof(*out) || !s3_ss2022_node_valid(out)) {
        s3_ss2022_node_wipe(out);
        return false;
    }
    return true;
}

bool s3_ss2022_node_store(const char *host, uint16_t port, const char *key_b64)
{
    if (!host || !key_b64 || !port || !valid_node_host(host) ||
        strlen(key_b64) != 24) return false;
    s3_ss2022_node_t node = {.magic = S3_SS2022_MAGIC, .server_port = port};
    memcpy(node.server_host, host, strlen(host) + 1);
    size_t n = 0;
    bool valid = mbedtls_base64_decode(node.psk, sizeof(node.psk), &n,
                                       (const unsigned char *)key_b64, strlen(key_b64)) == 0 &&
                 n == sizeof(node.psk) && s3_ss2022_node_valid(&node);
    if (!valid) {
        s3_ss2022_node_wipe(&node);
        return false;
    }
    nvs_handle_t handle;
    bool ok = false;
    if (nvs_open(S3_SS2022_NAMESPACE, NVS_READWRITE, &handle) == ESP_OK) {
        esp_err_t w = nvs_set_blob(handle, S3_SS2022_KEY, &node, sizeof(node));
        esp_err_t old = ESP_OK;
        if (w == ESP_OK) old = nvs_erase_key(handle, S3_SS2022_LEGACY_KEY);
        ok = w == ESP_OK &&
             (old == ESP_OK || old == ESP_ERR_NVS_NOT_FOUND) &&
             nvs_commit(handle) == ESP_OK;
        nvs_close(handle);
    }
    s3_ss2022_node_wipe(&node);
    return ok;
}

bool s3_ss2022_node_clear(void)
{
    nvs_handle_t handle;
    if (nvs_open(S3_SS2022_NAMESPACE, NVS_READWRITE, &handle) != ESP_OK) return false;
    esp_err_t modern = nvs_erase_key(handle, S3_SS2022_KEY);
    esp_err_t legacy = nvs_erase_key(handle, S3_SS2022_LEGACY_KEY);
    bool ok = (modern == ESP_OK || modern == ESP_ERR_NVS_NOT_FOUND) &&
              (legacy == ESP_OK || legacy == ESP_ERR_NVS_NOT_FOUND) &&
              nvs_commit(handle) == ESP_OK;
    nvs_close(handle);
    return ok;
}

bool s3_ss2022_start_clock(void)
{
    if (s_sntp_started) return true;
    esp_sntp_config_t config = ESP_NETIF_SNTP_DEFAULT_CONFIG("time.cloudflare.com");
    esp_err_t err = esp_netif_sntp_init(&config);
    s_sntp_started = err == ESP_OK;
    return s_sntp_started;
}

static bool time_ready(uint64_t *now)
{
    if (!s_sntp_started) return false;
    if (!s_sntp_synced) {
        if (esp_netif_sntp_sync_wait(pdMS_TO_TICKS(15000)) != ESP_OK) return false;
        s_sntp_synced = true;
    }
    time_t value = time(NULL);
    /* A fabricated 1970 default is never a valid SIP022 timestamp. */
    if (value < (time_t)1700000000) return false;
    *now = (uint64_t)value;
    return true;
}

static bool reserve_slot(bool dns)
{
    bool ok;
    portENTER_CRITICAL(&s_guard);
    if (dns) {
        ok = s_dns < S3_SS2022_MAX_DNS;
        if (ok) ++s_dns;
    } else {
        ok = s_relays < S3_SS2022_MAX_RELAY;
        if (ok) ++s_relays;
    }
    portEXIT_CRITICAL(&s_guard);
    return ok;
}

static void release_slot(bool dns)
{
    portENTER_CRITICAL(&s_guard);
    if (dns) {
        if (s_dns) --s_dns;
    } else {
        if (s_relays) --s_relays;
    }
    portEXIT_CRITICAL(&s_guard);
}

static bool send_all(int fd, const uint8_t *data, size_t n)
{
    while (n) {
        ssize_t sent = send(fd, data, n, 0);
        if (sent < 0 && errno == EINTR) continue;
        if (sent <= 0) return false;
        data += sent;
        n -= (size_t)sent;
    }
    return true;
}

/* Preserve the proxy-only destination boundary. Resolve ONLY the trusted,
   stored proxy server. Prefer IPv6 (AAAA), then IPv4 (A) if available.
   A failed AAAA MUST NEVER open a direct connection to the client target. */
static int connect_node(const s3_ss2022_node_t *node)
{
    char service[6];
    snprintf(service, sizeof(service), "%u", (unsigned)node->server_port);
    struct addrinfo hints = {.ai_family = AF_UNSPEC,
                             .ai_socktype = SOCK_STREAM,
                             .ai_protocol = IPPROTO_TCP};
    struct addrinfo *addresses = NULL;
    if (getaddrinfo(node->server_host, service, &hints, &addresses) != 0)
        return -1;
    int result = -1;
    for (int preferred = AF_INET6; preferred == AF_INET6 || preferred == AF_INET;
         preferred = preferred == AF_INET6 ? AF_INET : 0) {
        for (const struct addrinfo *addr = addresses; addr; addr = addr->ai_next) {
            if (addr->ai_family != preferred) continue;
            int fd = socket(addr->ai_family, addr->ai_socktype, addr->ai_protocol);
            if (fd < 0) continue;
            int flags = fcntl(fd, F_GETFL, 0);
            if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) != 0) {
                close(fd);
                continue;
            }
            int ret = connect(fd, addr->ai_addr, addr->ai_addrlen);
            if (ret != 0 && errno != EINPROGRESS) {
                close(fd);
                continue;
            }
            if (ret != 0) {
                fd_set writable;
                FD_ZERO(&writable);
                FD_SET(fd, &writable);
                struct timeval tv = {.tv_sec = 8};
                ret = select(fd + 1, NULL, &writable, NULL, &tv);
                int error = 0;
                socklen_t len = sizeof(error);
                if (ret <= 0 || getsockopt(fd, SOL_SOCKET, SO_ERROR,
                                           &error, &len) != 0 || error) {
                    close(fd);
                    continue;
                }
            }
            struct timeval tv = {.tv_sec = 5};
            if (fcntl(fd, F_SETFL, flags) == 0 &&
                setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv)) == 0 &&
                setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv)) == 0) {
                result = fd;
                break;
            }
            close(fd);
        }
        if (result >= 0) break;
    }
    freeaddrinfo(addresses);
    return result;
}

static void session_close(s3_ss2022_session_t *s)
{
    if (s->fd >= 0) close(s->fd);
    if (s->tx_ready) ss2022_cipher_free(&s->tx);
    if (s->rx_ready) ss2022_rx_free(s->rx);
    if (s->rx) {
        wipe(s->rx, sizeof(*s->rx));
        free(s->rx);
    }
    if (s->io) {
        wipe(s->io, S3_SS2022_IO_SIZE);
        free(s->io);
    }
    if (s->wire) {
        wipe(s->wire, S3_SS2022_WIRE_SIZE);
        free(s->wire);
    }
    if (s->slot) release_slot(s->dns);
    wipe(s, sizeof(*s));
}

static bool session_open(s3_ss2022_session_t *s, bool dns,
                         const s3_ss2022_node_t *node,
                         const char *destination, uint16_t port)
{
    memset(s, 0, sizeof(*s));
    s->fd = -1;
    s->dns = dns;
    if (!s3_ss2022_node_valid(node) || !destination || !destination[0] ||
        strlen(destination) > 253 || !port || !reserve_slot(dns))
        return false;
    s->slot = true;
    uint64_t now;
    if (!time_ready(&now)) return false;
    s->rx = heap_caps_malloc(sizeof(*s->rx), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    s->io = heap_caps_malloc(S3_SS2022_IO_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    s->wire = heap_caps_malloc(S3_SS2022_WIRE_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!s->rx || !s->io || !s->wire) return false;
    uint8_t salt[16];
    uint8_t padding[32];
    esp_fill_random(salt, sizeof(salt));
    esp_fill_random(padding, sizeof(padding));
    ss2022_rx_init(s->rx, node->psk, salt);
    s->rx_ready = true;
    if (!ss2022_cipher_init(&s->tx, node->psk, salt)) {
        wipe(salt, sizeof(salt));
        wipe(padding, sizeof(padding));
        return false;
    }
    s->tx_ready = true;
    size_t wire_len = 0;
    size_t pad_len = 1 + padding[0] % sizeof(padding);
    bool ok = ss2022_request(&s->tx, salt, destination, port, now, padding,
                             pad_len, s->wire, S3_SS2022_WIRE_SIZE, &wire_len);
    wipe(salt, sizeof(salt));
    wipe(padding, sizeof(padding));
    if (!ok) return false;
    s->fd = connect_node(node);
    if (s->fd < 0) return false;
    return send_all(s->fd, s->wire, wire_len);
}

static bool session_write(s3_ss2022_session_t *s, const uint8_t *p, size_t n)
{
    size_t length = 0;
    if (!n || n > S3_SS2022_IO_SIZE) return false;
    return ss2022_payload(&s->tx, p, n, s->wire, S3_SS2022_WIRE_SIZE, &length) &&
           send_all(s->fd, s->wire, length);
}

typedef struct {
    int client;
    s3_ss2022_bandwidth_cb downloaded;
} s3_relay_output_t;

static bool relay_emit(void *arg, const uint8_t *p, size_t n)
{
    s3_relay_output_t *output = arg;
    if (!send_all(output->client, p, n)) return false;
    if (output->downloaded) output->downloaded(n);
    return true;
}

bool s3_ss2022_relay(int client, const s3_ss2022_node_t *node,
                     const char *destination, uint16_t port,
                     const uint8_t *initial, size_t initial_length,
                     s3_ss2022_bandwidth_cb upload, s3_ss2022_bandwidth_cb download)
{
    if (client < 0 || (!initial && initial_length) || initial_length > S3_SS2022_IO_SIZE)
        return false;
    s3_ss2022_session_t s;
    if (!session_open(&s, false, node, destination, port)) {
        session_close(&s);
        return false;
    }
    if (initial_length && !session_write(&s, initial, initial_length)) {
        session_close(&s);
        return false;
    }
    if (upload && initial_length) upload(initial_length);
    struct timeval timeout = {.tv_sec = 5};
    setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    s3_relay_output_t output = {.client = client, .downloaded = download};
    bool ok = false;
    int64_t idle = 0;
    for (;;) {
        fd_set readfds;
        FD_ZERO(&readfds);
        FD_SET(client, &readfds);
        FD_SET(s.fd, &readfds);
        struct timeval tv = {.tv_sec = 1};
        int maxfd = client > s.fd ? client : s.fd;
        int rc = select(maxfd + 1, &readfds, NULL, NULL, &tv);
        if (rc < 0 && errno == EINTR) continue;
        if (rc < 0) break;
        if (!rc) {
            if (++idle > 180) break;
            continue;
        }
        idle = 0;
        if (FD_ISSET(client, &readfds)) {
            ssize_t n = recv(client, s.io, S3_SS2022_IO_SIZE, 0);
            if (n == 0) {
                /* Remote EOF (or local half-close) before any authenticated
                   server response is NOT a successful SS2022 connection. */
                ok = s.rx->phase == 2 && !s.rx->failed;
                break;
            }
            if (n < 0 || !session_write(&s, s.io, (size_t)n)) break;
            if (upload) upload((size_t)n);
        }
        if (FD_ISSET(s.fd, &readfds)) {
            ssize_t n = recv(s.fd, s.io, S3_SS2022_IO_SIZE, 0);
            if (n == 0) {
                /* Remote EOF (or local half-close) before any authenticated
                   server response is NOT a successful SS2022 connection. */
                ok = s.rx->phase == 2 && !s.rx->failed;
                break;
            }
            if (n < 0 || !ss2022_feed(s.rx, s.io, (size_t)n, (uint64_t)time(NULL),
                                      relay_emit, &output)) break;
        }
    }
    session_close(&s);
    return ok;
}

typedef struct {
    uint8_t response[514]; /* 2-byte TCP length + at most 512-byte DNS response */
    size_t have;
    bool invalid;
} s3_dns_output_t;

static bool dns_emit(void *arg, const uint8_t *p, size_t n)
{
    s3_dns_output_t *out = arg;
    if (out->invalid || n > sizeof(out->response) - out->have) {
        out->invalid = true;
        return false;
    }
    memcpy(out->response + out->have, p, n);
    out->have += n;
    if (out->have >= 2) {
        size_t len = ((size_t)out->response[0] << 8) | out->response[1];
        if (len < 12 || len > 512 || out->have > len + 2) {
            out->invalid = true;
            return false;
        }
    }
    return true;
}

bool s3_ss2022_dns_query(const s3_ss2022_node_t *node, const char *resolver,
                          uint8_t *packet, int *length, size_t capacity)
{
    if (!node || !resolver || !packet || !length || *length < 12 ||
        *length > 512 || capacity < 512) return false;
    s3_ss2022_session_t s;
    if (!session_open(&s, true, node, resolver, 53)) {
        session_close(&s);
        return false;
    }
    uint8_t request[514];
    request[0] = (uint8_t)(*length >> 8);
    request[1] = (uint8_t)(*length);
    memcpy(request + 2, packet, *length);
    bool ok = session_write(&s, request, *length + 2);
    wipe(request, sizeof(request));
    s3_dns_output_t out = {0};
    /* TCP can split a 59-byte authenticated header into arbitrarily many reads.
       Bound by BOTH a wall-clock deadline and a fragment count, not 5 recv calls. */
    time_t deadline = time(NULL) + 15;
    for (int fragments = 0; ok && fragments < 256 && time(NULL) <= deadline; ++fragments) {
        ssize_t n = recv(s.fd, s.io, S3_SS2022_IO_SIZE, 0);
        if (n <= 0 || !ss2022_feed(s.rx, s.io, (size_t)n, (uint64_t)time(NULL),
                                   dns_emit, &out)) {
            ok = false;
            break;
        }
        if (out.have >= 2) {
            size_t expected = ((size_t)out.response[0] << 8) | out.response[1];
            if (expected >= 12 && out.have == expected + 2) {
                memcpy(packet, out.response + 2, expected);
                *length = (int)expected;
                session_close(&s);
                return true;
            }
        }
    }
    session_close(&s);
    return false;
}
