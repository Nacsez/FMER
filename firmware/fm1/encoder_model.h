/* FMER: sample every matrix frame. Short valid states must not disappear
 * during fast turns. Bounce cancels before a full detent is reported. */
#ifndef FMER_ENCODER_MODEL_H
#define FMER_ENCODER_MODEL_H
#include <stdint.h>
static int32_t fmer_encoder_sample(uint32_t cur,volatile uint8_t *previous,
 volatile uint8_t *rest,volatile uint16_t *still,volatile int8_t *sub,
 volatile uint32_t *moves,volatile uint32_t *lost)
{
 uint32_t idx;int32_t n=0;
 if(*previous==255u){*previous=*rest=(uint8_t)cur;*still=0;*sub=0;return 0;}
 if(cur==*previous){
  if(*still<65535u && ++*still==900u && cur!=*rest){*rest=(uint8_t)cur;*sub=0;}
  return 0;
 }
 *still=0;idx=(uint32_t)*previous*4u+cur;
 if((0x4182u>>idx)&1u){++*sub;++*moves;}
 else if((0x2814u>>idx)&1u){--*sub;++*moves;}
 else {++*lost;if(*sub>0)*sub=(int8_t)(*sub+2);else if(*sub<0)*sub=(int8_t)(*sub-2);}
 *previous=(uint8_t)cur;
 if(*sub>100 || *sub< -100)*sub=0;
 if(cur==*rest){n=*sub<0?-*sub:*sub;n=n>=2?(n+2)/4:0;if(*sub<0)n=-n;*sub=0;}
 return n;
}
#endif
