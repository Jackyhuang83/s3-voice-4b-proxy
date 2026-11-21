/* SPDX-License-Identifier: MIT
 * One authenticated SS2022/VLESS DNS probe; never starts AP or auto-arms.
 * Caller must supply the exact captured epoch when proving a session.
 */
#pragma once
#include <stdbool.h>
#include "s3_gateway_dns_processor.h"
bool s3_gateway_dns_probe_node(const s3_gateway_dns_upstream_t *upstream);
