/* SPDX-License-Identifier: GPL-3.0-only
 *720:128 instruments and16 independent projects in the existing73-sector journal.
 * Eight320-byte sounds/group, one compact sixteen-pattern project/record.
 * Explicit one-commit layout initialization abandons old arrangements only after
 * a new metadata barrier is durable. Legacy layouts remain readable, read-only.
 * Current sector ownership, protected bounds and scanner trailer are unchanged.
 */
#ifndef FMER_BANK_STORE_H
#define FMER_BANK_STORE_H
#define FMER_DUAL_BANK 1
#include "preset_store.h"
#include "native_state.h"
#include "midi_settings.h"
enum {FMER_BANK_COMPACT_V1=1679,FMER_BANK_PAIR_V1=3390,FMER_BANK_COMPACT_V2=1709,FMER_BANK_PAIR_V2=3450,
 FMER_BANK_COMPACT_V3=1758,FMER_BANK_PAIR_V3=3548,FMER_BANK_COMPACT_V9=3168,FMER_BANK_COMPACT=3440,
 FMER_BANK_SOUND=320,FMER_BANK_GROUP=2592,FMER_BANK_PROJECT_V9=3200,FMER_BANK_PROJECT=3472,FMER_BANK_PROJECTS=16,FMER_BANK_META=64};
typedef struct {
 uint32_t epoch[2],user_empty,project_epoch,layout;
 uint64_t meta_generation,layout_generation;
 uint16_t latest_slot,latest_project,fx_default;
 fmer_midi_settings_t midi;
} fmer_bank_t;
typedef int (*fmer_bank_default_t)(uint32_t,uint8_t *);
/* Lossless project compression: duplicate operator values are reconstructed;
 * all controls, inactive steps, metadata and CRC remain exact. */
