/* SPDX-License-Identifier: GPL-3.0-only
 * Original FMER sector journal. Portable C, fixed memory, no device I/O here.
 * Call only outside audio/ISRs, with the platform's flash service exclusive.
 * All addresses are physical NOR offsets, never XIP pointers.
 *
 * A sector has an ownership header at 0, commit header at 32, payload at 256.
 * Ownership is verified first, payload is verified next, commit is last.
 * Current records are NEVER erased. Stale/prepared cells supply reclamation.
 * Unknown nonempty sectors are quarantined; mounting never formats or erases.
 * A torn ownership header consumes capacity until a separate recovery audit.
 * A failed write invalidates the in-RAM mount: remount before further use,
 * because a failed acknowledgement can still leave a committed new record.
 */
#ifndef FMER_PRESET_STORE_H
#define FMER_PRESET_STORE_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>

enum {
 FMER_STORE_LO=0x97000, FMER_STORE_HI=0xE0000,
 FMER_STORE_SECTOR=4096, FMER_STORE_PAGE=256,
 FMER_STORE_CELLS=(FMER_STORE_HI-FMER_STORE_LO)/FMER_STORE_SECTOR,
#ifdef FMER_DUAL_BANK
 FMER_STORE_SLOTS=65, FMER_STORE_PAYLOAD_MAX=3584,
#else
 FMER_STORE_SLOTS=64, FMER_STORE_PAYLOAD_MAX=3072,
#endif
 FMER_STORE_PAYLOAD_OFFSET=256, FMER_STORE_NO_SLOT=65535,
 FMER_STORE_NO_CELL=255,
#ifdef FMER_DUAL_BANK
 FMER_STORE_FORMAT=2
#else
 FMER_STORE_FORMAT=1
#endif
};
typedef enum {
 FMER_STORE_OK=0, FMER_STORE_EMPTY=1, FMER_STORE_ARGUMENT=2,
 FMER_STORE_IO=3, FMER_STORE_VERIFY=4, FMER_STORE_FULL=5,
 FMER_STORE_FOREIGN=6, FMER_STORE_LIMIT=7, FMER_STORE_SIZE=8,
 FMER_STORE_NOT_READY=9
} fmer_store_result_t;
typedef struct {
 void *context;
 int (*read)(void *,uint32_t,void *,uint32_t);
 int (*erase)(void *,uint32_t);
 int (*program)(void *,uint32_t,const void *,uint32_t);
} fmer_store_io_t;
typedef struct {
 uint64_t generation;
 uint32_t crc;
 uint16_t length;
 uint8_t cell, conflict;
} fmer_store_entry_t;
typedef struct {
 fmer_store_io_t io;
 fmer_store_entry_t slot[FMER_STORE_SLOTS];
 uint8_t cell[FMER_STORE_CELLS]; /* 0=blank, 1=ours committed, 2=foreign, 3=ours incomplete */
 uint8_t scratch[FMER_STORE_PAYLOAD_MAX];
 uint64_t generation;
 uint16_t latest_slot, valid_slots, foreign_cells, incomplete_cells, blank_cells, owned_cells;
 uint8_t mounted, cursor;
} fmer_store_t;

