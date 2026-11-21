/* R2-P1-1 compile-time compatibility shim for byte-identical NOAIC sources.
 * The original NOAIC proxy_config.h depends on its gateway_settings/NVS owner.
 * Do not import that owner into Xiaozhi; only numerical resource limits are
 * required by the selected flow_table.c and ap_clients.c.
 * This file is local, not presented as copied upstream code.
 */
#pragma once
#ifndef PROXY_AP_MAX_CLIENTS
#define PROXY_AP_MAX_CLIENTS 2
#endif
#ifndef PROXY_CLIENT_TCP_LIMIT
#define PROXY_CLIENT_TCP_LIMIT 48
#endif
#ifndef PROXY_CLIENT_UDP_LIMIT
#define PROXY_CLIENT_UDP_LIMIT 24
#endif
#ifndef PROXY_MAX_TCP_MAPPINGS
#define PROXY_MAX_TCP_MAPPINGS 512
#endif
#ifndef PROXY_CLIENT_TCP_MAPPINGS
#define PROXY_CLIENT_TCP_MAPPINGS 256
#endif
#ifndef PROXY_CLIENT_TCP_PENDING
#define PROXY_CLIENT_TCP_PENDING 16
#endif
