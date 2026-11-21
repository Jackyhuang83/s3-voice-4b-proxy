/* Real production s3_vless_tls.c linked to CI OpenSSL ESP-TLS API shim.
 * Loopback test fixture only. No user's VPS, credentials or 4B device.
 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <signal.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/wait.h>
#include "s3_vless_tls.h"

static const uint8_t UUID[16] = {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15};

static void relay_test(int port, bool must_succeed, const char *host)
{
    int fds[2];
    assert(socketpair(AF_UNIX, SOCK_STREAM, 0, fds) == 0);
    pid_t pid = fork();
    assert(pid >= 0);
    if (pid == 0) {
        close(fds[0]);
        const uint8_t initial[] = {'p','i','n','g'};
        bool ok = s3_vless_tls_relay(fds[1], host, (uint16_t)port, UUID,
                                     "198.51.100.7", 443, initial,
                                     sizeof(initial), NULL, NULL);
        close(fds[1]);
        _exit(ok ? 0 : 9);
    }
    close(fds[1]);
    struct timeval timeout = {.tv_sec = 9};
    assert(setsockopt(fds[0], SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) == 0);
    uint8_t got[8] = {0};
    ssize_t n = recv(fds[0], got, 4, MSG_WAITALL);
    if (must_succeed) assert(n == 4 && memcmp(got, "pong", 4) == 0);
    else assert(n <= 0); /* NO unauthenticated plaintext may be forwarded. */
    close(fds[0]);
    int status = 0;
    assert(waitpid(pid, &status, 0) == pid);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == (must_succeed ? 0 : 9));
    printf("PASS %s (%s)\n", must_succeed ? "verified TLS VLESS TCP" : "fail-closed TLS",
           must_succeed ? "pong" : "no plaintext/no successful fallback");
}

static void dns_test(int port, bool must_succeed, const char *host)
{
    uint8_t q[512] = {
        0x12, 0x34, 0x01, 0, 0, 1, 0, 0, 0, 0, 0, 0,
        0x04,'t','e','s','t',0,0,1,0,1
    };
    uint8_t backup[512];
    memcpy(backup, q, sizeof(backup));
    int length = 22;
    bool ok = s3_vless_tls_dns_query(host, (uint16_t)port, UUID, "1.1.1.1", q,
                                     &length, sizeof(q));
    assert(ok == must_succeed);
    if (must_succeed) {
        assert(length == 22 && q[0] == 0x12 && q[1] == 0x34);
        assert(q[2] == 0x81 && q[3] == 0x80);
    } else {
        assert(length == 22 && !memcmp(backup, q, sizeof(q)));
    }
    printf("PASS %s DNS over verified TLS, never direct UDP\n",
           must_succeed ? "authenticated" : "rejected");
}

int main(int argc, char **argv)
{
    signal(SIGPIPE, SIG_IGN);
    if (argc != 3) return 2;
    int port = atoi(argv[2]);
    if (port < 1 || port > 65535) return 2;
    if (!strcmp(argv[1], "relay")) relay_test(port, true, "vless.test");
    else if (!strcmp(argv[1], "dns")) dns_test(port, true, "vless.test");
    else if (!strcmp(argv[1], "dns-reject")) dns_test(port, false, "vless.test");
    else if (!strcmp(argv[1], "expired")) relay_test(port, false, "vless.test");
    else if (!strcmp(argv[1], "wrong-host")) relay_test(port, false, "wrong.test");
    else if (!strcmp(argv[1], "bad-ca")) relay_test(port, false, "vless.test");
    else if (!strcmp(argv[1], "wrong-host-dns")) dns_test(port, false, "wrong.test");
    else if (!strcmp(argv[1], "bad-header")) relay_test(port, false, "vless.test");
    else if (!strcmp(argv[1], "offline")) relay_test(port, false, "vless.test");
    else if (!strcmp(argv[1], "numeric-host")) relay_test(port, false, "127.0.0.1");
    else return 2;
    return 0;
}
