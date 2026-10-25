/* SPDX-License-Identifier: GPL-3.0-only
 * FMERNAT8: complete sound + sixteen mono patterns, fixed 3728-byte record.
 * Strictly reads original FMERNAT1 (784B), upgrading its pattern to bank0 and
 * seven empty banks. Wire assembly/CRC belong outside the audio callback.
 * Runtime voices/transport, physical controls, calibration and FX tails excluded.
 */
#ifndef FMER_NATIVE_STATE_H
#define FMER_NATIVE_STATE_H
#include "control_model.h"
#include "fx_order.h"
#include "../../core/song.h"
#include <stddef.h>
#include <string.h>
enum {
 FMER_NATIVE_VERSION=12, FMER_NATIVE_BYTES=4000, FMER_NATIVE_V9_BYTES=3728, FMER_NATIVE_SONG=3728, FMER_NATIVE_V1_BYTES=784, FMER_NATIVE_V4_BYTES=2176,
 FMER_NATIVE_HEADER=32, FMER_NATIVE_CONTROLS=32,
 FMER_NATIVE_VCED=32+FMER_PARAM_COUNT*2, FMER_NATIVE_STEPS=FMER_NATIVE_VCED+155,
 FMER_NATIVE_PADDING=FMER_NATIVE_STEPS+16*193, FMER_NATIVE_V4_PADDING=2127,
 FMER_NATIVE_CUSTOM_PRESET=65535, FMER_NATIVE_CHUNK_MAX=64,
 FMER_NATIVE_PATTERNS=16
};
typedef char fmer_native_v2_control_count_must_be_198[(FMER_PARAM_COUNT==198)?1:-1];
typedef enum {
 FMER_NATIVE_OK=0, FMER_NATIVE_ARGUMENT=1, FMER_NATIVE_SIZE=2,
 FMER_NATIVE_FORMAT=3, FMER_NATIVE_CRC=4, FMER_NATIVE_CONTROL=5,
 FMER_NATIVE_VOICE=6, FMER_NATIVE_PATTERN=7, FMER_NATIVE_METADATA=8,
 FMER_NATIVE_BUSY=9, FMER_NATIVE_TRANSACTION=10, FMER_NATIVE_ORDER=11,
 FMER_NATIVE_CONFLICT=12, FMER_NATIVE_INCOMPLETE=13, FMER_NATIVE_STALE=14
} fmer_native_result_t;
typedef struct {uint8_t pitch[64],velocity[64],gate[64],length;} fmer_native_pattern_t;
typedef struct {uint16_t chain_mask;uint8_t pattern,sound,level,mute,solo,fx_bypass;} fmer_native_track_t;
typedef struct {
 fmer_controls_t controls;
 uint8_t vced[155];
 /* The original flat fields always mean pattern0, independently of selection. */
 uint8_t pitch[64],velocity[64],gate[64];
 uint32_t source_generation;
 uint16_t preset_id;
 uint8_t length;
 fmer_native_pattern_t patterns[15]; /* patterns1..15 */
 fmer_native_track_t tracks[4];
 fmer_song_t song;
 uint8_t modulation[2]; /* chorus/phaser recipe0..3, independent amounts */
 uint16_t fx_order; /* permutation rank0..719; default0 */
} fmer_native_state_t;
static void fmer_native_track_defaults(fmer_native_state_t *s)
{
 uint32_t i;uint8_t ref=(uint8_t)(64u+(s->preset_id<64u?s->preset_id:0u));
 for(i=0;i<4u;i++){s->tracks[i].pattern=(uint8_t)i;s->tracks[i].chain_mask=0;s->tracks[i].sound=ref;s->tracks[i].level=100;s->tracks[i].mute=s->tracks[i].solo=s->tracks[i].fx_bypass=0;}
 for(i=150u;i<160u;i++)s->controls.value[i]=0;
 s->controls.value[FMER_GLIDE_MS]=150;s->controls.value[FMER_TRACK_SOUND]=ref;s->controls.value[FMER_TRACK_LEVEL]=100;s->controls.value[FMER_RECORD_MODE]=1;
}
static uint16_t fmer_native_rd16(const uint8_t *p)
{return (uint16_t)((uint16_t)p[0]|((uint16_t)p[1]<<8));}
static uint32_t fmer_native_rd32(const uint8_t *p)
{return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void fmer_native_wr16(uint8_t *p,uint16_t v)
{p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void fmer_native_wr32(uint8_t *p,uint32_t v)
{p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);p[2]=(uint8_t)(v>>16);p[3]=(uint8_t)(v>>24);}
static uint32_t fmer_native_crc_n(const uint8_t *p,size_t n)
{
 uint32_t crc=0xffffffffu,b;size_t i;
 for(i=0;i<n;i++){crc^=(i>=28u&&i<32u)?0u:p[i];for(b=0;b<8;b++)crc=(crc>>1)^(0xedb88320u&(0u-(crc&1u)));}
 return crc^0xffffffffu;
}
static uint32_t fmer_native_crc(const uint8_t *p){return fmer_native_crc_n(p,FMER_NATIVE_BYTES);}
static fmer_native_result_t fmer_native_state_valid(const fmer_native_state_t *s)
{
 uint32_t i,k,selected,bank,len;const uint8_t *pitch,*vel,*gate;
 if(!s)return FMER_NATIVE_ARGUMENT;
 if(!fmer_song_valid(&s->song))return FMER_NATIVE_METADATA;
 if(s->modulation[0]>3u || s->modulation[1]>3u)return FMER_NATIVE_METADATA;
 if(s->fx_order>=720u)return FMER_NATIVE_METADATA;
 if(s->preset_id>63u&&s->preset_id!=FMER_NATIVE_CUSTOM_PRESET)return FMER_NATIVE_METADATA;
 for(i=0;i<FMER_PARAM_COUNT;i++){
  if(!fmer_control_valid(i,s->controls.value[i]))return FMER_NATIVE_CONTROL;
 }
 for(i=0;i<145u;i++)if(s->vced[i]!=s->controls.value[i])return FMER_NATIVE_VOICE;
 for(i=145u;i<155u;i++)if(s->vced[i]>127u)return FMER_NATIVE_VOICE;
 selected=s->controls.value[FMER_SEQ_STEP];bank=s->controls.value[FMER_SEQ_PATTERN];
 for(k=0;k<FMER_NATIVE_PATTERNS;k++){
  len=k?s->patterns[k-1].length:s->length;
  pitch=k?s->patterns[k-1].pitch:s->pitch;vel=k?s->patterns[k-1].velocity:s->velocity;gate=k?s->patterns[k-1].gate:s->gate;
  if(!len||len>64u)return FMER_NATIVE_PATTERN;
  for(i=0;i<64u;i++)if(pitch[i]>FMER_TIE||!vel[i]||vel[i]>127u||!gate[i]||gate[i]>100u)return FMER_NATIVE_PATTERN;
  if(k==bank&&(len!=s->controls.value[FMER_SEQ_LENGTH]||selected>=len||
    pitch[selected]!=s->controls.value[FMER_SEQ_PITCH]||vel[selected]!=s->controls.value[FMER_SEQ_VELOCITY]||gate[selected]!=s->controls.value[FMER_SEQ_GATE]))return FMER_NATIVE_PATTERN;
 }
 for(i=0;i<4u;i++)if(s->tracks[i].pattern>15u||s->tracks[i].sound>127u||s->tracks[i].level>100u||s->tracks[i].mute>1u||s->tracks[i].solo>1u||s->tracks[i].fx_bypass>1u)return FMER_NATIVE_METADATA;
 i=s->controls.value[FMER_SEQ_TRACK];
 if(s->controls.value[FMER_TRACK_SOUND]!=s->tracks[i].sound||s->controls.value[FMER_TRACK_LEVEL]!=s->tracks[i].level||s->controls.value[FMER_TRACK_MUTE]!=s->tracks[i].mute)return FMER_NATIVE_METADATA;
 return FMER_NATIVE_OK;
}
/* Validate completely before writing any output, including migration. */
static fmer_native_result_t fmer_native_validate(const uint8_t *p,size_t n)
{
 uint32_t i,k,v,old,version,count,vo,so,pad,bank,selected,len,patterns;const uint8_t *step;
 if(!p)return FMER_NATIVE_ARGUMENT;
 if(n!=FMER_NATIVE_BYTES&&n!=FMER_NATIVE_V9_BYTES&&n!=FMER_NATIVE_V4_BYTES&&n!=FMER_NATIVE_V1_BYTES)return FMER_NATIVE_SIZE;
 version=fmer_native_rd16(p+8);old=version==1u;count=old?195u:198u;vo=32u+count*2u;so=vo+155u;
 patterns=old?1u:version<5u?8u:16u;pad=old?769u:so+patterns*193u;
 if(version<1u||version>12u||n!=(old?FMER_NATIVE_V1_BYTES:version<5u?FMER_NATIVE_V4_BYTES:version<10u?FMER_NATIVE_V9_BYTES:FMER_NATIVE_BYTES)||
  memcmp(p,"FMERNAT",7)||p[7]!=(version>=10u?'A'+version-10u:'0'+version)||fmer_native_rd16(p+10)!=32u||fmer_native_rd16(p+12)!=n||fmer_native_rd16(p+14)||
  fmer_native_rd16(p+22)!=count||fmer_native_rd16(p+24)!=155u||p[26]!=(old?64u:patterns)||(!old&&p[27]!=64u))return FMER_NATIVE_FORMAT;
 if(version>=4u) {
  const uint8_t *t=p+pad;uint32_t width=version==4u?5u:6u,shift=version==4u?0u:1u;
  if(memcmp(t,version==4u?"TRK1":version==5u?"TRK2":"TRK3",4))return FMER_NATIVE_FORMAT;
  for(i=0;i<4u;i++)if(t[4+i*width]>=patterns||t[6+shift+i*width]>127u||t[7+shift+i*width]>100u||t[8+shift+i*width]>(version<6u?1u:7u))return FMER_NATIVE_METADATA;
  i=fmer_native_rd16(p+32+2u*FMER_SEQ_TRACK);if(i>3u)return FMER_NATIVE_CONTROL;
  if(t[6+shift+width*i]!=fmer_native_rd16(p+32+2u*FMER_TRACK_SOUND)||t[7+shift+width*i]!=fmer_native_rd16(p+32+2u*FMER_TRACK_LEVEL)||(t[8+shift+width*i]&1u)!=fmer_native_rd16(p+32+2u*FMER_TRACK_MUTE))return FMER_NATIVE_METADATA;
  pad+=4+4*width;
 }
 if(version>=9u){if(memcmp(p+pad,"FX09",4)||fmer_native_rd16(p+pad+4)>=720u)return FMER_NATIVE_METADATA;pad+=6;}
 if(version>=11u){if(memcmp(p+pad,"MOD1",4)||p[pad+4]>3u||p[pad+5]>3u)return FMER_NATIVE_METADATA;pad+=6;}
 for(i=pad;i<(version>=10u?FMER_NATIVE_SONG:n);i++)if(p[i])return FMER_NATIVE_FORMAT;
 if(version>=10u && !fmer_song_wire_valid(p+FMER_NATIVE_SONG))return FMER_NATIVE_METADATA;
 if(fmer_native_crc_n(p,n)!=fmer_native_rd32(p+28))return FMER_NATIVE_CRC;
 v=fmer_native_rd16(p+20);if(v>(old?15u:63u)&&v!=FMER_NATIVE_CUSTOM_PRESET)return FMER_NATIVE_METADATA;
 for(i=0;i<count;i++){
  v=fmer_native_rd16(p+32+2u*i);
  if(i>=(version<3u?145u:version<4u?150u:version<7u?159u:160u)&&i<160u){if(v)return FMER_NATIVE_CONTROL;}
  else if((version<8u&&((i==FMER_ARP_ORDER&&v>9u)||(i==FMER_VA_WAVE&&v>3u)))||(version<7u&&i==FMER_REVERB_MODEL&&v>1u)||!fmer_control_valid(i,v)||(version<12u&&i==FMER_VOICE_BUDGET&&v>4u)||(old&&i==FMER_ARP_ORDER&&v>6u)||
    (version<5u&&((i==FMER_SEQ_PATTERN&&v>7u)||(i==FMER_SEQ_CHAIN_MASK&&v>255u)||(i==FMER_RECORD_MODE&&v>1u))))return FMER_NATIVE_CONTROL;
  if(i<145u&&v!=p[vo+i])return FMER_NATIVE_VOICE;
 }
 for(i=145u;i<155u;i++)if(p[vo+i]>127u)return FMER_NATIVE_VOICE;
 bank=old?0u:fmer_native_rd16(p+32+FMER_SEQ_PATTERN*2u);selected=fmer_native_rd16(p+32+FMER_SEQ_STEP*2u);
 for(k=0;k<patterns;k++){
  len=old?p[27]:p[so+k*193u];step=p+so+(old?0u:k*193u+1u);
  if(!len||len>64u)return FMER_NATIVE_PATTERN;
  for(i=0;i<64u;i++)if(step[3*i]>(version<4u?FMER_REST:FMER_TIE)||!step[3*i+1]||step[3*i+1]>127u||!step[3*i+2]||step[3*i+2]>100u)return FMER_NATIVE_PATTERN;
  if(k==bank){
   if(len!=fmer_native_rd16(p+32+FMER_SEQ_LENGTH*2u)||selected>=len)return FMER_NATIVE_PATTERN;
   for(i=0;i<3u;i++)if(step[selected*3+i]!=fmer_native_rd16(p+32+(FMER_SEQ_PITCH+i)*2u))return FMER_NATIVE_PATTERN;
  }
 }
 return FMER_NATIVE_OK;
}
static fmer_native_result_t fmer_native_encode(const fmer_native_state_t *s,uint8_t *p,size_t capacity)
{
 uint32_t i,k;uint8_t *dst;const uint8_t *pitch,*vel,*gate;fmer_native_result_t result;
 if(!p)return FMER_NATIVE_ARGUMENT;if(capacity<FMER_NATIVE_BYTES)return FMER_NATIVE_SIZE;
 result=fmer_native_state_valid(s);if(result!=FMER_NATIVE_OK)return result;
 memset(p,0,FMER_NATIVE_BYTES);memcpy(p,"FMERNATC",8);
 fmer_native_wr16(p+8,12);fmer_native_wr16(p+10,32);fmer_native_wr16(p+12,FMER_NATIVE_BYTES);
 fmer_native_wr32(p+16,s->source_generation);fmer_native_wr16(p+20,s->preset_id);
 fmer_native_wr16(p+22,198);fmer_native_wr16(p+24,155);p[26]=16;p[27]=64;
 for(i=0;i<198u;i++)fmer_native_wr16(p+32+2u*i,s->controls.value[i]);memcpy(p+FMER_NATIVE_VCED,s->vced,155);
 for(k=0;k<FMER_NATIVE_PATTERNS;k++){
  dst=p+FMER_NATIVE_STEPS+k*193u;*dst++=k?s->patterns[k-1].length:s->length;
  pitch=k?s->patterns[k-1].pitch:s->pitch;vel=k?s->patterns[k-1].velocity:s->velocity;gate=k?s->patterns[k-1].gate:s->gate;
  for(i=0;i<64u;i++){*dst++=pitch[i];*dst++=vel[i];*dst++=gate[i];}
 }
 memcpy(p+FMER_NATIVE_PADDING,"TRK3",4);
 for(i=0;i<4u;i++){dst=p+FMER_NATIVE_PADDING+4+6*i;dst[0]=s->tracks[i].pattern;fmer_native_wr16(dst+1,s->tracks[i].chain_mask);dst[3]=s->tracks[i].sound;dst[4]=s->tracks[i].level;dst[5]=(uint8_t)(s->tracks[i].mute|s->tracks[i].solo<<1|s->tracks[i].fx_bypass<<2);}
 memcpy(p+FMER_NATIVE_PADDING+28,"FX09",4);fmer_native_wr16(p+FMER_NATIVE_PADDING+32,s->fx_order);
 memcpy(p+FMER_NATIVE_PADDING+34,"MOD1",4);memcpy(p+FMER_NATIVE_PADDING+38,s->modulation,2);
 fmer_song_pack(&s->song,p+FMER_NATIVE_SONG);
 fmer_native_wr32(p+28,fmer_native_crc(p));return FMER_NATIVE_OK;
}
static fmer_native_result_t fmer_native_decode(const uint8_t *p,size_t n,fmer_native_state_t *s)
{
 uint32_t i,k,old,count,vo,so,version,patterns;const uint8_t *src;uint8_t *pitch,*vel,*gate;fmer_native_result_t result;
 if(!s)return FMER_NATIVE_ARGUMENT;
 result=fmer_native_validate(p,n);if(result!=FMER_NATIVE_OK)return result;
 version=fmer_native_rd16(p+8);old=version==1u;patterns=old?1u:version<5u?8u:16u;count=old?195u:198u;vo=32+count*2u;so=vo+155u;
 memset(s,0,sizeof *s);s->source_generation=fmer_native_rd32(p+16);s->preset_id=fmer_native_rd16(p+20);
 for(i=0;i<count;i++)s->controls.value[i]=fmer_native_rd16(p+32+2*i);memcpy(s->vced,p+vo,155);
 if(fmer_native_rd16(p+8)<3u)s->controls.value[FMER_LFO_ENABLE]=1;
 if(old)s->controls.value[FMER_SEQ_CHAIN_MASK]=1;
 for(k=0;k<FMER_NATIVE_PATTERNS;k++){
  pitch=k?s->patterns[k-1].pitch:s->pitch;vel=k?s->patterns[k-1].velocity:s->velocity;gate=k?s->patterns[k-1].gate:s->gate;
  if(k>=patterns){s->patterns[k-1].length=16;memset(pitch,FMER_REST,64);memset(vel,100,64);memset(gate,75,64);continue;}
  src=p+so+(old?0u:k*193u+1u);
  if(k)s->patterns[k-1].length=src[-1];else s->length=old?p[27]:src[-1];
  for(i=0;i<64u;i++){pitch[i]=*src++;vel[i]=*src++;gate[i]=*src++;}
 }
 if(fmer_native_rd16(p+8)<4u){fmer_native_track_defaults(s);s->controls.value[FMER_RECORD_MODE]=0;}
 else for(i=0;i<4u;i++){uint32_t width=version==4u?5u:6u,shift=version==4u?0u:1u;src=p+so+patterns*193u+4+width*i;s->tracks[i].pattern=src[0];s->tracks[i].chain_mask=version==4u?src[1]:fmer_native_rd16(src+1);s->tracks[i].sound=src[2+shift];s->tracks[i].level=src[3+shift];s->tracks[i].mute=src[4+shift]&1u;s->tracks[i].solo=version>=6u?(src[4+shift]>>1)&1u:0;s->tracks[i].fx_bypass=version>=6u?(src[4+shift]>>2)&1u:0;}
 if(version>=11u)memcpy(s->modulation,p+FMER_NATIVE_PADDING+38,2);
 if(version>=10u)fmer_song_unpack(p+FMER_NATIVE_SONG,&s->song);
 if(version>=9u)s->fx_order=fmer_native_rd16(p+FMER_NATIVE_PADDING+32);
 if(version==4u&&s->controls.value[FMER_RECORD_MODE]==1u)s->controls.value[FMER_RECORD_MODE]=2u;
 return FMER_NATIVE_OK;
}
/* Validated v2/v3/v4 compact-journal records expand in the caller's3728-byte
 * buffer. A24-byte track scratch replaces the former full-state stack copy.
 * This helper is deliberately not the v1 file migration path (decode handles it). */
static void fmer_native_upgrade_v2(uint8_t *p)
{
 uint32_t version=fmer_native_rd16(p+8),i,k,ref;uint8_t tracks[24],*dst;
 if(version>=12u)return;
 if(version==11u){if(fmer_native_validate(p,FMER_NATIVE_BYTES)!=FMER_NATIVE_OK)return;memcpy(p,"FMERNATC",8);fmer_native_wr16(p+8,12);fmer_native_wr32(p+28,fmer_native_crc(p));return;}
 if(version==10u){
  if(fmer_native_validate(p,FMER_NATIVE_BYTES)!=FMER_NATIVE_OK)return;
  memcpy(p,"FMERNATC",8);fmer_native_wr16(p+8,12);memcpy(p+FMER_NATIVE_PADDING+34,"MOD1",4);
  fmer_native_wr32(p+28,fmer_native_crc(p));return;
 }
 if(version==5u || version==6u || version==7u || version==8u || version==9u){
  if(fmer_native_validate(p,FMER_NATIVE_V9_BYTES)!=FMER_NATIVE_OK)return;
  memset(p+FMER_NATIVE_SONG,0,FMER_SONG_BYTES);fmer_native_wr16(p+12,FMER_NATIVE_BYTES);
  memcpy(p,"FMERNATC",8);fmer_native_wr16(p+8,12);memcpy(p+FMER_NATIVE_PADDING,"TRK3",4);
  memcpy(p+FMER_NATIVE_PADDING+28,"FX09",4);
  memcpy(p+FMER_NATIVE_PADDING+34,"MOD1",4);
  fmer_native_wr32(p+28,fmer_native_crc(p));return;
 }
 if(version<2u||fmer_native_validate(p,FMER_NATIVE_V4_BYTES)!=FMER_NATIVE_OK)return;
 memcpy(tracks,p+FMER_NATIVE_V4_PADDING,24);
 memset(p+FMER_NATIVE_V4_PADDING,0,FMER_NATIVE_BYTES-FMER_NATIVE_V4_PADDING);
 for(k=8;k<16;k++){dst=p+FMER_NATIVE_STEPS+k*193;*dst++=16;for(i=0;i<64;i++){*dst++=FMER_REST;*dst++=100;*dst++=75;}}
 memcpy(p,"FMERNATC",8);fmer_native_wr16(p+8,12);fmer_native_wr16(p+12,FMER_NATIVE_BYTES);p[26]=16;
 if(version<3)fmer_native_wr16(p+32+FMER_LFO_ENABLE*2,1);
 memcpy(p+FMER_NATIVE_PADDING,"TRK3",4);
 if(version<4){
  ref=fmer_native_rd16(p+20);ref=64+(ref<64?ref:0);
  for(i=150;i<160;i++)fmer_native_wr16(p+32+i*2,0);
  fmer_native_wr16(p+32+FMER_GLIDE_MS*2,150);fmer_native_wr16(p+32+FMER_TRACK_SOUND*2,(uint16_t)ref);fmer_native_wr16(p+32+FMER_TRACK_LEVEL*2,100);
  for(i=0;i<4;i++){dst=p+FMER_NATIVE_PADDING+4+6*i;dst[0]=(uint8_t)i;dst[3]=(uint8_t)ref;dst[4]=100;}
 }else{
  for(i=0;i<4;i++){const uint8_t *src=tracks+4+5*i;dst=p+FMER_NATIVE_PADDING+4+6*i;dst[0]=src[0];dst[1]=src[1];dst[3]=src[2];dst[4]=src[3];dst[5]=src[4];}
  if(fmer_native_rd16(p+32+FMER_RECORD_MODE*2)==1)fmer_native_wr16(p+32+FMER_RECORD_MODE*2,2);
 }
 memcpy(p+FMER_NATIVE_PADDING+28,"FX09",4);
 memcpy(p+FMER_NATIVE_PADDING+34,"MOD1",4);
 fmer_native_wr32(p+28,fmer_native_crc(p));
}
/* Transaction IDs and expected live revision are transport metadata, not file
 * identity. Consumer must recheck the live revision in the atomic publication
 * critical section. Ready never mutates the instrument. Explicitly abort/reset
 * on disconnect, timeout or rejected commit; no timeout clock lives here. */
typedef struct {
 uint8_t bytes[FMER_NATIVE_BYTES];
 uint32_t id,expected_generation;
 uint16_t received;
 uint8_t active;
} fmer_native_transfer_t;
static void fmer_native_transfer_reset(fmer_native_transfer_t *t)
{ if(t)memset(t,0,sizeof *t); }
static fmer_native_result_t fmer_native_transfer_begin(fmer_native_transfer_t *t,uint32_t id,uint32_t generation,size_t n)
{
 if(!t || !id)return FMER_NATIVE_ARGUMENT;
 if(n!=FMER_NATIVE_BYTES)return FMER_NATIVE_SIZE;
 if(t->active)return (t->id==id && t->expected_generation==generation)?FMER_NATIVE_OK:FMER_NATIVE_BUSY;
 t->id=id;t->expected_generation=generation;t->received=0;t->active=1;return FMER_NATIVE_OK;
}
static fmer_native_result_t fmer_native_transfer_chunk(fmer_native_transfer_t *t,uint32_t id,size_t offset,const uint8_t *p,size_t n)
{
 if(!t || !p)return FMER_NATIVE_ARGUMENT;
 if(!t->active || t->id!=id)return FMER_NATIVE_TRANSACTION;
 if(!n || n>FMER_NATIVE_CHUNK_MAX || offset>FMER_NATIVE_BYTES || n>FMER_NATIVE_BYTES-offset)return FMER_NATIVE_SIZE;
 if(offset<t->received) {
  if(n>t->received-offset)return FMER_NATIVE_ORDER;
  return memcmp(t->bytes+offset,p,n)?FMER_NATIVE_CONFLICT:FMER_NATIVE_OK;
 }
 if(offset!=t->received)return FMER_NATIVE_ORDER;
 memcpy(t->bytes+offset,p,n);t->received=(uint16_t)(t->received+n);return FMER_NATIVE_OK;
}
static fmer_native_result_t fmer_native_transfer_ready(const fmer_native_transfer_t *t,uint32_t id,uint32_t current_generation)
{
 if(!t)return FMER_NATIVE_ARGUMENT;
 if(!t->active || t->id!=id)return FMER_NATIVE_TRANSACTION;
 if(t->received!=FMER_NATIVE_BYTES)return FMER_NATIVE_INCOMPLETE;
 if(t->expected_generation!=current_generation)return FMER_NATIVE_STALE;
 return fmer_native_validate(t->bytes,FMER_NATIVE_BYTES);
}
#endif
