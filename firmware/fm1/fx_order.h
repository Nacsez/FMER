/* SPDX-License-Identifier: GPL-3.0-only
 * Six-stage permutation, rank0 is the original FMER signal path. */
#ifndef FMER_FX_ORDER_H
#define FMER_FX_ORDER_H
#include <stdint.h>
static void fmer_fx_unrank(uint16_t rank,uint8_t out[6]) {
    static const uint16_t factorial[]={120,24,6,2,1,1};
    uint8_t available[6]={0,1,2,3,4,5};uint32_t i,j,n;
    if(rank>=720u)rank=0;
    for(i=0;i<6;i++){n=rank/factorial[i];rank%=factorial[i];out[i]=available[n];
        for(j=n;j<5-i;j++)available[j]=available[j+1];}
}
static uint16_t fmer_fx_rank(const uint8_t order[6]) {
    static const uint16_t factorial[]={120,24,6,2,1,1};
    uint32_t i,j,rank=0,seen=0;
    for(i=0;i<6;i++){uint32_t n=0;if(order[i]>5u || (seen&(1u<<order[i])))return 720;
        for(j=0;j<order[i];j++)if(!(seen&(1u<<j)))n++;
        rank+=n*factorial[i];seen|=1u<<order[i];}
    return (uint16_t)rank;
}
static uint16_t fmer_fx_move(uint16_t rank,uint32_t effect,int32_t delta) {
    uint8_t order[6],tmp;int32_t at,to;
    if(rank>=720u || effect>5u)return rank;
    fmer_fx_unrank(rank,order);for(at=0;at<6 && order[at]!=effect;at++){}
    to=at+delta;if(to<0)to=0;if(to>5)to=5;
    while(at<to){tmp=order[at+1];order[at+1]=order[at];order[at++]=tmp;}
    while(at>to){tmp=order[at-1];order[at-1]=order[at];order[at--]=tmp;}
    return fmer_fx_rank(order);
}
#endif
