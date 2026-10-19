// Pure semantic LED tests. No HAL or hardware I/O; physical colors/brightness
// still need an owner observation. Expected matrix is independent of renderer.
#include "../firmware/fm1/led_model.h"
#include "../firmware/fm1/led_pwm.h"
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
static void require(bool ok,const char *why){if(!ok){std::fprintf(stderr,"FAIL: %s\n",why);std::exit(1);}}
static fmer_led_state_t state(){fmer_led_state_t s{};s.family=FMER_PANEL_FAMILIES;return s;}
static void note(fmer_led_state_t &s,unsigned pitch,bool gate){s.active_pitch[pitch/32]|=1u<<(pitch%32);if(gate)s.gated_pitch[pitch/32]|=1u<<(pitch%32);}
static unsigned at(const fmer_led_frame_t &f,unsigned col,unsigned row){return (f.lit[col]&(1u<<row))?FMER_LED_LIT:(f.dim[col]&(1u<<row))?FMER_LED_DIM:FMER_LED_OFF;}
static void clean(const fmer_led_frame_t &f){for(unsigned col=0;col<11;col++){unsigned allowed=col<9?0x1eu:0x1cu;require(!(f.lit[col]&f.dim[col]),"full and dim frame bits do not overlap");require(!((f.lit[col]|f.dim[col])&~allowed),"no encoder, unknown or nonexistent LED addressed");}}
static void no_keys(const fmer_led_frame_t &f,unsigned level=FMER_LED_DIM){for(unsigned id=14;id<41;id++)require(fmer_led_key_level(&f,id)==level,"unowned note key uses ready glow or fault darkness");}
int main(){
 for(unsigned mask=0;mask<32;mask++)require(fmer_led_scan_mask(30,mask,0)==30 && fmer_led_scan_mask(30,mask,1)==(30&~mask),"half-bright scan never changes other emitters");
 fmer_led_frame_t f{};auto s=state();fmer_led_render(&s,0,&f);fmer_led_frame_t blank{};
 require(sizeof(fmer_led_frame_t)==33 && !std::memcmp(f.lit,blank.lit,sizeof f.lit),"ready glow never claims an active note");no_keys(f);
 const int matrix[4][11]={{5,11,4,10,3,9,2,8,-1,-1,-1},{34,35,36,37,38,40,39,13,7,6,12},{23,24,25,26,27,28,29,30,31,32,33},{0,1,15,14,17,16,19,18,20,21,22}};
 unsigned seen=0;for(unsigned row=1;row<=4;row++)for(unsigned col=0;col<11;col++)if(matrix[row-1][col]>=0){
  auto id=(unsigned)matrix[row-1][col];require(fmer_led_key_position(id)==((col<<3)|row),"each ID maps to audited matrix coordinates");
  s=state();if(id<14)s.physical_buttons=1u<<id;else s.physical_keys=1u<<(id-14);fmer_led_render(&s,0,&f);
  require(at(f,col,row)==(id==9?FMER_LED_DIM:FMER_LED_LIT),"every physical button/key gives feedback at its own coordinate");
  unsigned bits=0;for(unsigned c=0;c<11;c++)for(unsigned r=1;r<=4;r++)bits+=at(f,c,r)!=FMER_LED_OFF;
  require(bits==41u,"single physical input never lights an unrelated address");clean(f);seen++;
 }
 require(seen==41 && FMER_LED_PLAY_GREEN==65 && fmer_led_key_position(12)==82,"41 unique key emitters and separate green PLAY");
 require(fmer_led_key_position(41)==FMER_LED_NO_POSITION && fmer_led_key_level(&f,UINT_MAX)==FMER_LED_OFF,"invalid key IDs are bounded");

 const unsigned families[]={8,6,4,2,5,10,11,7,9,3};
 for(unsigned family=0;family<FMER_PANEL_FAMILIES;family++){
  s=state();s.family=family;fmer_led_render(&s,0,&f);
  unsigned expected=family==FMER_PANEL_ARP?FMER_LED_DIM:FMER_LED_LIT;
  require(fmer_led_key_level(&f,families[family])==expected,"navigation lights active family with disabled ARP and SAVE exceptions");no_keys(f);clean(f);
 }
 s=state();s.family=FMER_PANEL_PRESETS;fmer_led_render(&s,0,&f);
 require(fmer_led_key_level(&f,3)==FMER_LED_LIT && fmer_led_key_level(&f,9)==FMER_LED_DIM && at(f,8,1)==FMER_LED_OFF,
         "preset browser lights SEL confirmation without claiming a saved sound or transport");
 s=state();s.family=FMER_PANEL_SAVE;s.physical_buttons=1u<<9;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,9)==FMER_LED_LIT,"SAVE page is navigational");
 s.physical_buttons=0;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,9)==FMER_LED_LIT,"SAVE stays selected without implying a write");
 for(int octave=-3;octave<=3;octave++){
  s=state();s.octave=octave;fmer_led_render(&s,0,&f);
  require(fmer_led_key_level(&f,0)==(octave<0?(octave==-1?FMER_LED_DIM:octave==-2?FMER_LED_HALF:FMER_LED_LIT):FMER_LED_DIM) && fmer_led_key_level(&f,1)==(octave>0?(octave==1?FMER_LED_DIM:octave==2?FMER_LED_HALF:FMER_LED_LIT):FMER_LED_DIM),"octave shows direction, zero dark");
  for(unsigned i=0;i<27;i++){s=state();s.octave=octave;note(s,(unsigned)(53+(int)i+12*octave),true);fmer_led_render(&s,0,&f);
   for(unsigned k=0;k<27;k++)require(fmer_led_key_level(&f,14+k)==(k==i?FMER_LED_LIT:FMER_LED_DIM),"active pitch maps exactly within the current octave, including word boundaries");clean(f);}
 }
 s=state();note(s,52,true);note(s,80,true);note(s,0,true);note(s,127,true);fmer_led_render(&s,0,&f);no_keys(f);
 for(int extreme:{INT_MIN,INT_MAX}){s.octave=extreme;fmer_led_render(&s,0,&f);no_keys(f);clean(f);}
 s=state();note(s,60,false);fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,21)==FMER_LED_DIM,"actual release tail is dim");
 note(s,60,true);fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,21)==FMER_LED_LIT,"gated or sustained actual voice is bright");
 s.active_pitch[60/32]=0;fmer_led_render(&s,0,&f);no_keys(f);require(s.gated_pitch[60/32]!=0,"orphan gated bit cannot invent an active voice");
 s=state();s.physical_keys=1u<<7;note(s,60,false);fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,21)==FMER_LED_LIT,"physical held key wins over dim tail");clean(f);
 s.arp_enabled=1;s.arp_held=1;note(s,64,true);fmer_led_render(&s,0,&f);
 require(fmer_led_key_level(&f,21)==FMER_LED_DIM && fmer_led_key_level(&f,25)==FMER_LED_LIT,"arp held chord stays dim while actual generated gate is bright");
 note(s,60,true);fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,21)==FMER_LED_LIT,"generated gate brightens its matching held chord key");clean(f);
 s=state();s.physical_keys=(1u<<0)|(1u<<26);note(s,60,true);fmer_led_render(&s,0,&f);
 std::memset(s.active_pitch,0,sizeof s.active_pitch);std::memset(s.gated_pitch,0,sizeof s.gated_pitch);fmer_led_render(&s,0,&f);
 require(fmer_led_key_level(&f,21)==FMER_LED_DIM && fmer_led_key_level(&f,14)==FMER_LED_LIT && fmer_led_key_level(&f,40)==FMER_LED_LIT,"panic clears voice activity but physical contact feedback remains truthful");
 s.physical_keys=0;fmer_led_render(&s,0,&f);no_keys(f);

 s=state();s.seq_running=1;fmer_led_render(&s,0,&f);
 require(at(f,8,1)==FMER_LED_DIM && fmer_led_key_level(&f,11)==FMER_LED_DIM && fmer_led_key_level(&f,12)==FMER_LED_DIM,"running uses dim green PLAY and SEQ between beats");
 s.beat_on=1;fmer_led_render(&s,0,&f);require(at(f,8,1)==FMER_LED_LIT && fmer_led_key_level(&f,11)==FMER_LED_LIT,"beat pulse brightens green PLAY and SEQ");
 s.beat_on=0;s.physical_buttons=1u<<12;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,12)==FMER_LED_LIT && at(f,8,1)==FMER_LED_DIM,"PLAY physical feedback remains available during RUN");
 s.physical_buttons=0;s.seq_running=0;s.recording=1;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,13)==FMER_LED_LIT && at(f,8,1)==FMER_LED_OFF,"armed step-entry uses REC without pretending to run");
 s.recording=0;s.fine_adjust=1;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,3)==FMER_LED_LIT && fmer_led_key_level(&f,13)==FMER_LED_DIM,"fine modifier is visible and disarming clears REC");
 s=state();s.arp_enabled=1;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,10)==FMER_LED_LIT,"enabled ARP waiting for keys stays clear");
 s.arp_held=3;s.beat_on=1;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,10)==FMER_LED_DIM,"arp between gates stays dim independent of sequencer beat");
 note(s,60,true);fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,10)==FMER_LED_LIT,"arp gate has bright phase");
 s.family=FMER_PANEL_ARP;s.active_pitch[60/32]=0;s.beat_on=0;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,10)==FMER_LED_DIM,"selected ARP retains useful between-gate dimming");

 for(unsigned failed=0;failed<2;failed++){
  s=state();s.seq_running=s.recording=s.arp_enabled=s.arp_held=1;note(s,60,true);
  if(failed)s.init_failed=1;else s.audio_paused=1;
  fmer_led_render(&s,0,&f);no_keys(f,FMER_LED_OFF);require(at(f,8,1)==FMER_LED_OFF && fmer_led_key_level(&f,11)==FMER_LED_OFF && fmer_led_key_level(&f,13)==FMER_LED_OFF && fmer_led_key_level(&f,10)==FMER_LED_OFF,"fault suppresses stale musical status");
  require(fmer_led_key_level(&f,12)==FMER_LED_LIT,"fault blinks ordinary PLAY on");
  fmer_led_render(&s,250,&f);require(fmer_led_key_level(&f,12)==FMER_LED_OFF,"fault blink has dark phase");
  s.physical_buttons=(1u<<12)|(1u<<13)|(1u<<9);s.physical_keys=1;fmer_led_render(&s,250,&f);
  require(fmer_led_key_level(&f,12)==FMER_LED_LIT && fmer_led_key_level(&f,13)==FMER_LED_LIT && fmer_led_key_level(&f,9)==FMER_LED_DIM,"physical press feedback has priority during fault");
  require(fmer_led_key_level(&f,14)==FMER_LED_DIM,"arp chord contact feedback remains explicit during pause");clean(f);
 }
 s=state();s.family=FMER_PANEL_HOME;s.physical_buttons=UINT_MAX;s.physical_keys=UINT_MAX;s.fine_adjust=s.seq_running=s.recording=s.arp_enabled=s.arp_held=s.beat_on=1;
 for(unsigned i=0;i<4;i++)s.active_pitch[i]=s.gated_pitch[i]=UINT_MAX;
 for(unsigned now:{0u,249u,250u,499u,500u,UINT_MAX}){fmer_led_render(&s,now,&f);clean(f);auto copy=f;fmer_led_render(&s,now,&f);require(!std::memcmp(&copy,&f,sizeof f),"identical snapshots render deterministically without latches");}
 s=state();s.recording=1;s.count_in=1;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,13)==FMER_LED_DIM,"count-in REC dims between clicks");
 s.beat_on=1;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,13)==FMER_LED_LIT,"count-in REC follows audio beat");
 s.count_in=s.beat_on=0;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,13)==FMER_LED_LIT,"actual recording remains steady");
 s=state();s.fx_enabled=s.lfo_enabled=s.sound_dirty=1;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,2)==FMER_LED_DIM && fmer_led_key_level(&f,5)==FMER_LED_DIM && fmer_led_key_level(&f,9)==FMER_LED_DIM,"enabled effects LFO and edited sound have distinct dim status");
 s.save_busy=1;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,9)==FMER_LED_LIT,"save busy bright phase");fmer_led_render(&s,125,&f);require(fmer_led_key_level(&f,9)==FMER_LED_DIM,"save busy dim phase");
 s.save_busy=0;s.save_feedback=1;fmer_led_render(&s,125,&f);require(fmer_led_key_level(&f,9)==FMER_LED_LIT,"verified save success acknowledgement");
 s=state();s.recent_buttons=1u<<4;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,4)==FMER_LED_LIT,"short button tap stays visible briefly");s.recent_buttons=0;fmer_led_render(&s,0,&f);require(fmer_led_key_level(&f,4)==FMER_LED_DIM,"tap feedback expires without latching state");
 std::puts("FMER LED model passed: matrix, semantic priorities, pitches, arp, transport, panic and faults.");
}
