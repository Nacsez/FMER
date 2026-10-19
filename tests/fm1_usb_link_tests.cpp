#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <algorithm>
static uint32_t regs[2][32],index_,dma_n,committed,connected,disconnected;
static uint8_t *control,*rxbuf,*txbuf;
static bool attach_host=true,respond=true,ack=true;
static std::vector<uint8_t> reply;
static size_t reply_at;
static std::vector<uint32_t> out,in;
static const uint8_t config[]={9,2,36,0,1,1,0,0x80,50,9,4,1,0,2,1,3,0,0,
    9,5,1,2,64,0,0,0,0,9,5,0x81,2,64,0,0,0,0};
static const uint8_t device[]={18,1,0x10,1,0,0,0,64,9,0x12,1,0,0x10,3,1,2,0,1};
static void ul_off(){}
static void ul_attach(void *p){control=(uint8_t*)p;regs[0][15]=attach_host?0x44:0;}
static uint32_t ul_read(uint32_t r){return regs[r<16?0:index_][r];}
static void ul_write(uint32_t r,uint32_t v){
 if(r==14){index_=v;return;}
 if(r==15)return;
 regs[r<16?0:index_][r]=v;
 if(!respond)return;
 if(index_==0 && r==17){
  if(v==0x0a){
   reply.clear();reply_at=0;unsigned n=control[6]|control[7]<<8;
   if(control[1]==6){const uint8_t *p=control[3]==1?device:config;unsigned size=control[3]==1?sizeof device:sizeof config;reply.assign(p,p+std::min(n,size));}
   regs[0][17]=0;
  }else if(v==0x20){unsigned n=std::min(size_t(64),reply.size()-reply_at);std::memcpy(control,reply.data()+reply_at,n);reply_at+=n;regs[0][22]=n;regs[0][17]=1;}
  else if(v==0x60){regs[0][22]=0;regs[0][17]=1;}
  else if(v==0x42)regs[0][17]=0;
 }
 if(index_==1 && r==17 && v==1 && ack)regs[1][17]=0;
}
static void ul_dma_control(void *p,uint32_t n){control=(uint8_t*)p;dma_n=n;}
static void ul_dma_bulk(void *r,void *t){rxbuf=(uint8_t*)r;txbuf=(uint8_t*)t;}
static void ul_dma_send(void *p,uint32_t n){txbuf=(uint8_t*)p;dma_n=n;}
static void ul_rx_sync(){}
static void ul_disconnect(){disconnected++;}
static void ul_connected(){connected++;}
static int ul_midi_receive(uint32_t p){in.push_back(p);return 1;}
static uint32_t ul_midi_peek(uint8_t *p,uint32_t limit){unsigned n=std::min(unsigned(out.size()-committed),limit/4);for(unsigned i=0;i<n;i++)std::memcpy(p+i*4,&out[committed+i],4);return n*4;}
static void ul_midi_commit(uint32_t n){committed+=n;}
#include "../firmware/fm1/usb_link.h"
static void check(bool b,const char *s){if(!b){std::fprintf(stderr,"FAIL %s state=%u err=%u phase=%u stage=%u\n",s,ul.state,ul.error,ul.phase,ul.stage);std::exit(1);}}
static void fresh(){ul={};std::memset(regs,0,sizeof regs);index_=0;connected=disconnected=committed=0;out.clear();in.clear();respond=ack=attach_host=true;}
static uint32_t ready(){fresh();ul_start(0);for(unsigned t=0;t<500;t++) {ul_poll(t);if(ul.state==UL_READY)return t;}check(false,"bounded enumeration");return 0;}
int main(){
 fmer_usb_link_t s{};check(ul_configuration(&s,config,sizeof config) && s.ep_in==1 && s.ep_out==1,"MIDI endpoints found");
 for(unsigned i=0;i<sizeof config;i++)check(!ul_configuration(&s,config,i),"truncated configuration rejected");
 auto broken=std::vector<uint8_t>(config,config+sizeof config);broken[18]=0;check(!ul_configuration(&s,broken.data(),broken.size()),"zero descriptor length bounded");
 broken.assign(config,config+sizeof config);broken[21]=1;check(!ul_configuration(&s,broken.data(),broken.size()),"isochronous endpoint rejected");
 broken.assign(config,config+sizeof config);broken[22]=128;check(!ul_configuration(&s,broken.data(),broken.size()),"oversize bulk packet rejected");
 unsigned now=ready();check(connected==1 && ul.connects==1,"configure publishes ready once");
 out={0x643c9009,0x0000f80f,0x003c8008};ul_poll(++now);check(committed==0 && ul.tx_pending==3,"send retains ownership until ACK");
 ul_poll(++now);check(committed==3 && ul.tx_events==3,"ACK commits exact events");
 std::memcpy(rxbuf,out.data(),12);regs[1][22]=12;regs[1][23]=0;regs[1][20]=1;ul_poll(++now);check(in==out && ul.rx_events==3,"receive packet order preserved");
 regs[0][15]=0;ul_poll(++now);check(ul.state==UL_FAILED && ul.error==UL_DISCONNECTED,"detach reports failure and releases receiver");
 now=ready();ack=false;out={0x643c9009};ul_poll(++now);regs[1][17]=0x80;ul_poll(++now);check(committed==0,"NAK cannot dequeue");ul_poll(now+1001);check(ul.error==UL_TX_TIMEOUT && !committed,"persistent NAK bounded without duplicate commit");
 now=ready();regs[1][20]=0x40;ul_poll(++now);check(ul.error==UL_BULK_ERROR,"stall closes stream instead of dropping note-off");
 now=ready();regs[1][22]=65;regs[1][20]=1;ul_poll(++now);check(ul.error==UL_BULK_ERROR,"invalid RX length never overruns buffer");
 fresh();attach_host=false;ul_start(0);ul_poll(25);ul_poll(30026);check(ul.error==UL_NO_HOST,"missing host role times out");
 fresh();respond=false;ul_start(0);for(unsigned t=0;t<2000;t++)ul_poll(t);check(ul.error==UL_CONTROL_TIMEOUT,"unresponsive EP0 times out");
 fresh();ul_start(0xfffffff0u);ul_poll(20);check(ul.state==UL_WAIT,"uptime wrap preserves attach timing");
 std::puts("USB link descriptor, enumeration, ACK/NAK, MIDI ordering, disconnect and timeout tests passed.");
}
