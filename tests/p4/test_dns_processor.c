#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "s3_gateway_dns_processor.h"
#include "s3_gateway_policy.h"
#include "s3_vless_tls.h"
static const uint8_t q[]={0x33,0x55,1,0,0,1,0,0,0,0,0,0,1,'x',0,0,1,0,1};
static bool ready=false;
static int ss_calls=0,vless_calls=0,behavior=0;
static s3_gateway_policy_t dummy={0};
s3_gateway_policy_t *s3_gateway_policy_device(void){return &dummy;}
bool s3_gateway_policy_ready(const s3_gateway_policy_t *p){return p==&dummy && ready;}
static bool mock(uint8_t *packet,int *length){
 if(behavior==1)return false;
 if(behavior==2){packet[0]^=1;}
 if(behavior==3){packet[13]='y';}
 if(behavior==4){ready=false;}
 packet[2]=0x81;packet[3]=0x80;
 return *length==sizeof(q);
}
bool s3_ss2022_dns_query(const s3_ss2022_node_t *node,const char *r,uint8_t *p,int *n,size_t c){
 assert(node&&r&&c==512);++ss_calls;return mock(p,n);
}
bool s3_vless_tls_dns_query(const char *s,uint16_t port,const uint8_t uuid[16],const char *r,uint8_t *p,int *n,size_t c){
 assert(s&&port==443&&uuid&&r&&c==512);++vless_calls;return mock(p,n);
}
int main(void){
 uint8_t answer[512];s3_ss2022_node_t node={0};uint8_t uuid[16]={1};
 s3_gateway_dns_upstream_t u={.transport=S3_GATEWAY_DNS_SS2022,.ss2022_node=&node,.resolver="1.1.1.1"};
 size_t n=s3_gateway_dns_process(&u,q,sizeof(q),answer,sizeof(answer));
 assert(n==sizeof(q)&&answer[3]==0x82&&ss_calls==0);
 ready=true;n=s3_gateway_dns_process(&u,q,sizeof(q),answer,sizeof(answer));
 assert(n==sizeof(q)&&answer[3]==0x80&&ss_calls==1);
 behavior=1;n=s3_gateway_dns_process(&u,q,sizeof(q),answer,sizeof(answer));
 assert(n==sizeof(q)&&answer[3]==0x82&&ss_calls==2);
 behavior=2;n=s3_gateway_dns_process(&u,q,sizeof(q),answer,sizeof(answer));
 assert(n==sizeof(q)&&answer[3]==0x82&&ss_calls==3);
 behavior=3;n=s3_gateway_dns_process(&u,q,sizeof(q),answer,sizeof(answer));
 assert(n==sizeof(q)&&answer[3]==0x82&&ss_calls==4);
 behavior=4;n=s3_gateway_dns_process(&u,q,sizeof(q),answer,sizeof(answer));
 assert(n==sizeof(q)&&answer[3]==0x82&&!ready&&ss_calls==5);
 ready=true;behavior=0;u.transport=S3_GATEWAY_DNS_VLESS_TLS;u.vless_sni="example.org";u.vless_port=443;u.vless_uuid=uuid;
 n=s3_gateway_dns_process(&u,q,sizeof(q),answer,sizeof(answer));
 assert(n==sizeof(q)&&answer[3]==0x80&&vless_calls==1&&ss_calls==5);
 u.transport=S3_GATEWAY_DNS_NONE;n=s3_gateway_dns_process(&u,q,sizeof(q),answer,sizeof(answer));
 assert(n==sizeof(q)&&answer[3]==0x82&&vless_calls==1);
 u.transport=S3_GATEWAY_DNS_SS2022;u.resolver=NULL;n=s3_gateway_dns_process(&u,q,sizeof(q),answer,sizeof(answer));
 assert(n==sizeof(q)&&answer[3]==0x82&&ss_calls==5);
 assert(s3_gateway_dns_process(&u,q,3,answer,sizeof(answer))==0);
 puts("P4_DNS_PROCESS_PASS: never direct; secure SS2022/VLESS; SERVFAIL; revoke in flight");
 return 0;
}
