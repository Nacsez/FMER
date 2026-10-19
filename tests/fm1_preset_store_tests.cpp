// NOR fault model only. No device, OS flash access, or upstream code execution.
#include "../firmware/fm1/preset_store.h"
#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static unsigned checks=0, interruptions=0;
static void check(bool yes,const char *why)
{++checks;if(!yes){std::fprintf(stderr,"FAIL: %s (check %u)\n",why,checks);std::exit(1);}}
struct Nor {
 std::vector<uint8_t> bytes=std::vector<uint8_t>(0x100000,0xa5);
 long long remaining=-1;
 unsigned mutations=0, erases=0, programs=0, reads=0, fail_read=0;
 int partial_bits=-1;
 bool silent_program=false, silent_erase=false, out_of_bounds=false;
 Nor(){std::fill(bytes.begin()+FMER_STORE_LO,bytes.begin()+FMER_STORE_HI,0xff);}
 bool range(uint32_t a,uint32_t n) {if(!fmer_store_range(a,n)){out_of_bounds=true;return false;}return true;}
 bool byte(uint32_t at,uint8_t value,bool erase) {
  if(remaining==0) {
   if(partial_bits>=0){uint8_t mask=(uint8_t)((1u<<partial_bits)-1u);bytes[at]=erase?(uint8_t)(bytes[at]|mask):(uint8_t)(bytes[at]&(value|(uint8_t)~mask));}
   return false;
  }
  bytes[at]=erase?value:(uint8_t)(bytes[at]&value);++mutations;if(remaining>0)--remaining;return true;
 }
 static int read(void *v,uint32_t a,void *p,uint32_t n) {
  auto &s=*static_cast<Nor *>(v);++s.reads;if(!s.range(a,n)||s.reads==s.fail_read)return -1;
  std::memcpy(p,s.bytes.data()+a,n);return 0;
 }
 static int erase(void *v,uint32_t a) {
  auto &s=*static_cast<Nor *>(v);++s.erases;
  if(!s.range(a,4096)||(a&4095))return -1;if(s.silent_erase)return 0;
  for(unsigned i=0;i<4096;i++)if(!s.byte(a+i,255,true))return -1;return 0;
 }
 static int program(void *v,uint32_t a,const void *p,uint32_t n) {
  auto &s=*static_cast<Nor *>(v);++s.programs;auto b=static_cast<const uint8_t *>(p);
  if(!n||n>256||((a&255)+n)>256||!s.range(a,n))return -1;if(s.silent_program)return 0;
  for(unsigned i=0;i<n;i++){if((s.bytes[a+i]&b[i])!=b[i])return -1;if(!s.byte(a+i,b[i],false))return -1;}return 0;
 }
 fmer_store_io_t io(){return {this,read,erase,program};}
};
static fmer_store_result_t mount(fmer_store_t &s,Nor &n){auto io=n.io();return fmer_store_mount(&s,&io);}
static std::vector<uint8_t> payload(unsigned seed,unsigned length)
{std::vector<uint8_t> p(length);for(unsigned i=0;i<length;i++)p[i]=(uint8_t)((seed*37+i*17+(i>>3)*9)%251);return p;}
static bool loaded(fmer_store_t &s,unsigned slot,const std::vector<uint8_t> &p)
{std::array<uint8_t,3072> dst{};uint32_t n=0;return fmer_store_load(&s,slot,dst.data(),dst.size(),&n)==FMER_STORE_OK&&n==p.size()&&std::equal(p.begin(),p.end(),dst.begin());}
static void protected_unchanged(const Nor &n)
{
 check(std::all_of(n.bytes.begin(),n.bytes.begin()+FMER_STORE_LO,[](uint8_t x){return x==0xa5;}),"all lower protected bytes intact");
 check(std::all_of(n.bytes.begin()+FMER_STORE_HI,n.bytes.end(),[](uint8_t x){return x==0xa5;}),"OTA/BTIF/USR/key and upper bytes intact");
 check(!n.out_of_bounds,"all callbacks within qualified journal region");
 for(unsigned i=0;i<FMER_STORE_CELLS;i++)check(std::all_of(n.bytes.begin()+fmer_store_address(i)+0xf00,n.bytes.begin()+fmer_store_address(i)+0x1000,[](uint8_t x){return x==255;}),"loader record scan locations stay erased");
}
static void basic()
{
 Nor n;fmer_store_t s{};auto a=payload(2,784),b=payload(7,3072);std::array<uint8_t,3072> out{};out.fill(42);uint32_t len=777,crc=0;
 check(mount(s,n)==FMER_STORE_OK&&s.blank_cells==73&&s.latest_slot==FMER_STORE_NO_SLOT,"blank mount is read only");
 check(n.programs==0&&n.erases==0,"mount never mutates flash");
 check(fmer_store_region_crc(&s,&crc)==FMER_STORE_OK&&crc==fmer_store_crc(n.bytes.data()+FMER_STORE_LO,FMER_STORE_HI-FMER_STORE_LO),"whole physical partition CRC");
 check(fmer_store_load(&s,0,out.data(),out.size(),&len)==FMER_STORE_EMPTY&&len==777&&out[0]==42,"empty load leaves outputs untouched");
 check(fmer_store_save(&s,64,a.data(),a.size())==FMER_STORE_ARGUMENT,"out-of-range ID refused");
 check(fmer_store_save(&s,0,a.data(),0)==FMER_STORE_ARGUMENT,"empty payload refused");
 check(fmer_store_save(&s,0,a.data(),3073)==FMER_STORE_ARGUMENT,"oversized payload refused before read");
 check(fmer_store_save(&s,0,a.data(),a.size())==FMER_STORE_OK&&loaded(s,0,a),"native-sized record round trip");
 check(s.generation==1&&s.valid_slots==1&&s.latest_slot==0&&s.blank_cells==72,"directory metadata after commit");
 check(fmer_store_load(&s,0,out.data(),100,&len)==FMER_STORE_SIZE&&len==777&&out[0]==42,"short destination unchanged");
 check(fmer_store_save(&s,63,b.data(),b.size())==FMER_STORE_OK&&loaded(s,63,b),"maximum payload and highest ID");
 check(mount(s,n)==FMER_STORE_OK&&s.generation==2&&s.latest_slot==63&&loaded(s,0,a)&&loaded(s,63,b),"reboot scan restores both exact payloads");
 auto prev=n.bytes;
 check(fmer_store_save(&s,0,b.data(),b.size())==FMER_STORE_OK&&loaded(s,0,b),"overwrite new generation");
 check(std::equal(prev.begin()+FMER_STORE_LO,prev.begin()+FMER_STORE_LO+4096,n.bytes.begin()+FMER_STORE_LO),"previous current sector retained after commit");
 protected_unchanged(n);
 std::printf("PASS basic, bounds, reboot, exact readback\n");
}
static void capacity_and_foreign()
{
 Nor n;fmer_store_t s{};auto p=payload(3,1200);
 n.bytes[FMER_STORE_LO+3]=0;check(mount(s,n)==FMER_STORE_FOREIGN&&s.foreign_cells==1,"unknown format quarantined");
 auto foreign=std::vector<uint8_t>(n.bytes.begin()+FMER_STORE_LO,n.bytes.begin()+FMER_STORE_LO+4096);
 for(unsigned i=0;i<64;i++)check(fmer_store_save(&s,i,p.data(),p.size())==FMER_STORE_OK,"all 64 slots with quarantine");
 for(unsigned i=0;i<200;i++){auto q=payload(i,784+i%2200);check(fmer_store_save(&s,i%64,q.data(),q.size())==FMER_STORE_OK,"stale-cell reclamation under full logical capacity");}
 check(mount(s,n)==FMER_STORE_FOREIGN&&s.valid_slots==64&&s.foreign_cells==1,"full directory reboot and visible quarantine");
 check(std::equal(foreign.begin(),foreign.end(),n.bytes.begin()+FMER_STORE_LO),"foreign cell never erased or programmed");
 protected_unchanged(n);
 Nor full;for(unsigned i=0;i<10;i++)full.bytes[fmer_store_address(i)]=0;
 check(mount(s,full)==FMER_STORE_FOREIGN,"foreign capacity is explicit");
 for(unsigned i=0;i<63;i++)check(fmer_store_save(&s,i,p.data(),p.size())==FMER_STORE_OK,"63 available physical records");
 auto snapshot=full.bytes;
 check(fmer_store_save(&s,63,p.data(),p.size())==FMER_STORE_FULL,"new slot refuses exhausted spare capacity");
 check(fmer_store_save(&s,0,p.data(),p.size())==FMER_STORE_FULL,"overwrite refuses to erase last committed copy");
 check(full.bytes==snapshot&&loaded(s,0,p),"FULL preserves every committed byte");
 std::printf("PASS 64 slots, rotation, quarantine, full refusal\n");
}
static void failures_and_corruption()
{
 Nor n;fmer_store_t s{};auto old=payload(1,784),fresh=payload(2,1600);mount(s,n);
 check(fmer_store_save(&s,4,old.data(),old.size())==FMER_STORE_OK,"baseline record");
 n.silent_program=true;check(fmer_store_save(&s,4,fresh.data(),fresh.size())==FMER_STORE_VERIFY&&!s.mounted,"silent write failure never reports saved");
 n.silent_program=false;check(mount(s,n)==FMER_STORE_OK&&loaded(s,4,old),"silent write failure preserves original");
 check(fmer_store_save(&s,4,fresh.data(),fresh.size())==FMER_STORE_OK,"new valid commit");
 auto at=fmer_store_address(s.slot[4].cell);n.bytes[at+300]^=1;
 check(mount(s,n)==FMER_STORE_OK&&s.incomplete_cells==1&&loaded(s,4,old),"corrupt newest payload falls back to prior valid record");
 n.fail_read=n.reads+1;check(mount(s,n)==FMER_STORE_IO&&!s.mounted,"mount I/O error blocks writes");
 check(fmer_store_save(&s,0,old.data(),old.size())==FMER_STORE_NOT_READY,"unmounted write rejected");
 n.fail_read=0;check(mount(s,n)==FMER_STORE_OK,"mount recovers after read fault");
 // Returning an I/O error after commit is ambiguous; reboot may find the NEW
 // complete record. The API must not reuse its old directory in that case.
 Nor reference=n;mount(s,reference);reference.reads=0;
 check(fmer_store_save(&s,4,fresh.data(),fresh.size())==FMER_STORE_OK,"post-commit read-failure reference");
 const unsigned final_read=reference.reads;
 mount(s,n);n.reads=0;n.fail_read=final_read;
 check(fmer_store_save(&s,4,fresh.data(),fresh.size())==FMER_STORE_VERIFY&&!s.mounted,"post-commit verification failure reports uncertainty");
 n.fail_read=0;check(mount(s,n)==FMER_STORE_OK&&loaded(s,4,fresh),"reboot resolves acknowledged-error record to new exact state");
 s.generation=UINT64_MAX;auto before=n.bytes;
 check(fmer_store_save(&s,1,old.data(),old.size())==FMER_STORE_LIMIT&&n.bytes==before,"generation exhaustion refuses without wrap");
 // A CRC-valid equal-generation fork cannot be produced by this writer, but
 // must never be resolved by whichever physical sector happens to scan first.
 Nor fork;mount(s,fork);check(fmer_store_save(&s,2,old.data(),old.size())==0,"fork fixture original");
 const unsigned first=s.slot[2].cell;
 check(fmer_store_save(&s,2,fresh.data(),fresh.size())==0,"fork fixture successor");
 const unsigned second=s.slot[2].cell;auto *h=fork.bytes.data()+fmer_store_address(second)+32;
 fmer_store_wr64(h+12,1);fmer_store_wr32(h+28,fmer_store_crc(h,28));
 check(mount(s,fork)==FMER_STORE_FOREIGN&&s.foreign_cells==2&&s.slot[2].conflict,"equal-generation conflict quarantines BOTH cells");
 std::array<uint8_t,3072> output{};uint32_t count=0;
 check(fmer_store_load(&s,2,output.data(),output.size(),&count)==FMER_STORE_VERIFY,"ambiguous slot refuses arbitrary load");
 const auto fork_bytes=fork.bytes;
 check(fmer_store_save(&s,2,old.data(),old.size())==FMER_STORE_VERIFY&&fork.bytes==fork_bytes,"ambiguous slot requires deliberate recovery");
 check(fmer_store_save(&s,3,old.data(),old.size())==FMER_STORE_OK&&loaded(s,3,old),"other slots still usable after fork quarantine");
 check(s.cell[first]==2&&s.cell[second]==2,"fork sectors remain quarantined");
 std::printf("PASS read/program faults, corruption fallback, generation limit\n");
}
static void first_save_interruptions()
{
 auto fresh=payload(77,784);
 for(unsigned cut=0;cut<=32+784+32;cut++) {
  Nor n;fmer_store_t s{};mount(s,n);n.remaining=cut;
  fmer_store_save(&s,3,fresh.data(),fresh.size());n.remaining=-1;
  auto m=mount(s,n);check(m==FMER_STORE_OK||m==FMER_STORE_FOREIGN,"first-save torn ownership is quarantined");
  if(s.slot[3].cell!=FMER_STORE_NO_CELL)check(loaded(s,3,fresh),"first-save committed state is exact");
  check(fmer_store_save(&s,3,fresh.data(),fresh.size())==FMER_STORE_OK&&loaded(s,3,fresh),"first save can retry in a spare");
  ++interruptions;
 }
 std::printf("PASS first-save interruption and retry at every byte\n");
}
static void cut_case(const Nor &baseline,const std::array<std::vector<uint8_t>,64> &old,
                     const std::vector<uint8_t> &fresh,unsigned cut,int bits)
{
 Nor n=baseline;n.remaining=cut;n.mutations=0;n.partial_bits=bits;fmer_store_t s{};
 auto m=mount(s,n);check(m==FMER_STORE_OK,"cut fixture mounted");
 auto r=fmer_store_save(&s,0,fresh.data(),fresh.size());
 if(r!=FMER_STORE_OK)check(!s.mounted,"failed write invalidates potentially stale RAM directory");
 n.remaining=-1;n.partial_bits=-1;
 m=mount(s,n);check(m==FMER_STORE_OK||m==FMER_STORE_FOREIGN,"cut mount reconstructs owned records");
 check(loaded(s,0,old[0])||loaded(s,0,fresh),"cut yields exact previous or complete new payload, never partial");
 for(unsigned id=1;id<64;id++)check(loaded(s,id,old[id]),"unrelated committed slot survives cut");
 // A quarantine never prevents future writes while a spare remains.
 check(fmer_store_save(&s,0,fresh.data(),fresh.size())==FMER_STORE_OK&&loaded(s,0,fresh),"save resumes using spare after reboot");
 check(!n.out_of_bounds,"fault-path addresses bounded");++interruptions;
}
static void interruption_sweep()
{
 Nor n;fmer_store_t s{};std::array<std::vector<uint8_t>,64> old;
 mount(s,n);for(unsigned i=0;i<64;i++){old[i]=payload(i+1,64);check(fmer_store_save(&s,i,old[i].data(),old[i].size())==FMER_STORE_OK,"cut fixture64 slots");}
 // Consume the nine blank spares. The next write reclaims a stale, never-current sector.
 for(unsigned i=0;i<9;i++){old[i]=payload(i+101,64);check(fmer_store_save(&s,i,old[i].data(),old[i].size())==FMER_STORE_OK,"cut fixture fills all73 cells");}
 auto fresh=payload(250,3072);Nor probe=n;mount(s,probe);probe.mutations=0;
 check(fmer_store_save(&s,0,fresh.data(),fresh.size())==FMER_STORE_OK,"reference reclaimed write");
 const unsigned mutation_bytes=probe.mutations;check(mutation_bytes==4096+32+3072+32,"erase/owner/payload/commit mutation extent");
 for(unsigned cut=0;cut<=mutation_bytes;cut++)cut_case(n,old,fresh,cut,-1);
 // Bit-level torn owner/commit bytes as well as every byte boundary above.
 for(unsigned base: {4096u,4096u+32u+3072u})for(unsigned byte=0;byte<32;byte++)for(int bits=1;bits<8;bits++)cut_case(n,old,fresh,base+byte,bits);
 protected_unchanged(probe);
 std::printf("PASS %u rebooted byte/bit interruptions including stale-sector reclamation\n",interruptions);
}
int main()
{
 static_assert(FMER_STORE_PAYLOAD_OFFSET+FMER_STORE_PAYLOAD_MAX<=0xf00,"never touch SPL scan suffix");
 basic();capacity_and_foreign();failures_and_corruption();first_save_interruptions();interruption_sweep();
 std::printf("PASS all %u assertions; fixed store state %zu bytes; no device I/O\n",checks,sizeof(fmer_store_t));return 0;
}
