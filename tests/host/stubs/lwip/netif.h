#pragma once
#include <stdint.h>
#include "lwip/err.h"
struct pbuf;
struct netif;
typedef struct { uint32_t addr; } ip4_addr_t;
typedef err_t (*netif_output_fn)(struct netif *, struct pbuf *, const ip4_addr_t *);
typedef err_t (*netif_linkoutput_fn)(struct netif *, struct pbuf *);
struct netif { ip4_addr_t ip_addr; netif_output_fn output; netif_linkoutput_fn linkoutput; };
static inline const ip4_addr_t *netif_ip4_addr(const struct netif *n) { return &n->ip_addr; }
