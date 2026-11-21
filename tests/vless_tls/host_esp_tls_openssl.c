/* POSIX CI-only adapter for official ESP-TLS API calls.
 * Uses REAL OpenSSL certificate chain, SAN/hostname verification and SNI.
 * It is not compiled into ESP32 firmware. The firmware uses esp-tls directly.
 */
#include "esp_tls.h"
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <openssl/ssl.h>
#include <openssl/x509v3.h>

struct esp_tls {
    SSL_CTX *context;
    SSL *ssl;
    int fd;
};

esp_tls_t *esp_tls_init(void)
{
    esp_tls_t *s = calloc(1, sizeof(*s));
    if (s) s->fd = -1;
    return s;
}

int esp_tls_conn_new_sync(const char *host, int hostlen, int port,
                          const esp_tls_cfg_t *cfg, esp_tls_t *s)
{
    const char *ca = getenv("S3_VLESS_TEST_CA");
    const char *connect_ip = getenv("S3_VLESS_TEST_CONNECT_IP");
    if (!s || !cfg || !host || hostlen <= 0 || hostlen != (int)strlen(host) ||
        !cfg->crt_bundle_attach || cfg->skip_common_name ||
        !cfg->common_name || !ca || !*ca || !connect_ip || !*connect_ip ||
        port < 1 || port > 65535) return -1;
    s->context = SSL_CTX_new(TLS_client_method());
    if (!s->context) return -1;
    SSL_CTX_set_verify(s->context, SSL_VERIFY_PEER, NULL);
    if (SSL_CTX_load_verify_locations(s->context, ca, NULL) != 1) return -1;
    s->fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s->fd < 0) return -1;
    struct timeval tv = {.tv_sec = cfg->timeout_ms > 0 ? cfg->timeout_ms / 1000 + 1 : 10};
    if (setsockopt(s->fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv)) != 0 ||
        setsockopt(s->fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv)) != 0) return -1;
    struct sockaddr_in addr = {.sin_family = AF_INET, .sin_port = htons((uint16_t)port)};
    if (inet_pton(AF_INET, connect_ip, &addr.sin_addr) != 1 ||
        connect(s->fd, (const struct sockaddr *)&addr, sizeof(addr)) != 0) return -1;
    s->ssl = SSL_new(s->context);
    if (!s->ssl || SSL_set_fd(s->ssl, s->fd) != 1 ||
        SSL_set_tlsext_host_name(s->ssl, cfg->common_name) != 1 ||
        SSL_set1_host(s->ssl, cfg->common_name) != 1 ||
        SSL_connect(s->ssl) != 1 ||
        SSL_get_verify_result(s->ssl) != X509_V_OK) return -1;
    return 1;
}

ssize_t esp_tls_conn_read(esp_tls_t *s, void *data, size_t size)
{
    if (!s || !s->ssl || !data || !size) return -1;
    int n = SSL_read(s->ssl, data, size > INT_MAX ? INT_MAX : (int)size);
    if (n > 0) return n;
    int e = SSL_get_error(s->ssl, n);
    if (e == SSL_ERROR_ZERO_RETURN) return 0;
    if (e == SSL_ERROR_WANT_READ) return ESP_TLS_ERR_SSL_WANT_READ;
    if (e == SSL_ERROR_WANT_WRITE) return ESP_TLS_ERR_SSL_WANT_WRITE;
    return -1;
}

ssize_t esp_tls_conn_write(esp_tls_t *s, const void *data, size_t size)
{
    if (!s || !s->ssl || !data || !size) return -1;
    int n = SSL_write(s->ssl, data, size > INT_MAX ? INT_MAX : (int)size);
    if (n > 0) return n;
    int e = SSL_get_error(s->ssl, n);
    if (e == SSL_ERROR_WANT_READ) return ESP_TLS_ERR_SSL_WANT_READ;
    if (e == SSL_ERROR_WANT_WRITE) return ESP_TLS_ERR_SSL_WANT_WRITE;
    return -1;
}

int esp_tls_conn_destroy(esp_tls_t *s)
{
    if (!s) return -1;
    if (s->ssl) SSL_free(s->ssl);
    if (s->context) SSL_CTX_free(s->context);
    if (s->fd >= 0) close(s->fd);
    free(s);
    return 0;
}

esp_err_t esp_tls_get_conn_sockfd(esp_tls_t *s, int *out)
{
    if (!s || !out || s->fd < 0) return -1;
    *out = s->fd;
    return ESP_OK;
}
ssize_t esp_tls_get_bytes_avail(esp_tls_t *s)
{
    return s && s->ssl ? SSL_pending(s->ssl) : -1;
}