static void fmer_bank_pack(const uint8_t *wire,uint8_t *out)
{
 uint32_t i,k,bit;uint8_t *dst;const uint8_t *src;
 memset(out,0,FMER_BANK_COMPACT);memcpy(out,wire,32);memcpy(out+32,wire+FMER_NATIVE_VCED,155);
 memcpy(out+187,wire+32+145*2,106);memcpy(out+3125,wire+FMER_NATIVE_PADDING,fmer_native_rd16(wire+8)>=11u?40u:fmer_native_rd16(wire+8)>=9u?34u:28u);
 if(fmer_native_rd16(wire+8)>=10u)memcpy(out+3168,wire+FMER_NATIVE_SONG,FMER_SONG_BYTES);
 for(k=0;k<16u;k++) {
  src=wire+FMER_NATIVE_STEPS+k*193;dst=out+293+k*177;*dst++=*src++;bit=0;
  for(i=0;i<192u;i++){uint32_t b,width=i%3u?7u:8u;for(b=0;b<width;b++,bit++)dst[bit/8u]|=((src[i]>>b)&1u)<<(bit%8u);}
 }
}
static int fmer_bank_unpack(const uint8_t *in,uint8_t *wire)
{
 uint32_t i,k,bit;uint8_t *dst;const uint8_t *src;
 for(i=fmer_native_rd16(in+8)>=11u?3165u:fmer_native_rd16(in+8)>=9u?3159u:3153u;i<FMER_BANK_COMPACT_V9;i++)if(in[i])return 0;
 memset(wire,0,FMER_NATIVE_BYTES);memcpy(wire,in,32);memcpy(wire+FMER_NATIVE_VCED,in+32,155);
 memcpy(wire+32+145*2,in+187,106);memcpy(wire+FMER_NATIVE_PADDING,in+3125,fmer_native_rd16(in+8)>=11u?40u:fmer_native_rd16(in+8)>=9u?34u:28u);
 for(i=0;i<145u;i++)fmer_native_wr16(wire+32+2*i,in[32+i]);
 for(k=0;k<16u;k++) {
  src=in+293+k*177;dst=wire+FMER_NATIVE_STEPS+k*193;*dst++=*src++;bit=0;
  for(i=0;i<192u;i++){uint32_t b,width=i%3u?7u:8u;for(b=0;b<width;b++,bit++)dst[i]|=((src[bit/8u]>>(bit%8u))&1u)<<b;}
 }
 if(fmer_native_rd16(in+8)>=10u)memcpy(wire+FMER_NATIVE_SONG,in+3168,FMER_SONG_BYTES);
 if(fmer_native_validate(wire,fmer_native_rd16(wire+12))!=FMER_NATIVE_OK)return 0;
 fmer_native_upgrade_v2(wire);return 1;
}
static int fmer_bank_legacy_unpack(const uint8_t *in,uint8_t *wire)
{
 uint32_t i,k,bit;uint8_t *dst;const uint8_t *src;
 memset(wire,0,FMER_NATIVE_BYTES);memcpy(wire,in,32);
 if(fmer_native_rd16(in+8)>=4u)memcpy(wire+FMER_NATIVE_V4_PADDING,in+1709,49);
 if(fmer_native_rd16(in+8)>=3u)memcpy(wire+32+145*2,in+1679,30);
 memcpy(wire+FMER_NATIVE_VCED,in+32,155);memcpy(wire+32+320,in+187,76);
 for(i=0;i<145u;i++)fmer_native_wr16(wire+32+2*i,in[32+i]);
 for(k=0;k<8u;k++) {
  src=in+263+k*177;dst=wire+FMER_NATIVE_STEPS+k*193;*dst++=*src++;bit=0;
  for(i=0;i<192u;i++) {
   uint32_t b,width=i%3u?7u:8u;
   for(b=0;b<width;b++,bit++)dst[i]|=((src[bit/8u]>>(bit%8u))&1u)<<b;
  }
 }
 if(fmer_native_validate(wire,FMER_NATIVE_V4_BYTES)!=FMER_NATIVE_OK)return 0;
 fmer_native_upgrade_v2(wire);return 1;
}
static int fmer_bank_legacy_group_valid(const uint8_t *p,uint32_t n,uint32_t group)
{
 uint32_t i;
 if(!((n==FMER_BANK_PAIR_V1&&p[8]==1)||(n==FMER_BANK_PAIR_V2&&p[8]==2)||(n==FMER_BANK_PAIR_V3&&p[8]==3)) || memcmp(p,"FMERPAIR",8) || p[9]!=group || p[10]>3 || p[11]>1)return 0;
 for(i=16;i<32;i++)if(p[i])return 0;
 return 1;
}

/* Strip only project state when storing an instrument. Preserve sound, envelopes,
 * glide, FX, arp and channel controls exactly. One sound carries no arrangement. */
