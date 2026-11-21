/* SPDX-License-Identifier: MIT
 * Called only inside the existing 78/esp-wifi-connect WifiStation owner.
 * Never initializes, starts or stops a second Wi-Fi driver.
 */
#pragma once
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
bool s3_gateway_ap_pre_start(void);
bool s3_gateway_ap_after_start(void);
/* True only after AP-bound DHCP offers safe local DNS. */
bool s3_gateway_ap_ready(void);
void s3_gateway_ap_before_stop(void);
bool s3_gateway_ap_after_stop(void);
#ifdef __cplusplus
}
#endif
