/* SPDX-License-Identifier: MIT
 * Single-Wi-Fi-owner 4B gateway supervisor. Only AP-local sockets.
 * Arm must be an explicit LOCAL administrator action from a non-voice task.
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_netif.h"
#include "s3_gateway_dns_processor.h"

bool s3_gateway_workers_start_dns(esp_netif_t *ap);
/* Bounded two-client TCP relay, encrypted and fail closed. Never auto-arm. */
bool s3_gateway_workers_admin_arm(const s3_gateway_dns_upstream_t *node);
/* Nonblocking: safe in Xiaozhi Wi-Fi event callback; old epoch revoked. */
void s3_gateway_workers_revoke(void);
void s3_gateway_workers_request_stop(void);
/* Task-context only. False means AP netif must be retained locked off. */
bool s3_gateway_workers_drain(uint32_t timeout_ms);
