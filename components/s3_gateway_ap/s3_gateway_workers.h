/* SPDX-License-Identifier: MIT
 * AP-bound DNS task owner. No automatic node authorization or relay.
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_netif.h"
bool s3_gateway_workers_start_dns(esp_netif_t *ap);
void s3_gateway_workers_request_stop(void);
/* Failed drain retains referenced AP netif, rather than risking UAF. */
bool s3_gateway_workers_drain(uint32_t timeout_ms);