static void fmer_bank_sound_pack(const uint8_t *wire,uint8_t out[FMER_BANK_SOUND])
{
 memset(out,0,FMER_BANK_SOUND);memcpy(out,"FMERSND3",8);memcpy(out+8,wire+16,6);
 memcpy(out+16,wire+FMER_NATIVE_VCED,155);memcpy(out+171,wire+32+145*2,106);
 if(fmer_native_rd16(wire+8)>=9u)memcpy(out+277,wire+FMER_NATIVE_PADDING+32,2);
 if(fmer_native_rd16(wire+8)>=11u)memcpy(out+279,wire+FMER_NATIVE_PADDING+38,2);
}
static int fmer_bank_sound_unpack(const uint8_t in[FMER_BANK_SOUND],uint8_t *wire)
{
 uint32_t i,k,ref;uint8_t *p;
 if((memcmp(in,"FMERSND1",8)&&memcmp(in,"FMERSND2",8)&&memcmp(in,"FMERSND3",8))||in[14]||in[15])return 0;
 if(in[7]>='2' && fmer_native_rd16(in+277)>=720u)return 0;
 if(in[7]=='3' && (in[279]>3u || in[280]>3u))return 0;
 for(i=in[7]=='3'?281u:in[7]=='2'?279u:277u;i<FMER_BANK_SOUND;i++)if(in[i])return 0;
 memset(wire,0,FMER_NATIVE_BYTES);memcpy(wire,"FMERNATB",8);
 fmer_native_wr16(wire+8,11);fmer_native_wr16(wire+10,32);fmer_native_wr16(wire+12,FMER_NATIVE_BYTES);
 memcpy(wire+16,in+8,6);fmer_native_wr16(wire+22,198);fmer_native_wr16(wire+24,155);wire[26]=16;wire[27]=64;
 memcpy(wire+FMER_NATIVE_VCED,in+16,155);memcpy(wire+32+145*2,in+171,106);
 for(i=0;i<145;i++)fmer_native_wr16(wire+32+i*2,in[16+i]);
 ref=fmer_native_rd16(wire+20);ref=64+(ref<64?ref:0);
 for(i=153;i<159;i++)fmer_native_wr16(wire+32+i*2,0);
 fmer_native_wr16(wire+32+155*2,(uint16_t)ref);fmer_native_wr16(wire+32+156*2,100);
 fmer_native_wr16(wire+32+186*2,16);fmer_native_wr16(wire+32+187*2,0);fmer_native_wr16(wire+32+188*2,128);
 fmer_native_wr16(wire+32+189*2,100);fmer_native_wr16(wire+32+190*2,75);
 fmer_native_wr16(wire+32+195*2,0);fmer_native_wr16(wire+32+196*2,0);fmer_native_wr16(wire+32+197*2,1);
 for(k=0;k<16;k++){p=wire+FMER_NATIVE_STEPS+k*193;*p++=16;for(i=0;i<64;i++){*p++=128;*p++=100;*p++=75;}}
 memcpy(wire+FMER_NATIVE_PADDING,"TRK3",4);
 for(i=0;i<4;i++){p=wire+FMER_NATIVE_PADDING+4+6*i;p[0]=(uint8_t)i;p[3]=(uint8_t)ref;p[4]=100;}
 memcpy(wire+FMER_NATIVE_PADDING+28,"FX09",4);if(in[7]>='2')memcpy(wire+FMER_NATIVE_PADDING+32,in+277,2);
 memcpy(wire+FMER_NATIVE_PADDING+34,"MOD1",4);if(in[7]=='3')memcpy(wire+FMER_NATIVE_PADDING+38,in+279,2);
 fmer_native_wr32(wire+28,fmer_native_crc(wire));return fmer_native_validate(wire,FMER_NATIVE_BYTES)==FMER_NATIVE_OK;
}
/* In-place merge, no native-size stack temporary. Sound recall keeps arrangement,
 * selected track/mixer, tempo, voice budget and chain. It restores the instrument's
 * own FX/arp/glide values, as distinct from fast audition (which preserves FX). */
