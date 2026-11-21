#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "s3_gateway_dns_codec.h"
static const uint8_t normal[] = {
 0xbe,0xef,0x01,0x00,0,1,0,0,0,0,0,0,
 7,'e','x','a','m','p','l','e',3,'c','o','m',0,
 0,1,0,1
};
int main(void) {
 uint8_t out[512]; size_t end=0;
 assert(s3_gateway_dns_question(normal,sizeof(normal),false,&end));
 assert(end==sizeof(normal));
 assert(!s3_gateway_dns_question(normal,sizeof(normal),true,&end));
 size_t n=s3_gateway_dns_servfail(normal,sizeof(normal),out,sizeof(out));
 assert(n==sizeof(normal) && out[0]==0xbe && out[1]==0xef);
 assert(out[2]==0x81 && out[3]==0x82 && out[5]==1 && out[11]==0);
 assert(s3_gateway_dns_matches(normal,sizeof(normal),out,n));
 uint8_t other[sizeof(normal)]; memcpy(other,normal,sizeof(other));
 other[0]^=1; assert(!s3_gateway_dns_matches(other,sizeof(other),out,n));
 memcpy(other,normal,sizeof(other)); other[15]^=1;
 assert(!s3_gateway_dns_matches(other,sizeof(other),out,n));
 memcpy(other,normal,sizeof(other)); other[12]=0xc0;
 assert(s3_gateway_dns_servfail(other,sizeof(other),out,sizeof(out))==0);
 memcpy(other,normal,sizeof(other)); other[5]=2;
 assert(!s3_gateway_dns_question(other,sizeof(other),false,&end));
 memcpy(other,normal,sizeof(other)); other[2]=0x81;
 assert(s3_gateway_dns_servfail(other,sizeof(other),out,sizeof(out))==0);
 memcpy(other,normal,sizeof(other)); other[2]=0x11;
 assert(s3_gateway_dns_servfail(other,sizeof(other),out,sizeof(out))==0);
 assert(s3_gateway_dns_servfail(normal,11,out,sizeof(out))==0);
 assert(s3_gateway_dns_servfail(normal,sizeof(normal),out,10)==0);
 assert(!s3_gateway_dns_question(NULL,sizeof(normal),false,&end));
 assert(!s3_gateway_dns_matches(normal,sizeof(normal),NULL,0));
 puts("P4_DNS_CODEC_PASS: canonical question, SERVFAIL, exact ID/question");
 return 0;
}
