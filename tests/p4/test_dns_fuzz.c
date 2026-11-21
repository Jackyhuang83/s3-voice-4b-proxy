#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "s3_gateway_dns_codec.h"
int main(void) {
  uint32_t x = 0x9f3c270d;
  uint8_t a[620], b[512];
  for (unsigned n = 0; n < 100000; ++n) {
    for (unsigned i = 0; i < sizeof(a); ++i) {
       x ^= x << 13; x ^= x >> 17; x ^= x << 5;
       a[i] = (uint8_t)x;
    }
    size_t len = x % sizeof(a), end = 0;
    if (s3_gateway_dns_question(a,len,false,&end)) {
      if (!end || end > len) abort();
      size_t r = s3_gateway_dns_servfail(a,len,b,sizeof(b));
      if (!r || r > sizeof(b) || !s3_gateway_dns_matches(a,len,b,r)) abort();
    } else if (s3_gateway_dns_servfail(a,len,b,sizeof(b))) abort();
  }
  puts("P4_DNS_FUZZ_PASS 100000 deterministic bounded inputs");
  return 0;
}