static int fmer_native_merge_sound(uint8_t *sound,const uint8_t *project)
{
 uint32_t i;
 if(fmer_native_validate(sound,FMER_NATIVE_BYTES)||fmer_native_validate(project,FMER_NATIVE_BYTES))return 0;
 fmer_native_upgrade_v2(sound);
 memcpy(sound+FMER_NATIVE_STEPS,project+FMER_NATIVE_STEPS,FMER_NATIVE_PADDING+28-FMER_NATIVE_STEPS);
 if(fmer_native_rd16(project+8)==5u)memcpy(sound+FMER_NATIVE_PADDING,"TRK3",4);
 if(!fmer_native_rd16(project+32+FMER_SEQ_MODE*2))for(i=150;i<153;i++)memcpy(sound+32+i*2,project+32+i*2,2);
 for(i=153;i<159;i++)memcpy(sound+32+i*2,project+32+i*2,2);
 for(i=186;i<=191;i++)memcpy(sound+32+i*2,project+32+i*2,2);
 for(i=195;i<=197;i++)memcpy(sound+32+i*2,project+32+i*2,2);
 memcpy(sound+32+178*2,project+32+178*2,2);
 memcpy(sound+FMER_NATIVE_SONG,project+FMER_NATIVE_SONG,FMER_SONG_BYTES);
 fmer_native_wr32(sound+28,fmer_native_crc(sound));return fmer_native_validate(sound,FMER_NATIVE_BYTES)==FMER_NATIVE_OK;
}
static int fmer_native_merge_sound_slot(uint8_t *sound,const uint8_t *project,uint32_t slot)
{
 uint32_t selected;
 if(slot>=128u||!fmer_native_merge_sound(sound,project))return 0;
 selected=fmer_native_rd16(sound+32+FMER_SEQ_TRACK*2);
 fmer_native_wr16(sound+32+FMER_TRACK_SOUND*2,(uint16_t)slot);
 sound[FMER_NATIVE_PADDING+4+6*selected+3]=(uint8_t)slot;
 fmer_native_wr32(sound+28,fmer_native_crc(sound));return fmer_native_validate(sound,FMER_NATIVE_BYTES)==FMER_NATIVE_OK;
}
static int fmer_bank_sound_equal(const uint8_t *a,const uint8_t *b)
{
 uint8_t pa[FMER_BANK_SOUND],pb[FMER_BANK_SOUND];uint32_t i;
 fmer_bank_sound_pack(a,pa);fmer_bank_sound_pack(b,pb);
 /* Ignore project/editor controls normalized when the instrument is reconstructed. */
 for(i=153;i<159;i++)memset(pa+171+(i-145)*2,0,2),memset(pb+171+(i-145)*2,0,2);
 for(i=186;i<=190;i++)memset(pa+171+(i-145)*2,0,2),memset(pb+171+(i-145)*2,0,2);
 for(i=195;i<=197;i++)memset(pa+171+(i-145)*2,0,2),memset(pb+171+(i-145)*2,0,2);
 return !memcmp(pa,pb,sizeof pa);
}
static int fmer_bank_group_valid(const uint8_t *p,uint32_t n,uint32_t group)
{
 uint32_t i;if(n!=FMER_BANK_GROUP||memcmp(p,"FMERINS1",8)||p[8]!=1||p[9]!=group||p[11]>7||!(p[10]&(1u<<p[11])))return 0;
 for(i=16;i<32;i++)if(p[i])return 0;return 1;
}
static int fmer_bank_project_valid(const uint8_t *p,uint32_t n,uint32_t project)
{
 uint32_t i;if((n!=FMER_BANK_PROJECT && n!=FMER_BANK_PROJECT_V9)||memcmp(p,"FMERPRJ1",8)||p[8]!=project)return 0;
 if(n!=(fmer_native_rd16(p+32+8)>=10u?FMER_BANK_PROJECT:FMER_BANK_PROJECT_V9))return 0;
 for(i=9;i<12;i++)if(p[i])return 0;for(i=16;i<32;i++)if(p[i])return 0;return 1;
}
static int fmer_bank_meta_valid(const uint8_t *p,uint32_t n)
{
 uint32_t i,modern=n==48u;
 if((!modern&&n!=32u)||(modern?(memcmp(p,"FMERBNK3",8)&&memcmp(p,"FMERBNK4",8)):memcmp(p,"FMERBNK2",8))||p[16]>1||p[17]>1)return 0;
 if(p[17]){fmer_midi_settings_t value;memcpy(value.value,p+18,8);if(!fmer_midi_settings_valid(&value))return 0;}
 else for(i=18;i<26;i++)if(p[i])return 0;
 if(modern){if(p[26]||p[27])return 0;if(p[7]=='4'&&fmer_native_rd16(p+40)>=720u)return 0;for(i=p[7]=='4'?42u:40u;i<48;i++)if(p[i])return 0;}
 else for(i=26;i<32;i++)if(p[i])return 0;
 return 1;
}
static void fmer_bank_release_index(fmer_store_t *s,uint32_t id)
{
 if(s->slot[id].cell!=FMER_STORE_NO_CELL){memset(&s->slot[id],0,sizeof s->slot[id]);s->slot[id].cell=FMER_STORE_NO_CELL;--s->valid_slots;}
}
static uint32_t fmer_bank_mount(fmer_bank_t *b,fmer_store_t *s)
{
 uint32_t n,g,result;uint64_t latest=0,project_latest=0;
 memset(b,0,sizeof *b);b->layout=s->valid_slots?2:3;b->latest_slot=b->latest_project=FMER_STORE_NO_SLOT;fmer_midi_defaults(&b->midi);
 result=fmer_store_load(s,FMER_BANK_META,s->scratch,sizeof s->scratch,&n);
 if(result!=FMER_STORE_EMPTY) {
  if(result!=FMER_STORE_OK)return result;if(!fmer_bank_meta_valid(s->scratch,n))return FMER_STORE_VERIFY;
  b->layout=n==48?3:2;b->epoch[0]=fmer_store_rd32(s->scratch+8);b->epoch[1]=fmer_store_rd32(s->scratch+12);
  b->user_empty=s->scratch[16];b->meta_generation=s->slot[FMER_BANK_META].generation;
  if(s->scratch[17])memcpy(b->midi.value,s->scratch+18,8);
  if(n==48u&&s->scratch[7]=='4')b->fx_default=fmer_native_rd16(s->scratch+40);
  if(b->layout==3){b->project_epoch=fmer_store_rd32(s->scratch+28);b->layout_generation=fmer_store_rd64(s->scratch+32);if(b->layout_generation>b->meta_generation)return FMER_STORE_VERIFY;}
 }
 for(g=0;g<64;g++) {
  if(b->layout==3&&s->slot[g].generation<=b->layout_generation){fmer_bank_release_index(s,g);continue;}
  result=fmer_store_load(s,g,s->scratch,sizeof s->scratch,&n);if(result==FMER_STORE_EMPTY)continue;if(result!=FMER_STORE_OK)return result;
  if(b->layout==2){
   if(!fmer_bank_legacy_group_valid(s->scratch,n,g))return FMER_STORE_VERIFY;
   if(fmer_store_rd32(s->scratch+12)!=b->epoch[g/32])continue;
   if(s->slot[g].generation>latest){latest=s->slot[g].generation;b->latest_slot=(uint16_t)(g*2+s->scratch[11]);}
  }else if(g<16){
   if(!fmer_bank_group_valid(s->scratch,n,g))return FMER_STORE_VERIFY;
   if(fmer_store_rd32(s->scratch+12)!=b->epoch[g/8]){fmer_bank_release_index(s,g);continue;}
   if(s->slot[g].generation>latest){latest=s->slot[g].generation;b->latest_slot=(uint16_t)(g*8+s->scratch[11]);}
  }else if(g<32){
   if(!fmer_bank_project_valid(s->scratch,n,g-16))return FMER_STORE_VERIFY;
   if(fmer_store_rd32(s->scratch+12)!=b->project_epoch){fmer_bank_release_index(s,g);continue;}
   if(s->slot[g].generation>project_latest){project_latest=s->slot[g].generation;b->latest_project=(uint16_t)(g-16);}
  }else return FMER_STORE_VERIFY;
 }
 return FMER_STORE_OK;
}
static uint32_t fmer_bank_load(fmer_bank_t *b,fmer_store_t *s,uint32_t slot,uint8_t *wire,fmer_bank_default_t original)
{
 uint32_t n,result,g=slot/(b->layout==2?2:8);
 if(slot>=128)return FMER_STORE_ARGUMENT;result=fmer_store_load(s,g,s->scratch,sizeof s->scratch,&n);
 if(result!=FMER_STORE_EMPTY){
  if(result!=FMER_STORE_OK)return result;
  if(b->layout==2){
   if(!fmer_bank_legacy_group_valid(s->scratch,n,g))return FMER_STORE_VERIFY;
   if(fmer_store_rd32(s->scratch+12)==b->epoch[slot/64]&&(s->scratch[10]&(1u<<(slot%2))))
    return fmer_bank_legacy_unpack(s->scratch+32+(slot%2)*(s->scratch[8]==1?FMER_BANK_COMPACT_V1:s->scratch[8]==2?FMER_BANK_COMPACT_V2:FMER_BANK_COMPACT_V3),wire)?FMER_STORE_OK:FMER_STORE_VERIFY;
  }else{
   if(!fmer_bank_group_valid(s->scratch,n,g))return FMER_STORE_VERIFY;
   if(fmer_store_rd32(s->scratch+12)==b->epoch[slot/64]&&(s->scratch[10]&(1u<<(slot%8))))
    return fmer_bank_sound_unpack(s->scratch+32+(slot%8)*FMER_BANK_SOUND,wire)?FMER_STORE_OK:FMER_STORE_VERIFY;
  }
 }
 if(slot<64&&b->user_empty)return FMER_STORE_EMPTY;return original(slot%64,wire)?FMER_STORE_OK:FMER_STORE_VERIFY;
}
static uint32_t fmer_bank_initialize(fmer_bank_t *,fmer_store_t *);
static uint32_t fmer_bank_save(fmer_bank_t *b,fmer_store_t *s,uint32_t slot,const uint8_t *wire)
{
 uint32_t n,result,g=slot/8;
 if(slot>=128||fmer_native_validate(wire,FMER_NATIVE_BYTES))return FMER_STORE_ARGUMENT;
 if(b->layout!=3)return FMER_STORE_NOT_READY;
 if(!b->meta_generation){result=fmer_bank_initialize(b,s);if(result)return result;}
 result=fmer_store_load(s,g,s->scratch,sizeof s->scratch,&n);if(result!=FMER_STORE_EMPTY&&result!=FMER_STORE_OK)return result;
 if(result==FMER_STORE_OK&&!fmer_bank_group_valid(s->scratch,n,g))return FMER_STORE_VERIFY;
 if(result==FMER_STORE_EMPTY||fmer_store_rd32(s->scratch+12)!=b->epoch[slot/64]){
  memset(s->scratch,0,FMER_BANK_GROUP);memcpy(s->scratch,"FMERINS1",8);s->scratch[8]=1;s->scratch[9]=(uint8_t)g;fmer_store_wr32(s->scratch+12,b->epoch[slot/64]);
 }
 s->scratch[10]|=1u<<(slot%8);s->scratch[11]=(uint8_t)(slot%8);fmer_bank_sound_pack(wire,s->scratch+32+(slot%8)*FMER_BANK_SOUND);
 result=fmer_store_save(s,g,s->scratch,FMER_BANK_GROUP);if(!result)b->latest_slot=(uint16_t)slot;return result;
}
static uint32_t fmer_bank_project_load(fmer_bank_t *b,fmer_store_t *s,uint32_t project,uint8_t *wire)
{
 uint32_t n,result;if(project>=16)return FMER_STORE_ARGUMENT;if(b->layout!=3)return FMER_STORE_NOT_READY;
 result=fmer_store_load(s,16+project,s->scratch,sizeof s->scratch,&n);if(result)return result;
 if(!fmer_bank_project_valid(s->scratch,n,project))return FMER_STORE_VERIFY;
 if(fmer_store_rd32(s->scratch+12)!=b->project_epoch)return FMER_STORE_EMPTY;
 return fmer_bank_unpack(s->scratch+32,wire)?FMER_STORE_OK:FMER_STORE_VERIFY;
}
static uint32_t fmer_bank_project_save(fmer_bank_t *b,fmer_store_t *s,uint32_t project,const uint8_t *wire)
{
 uint32_t result;if(project>=16||fmer_native_validate(wire,FMER_NATIVE_BYTES))return FMER_STORE_ARGUMENT;if(b->layout!=3)return FMER_STORE_NOT_READY;
 if(!b->meta_generation){result=fmer_bank_initialize(b,s);if(result)return result;}
 memset(s->scratch,0,32);memcpy(s->scratch,"FMERPRJ1",8);s->scratch[8]=(uint8_t)project;fmer_store_wr32(s->scratch+12,b->project_epoch);
 fmer_bank_pack(wire,s->scratch+32);result=fmer_store_save(s,16+project,s->scratch,FMER_BANK_PROJECT);
 if(!result)b->latest_project=(uint16_t)project;return result;
}
static void fmer_bank_meta(const fmer_bank_t *b,uint8_t meta[48])
{
 memset(meta,0,48);memcpy(meta,"FMERBNK4",8);fmer_native_wr16(meta+40,b->fx_default);fmer_store_wr32(meta+8,b->epoch[0]);fmer_store_wr32(meta+12,b->epoch[1]);
 meta[16]=(uint8_t)b->user_empty;meta[17]=1;memcpy(meta+18,b->midi.value,8);fmer_store_wr32(meta+28,b->project_epoch);fmer_store_wr64(meta+32,b->layout_generation);
}
/* Explicit migration/reset. Only this committed barrier releases old current
 * records for reclamation. Foreign sectors remain quarantined by the journal. */
