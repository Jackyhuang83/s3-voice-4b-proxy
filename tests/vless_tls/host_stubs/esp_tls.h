#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <sys/types.h>
#define ESP_OK 0
#define ESP_TLS_ERR_SSL_WANT_READ (-0x6900)
#define ESP_TLS_ERR_SSL_WANT_WRITE (-0x6880)
typedef int esp_err_t;
typedef struct esp_tls esp_tls_t;
typedef struct {
    int (*crt_bundle_attach)(void *);
    const char *common_name;
    bool skip_common_name;
    int timeout_ms;
} esp_tls_cfg_t;
esp_tls_t *esp_tls_init(void);
int esp_tls_conn_new_sync(const char *, int, int, const esp_tls_cfg_t *, esp_tls_t *);
ssize_t esp_tls_conn_write(esp_tls_t *, const void *, size_t);
ssize_t esp_tls_conn_read(esp_tls_t *, void *, size_t);
int esp_tls_conn_destroy(esp_tls_t *);
esp_err_t esp_tls_get_conn_sockfd(esp_tls_t *, int *);
ssize_t esp_tls_get_bytes_avail(esp_tls_t *);
