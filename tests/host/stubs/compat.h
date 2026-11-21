#pragma once
#include <stddef.h>
#include <string.h>
static inline size_t strlcpy(char *dst, const char *src, size_t n)
{
    size_t len = strlen(src);
    if (n) { size_t copied = len >= n ? n - 1 : len; memcpy(dst, src, copied); dst[copied] = 0; }
    return len;
}
