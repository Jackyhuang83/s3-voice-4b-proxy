/* SPDX-License-Identifier: MIT */
#include "s3_gateway_dns_codec.h"
#include <string.h>

static bool question_end_at(const uint8_t *msg, size_t n, size_t *end) {
    if (n < 12 || n > S3_GATEWAY_DNS_WIRE_MAX) return false;
    size_t pos = 12;
    size_t name_wire = 0;
    for (unsigned labels = 0; labels < 128; ++labels) {
        if (pos >= n) return false;
        uint8_t len = msg[pos++];
        if ((len & 0xc0u) != 0 || len > 63) return false;
        name_wire += (size_t)len + 1;
        if (name_wire > 255u || pos + len > n) return false;
        pos += len;
        if (len == 0) {
            if (pos + 4 > n) return false;
            *end = pos + 4;
            return true;
        }
    }
    return false;
}

bool s3_gateway_dns_question(const uint8_t *msg, size_t length,
                             bool expect_reply, size_t *question_end) {
    if (!msg || !question_end || length < 12 || length > S3_GATEWAY_DNS_WIRE_MAX)
        return false;
    if (((msg[2] & 0x80u) != 0) != expect_reply) return false;
    if (msg[2] & 0x78u) return false;
    if (msg[4] != 0 || msg[5] != 1) return false;
    if (!expect_reply && (msg[6] || msg[7] || msg[8] || msg[9])) return false;
    return question_end_at(msg, length, question_end);
}

size_t s3_gateway_dns_servfail(const uint8_t *query, size_t query_length,
                               uint8_t *reply, size_t reply_capacity) {
    size_t end = 0;
    if (!reply || !s3_gateway_dns_question(query, query_length, false, &end) ||
        reply_capacity < end || reply_capacity > S3_GATEWAY_DNS_WIRE_MAX)
        return 0;
    memmove(reply, query, end);
    reply[2] = (uint8_t)(0x80u | (query[2] & 0x01u));
    reply[3] = 0x82u; /* RA=1, RCODE=SERVFAIL. */
    memset(reply + 6, 0, 6);
    return end;
}

bool s3_gateway_dns_matches(const uint8_t *query, size_t query_length,
                             const uint8_t *reply, size_t reply_length) {
    size_t query_end = 0, reply_end = 0;
    if (!s3_gateway_dns_question(query, query_length, false, &query_end) ||
        !s3_gateway_dns_question(reply, reply_length, true, &reply_end) ||
        query_end != reply_end || query[0] != reply[0] || query[1] != reply[1])
        return false;
    return memcmp(query + 12, reply + 12, query_end - 12) == 0;
}
