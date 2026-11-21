#pragma once
#include <stdint.h>
#include <stddef.h>
#include <sys/random.h>
#include <assert.h>
static inline void esp_fill_random(void *ptr, size_t n) { assert(getrandom(ptr, n, 0) == (ssize_t)n); }
