#pragma once
#include "lwip/netif.h"
#include "lwip/pbuf.h"
err_t ip4_input(struct pbuf *p, struct netif *inp);