static uint16_t fmer_store_rd16(const uint8_t *p)
{return (uint16_t)((uint16_t)p[0]|((uint16_t)p[1]<<8));}
static uint32_t fmer_store_rd32(const uint8_t *p)
{return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static uint64_t fmer_store_rd64(const uint8_t *p)
{return (uint64_t)fmer_store_rd32(p)|((uint64_t)fmer_store_rd32(p+4)<<32);}
static void fmer_store_wr16(uint8_t *p,uint16_t v)
{p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void fmer_store_wr32(uint8_t *p,uint32_t v)
{p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);p[2]=(uint8_t)(v>>16);p[3]=(uint8_t)(v>>24);}
static void fmer_store_wr64(uint8_t *p,uint64_t v)
{fmer_store_wr32(p,(uint32_t)v);fmer_store_wr32(p+4,(uint32_t)(v>>32));}
static uint32_t fmer_store_crc_update(uint32_t c,const void *data,uint32_t length)
{
 const uint8_t *p=(const uint8_t *)data;uint32_t b;
 while(length--) {c^=*p++;for(b=0;b<8u;b++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}
 return c;
}
static uint32_t fmer_store_crc(const void *data,uint32_t length)
{return fmer_store_crc_update(0xffffffffu,data,length)^0xffffffffu;}
static int fmer_store_range(uint32_t address,uint32_t length)
{return address>=FMER_STORE_LO && address<=FMER_STORE_HI && length<=FMER_STORE_HI-address;}
static uint32_t fmer_store_address(uint32_t cell)
{return FMER_STORE_LO+cell*FMER_STORE_SECTOR;}
static int fmer_store_read(fmer_store_t *s,uint32_t address,void *dst,uint32_t n)
{return !fmer_store_range(address,n)||s->io.read(s->io.context,address,dst,n);}
static int fmer_store_program(fmer_store_t *s,uint32_t address,const void *p,uint32_t n)
{
 return !n||n>FMER_STORE_PAGE||((address&255u)+n)>256u||!fmer_store_range(address,n)||
  s->io.program(s->io.context,address,p,n);
}
static void fmer_store_owner(uint32_t cell,uint8_t h[32])
{
 memset(h,0xff,32);memcpy(h,"FMERJNL1",8);
 h[7]=(uint8_t)('0'+FMER_STORE_FORMAT);
 fmer_store_wr16(h+8,FMER_STORE_FORMAT);fmer_store_wr16(h+10,32);
 fmer_store_wr32(h+12,fmer_store_address(cell));
 fmer_store_wr32(h+16,FMER_STORE_LO);fmer_store_wr32(h+20,FMER_STORE_HI);
 fmer_store_wr16(h+24,FMER_STORE_PAYLOAD_MAX);fmer_store_wr16(h+26,FMER_STORE_SLOTS);
 fmer_store_wr32(h+28,fmer_store_crc(h,28));
}
static int fmer_store_commit_valid(const uint8_t h[32])
{
 return !memcmp(h,"FMERSAV1",8) && fmer_store_rd16(h+8)<FMER_STORE_SLOTS &&
  fmer_store_rd16(h+10)>0 && fmer_store_rd16(h+10)<=FMER_STORE_PAYLOAD_MAX &&
  fmer_store_rd64(h+12)>0 && fmer_store_rd32(h+24)==0xffffffffu &&
  fmer_store_rd32(h+28)==fmer_store_crc(h,28);
}
static int fmer_store_blank(fmer_store_t *s,uint32_t cell)
{
 uint8_t b[256];uint32_t off,i;
 for(off=0;off<FMER_STORE_SECTOR;off+=sizeof b) {
  if(fmer_store_read(s,fmer_store_address(cell)+off,b,sizeof b))return -1;
  for(i=0;i<sizeof b;i++)if(b[i]!=0xffu)return 0;
 }
 return 1;
}
/* Mount returns FOREIGN as a warning while retaining readable slots and usable
 * cells. A write returns FULL if no spare exists; unknown cells are never erased.
 * In an entirely owned partition, 64 latest records leave 9 spare cells.
 * Older data-format versions must be deliberately migrated outside this codec. */
static fmer_store_result_t fmer_store_mount(fmer_store_t *s,const fmer_store_io_t *io)
{
 uint8_t owner[32],head[64];uint32_t cell,id,length,crc;uint64_t generation;
 fmer_store_io_t callbacks;
 if(!s||!io||!io->read||!io->erase||!io->program)return FMER_STORE_ARGUMENT;
 callbacks=*io;memset(s,0,sizeof *s);s->io=callbacks;s->latest_slot=FMER_STORE_NO_SLOT;
 for(id=0;id<FMER_STORE_SLOTS;id++)s->slot[id].cell=FMER_STORE_NO_CELL;
 for(cell=0;cell<FMER_STORE_CELLS;cell++) {
  int blank;
  if(fmer_store_read(s,fmer_store_address(cell),head,sizeof head))return FMER_STORE_IO;
  fmer_store_owner(cell,owner);
  if(memcmp(head,owner,32)) {
   blank=fmer_store_blank(s,cell);if(blank<0)return FMER_STORE_IO;
   if(!blank) {s->cell[cell]=2;++s->foreign_cells;}else ++s->blank_cells;
   continue;
  }
  s->cell[cell]=1;++s->owned_cells;
  if(!fmer_store_commit_valid(head+32)) {s->cell[cell]=3;++s->incomplete_cells;continue;}
  id=fmer_store_rd16(head+40);length=fmer_store_rd16(head+42);
  generation=fmer_store_rd64(head+44);crc=fmer_store_rd32(head+52);
  if(fmer_store_read(s,fmer_store_address(cell)+FMER_STORE_PAYLOAD_OFFSET,s->scratch,length))return FMER_STORE_IO;
  if(fmer_store_crc(s->scratch,length)!=crc) {s->cell[cell]=3;++s->incomplete_cells;continue;}
  if(generation>s->generation) {
   s->generation=generation;s->cursor=(uint8_t)((cell+1u)%FMER_STORE_CELLS);
  }
  if(s->slot[id].conflict) {
   s->cell[cell]=2;++s->foreign_cells;--s->owned_cells;continue;
  }
  if(s->slot[id].cell!=FMER_STORE_NO_CELL && s->slot[id].generation==generation &&
     (s->slot[id].crc!=crc || s->slot[id].length!=length)) {
   /* Conflicting valid records are not resolved by physical address. Preserve
    * both sectors, refuse this slot, and allow unrelated slots to work. */
   s->cell[s->slot[id].cell]=2;s->cell[cell]=2;
   s->foreign_cells+=2;s->owned_cells-=2;--s->valid_slots;
   s->slot[id].cell=FMER_STORE_NO_CELL;s->slot[id].conflict=1;continue;
  }
  if(s->slot[id].cell==FMER_STORE_NO_CELL || generation>s->slot[id].generation) {
   if(s->slot[id].cell==FMER_STORE_NO_CELL)++s->valid_slots;
   s->slot[id].cell=(uint8_t)cell;s->slot[id].length=(uint16_t)length;
   s->slot[id].crc=crc;s->slot[id].generation=generation;
  }
 }
 {uint64_t latest=0;
  for(id=0;id<FMER_STORE_SLOTS;id++)if(s->slot[id].cell!=FMER_STORE_NO_CELL && s->slot[id].generation>latest) {
   latest=s->slot[id].generation;s->latest_slot=(uint16_t)id;
  }
 }
 s->mounted=1;
 return s->foreign_cells?FMER_STORE_FOREIGN:FMER_STORE_OK;
}
/* Optional exact physical-region observation for the pre-write device audit.
 * Reading this does not mount, format, repair, program or erase any cell. */
static fmer_store_result_t fmer_store_region_crc(fmer_store_t *s,uint32_t *crc)
{
 uint8_t b[256];uint32_t off,c=0xffffffffu;
 if(!s||!crc||!s->io.read)return FMER_STORE_ARGUMENT;
 for(off=FMER_STORE_LO;off<FMER_STORE_HI;off+=sizeof b) {
  if(fmer_store_read(s,off,b,sizeof b))return FMER_STORE_IO;
  c=fmer_store_crc_update(c,b,sizeof b);
 }
 *crc=c^0xffffffffu;return FMER_STORE_OK;
}
static fmer_store_result_t fmer_store_load(fmer_store_t *s,uint32_t slot,void *dst,uint32_t capacity,uint32_t *length)
{
 const fmer_store_entry_t *e;
 if(!s||!dst||!length||slot>=FMER_STORE_SLOTS)return FMER_STORE_ARGUMENT;
 if(!s->mounted)return FMER_STORE_NOT_READY;
 e=&s->slot[slot];if(e->conflict)return FMER_STORE_VERIFY;
 if(e->cell==FMER_STORE_NO_CELL)return FMER_STORE_EMPTY;
 if(e->length>capacity)return FMER_STORE_SIZE;
 if(fmer_store_read(s,fmer_store_address(e->cell)+FMER_STORE_PAYLOAD_OFFSET,s->scratch,e->length))return FMER_STORE_IO;
 if(fmer_store_crc(s->scratch,e->length)!=e->crc)return FMER_STORE_VERIFY;
 if(dst!=s->scratch)memcpy(dst,s->scratch,e->length);
 *length=e->length;return FMER_STORE_OK;
}
static int fmer_store_current_cell(const fmer_store_t *s,uint32_t cell)
{uint32_t id;for(id=0;id<FMER_STORE_SLOTS;id++)if(s->slot[id].cell==cell)return 1;return 0;}
static int fmer_store_verify_bytes(fmer_store_t *s,uint32_t address,const uint8_t *bytes,uint32_t length)
{
 uint8_t b[256];uint32_t off,n;
 for(off=0;off<length;off+=n) {
  n=length-off;if(n>sizeof b)n=sizeof b;
  if(fmer_store_read(s,address+off,b,n)||memcmp(b,bytes+off,n))return -1;
 }
 return 0;
}
static fmer_store_result_t fmer_store_save(fmer_store_t *s,uint32_t slot,const void *bytes,uint32_t length)
{
 uint8_t owner[32],commit[32];uint32_t cell,i,off,n,address;uint64_t generation;
 fmer_store_entry_t *e;
 if(!s||!bytes||slot>=FMER_STORE_SLOTS||!length||length>FMER_STORE_PAYLOAD_MAX)return FMER_STORE_ARGUMENT;
 if(!s->mounted)return FMER_STORE_NOT_READY;
 if(s->slot[slot].conflict)return FMER_STORE_VERIFY;
 if(s->generation==UINT64_MAX)return FMER_STORE_LIMIT;
 for(i=0;i<FMER_STORE_CELLS;i++) {
  cell=(s->cursor+i)%FMER_STORE_CELLS;
  if(s->cell[cell]!=2 && !fmer_store_current_cell(s,cell))break;
 }
 if(i==FMER_STORE_CELLS)return FMER_STORE_FULL;
 if(bytes!=s->scratch)memcpy(s->scratch,bytes,length);
 address=fmer_store_address(cell);generation=s->generation+1u;
 fmer_store_owner(cell,owner);memset(commit,0xff,sizeof commit);memcpy(commit,"FMERSAV1",8);
 fmer_store_wr16(commit+8,(uint16_t)slot);fmer_store_wr16(commit+10,(uint16_t)length);
 fmer_store_wr64(commit+12,generation);fmer_store_wr32(commit+20,fmer_store_crc(s->scratch,length));
 fmer_store_wr32(commit+28,fmer_store_crc(commit,28));
 /* After the first mutation any failure is potentially committed. Force a
  * fresh scan instead of allowing stale in-RAM indexes to erase newer data. */
 s->mounted=0;
 if(s->cell[cell]!=0 &&
    (!fmer_store_range(address,FMER_STORE_SECTOR)||(address&4095u)||s->io.erase(s->io.context,address)))return FMER_STORE_IO;
 if(fmer_store_blank(s,cell)!=1)return FMER_STORE_VERIFY;
 if(fmer_store_program(s,address,owner,sizeof owner))return FMER_STORE_IO;
 if(fmer_store_verify_bytes(s,address,owner,sizeof owner))return FMER_STORE_VERIFY;
 for(off=0;off<length;off+=n) {
  n=length-off;if(n>FMER_STORE_PAGE)n=FMER_STORE_PAGE;
  if(fmer_store_program(s,address+FMER_STORE_PAYLOAD_OFFSET+off,s->scratch+off,n))return FMER_STORE_IO;
 }
 if(fmer_store_verify_bytes(s,address+FMER_STORE_PAYLOAD_OFFSET,s->scratch,length))return FMER_STORE_VERIFY;
 if(fmer_store_program(s,address+32,commit,sizeof commit))return FMER_STORE_IO;
 if(fmer_store_verify_bytes(s,address+32,commit,sizeof commit)||
    fmer_store_verify_bytes(s,address+FMER_STORE_PAYLOAD_OFFSET,s->scratch,length))return FMER_STORE_VERIFY;
 e=&s->slot[slot];if(e->cell==FMER_STORE_NO_CELL)++s->valid_slots;
 e->cell=(uint8_t)cell;e->length=(uint16_t)length;e->generation=generation;e->crc=fmer_store_rd32(commit+20);
 if(s->cell[cell]==0) {--s->blank_cells;++s->owned_cells;}
 else if(s->cell[cell]==3 && s->incomplete_cells)--s->incomplete_cells;
 s->cell[cell]=1;s->generation=generation;s->latest_slot=(uint16_t)slot;
 s->cursor=(uint8_t)((cell+1u)%FMER_STORE_CELLS);s->mounted=1;
 return FMER_STORE_OK;
}
#endif
