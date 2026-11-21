/* SPDX-License-Identifier: Apache-2.0
 * Minimal VLESS TCP framing, carried only over validated ESP-TLS.
 * Cryptography, root CAs, TLS 1.2/1.3, hostname/SNI validation: official IDF.
 * No Reality, no TLS bypass and no internet UDP in this component.
 */
#include "s3_vless_tls.h"

#include <errno.h>
#include <string.h>
#include <time.h>
#include <sys/select.h>
#include "esp_tls.h"
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "lwip/sockets.h"

#define S3_VLESS_TLS_IO 2048
#define S3_VLESS_TLS_MAX_CONCURRENT 2
#define S3_VLESS_TLS_READ_TIMEOUT_S 5
#define S3_VLESS_TLS_IDLE_S 180

typedef struct {
    esp_tls_t *tls;
    uint8_t *io;
    int socket_fd;
    bool slot;
    bool response_header_valid;
} s3_vless_tls_conn_t;

static portMUX_TYPE s_guard = portMUX_INITIALIZER_UNLOCKED;
static unsigned s_concurrent;

static bool valid_dns_host(const char *s)
{
    if (!s) return false;
    size_t n = strnlen(s, 255);
    if (n < 4 || n > 253 || !strchr(s, '.')) return false;
    /* Require a DNS identity; IP literals must use an explicit SAN/SNI
       configuration in P3-2 and may not skip verification. */
    unsigned digits_and_dots = 1;
    for (size_t i = 0; i < n; ++i) {
        char c = s[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '-' || c == '.'))
            return false;
        if (!(c >= '0' && c <= '9') && c != '.') digits_and_dots = 0;
        if (c == '.' && (i == 0 || i == n - 1 || s[i - 1] == '.')) return false;
    }
    return !digits_and_dots;
}

static bool reserve_slot(void)
{
    bool ok;
    portENTER_CRITICAL(&s_guard);
    ok = s_concurrent < S3_VLESS_TLS_MAX_CONCURRENT;
    if (ok) s_concurrent++;
    portEXIT_CRITICAL(&s_guard);
    return ok;
}

static void release_slot(void)
{
    portENTER_CRITICAL(&s_guard);
    if (s_concurrent) s_concurrent--;
    portEXIT_CRITICAL(&s_guard);
}

static void close_conn(s3_vless_tls_conn_t *s)
{
    if (s->tls) esp_tls_conn_destroy(s->tls);
    if (s->io) {
        memset(s->io, 0, S3_VLESS_TLS_IO);
        free(s->io);
    }
    if (s->slot) release_slot();
    memset(s, 0, sizeof(*s));
}

static bool open_conn(s3_vless_tls_conn_t *s, const char *host, uint16_t port)
{
    memset(s, 0, sizeof(*s));
    s->socket_fd = -1;
    if (!valid_dns_host(host) || !port || !reserve_slot()) return false;
    s->slot = true;
    s->io = heap_caps_malloc(S3_VLESS_TLS_IO, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!s->io) return false;
    s->tls = esp_tls_init();
    if (!s->tls) return false;
    const esp_tls_cfg_t cfg = {
        .crt_bundle_attach = esp_crt_bundle_attach,
        .common_name = host,             /* SNI and certificate identity. */
        .skip_common_name = false,      /* Never skip CN/SAN verification. */
        .timeout_ms = 10000,
    };
    if (esp_tls_conn_new_sync(host, (int)strlen(host), port, &cfg, s->tls) != 1)
        return false;
    if (esp_tls_get_conn_sockfd(s->tls, &s->socket_fd) != ESP_OK ||
        s->socket_fd < 0) return false;
    struct timeval timeout = {.tv_sec = S3_VLESS_TLS_READ_TIMEOUT_S};
    if (setsockopt(s->socket_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout,
                   sizeof(timeout)) != 0 ||
        setsockopt(s->socket_fd, SOL_SOCKET, SO_SNDTIMEO, &timeout,
                   sizeof(timeout)) != 0) return false;
    return true;
}

static bool tls_send_all(esp_tls_t *tls, const uint8_t *p, size_t len)
{
    unsigned retry = 0;
    while (len) {
        ssize_t n = esp_tls_conn_write(tls, p, len);
        if (n > 0) {
            p += n;
            len -= (size_t)n;
            retry = 0;
            continue;
        }
        if (++retry > 8 || (n < 0 && n != ESP_TLS_ERR_SSL_WANT_READ &&
                              n != ESP_TLS_ERR_SSL_WANT_WRITE)) return false;
    }
    return true;
}

static bool tls_read_exact(esp_tls_t *tls, uint8_t *out, size_t len)
{
    unsigned retry = 0;
    while (len) {
        ssize_t n = esp_tls_conn_read(tls, out, len);
        if (n > 0) {
            out += n;
            len -= (size_t)n;
            retry = 0;
            continue;
        }
        if (!n || ++retry > 8 ||
            (n != ESP_TLS_ERR_SSL_WANT_READ && n != ESP_TLS_ERR_SSL_WANT_WRITE))
            return false;
    }
    return true;
}

static bool socket_send_all(int fd, const uint8_t *p, size_t len)
{
    while (len) {
        ssize_t n = send(fd, p, len, 0);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return false;
        p += n;
        len -= (size_t)n;
    }
    return true;
}

