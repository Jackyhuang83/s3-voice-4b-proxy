/*
 * Standalone P2-3 production C interop probe against real shadowsocks-rust.
 * Test PSKs and addresses are public, loopback-only. Not device firmware.
 */
#include <assert.h>
#include <arpa/inet.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <unistd.h>
#include <time.h>
#include "muse_ss2022.h"
#include "s3_ss2022_link.h"

static const char *GOOD_KEY = "AAECAwQFBgcICQoLDA0ODw=="; /* bytes 00..0F, public fixture */
static const char *BAD_KEY  = "/////////////////////w=="; /* bytes FFx16 */
static const uint8_t PSK[16] = {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15};
static const int ECHO_PORT = 19443;

static void node(s3_ss2022_node_t *n, int port, bool wrong)
{
    assert(port > 0 && port < 65536);
    assert(s3_ss2022_node_store("127.0.0.1", (uint16_t)port,
                               wrong ? BAD_KEY : GOOD_KEY));
    assert(s3_ss2022_node_load(n));
    assert(s3_ss2022_start_clock());
}

static void relay_test(int port, bool wrong)
{
    s3_ss2022_node_t n;
    node(&n, port, wrong);
    int fds[2];
    assert(socketpair(AF_UNIX, SOCK_STREAM, 0, fds) == 0);
    pid_t child = fork();
    assert(child >= 0);
    if (child == 0) {
        close(fds[0]);
        const uint8_t ping[] = {'p','i','n','g'};
        bool ok = s3_ss2022_relay(fds[1], &n, "127.0.0.1", ECHO_PORT,
                                  ping, sizeof(ping), NULL, NULL);
        close(fds[1]);
        s3_ss2022_node_wipe(&n);
        _exit(ok ? 0 : 11);
    }
    close(fds[1]);
    struct timeval timeout = {.tv_sec = 8};
    assert(setsockopt(fds[0], SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) == 0);
    uint8_t response[16] = {0};
    ssize_t count = recv(fds[0], response, sizeof(response), MSG_WAITALL);
    if (wrong) {
        /* A server rejecting the wrong PSK must never produce client plaintext. */
        assert(count <= 0);
    } else {
        assert(count == 4 && memcmp(response, "pong", 4) == 0);
    }
    close(fds[0]);
    int status = 0;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status));
    if (wrong) assert(WEXITSTATUS(status) == 11);
    else assert(WEXITSTATUS(status) == 0);
    s3_ss2022_node_wipe(&n);
    printf("PASS official server %s: %s\n", wrong ? "wrong-PSK" : "TCP",
           wrong ? "blocked; no plaintext/no success" : "authenticated echo/pong");
}

static void dns_test(int port, bool wrong)
{
    s3_ss2022_node_t n;
    node(&n, port, wrong);
    uint8_t packet[512] = {
        0x12,0x34,0x01,0x00,0x00,0x01,0,0,0,0,0,0,
        0x04,'t','e','s','t',0,0,0x01,0,0x01
    };
    int len = 22;
    uint8_t original[sizeof(packet)];
    memcpy(original, packet, sizeof(packet));
    bool ok = s3_ss2022_dns_query(&n, "127.0.0.1", packet, &len, sizeof(packet));
    if (wrong) {
        assert(!ok);
        assert(len == 22);
        assert(memcmp(packet, original, sizeof(packet)) == 0);
        printf("PASS official server wrong-key DNS blocked; no fake success\n");
    } else {
        assert(ok && len == 22);
        assert(packet[0] == 0x12 && packet[1] == 0x34);
        assert(packet[2] == 0x81 && packet[3] == 0x80);
        printf("PASS official server authenticated SS2022 TCP/53 DNS\n");
    }
    s3_ss2022_node_wipe(&n);
}

