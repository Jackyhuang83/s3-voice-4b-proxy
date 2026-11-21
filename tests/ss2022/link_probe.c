/* Host-only integration executable linked against real S3 SS2022 adapter/core.
 * Python mock server separately implements all SIP022 AES-GCM wire crypto.
 */
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <sys/time.h>
#include "s3_ss2022_link.h"

static const char *key_b64 = "AAECAwQFBgcICQoLDA0ODw==";
static void init_node(s3_ss2022_node_t *node, int port)
{
    assert(s3_ss2022_node_store("127.0.0.1", (uint16_t)port, key_b64));
    assert(s3_ss2022_node_load(node));
    assert(s3_ss2022_node_valid(node));
    assert(s3_ss2022_start_clock());
}
static void test_config(void)
{
    s3_ss2022_node_t node;
    assert(!s3_ss2022_node_load(&node));
    assert(!s3_ss2022_node_store("bad host", 443, key_b64));
    assert(!s3_ss2022_node_store("127.0.0.1", 0, key_b64));
    assert(!s3_ss2022_node_store("127.0.0.1", 443, "bad"));
    assert(!s3_ss2022_node_store("127.0.0.1", 443, "AAAAAAAAAAAAAAAAAAAAAA=="));
    assert(s3_ss2022_node_store("127.0.0.1", 443, key_b64));
    assert(s3_ss2022_node_load(&node));
    assert(node.server_port == 443);
    assert(node.psk[0] == 0 && node.psk[15] == 15);
    assert(s3_ss2022_node_clear());
    assert(!s3_ss2022_node_load(&node));
    printf("PASS SS2022 credentials, base64, IPv4 validation, separate NVS/clear\n");
}
static void test_relay(int port)
{
    s3_ss2022_node_t node;
    init_node(&node, port);
    int local[2];
    assert(socketpair(AF_UNIX, SOCK_STREAM, 0, local) == 0);
    pid_t child = fork();
    assert(child >= 0);
    if (child == 0) {
        close(local[0]);
        static const uint8_t ping[] = {'p','i','n','g'};
        bool ok = s3_ss2022_relay(local[1], &node, "198.51.100.7", 443,
                                  ping, sizeof(ping), NULL, NULL);
        close(local[1]);
        s3_ss2022_node_wipe(&node);
        _exit(ok ? 0 : 9);
    }
    close(local[1]);
    struct timeval tv = {.tv_sec = 12};
    setsockopt(local[0], SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    uint8_t reply[4] = {0};
    ssize_t n = recv(local[0], reply, sizeof(reply), MSG_WAITALL);
    assert(n == 4 && memcmp(reply, "pong", 4) == 0);
    close(local[0]); /* cause child to close relay after first authenticated server response */
    int status = 0;
    assert(waitpid(child, &status, 0) == child);
    assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
    s3_ss2022_node_wipe(&node);
    printf("PASS SS2022 live localhost TCP encrypted relay and authenticated response\n");
}
static void test_dns(int port, bool reject)
{
    s3_ss2022_node_t node;
    init_node(&node, port);
    uint8_t packet[512] = {0x12,0x34,0x01,0x00,0x00,0x01,0x00,0x00,0x00,0x00,0x00,0x00};
    int len = 12;
    uint8_t original[sizeof(packet)];
    memcpy(original, packet, sizeof(original));
    bool ok = s3_ss2022_dns_query(&node, "1.1.1.1", packet, &len, sizeof(packet));
    assert(ok == !reject);
    assert(len == 12);
    if (reject)
        assert(memcmp(original, packet, sizeof(packet)) == 0);
    else {
        assert(packet[0] == 0x12 && packet[1] == 0x34);
        assert(packet[2] == 0x81 && packet[3] == 0x80);
    }
    s3_ss2022_node_wipe(&node);
    printf("PASS SS2022 %s DNS over authenticated TCP; failed query unchanged\n",
           reject ? "rejected" : "accepted");
}
int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1],"config")) test_config();
    else if (argc == 3 && !strcmp(argv[1],"relay")) test_relay(atoi(argv[2]));
    else if (argc == 3 && !strcmp(argv[1],"dns")) test_dns(atoi(argv[2]), false);
    else if (argc == 3 && !strcmp(argv[1],"dns-reject")) test_dns(atoi(argv[2]), true);
    else return 2;
    return 0;
}
