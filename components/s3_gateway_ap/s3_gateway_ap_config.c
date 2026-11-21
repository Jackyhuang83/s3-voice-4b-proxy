/* SPDX-License-Identifier: MIT */
#include "s3_gateway_ap_config.h"
#include <stddef.h>
#include <string.h>
bool s3_gateway_ap_credentials_valid(const char *ssid, const char *psk)
{
    if (!ssid || !psk) return false;
    size_t sn = strnlen(ssid, 33);
    size_t pn = strnlen(psk, 64);
    if (sn == 0 || sn > 32 || pn < 12 || pn > 63) return false;
    /* Never accept a control character; Wi-Fi credentials are never logged. */
    for (size_t i = 0; i < sn; ++i)
        if ((unsigned char)ssid[i] < 32 || (unsigned char)ssid[i] == 127)
            return false;
    for (size_t i = 0; i < pn; ++i)
        if ((unsigned char)psk[i] < 32 || (unsigned char)psk[i] == 127)
            return false;
    return true;
}