static void offline_test(int port)
{
    s3_ss2022_node_t n;
    node(&n, port, false);
    int fds[2];
    assert(socketpair(AF_UNIX, SOCK_STREAM, 0, fds) == 0);
    const uint8_t ping[] = {'p','i','n','g'};
    assert(!s3_ss2022_relay(fds[1], &n, "127.0.0.1", ECHO_PORT,
                            ping, sizeof(ping), NULL, NULL));
    close(fds[1]);
    uint8_t data[16];
    assert(recv(fds[0], data, sizeof(data), MSG_DONTWAIT) <= 0);
    close(fds[0]);
    s3_ss2022_node_wipe(&n);
    printf("PASS SS2022 offline: no direct-route fallback\n");
}

static bool write_all(int fd, const uint8_t *data, size_t n)
{
    while (n) {
        ssize_t wrote = send(fd, data, n, 0);
        if (wrote < 0 && errno == EINTR) continue;
        if (wrote <= 0) return false;
        data += wrote;
        n -= (size_t)wrote;
    }
    return true;
}

static int dial_local(int port)
{
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    assert(fd >= 0);
    struct timeval tv = {.tv_sec = 3};
    assert(setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv)) == 0);
    assert(setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv)) == 0);
    struct sockaddr_in addr = {.sin_family = AF_INET, .sin_port = htons((uint16_t)port)};
    assert(inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr) == 1);
    assert(connect(fd, (struct sockaddr *)&addr, sizeof(addr)) == 0);
    return fd;
}

/* Create a fresh wire request with a FIXED public salt, intentionally twice.
   This tests the independent server replay cache; not used in production. */
static void replay_or_stale(int port, bool stale)
{
    uint8_t salt[16];
    for (size_t i = 0; i < sizeof(salt); ++i) salt[i] = (uint8_t)(i + (stale ? 0x70 : 0x50));
    uint8_t header[256], body[256];
    const uint8_t padding[] = {0x6d,0x43,0x22};
    const uint8_t ping[] = {'p','i','n','g'};
    size_t hlen = 0, blen = 0;
    ss2022_cipher_t cipher = {0};
    assert(ss2022_cipher_init(&cipher, PSK, salt));
    uint64_t now = (uint64_t)time(NULL);
    assert(ss2022_request(&cipher, salt, "127.0.0.1", ECHO_PORT,
                          stale ? now - 120 : now,
                          padding, sizeof(padding),
                          header, sizeof(header), &hlen));
    assert(ss2022_payload(&cipher, ping, sizeof(ping), body, sizeof(body), &blen));
    ss2022_cipher_free(&cipher);

    int attempts = stale ? 1 : 2;
    for (int attempt = 0; attempt < attempts; ++attempt) {
        int fd = dial_local(port);
        assert(write_all(fd, header, hlen));
        /* The server might immediately reject after the header, in which case
           a failed send is still a rejected stale/replayed connection. */
        bool submitted = write_all(fd, body, blen);
        uint8_t response[128];
        ssize_t n = recv(fd, response, sizeof(response), 0);
        if (!stale && attempt == 0) {
            assert(submitted && n > 0);
            printf("PASS official server accepted first fixed-salt SS2022 handshake\n");
        } else {
            assert(n <= 0); /* no server data for stale/replayed request */
            printf("PASS official server rejected %s request\n",
                   stale ? "stale timestamp" : "repeated salt");
        }
        close(fd);
    }
}

int main(int argc, char **argv)
{
    if (argc != 3) return 2;
    int port = atoi(argv[2]);
    if (port < 1 || port > 65535) return 2;
    if (!strcmp(argv[1],"tcp")) relay_test(port, false);
    else if (!strcmp(argv[1],"badkey")) relay_test(port, true);
    else if (!strcmp(argv[1],"dns")) dns_test(port, false);
    else if (!strcmp(argv[1],"bad-dns")) dns_test(port, true);
    else if (!strcmp(argv[1],"offline")) offline_test(port);
    else if (!strcmp(argv[1],"replay")) replay_or_stale(port, false);
    else if (!strcmp(argv[1],"stale")) replay_or_stale(port, true);
    else return 2;
    return 0;
}
