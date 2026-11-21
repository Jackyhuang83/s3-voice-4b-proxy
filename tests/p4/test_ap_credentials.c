#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "s3_gateway_ap_config.h"
int main(void)
{
    assert(!s3_gateway_ap_credentials_valid(NULL, "123456789012"));
    assert(!s3_gateway_ap_credentials_valid("gateway", NULL));
    assert(!s3_gateway_ap_credentials_valid("", "123456789012"));
    assert(!s3_gateway_ap_credentials_valid("gateway", "12345678901"));
    assert(s3_gateway_ap_credentials_valid("Gateway-4B", "123456789012"));
    char name[34]; memset(name, 'a', 32); name[32] = 0;
    assert(s3_gateway_ap_credentials_valid(name, "123456789012"));
    name[32] = 'a'; name[33] = 0;
    assert(!s3_gateway_ap_credentials_valid(name, "123456789012"));
    char key[65]; memset(key, 'p', 63); key[63] = 0;
    assert(s3_gateway_ap_credentials_valid("Gateway-4B", key));
    key[63] = 'p'; key[64] = 0;
    assert(!s3_gateway_ap_credentials_valid("Gateway-4B", key));
    assert(!s3_gateway_ap_credentials_valid("Bad\nName", "123456789012"));
    assert(!s3_gateway_ap_credentials_valid("Gateway-4B", "Bad\nPassword2"));
    puts("P4_AP_CREDENTIALS_PASS no blank/weak/overflow/control passwords");
    return 0;
}
