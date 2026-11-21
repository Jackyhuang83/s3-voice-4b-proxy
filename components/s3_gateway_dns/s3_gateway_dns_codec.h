/* SPDX-License-Identifier: MIT
 * Bounded DNS safeguards for AP clients; no network sockets or direct DNS.
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define S3_GATEWAY_DNS_WIRE_MAX 512u
bool s3_gateway_dns_question(const uint8_t *msg, size_t length,
                             bool expect_reply, size_t *question_end);
size_t s3_gateway_dns_servfail(const uint8_t *query, size_t query_length,
                               uint8_t *reply, size_t reply_capacity);
bool s3_gateway_dns_matches(const uint8_t *query, size_t query_length,
                             const uint8_t *reply, size_t reply_length);