static bool send_vless_request(s3_vless_tls_conn_t *s, const uint8_t uuid[16],
                               const char *dst, uint16_t port)
{
    if (!uuid || !dst || !port) return false;
    size_t n = strnlen(dst, 254);
    if (!n || n > 253) return false;
    /* Reuse the pinned upstream layout: ver 0 | UUID | optlen 0 | TCP 1 |
       port big endian | addr domain 2 | len 1 | domain. */
    uint8_t header[24 + 253] = {0};
    size_t pos = 0;
    header[pos++] = 0;
    memcpy(header + pos, uuid, 16);
    pos += 16;
    header[pos++] = 0;
    header[pos++] = 1;
    header[pos++] = (uint8_t)(port >> 8);
    header[pos++] = (uint8_t)port;
    header[pos++] = 2;
    header[pos++] = (uint8_t)n;
    memcpy(header + pos, dst, n);
    pos += n;
    return tls_send_all(s->tls, header, pos);
}

static bool read_vless_response_header(esp_tls_t *tls)
{
    uint8_t header[2];
    if (!tls_read_exact(tls, header, sizeof(header)) || header[0] != 0)
        return false;
    if (header[1]) {
        uint8_t addon[255];
        if (!tls_read_exact(tls, addon, header[1])) return false;
    }
    return true;
}

bool s3_vless_tls_relay(int client_fd, const char *server_hostname,
                        uint16_t server_port, const uint8_t uuid[16],
                        const char *destination, uint16_t destination_port,
                        const uint8_t *initial, size_t initial_length,
                        s3_vless_tls_bandwidth_cb upload,
                        s3_vless_tls_bandwidth_cb download)
{
    if (client_fd < 0 || !uuid || (!initial && initial_length) ||
        initial_length > S3_VLESS_TLS_IO) return false;
    s3_vless_tls_conn_t s;
    if (!open_conn(&s, server_hostname, server_port)) {
        close_conn(&s);
        return false;
    }
    if (!send_vless_request(&s, uuid, destination, destination_port) ||
        (initial_length && !tls_send_all(s.tls, initial, initial_length))) {
        close_conn(&s);
        return false;
    }
    if (initial_length && upload) upload(initial_length);
    struct timeval timeout = {.tv_sec = S3_VLESS_TLS_READ_TIMEOUT_S};
    if (setsockopt(client_fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) != 0) {
        close_conn(&s);
        return false;
    }

    bool ok = false;
    unsigned idle = 0;
    for (;;) {
        fd_set rfds;
        FD_ZERO(&rfds);
        FD_SET(client_fd, &rfds);
        FD_SET(s.socket_fd, &rfds);
        int maxfd = client_fd > s.socket_fd ? client_fd : s.socket_fd;
        struct timeval tv = {.tv_sec = 1};
        bool pending = esp_tls_get_bytes_avail(s.tls) > 0;
        int rc = pending ? 1 : select(maxfd + 1, &rfds, NULL, NULL, &tv);
        if (rc < 0 && errno == EINTR) continue;
        if (rc < 0) break;
        if (rc == 0) {
            if (++idle > S3_VLESS_TLS_IDLE_S) break;
            continue;
        }
        idle = 0;
        if (pending || FD_ISSET(s.socket_fd, &rfds)) {
            if (!s.response_header_valid) {
                if (!read_vless_response_header(s.tls)) break;
                s.response_header_valid = true;
            }
            ssize_t n = esp_tls_conn_read(s.tls, s.io, S3_VLESS_TLS_IO);
            if (n > 0) {
                if (!socket_send_all(client_fd, s.io, (size_t)n)) break;
                if (download) download((size_t)n);
            } else if (n == 0) {
                ok = s.response_header_valid;
                break;
            } else if (n != ESP_TLS_ERR_SSL_WANT_READ &&
                       n != ESP_TLS_ERR_SSL_WANT_WRITE) break;
        }
        if (!pending && FD_ISSET(client_fd, &rfds)) {
            ssize_t n = recv(client_fd, s.io, S3_VLESS_TLS_IO, 0);
            if (n == 0) {
                ok = s.response_header_valid;
                break;
            }
            if (n < 0 || !tls_send_all(s.tls, s.io, (size_t)n)) break;
            if (upload) upload((size_t)n);
        }
    }
    close_conn(&s);
    return ok;
}

bool s3_vless_tls_dns_query(const char *server_hostname, uint16_t server_port,
                            const uint8_t uuid[16], const char *resolver,
                            uint8_t *packet, int *length, size_t capacity)
{
    if (!uuid || !resolver || !packet || !length ||
        *length < 12 || *length > 512 || capacity < 512) return false;
    s3_vless_tls_conn_t s;
    if (!open_conn(&s, server_hostname, server_port)) {
        close_conn(&s);
        return false;
    }
    uint8_t request[514];
    request[0] = (uint8_t)(*length >> 8);
    request[1] = (uint8_t)(*length);
    memcpy(request + 2, packet, *length);
    bool ok = send_vless_request(&s, uuid, resolver, 53) &&
              tls_send_all(s.tls, request, (size_t)*length + 2) &&
              read_vless_response_header(s.tls);
    memset(request, 0, sizeof(request));
    if (!ok) {
        close_conn(&s);
        return false;
    }
    uint8_t lenbuf[2];
    ok = tls_read_exact(s.tls, lenbuf, 2);
    size_t reply_len = ((size_t)lenbuf[0] << 8) | lenbuf[1];
    uint8_t response[512];
    if (ok && reply_len >= 12 && reply_len <= sizeof(response) &&
        tls_read_exact(s.tls, response, reply_len)) {
        /* Preserve caller bytes on all failure paths; reply is authenticated
           by the TLS certificate and encrypted transport. */
        memcpy(packet, response, reply_len);
        *length = (int)reply_len;
        close_conn(&s);
        return true;
    }
    close_conn(&s);
    return false;
}
