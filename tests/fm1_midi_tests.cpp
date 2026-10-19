// Actual shared DSP boundary: routing, clock ownership and disconnect safety.
#include "../firmware/fm1/dsp_adapter.h"
#include "../core/performance.hpp"
#include "../core/synth.hpp"
#include <array>
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <algorithm>
#include <utility>
struct Msg {uint8_t s,a,b;};
static std::vector<Msg> messages;
static unsigned checks;
static void check(bool v,const char* why){++checks;if(!v){std::fprintf(stderr,"FAIL %u: %s\n",checks,why);std::exit(1);}}
static int output(uint8_t s,uint8_t a,uint8_t b){messages.push_back({s,a,b});return 1;}
static size_t count(uint8_t status){return std::count_if(messages.begin(),messages.end(),[=](Msg m){return m.s==status;});}
static void render(unsigned frames){std::array<int32_t,256> audio{};while(frames){auto n=std::min(frames,128u);fmer_dsp_render(audio.data(),n,1024);frames-=n;}}
static fmer_performance_state_t performance(){fmer_performance_state_t s{};fmer_dsp_performance(&s);return s;}
static void settings(uint8_t route,uint8_t local,uint8_t clock,uint8_t send=0,uint8_t transport=1,uint8_t cc=0){
 fmer_dsp_panic();fmer_midi_settings_t s{{route,2,local,clock,send,transport,cc,0}};
 check(fmer_dsp_set_midi_settings(&s),"valid MIDI settings");messages.clear();
}
static void edit(uint32_t id,uint16_t value){fmer_controls_t c{};fmer_dsp_get_controls(&c);c.value[id]=value;check(fmer_dsp_apply_controls(&c),"live control");}
static void routing(){
 settings(3,1,0);fmer_dsp_midi(0x90,60,100,1);check(messages.empty(),"USB input never echoes");
 fmer_dsp_midi(0x90,64,100,2);check(messages.empty(),"TRS input never echoes");
 fmer_dsp_midi(0x90,67,110,3);check(count(0x92)==1&&messages.back().a==67,"physical output follows TX channel");
 fmer_dsp_midi(0x80,67,0,3);check(count(0x82)==1,"physical release matches output channel");
 settings(3,0,0);fmer_dsp_midi(0x90,60,100,3);check(fmer_dsp_active()==0&&count(0x92)==1,"Local Off sends without local sound");
 fmer_dsp_midi(0x90,64,100,1);check(fmer_dsp_active()==1&&count(0x92)==1,"Local Off retains external sound-module input without echo");
 settings(0,1,0,0,1,1);edit(FMER_CUTOFF,1200);check(count(0xb2)==1&&messages.back().a==74,"panel cutoff emits selected CC");
 messages.clear();fmer_dsp_midi(0xb0,74,80,1);check(messages.empty(),"received CC does not feed back");
 for(auto pair:{std::pair<unsigned,unsigned>{FMER_DELAY,12},{FMER_REVERB,91},{FMER_CHORUS,93},{FMER_PHASER,95}}){
  edit(pair.first,0);messages.clear();edit(pair.first,100);
  check(messages.size()==1 && messages[0].s==0xb2 && messages[0].a==pair.second && messages[0].b==127,"shared effect output reaches canonical full scale on base channel");
  messages.clear();fmer_dsp_midi(0xb0,static_cast<uint8_t>(pair.second),64,1);check(messages.empty(),"shared FX input never echoes");
 }
 edit(FMER_SEQ_MODE,1);edit(FMER_SEQ_TRACK,2);edit(FMER_VA_CUTOFF,1200);messages.clear();edit(FMER_VA_CUTOFF,18000);
 check(messages.size()==1 && messages[0].s==0xb4 && messages[0].a==74 && messages[0].b==127,"part cutoff output uses selected track plus TX base and exact log endpoint");
 edit(FMER_SEQ_MODE,0);

 settings(3,1,0);fmer_dsp_midi(0x90,65,100,3);fmer_dsp_midi(0x90,70,100,1);
 fmer_dsp_midi_disconnected();check(fmer_dsp_active()==1,"USB disconnect retires only USB voices");
 fmer_dsp_panic();edit(FMER_ARP_ENABLE,0);check(fmer_dsp_transport(FMER_TRANSPORT_PLAY),"start local sequencer");render(7000);
 auto before=performance();fmer_dsp_midi_disconnected();render(6000);check(performance().running&&performance().seq_position!=before.seq_position,"USB disconnect preserves standalone playback");
 before=performance();check(fmer_dsp_transport(FMER_TRANSPORT_CLEAR_STEP),"live erase accepted");check(performance().seq_position==before.seq_position&&performance().running,"live erase preserves phase");
}
static void clocking(){
 settings(2,0,0,1);edit(FMER_ARP_ENABLE,0);edit(FMER_TEMPO,120);check(fmer_dsp_transport(FMER_TRANSPORT_PLAY),"internal playback starts");
 render(44100);check(count(0xfa)==1&&count(0xf8)==48,"one second at120 BPM emits exactly48 clocks and one Start");
 check(fmer_dsp_transport(FMER_TRANSPORT_STOP),"stop transport");check(count(0xfc)==1,"Stop sent once");auto n=count(0xf8);render(12000);check(count(0xf8)==n,"no outgoing clock after stop");
 settings(2,0,1,1);fmer_dsp_midi(0xfa,0,0,1);render(5000);check(performance().running&&count(0x92)==0,"external start waits for actual clock");
 for(unsigned i=0;i<24;i++){fmer_dsp_midi(0xf8,0,0,1);render(920);}
 check(performance().seq_position==3,"24 received clocks advance four sixteenths");check(count(0xf8)==0&&count(0xfa)==0,"external clock/transport never echo");
 auto pos=performance().seq_position;fmer_dsp_midi(0xfc,0,0,1);render(5000);check(!performance().running,"external Stop halts");
 fmer_dsp_midi(0xf2,2,0,1);fmer_dsp_midi(0xfb,0,0,1);fmer_dsp_midi(0xf8,0,0,1);render(128);check(performance().seq_position==2,"Song Position then Continue seeks selected pattern");
 render(30000);check(!performance().running,"clock loss stops transport");fmer_midi_metrics_t m{};fmer_dsp_midi_metrics(&m);check(m.clock_timeouts>0,"clock loss observable");
 settings(2,0,1,0,0);check(fmer_dsp_transport(FMER_TRANSPORT_PLAY),"panel play arms clock-only mode");fmer_dsp_midi(0xf8,0,0,1);render(128);check(performance().running,"external clock without transport RX runs from panel");
 fmer_dsp_midi_disconnected();check(!performance().running,"USB clock disconnect stops USB-slaved sequence");
 settings(3,0,1);edit(FMER_ARP_ENABLE,1);edit(FMER_ARP_RATE,16);edit(FMER_ARP_ORDER,0);fmer_dsp_midi(0x90,60,100,3);fmer_dsp_midi(0x90,64,100,3);fmer_dsp_midi(0xfa,0,0,1);messages.clear();
 for(unsigned i=0;i<24;i++){fmer_dsp_midi(0xf8,0,0,1);render(920);}
 check(count(0x92)==4,"clocked arp emits four sixteenths without raw-key doubles");
 const auto notes=count(0x92);render(30000);check(count(0x92)==notes,"absent clocks cannot free-run arp attacks");
}
static void wheel(){
 for(auto engine:{fmer::SynthEngine::fm,fmer::SynthEngine::va}) {
  fmer::Synth dry,wet,chunk;dry.init();wet.init();chunk.init();
  for(auto* s:{&dry,&wet,&chunk}){s->set_engine(engine);s->note_on(0,60,100);}
  wet.control_change(0,1,127);chunk.control_change(0,1,127);
  std::vector<float> a(12000),b(12000),c(12000);dry.render(a.data(),a.size());wet.render(b.data(),b.size());
  for(size_t i=0;i<c.size();i+=17)chunk.render(c.data()+i,std::min<size_t>(17,c.size()-i));
  check(a!=b&&b==c,"live modwheel audible and render-chunk invariant in both engines");
  check(!wet.stats().rejected_events,"modwheel accepted");
 }
}
int main(){check(fmer_dsp_init(),"DSP init");fmer_dsp_set_midi_output(output);routing();clocking();wheel();std::printf("PASS %u MIDI integration checks\n",checks);}
