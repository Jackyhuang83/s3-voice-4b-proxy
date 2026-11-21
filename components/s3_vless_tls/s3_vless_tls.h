/* SPDX-License-Identifier: Apache-2.0
 * VLESS TCP over a VERIFIED ESP-TLS transport only.
 * P3-1: use the upstream IPv4 flow table; IPv6-only STA dialing is P3-2.
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef void (*s3_vless_tls_bandwidth_cb)(size_t);

/* The caller owns client_fd and supplies the 16-byte UUID parsed by the
 * existing upstream transport_tcp_uuid_to_bytes(), not a copied parser.
 * The server hostname is the SNI/certificate identity (DNS name).
 */
bool s3_vless_tls_relay(int client_fd, const char *server_hostname,
                        uint16_t server_port, const uint8_t uuid[16],
                        const char *destination, uint16_t destination_port,
                        const uint8_t *initial, size_t initial_length,
                        s3_vless_tls_bandwidth_cb upload,
                        s3_vless_tls_bandwidth_cb download);

/* DNS-over-TCP inside the SAME authenticated VLESS-over-TLS transport.
 * The buffer is only modified on a fully authenticated/validated DNS reply.
 * Never fallback to raw UDP or unencrypted VLESS on failure.
 */
bool s3_vless_tls_dns_query(const char *server_hostname, uint16_t server_port,
                            const uint8_t uuid[16], const char *resolver,
                            uint8_t *packet, int *length, size_t capacity);