static uint32_t fmer_bank_initialize(fmer_bank_t *b,fmer_store_t *s)
{
 uint8_t meta[48];uint32_t result;fmer_bank_t fresh=*b;
 if(s->generation==UINT64_MAX)return FMER_STORE_LIMIT;
 fresh.epoch[0]=fresh.epoch[1]=fresh.user_empty=fresh.project_epoch=0;fresh.layout_generation=s->generation+1;
 fmer_bank_meta(&fresh,meta);result=fmer_store_save(s,FMER_BANK_META,meta,sizeof meta);if(!result)result=fmer_bank_mount(b,s);return result;
}
static uint32_t fmer_bank_reset(fmer_bank_t *b,fmer_store_t *s,uint32_t action)
{
 uint8_t meta[48];uint32_t bank=action==3?1:0,result;
 if(action<3||action>5)return FMER_STORE_ARGUMENT;if(b->layout!=3)return FMER_STORE_NOT_READY;
 if(b->epoch[bank]==UINT32_MAX)return FMER_STORE_LIMIT;
 fmer_bank_meta(b,meta);fmer_store_wr32(meta+8+4*bank,b->epoch[bank]+1);
 if(bank==0)meta[16]=(uint8_t)(action==5);
 result=fmer_store_save(s,FMER_BANK_META,meta,sizeof meta);if(!result)result=fmer_bank_mount(b,s);return result;
}
static uint32_t fmer_bank_reset_projects(fmer_bank_t *b,fmer_store_t *s)
{
 uint8_t meta[48];uint32_t result;if(b->layout!=3)return FMER_STORE_NOT_READY;if(b->project_epoch==UINT32_MAX)return FMER_STORE_LIMIT;
 fmer_bank_meta(b,meta);fmer_store_wr32(meta+28,b->project_epoch+1);result=fmer_store_save(s,FMER_BANK_META,meta,sizeof meta);
 if(!result)result=fmer_bank_mount(b,s);return result;
}
static uint32_t fmer_bank_save_midi(fmer_bank_t *b,fmer_store_t *s,const fmer_midi_settings_t *settings)
{
 uint8_t meta[48];uint32_t result;if(!fmer_midi_settings_valid(settings))return FMER_STORE_ARGUMENT;if(b->layout!=3)return FMER_STORE_NOT_READY;
 fmer_bank_meta(b,meta);memcpy(meta+18,settings->value,8);result=fmer_store_save(s,FMER_BANK_META,meta,sizeof meta);
 if(!result)result=fmer_bank_mount(b,s);return result;
}
/* A global reset target; independent of both instrument and project epochs. */
static uint32_t fmer_bank_save_fx_default(fmer_bank_t *b,fmer_store_t *s,uint32_t rank)
{
 uint8_t meta[48];uint32_t result;if(rank>=720u)return FMER_STORE_ARGUMENT;if(b->layout!=3)return FMER_STORE_NOT_READY;
 fmer_bank_meta(b,meta);fmer_native_wr16(meta+40,(uint16_t)rank);
 result=fmer_store_save(s,FMER_BANK_META,meta,sizeof meta);if(!result)result=fmer_bank_mount(b,s);return result;
}
#endif
