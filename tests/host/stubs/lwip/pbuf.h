#pragma once
#include <stddef.h>
#include <stdint.h>
#include "lwip/err.h"
#define PBUF_RAW 0
#define PBUF_RAM 0
struct pbuf { uint16_t len, tot_len; unsigned char *payload; };
struct pbuf *pbuf_alloc(int layer, uint16_t length, int type);
err_t pbuf_copy(struct pbuf *dest, const struct pbuf *src);
uint16_t pbuf_copy_partial(const struct pbuf *p, void *data, uint16_t len, uint16_t offset);
err_t pbuf_take_at(struct pbuf *p, const void *data, uint16_t len, uint16_t offset);
uint8_t pbuf_free(struct pbuf *p);
uint8_t pbuf_header(struct pbuf *p, int16_t increment);
