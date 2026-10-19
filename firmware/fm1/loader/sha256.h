/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 FMER contributors.
 * Original bounded SHA-256 implementation following FIPS 180-4 section 6.2.
 * No allocation, platform calls, or wide-integer runtime helpers. */
#ifndef FMER_SHA256_H
#define FMER_SHA256_H
#include <stdint.h>

typedef struct {
    uint32_t h[8], bytes_lo, bytes_hi, used;
    uint8_t block[64];
} fmer_sha256;

static uint32_t fmer_ror(uint32_t x, uint32_t n) { return (x >> n) | (x << (32u - n)); }

static void fmer_sha256_block(fmer_sha256 *s, const uint8_t *p)
{
    static const uint32_t k[64] = {
        0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
        0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
        0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
        0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
        0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
        0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
        0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
        0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u
    };
    uint32_t w[64], a=s->h[0],b=s->h[1],c=s->h[2],d=s->h[3],e=s->h[4],f=s->h[5],g=s->h[6],h=s->h[7];
    uint32_t i, x, y, t1, t2;
    for (i=0;i<16;i++) w[i]=(uint32_t)p[i*4]<<24|(uint32_t)p[i*4+1]<<16|(uint32_t)p[i*4+2]<<8|p[i*4+3];
    for (i=16;i<64;i++) {
        x=w[i-15]; y=w[i-2];
        w[i]=w[i-16]+(fmer_ror(x,7)^fmer_ror(x,18)^(x>>3))+w[i-7]+(fmer_ror(y,17)^fmer_ror(y,19)^(y>>10));
    }
    for (i=0;i<64;i++) {
        t1=h+(fmer_ror(e,6)^fmer_ror(e,11)^fmer_ror(e,25))+((e&f)^(~e&g))+k[i]+w[i];
        t2=(fmer_ror(a,2)^fmer_ror(a,13)^fmer_ror(a,22))+((a&b)^(a&c)^(b&c));
        h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
    }
    s->h[0]+=a;s->h[1]+=b;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}

static void fmer_sha256_init(fmer_sha256 *s)
{
    static const uint32_t initial[8]={0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
    uint32_t i; for(i=0;i<8;i++)s->h[i]=initial[i];
    s->bytes_lo=s->bytes_hi=s->used=0;
}

static void fmer_sha256_update(fmer_sha256 *s,const uint8_t *p,uint32_t n)
{
    uint32_t old=s->bytes_lo;
    s->bytes_lo+=n; if(s->bytes_lo<old)s->bytes_hi++;
    while(n--) {
        s->block[s->used++]=*p++;
        if(s->used==64u) { fmer_sha256_block(s,s->block);s->used=0; }
    }
}

static void fmer_sha256_final(fmer_sha256 *s,uint8_t out[32])
{
    uint32_t i,lo=s->bytes_lo<<3,hi=(s->bytes_hi<<3)|(s->bytes_lo>>29);
    s->block[s->used++]=0x80;
    if(s->used>56u) { while(s->used<64u)s->block[s->used++]=0;fmer_sha256_block(s,s->block);s->used=0; }
    while(s->used<56u)s->block[s->used++]=0;
    for(i=0;i<4;i++) {s->block[56+i]=(uint8_t)(hi>>(24u-i*8u));s->block[60+i]=(uint8_t)(lo>>(24u-i*8u));}
    fmer_sha256_block(s,s->block);
    for(i=0;i<32;i++)out[i]=(uint8_t)(s->h[i/4]>>(24u-(i%4)*8u));
}
#endif
