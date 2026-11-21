/* SPDX-License-Identifier: MIT
 * Credential constraints for a private, authorized WPA2 4B gateway AP.
 * Pure C11: no Wi-Fi calls and no hardcoded SSID/password.
 */
#pragma once
#include <stdbool.h>
bool s3_gateway_ap_credentials_valid(const char *ssid, const char *psk);
