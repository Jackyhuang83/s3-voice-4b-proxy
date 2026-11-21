/* Host-only test probe for unmodified rlog SS2022 production C component.
 * Public constant test key/salts are NOT live proxy credentials. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "muse_ss2022.h"

static const uint8_t k_psk[16] = {
    0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,
    0x08,0x09,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f
};
static const uint8_t k_request_salt[16] = {
    0x10,0x11,0x12,0x13,0x14,0x15,0x16,0x17,
    0x18,0x19,0x1a,0x1b,0x1c,0x1d,0x1e,0x1f
};
static const uint64_t k_now = UINT64_C(1700000000);
static uint8_t received[32768];
static size_t received_len;

static void hex_print(const char *tag, const uint8_t *p, size_t n) {
    printf("%s ", tag);
    for (size_t i = 0; i < n; i++) printf("%02x", p[i]);
    putchar('\n');
}
static int nibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}
static size_t decode(const char *hex, uint8_t *out, size_t cap) {
    size_t n = strlen(hex);
    if (n % 2 || n / 2 > cap) return 0;
    for (size_t i = 0; i < n / 2; i++) {
        int high = nibble(hex[i * 2]), low = nibble(hex[i * 2 + 1]);
        if (high < 0 || low < 0) return 0;
        out[i] = (uint8_t)((high << 4) | low);
    }
    return n / 2;
}
static bool emit(void *arg, const uint8_t *data, size_t n) {
    (void)arg;
    if (received_len + n > sizeof(received)) return false;
    memcpy(received + received_len, data, n);
    received_len += n;
    return true;
}

static void request_test(void) {
    ss2022_cipher_t cipher;
    const uint8_t padding[] = {0,1,2,3,4,5,6,7,8};
    uint8_t output[2048];
    size_t n = 0;
    assert(ss2022_cipher_init(&cipher, k_psk, k_request_salt));
    assert(ss2022_request(&cipher, k_request_salt, "example.org", 443,
                          k_now, padding, sizeof(padding), output, sizeof(output), &n));
    hex_print("REQUEST", output, n);
    static const uint8_t message[] = {'h','e','l','l','o'};
    assert(ss2022_payload(&cipher, message, sizeof(message), output, sizeof(output), &n));
    hex_print("PAYLOAD", output, n);
    ss2022_cipher_free(&cipher);
    assert(cipher.key == 0);
}

static void negative_request_tests(void) {
    ss2022_cipher_t cipher;
    uint8_t output[65569] = {0};
    uint8_t padding[1] = {0x33};
    size_t n = 0;
    assert(ss2022_cipher_init(&cipher, k_psk, k_request_salt));
    assert(!ss2022_request(&cipher, k_request_salt, "", 443,
                           k_now, padding, 1, output, sizeof(output), &n));
    assert(!ss2022_request(&cipher, k_request_salt, "example.org", 0,
                           k_now, padding, 1, output, sizeof(output), &n));
    assert(!ss2022_request(&cipher, k_request_salt, "example.org", 443,
                           k_now, padding, 0, output, sizeof(output), &n));
    assert(!ss2022_request(&cipher, k_request_salt, "example.org", 443,
                           k_now, padding, 1, output, 10, &n));
    assert(!ss2022_payload(&cipher, padding, 0, output, sizeof(output), &n));
    assert(!ss2022_payload(&cipher, padding, 1, output, 10, &n));
    uint8_t *max_payload = malloc(65535);
    assert(max_payload);
    memset(max_payload, 'X', 65535);
    assert(ss2022_payload(&cipher, max_payload, 65535, output, sizeof(output), &n));
    assert(n == 65569);
    free(max_payload);
    ss2022_cipher_free(&cipher);
    printf("PASS request rejection and 65535-byte payload boundary\n");
}

static void response_test(const char *hex, bool valid, size_t fragment_size) {
    uint8_t wire[2048] = {0};
    size_t n = decode(hex, wire, sizeof(wire));
    assert(n > 0 && fragment_size);
    ss2022_rx_t *rx = malloc(sizeof(*rx));
    assert(rx);
    ss2022_rx_init(rx, k_psk, k_request_salt);
    received_len = 0;
    bool accepted = true;
    for (size_t i = 0; i < n; ) {
        size_t take = fragment_size < (n - i) ? fragment_size : n - i;
        if (!ss2022_feed(rx, wire + i, take, k_now, emit, NULL)) {
            accepted = false;
            break;
        }
        i += take;
    }
    if (valid) {
        assert(accepted && !rx->failed);
        hex_print("RESPONSE", received, received_len);
    } else {
        assert(!accepted && rx->failed);
        printf("PASS invalid response rejected\n");
    }
    ss2022_rx_free(rx);
    free(rx);
}
int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "request")) request_test();
    else if (argc == 2 && !strcmp(argv[1], "negative")) negative_request_tests();
    else if (argc == 5 && !strcmp(argv[1], "response")) {
        response_test(argv[2], !strcmp(argv[3], "valid"), (size_t)atoi(argv[4]));
    } else {
        fprintf(stderr, "usage: %s request|negative|response HEX valid|invalid CHUNK\n", argv[0]);
        return 2;
    }
    return 0;
}
