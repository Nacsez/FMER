#include <cstdint>
#include <vector>
#include <cstdio>
#include <cstdlib>
static unsigned checks;
static void check(bool v,const char* why){++checks;if(!v){std::fprintf(stderr,"FAIL %s\n",why);std::exit(1);}}
static struct{uint8_t st,need,got,d0,sysex;uint32_t msgs,drops;}um;
static struct{uint32_t config=1,sx_on;}usb;
static uint32_t midi_in_overflow,sx_collect,updating,mo_w,mo_r,midi_tx_overflows,midi_tx_recovery,midi_tx_stop_pending;
static constexpr unsigned MQ=64;
static uint32_t output_queue[MQ];
static std::vector<uint32_t> input,source,sysex;
static int midi_enqueue(uint32_t p,uint32_t s){input.push_back(p);source.push_back(s);return 1;}
static void sysex_byte(uint8_t b){sysex.push_back(b);}
static void midi_out_event(uint32_t p){check(mo_w-mo_r<MQ,"never exceed TX capacity");output_queue[mo_w++%MQ]=p;}
#define FELUCCA_OTA 1
#include "midi_io.inc"
int main(){
 for(uint32_t s:{0xf8,0xfa,0xfb,0xfc,0xfe,0xff}){midi_in_event(15|(s<<8));check(input.back()==(15|(s<<8))&&source.back()==1,"USB realtime source retained");um_byte(s);check(source.back()==2,"TRS realtime source retained");}
 midi_in_event(3|(0xf2<<8)|(12<<16)|(3<<24));check(input.back()==0x030cf203,"USB Song Position exact14bits");
 auto n=input.size();midi_in_event(3|(0xf2<<8)|(128<<16));check(input.size()==n,"malformed SPP rejected");
 um_byte(0x90);um_byte(60);um_byte(0xf8);um_byte(100);um_byte(64);um_byte(0xfe);um_byte(80);
 check(input.back()==0x50409009,"TRS running status survives interleaved realtime");
 um_byte(0xf2);um_byte(12);um_byte(0xf8);um_byte(3);check(input.back()==0x030cf203,"TRS Song Position with realtime interleave");
 n=input.size();um_byte(64);um_byte(100);check(input.size()==n,"SPP cancels running status");
 um_byte(0xf0);um_byte(0x22);um_byte(0x24);um_byte(0x35);um_byte(0x7f);um_byte(0xf7);check(input.size()==n,"TRS SysEx cannot invoke updater");
 check(midi_output(0xf2,12,3)==1 && output_queue[0]==0x030cf203,"output Song Position uses system-common CIN3");mo_r=mo_w=0;
 for(unsigned i=0;i<48;++i)check(midi_output(0x90,60,100),"normal TX reserve");
 check(!midi_output(0x90,61,100)&&mo_w==48,"new notes refused before release reserve");
 for(unsigned i=0;i<16;++i)check(midi_output(0x80,60,0),"reserved releases admitted");
 check(!midi_output(0x80,61,0)&&midi_tx_recovery==1,"failed release arms channel recovery");
 mo_r=mo_w;midi_output_recover();check(mo_w-mo_r==3&&!midi_tx_recovery,"draining capacity emits bounded all-notes-off recovery");
 check(output_queue[mo_r%MQ]==0x0040b00b&&output_queue[(mo_r+1)%MQ]==0x007bb00b&&output_queue[(mo_r+2)%MQ]==0x0078b00b,"recovery lifts sustain and terminates notes/sound");
 mo_w=mo_r+MQ;check(!midi_output(0xfc,0,0)&&midi_tx_stop_pending&&!midi_tx_recovery,"full queue defers Stop without spurious channel12 reset");
 mo_r=mo_w;midi_output_recover();check(mo_w-mo_r==1&&output_queue[mo_r%MQ]==0xfc0f&&!midi_tx_stop_pending,"deferred Stop delivered after drain");
 usb.config=0;midi_output_recover();check(mo_r==mo_w,"disconnect discards orphaned TX queue");
 std::printf("PASS %u exact MIDI parser/queue checks\n",checks);
}
