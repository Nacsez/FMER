// Exercises the pure C navigation/control boundary without board I/O.
#include "../firmware/fm1/panel_model.h"
#include "../firmware/fm1/delay_timing.h"
#include <array>
#include <climits>
#include <cstdio>
#include <cstdlib>
static void require(bool ok,const char *why){if(!ok){std::fprintf(stderr,"FAIL: %s\n",why);std::exit(1);}}
int main(){
 fmer_controls_t c{};fmer_panel_t p;fmer_panel_init(&p);
 for(unsigned id=0;id<FMER_PARAM_COUNT;id++)c.value[id]=(uint16_t)fmer_control_min(id);
 c.value[FMER_CUTOFF]=20000;c.value[FMER_VA_CUTOFF]=18000;
 require(p.operator_number==1 && p.family==FMER_PANEL_HOME,"known home state");
 fmer_panel_button(&p,8,&c,0);require(p.scope_only,"HOME on HOME opens scope-only view");
 fmer_panel_button(&p,8,&c,0);require(!p.scope_only,"HOME again closes scope-only view");
 fmer_panel_button(&p,8,&c,0);fmer_panel_button(&p,2,&c,0);
 require(!p.scope_only && p.family==FMER_PANEL_FX,"another button restores controls and keeps its normal action");
 fmer_panel_button(&p,8,&c,0);require(!p.scope_only,"HOME from another menu opens normal HOME");
 require(fmer_panel_encoder(&p,0,1,&c,0) && c.value[FMER_ENGINE]==1,"home selector changes actual engine");
 require(fmer_panel_knob_id(&p,1,&c)==FMER_FX_RESONANCE,"VA home resonance mapping");
 fmer_panel_encoder(&p,0,-1,&c,1);require(c.value[FMER_ENGINE]==0,"reverse selection returnsFM");
 fmer_panel_button(&p,6,&c,2);require(p.family==FMER_PANEL_EDIT,"edit opens operator context");
 require(fmer_panel_knob_id(&p,0,&c)==121,"OP1 maps to reverse-order VCED output byte");
 fmer_panel_encoder(&p,2,1,&c,3);require(c.value[121]==1 && c.value[16]==0,"slow editing OP1 does not modifyOP6");
 fmer_panel_encoder(&p,0,-1,&c,4);require(p.operator_number==6,"operator navigation wraps without musical edits");
 require(fmer_panel_knob_id(&p,0,&c)==16,"OP6 maps to first VCED group");
 fmer_panel_button(&p,3,&c,5);require(p.page[p.family]==1,"SEL advancespage");
 require(fmer_panel_encoder(&p,1,1,&c,6) && c.value[134]==1 && p.family==FMER_PANEL_EDIT,"dedicated encoder edits only the current FM working patch algorithm");
 fmer_panel_button(&p,8,&c,7);require(p.family==FMER_PANEL_HOME && !p.focus_active,"HOME closespopup");
 auto browse_before=c;
 fmer_panel_encoder(&p,6,1,&c,8);require(p.family==FMER_PANEL_PRESETS && p.preset_candidate==1,"PRESETS opens named candidate browser");
 require(p.page[FMER_PANEL_EDIT]==1 && p.operator_number==6 && !std::memcmp(&browse_before,&c,sizeof c) && p.audition_request && p.audition_slot==65,"browse queues exact default sound without touching audio-owned controls");
 fmer_panel_encoder(&p,6,-2,&c,8);require(p.preset_bank==2 && p.preset_candidate==63,"PRESETS traverses backwards from FM into final USER slot");
 require(!fmer_panel_encoder(&p,3,1,&c,8) && !std::memcmp(&browse_before,&c,sizeof c),"unmapped browse knobs cannot mutate sound");
 require(!fmer_panel_button(&p,8,&c,8) && p.family==FMER_PANEL_HOME && !std::memcmp(&browse_before,&c,sizeof c),"HOME returns from instant browser without another recall");
 fmer_panel_encoder(&p,6,1,&c,8);require(p.preset_bank==0 && p.preset_candidate==0,"last USER wraps into first FM sound");
 p.audition_request=0;
 require(!fmer_panel_button(&p,3,&c,8) && p.family==FMER_PANEL_HOME && !p.audition_request,"SEL returns HOME without repeating instant sound recall");
 fmer_panel_encoder(&p,6,1,&c,8);fmer_panel_encoder(&p,2,1,&c,8);
 require(p.preset_bank==1 && p.preset_candidate==8,"bank knob opens VA while preserving original program IDs");
 fmer_panel_encoder(&p,6,-1,&c,8);require(p.preset_bank==0 && p.preset_candidate==39,"reverse first VA crosses into last FM with stable IDs");
 p.save_slot=42;fmer_panel_encoder(&p,2,2,&c,8);require(p.preset_bank==2 && p.preset_candidate==42,"user bank starts on remembered save destination");
 require(p.audition_request && p.audition_slot==42,"USER bank browsing requests sound-only recall on exact slot");
 p.audition_request=0;fmer_panel_button(&p,3,&c,8);require(!p.load_request && !p.save_request && !p.audition_request && p.family==FMER_PANEL_HOME,"USER browser SELECT exits without full project restore");
 fmer_panel_button(&p,8,&c,8);require(!p.load_request && !p.save_request,"ordinary navigation clears storage action latches");
 std::array<bool,64> factory_seen{};
 for(unsigned bank=0;bank<2;bank++)for(unsigned index=0;index<32;index++){
  auto id=fmer_panel_factory_id(bank,index);require(id<64 && !factory_seen[id],"factory banks cover each stable ID exactly once");factory_seen[id]=true;
  require(fmer_panel_factory_index(bank,id)==index,"factory bank ID mapping roundtrips");}
 c.value[134]=31;require(fmer_panel_encoder(&p,1,1,&c,8) && c.value[134]==0,"FM algorithm wraps31 to0");
 require(fmer_panel_encoder(&p,1,-1,&c,8) && c.value[134]==31,"FM algorithm wraps0 to31");
 c.value[FMER_ENGINE]=1;c.value[FMER_VA_WAVE]=4;
 require(fmer_panel_encoder(&p,1,1,&c,8) && c.value[FMER_VA_WAVE]==0,"VA algorithm knob wraps5waveforms");
 c.value[FMER_ENGINE]=0;
 require(fmer_panel_button(&p,12,&c,9)==FMER_TRANSPORT_PLAY,"PLAY transport available on soundpage");
 require(fmer_panel_button(&p,13,&c,10)==FMER_TRANSPORT_RECORD && p.family==FMER_PANEL_SEQ,"REC explicitly entersstepentry");
 auto before=c;fmer_panel_button(&p,9,&c,11);
 require(p.family==FMER_PANEL_SAVE && !p.save_request && !std::memcmp(&before,&c,sizeof c),"SAVE opens destination without writing");
 require(!fmer_panel_encoder(&p,2,1,&c,12) && p.save_slot==43 && !p.save_request,"SAVE knob chooses destination without writing");
 fmer_panel_button(&p,3,&c,12);require(p.save_request && p.slot_index==43 && !p.load_request,"SEL confirms exact onboard destination");
 p.family=FMER_PANEL_SEQ;p.page[p.family]=0;c.value[FMER_SEQ_LENGTH]=16;c.value[FMER_SEQ_STEP]=15;
 require(!fmer_panel_encoder(&p,2,5,&c,13) && c.value[FMER_SEQ_STEP]==15,"step cannotmove beyondcurrentlength");
 p.page[p.family]=1;c.value[FMER_SEQ_STEP]=15;
 require(fmer_panel_encoder(&p,4,-8,&c,14) && c.value[FMER_SEQ_LENGTH]==8 && c.value[FMER_SEQ_STEP]==7,"shorteninglengthatomicallyclamps selectedstep");
 fmer_panel_encoder(&p,4,-999,&c,15);require(c.value[FMER_SEQ_LENGTH]==1 && c.value[FMER_SEQ_STEP]==0,"shortestpatternretains validfirststep");
 p.page[p.family]=2;c.value[FMER_SEQ_CHAIN_MASK]=1;p.chain_cursor=0;
 require(!fmer_panel_encoder(&p,3,-1,&c,16) && c.value[FMER_SEQ_CHAIN_MASK]==1,"cannot remove final chain member");
 fmer_panel_encoder(&p,2,3,&c,17);require(p.chain_cursor==3 && c.value[FMER_SEQ_CHAIN_MASK]==1,"chain cursor alone preserves membership");
 require(fmer_panel_encoder(&p,3,1,&c,18) && c.value[FMER_SEQ_CHAIN_MASK]==9,"include adds selected pattern bit");
 require(fmer_panel_encoder(&p,3,-1,&c,19) && c.value[FMER_SEQ_CHAIN_MASK]==1,"exclude removes selected pattern bit");

 // Arbitrary imported frequencies remain exact until one deliberate turn.
 require(fmer_panel_step(FMER_CUTOFF,1234,1)==1307 && fmer_panel_step(FMER_CUTOFF,1234,-1)==1165,"slow frequency turn is proportional from exact imported value");
 require(fmer_panel_step_mode(FMER_CUTOFF,1234,1,1)==1243 && fmer_panel_step_mode(FMER_CUTOFF,1234,-1,1)==1225,"heldSEL frequency is musical precision without snapping");
 require(fmer_panel_step_mode(FMER_CUTOFF,20000,-1,1)==19856,"fine filter movement at20k is useful rather than oneHz");
 require(fmer_panel_step_mode(FMER_CUTOFF,20,1,1)==21,"fine filter retains oneHz resolution at low end");
 require(fmer_panel_step_mode(FMER_ATTACK,1234,1,1)==1252,"heldSEL duration scales proportionally");
 require(fmer_panel_step(FMER_VA_CUTOFF,17999,1)==18000,"VA top step reachesactual18kcorelimit");
 require(fmer_panel_step(FMER_VA_CUTOFF,18000,1)==18000,"VA top cannotstall on invalid20k");
 require(fmer_panel_step(FMER_ARP_RATE,16,1)==32 && fmer_panel_step(FMER_ARP_RATE,16,-1)==8,"arp rates remain powersoftwo");
 require(fmer_panel_step(FMER_ATTACK,9999,1)==10000,"envelope reachesupperbound");
 require(fmer_panel_step(FMER_DELAY,0,INT_MIN)==0 && fmer_panel_step(FMER_DELAY,100,INT_MAX)==100,"extreme deltas clamp safely");
 for(unsigned id:{(unsigned)FMER_CUTOFF,(unsigned)FMER_VA_CUTOFF,(unsigned)FMER_ATTACK,(unsigned)FMER_DECAY,
                  (unsigned)FMER_RELEASE,(unsigned)FMER_DELAY_MS,(unsigned)FMER_LFO_RATE})
  for(unsigned fine=0;fine<2;++fine)for(unsigned value=fmer_control_min(id);value<=fmer_control_max(id);++value){
   auto up=fmer_panel_step_mode(id,value,1,fine),down=fmer_panel_step_mode(id,value,-1,fine);
   require(fmer_control_valid(id,up) && fmer_control_valid(id,down),"every proportional value remains in actual canonical bounds");
   require(value==fmer_control_max(id)?up==value:up>value,"every upward detent moves without an interior dead zone");
   require(value==fmer_control_min(id)?down==value:down<value,"every downward detent moves without an interior dead zone");
   require(fmer_panel_step_mode(id,value,0,fine)==value,"no gesture preserves every exact imported value");
   if(fine)require(up<=fmer_panel_step_mode(id,value,1,0) && down>=fmer_panel_step_mode(id,value,-1,0),"fine movement never exceeds ordinary movement");
  }
 require(!fmer_panel_stored_only(14) && !fmer_panel_stored_only(140) && fmer_panel_stored_only(136),"audible AMS and AMD are enabled while unsupported oscillator sync stays explicit");
 p.family=FMER_PANEL_GLO;p.page[p.family]=2;
 require(fmer_panel_pages(FMER_PANEL_GLO,0)==10 && fmer_panel_knob_id(&p,0,&c)==FMER_MIDI_CHANNEL,"receive channel stays on musical MIDI INPUT page before maintenance");
 for(unsigned knob=1;knob<4;++knob)require(fmer_panel_knob_id(&p,knob,&c)==FMER_PANEL_INVALID,"MIDI page does not invent unavailable routing controls");
 p.family=FMER_PANEL_FX;p.page[p.family]=0;
 require(fmer_panel_knob_id(&p,0,&c)==FMER_CUTOFF && fmer_panel_knob_id(&p,1,&c)==FMER_FX_RESONANCE &&
         fmer_panel_knob_id(&p,2,&c)==FMER_REVERB && fmer_panel_knob_id(&p,3,&c)==FMER_DELAY,
         "primary FX page has frequency, resonance, reverb and delay");
 for(unsigned id:{16u,0u,(unsigned)FMER_CUTOFF,(unsigned)FMER_ATTACK,(unsigned)FMER_DELAY_MS,
                  (unsigned)FMER_LFO_RATE,(unsigned)FMER_TEMPO,(unsigned)FMER_SEQ_VELOCITY}) {
  unsigned value=fmer_control_min(id);
  for(unsigned detent=0;detent<300;detent++)value=fmer_panel_step(id,value,1);
  require(value==fmer_control_max(id),"slow continuous range reaches maximum without a dead zone");
  for(unsigned detent=0;detent<300;detent++)value=fmer_panel_step(id,value,-1);
  require(value==fmer_control_min(id),"slow continuous range returns to minimum without a dead zone");
 }
 for(unsigned id:{134u,144u,18u,(unsigned)FMER_SEQ_STEP,(unsigned)FMER_SEQ_PITCH,(unsigned)FMER_SEQ_LENGTH,(unsigned)FMER_MIDI_CHANNEL})
  require(fmer_panel_step(id,10,1)==11,"musical andnavigation indices keep single-step resolution");
 p.family=FMER_PANEL_EDIT;p.page[p.family]=0;p.operator_number=1;c.value[121]=11;p.fine_adjust=1;
 fmer_panel_encoder(&p,2,1,&c,100);require(c.value[121]==12,"panel routes fine modifier to exactcanonical edit");
 p.fine_adjust=0;fmer_panel_encoder(&p,2,1,&c,101);require(c.value[121]==13,"first ordinary turn remains precise");
 fmer_panel_encoder(&p,2,1,&c,126);require(c.value[121]==14,"fine-mode transition restarts the acceleration run");
 fmer_panel_encoder(&p,2,1,&c,151);require(c.value[121]==18,"third fast same-direction turn accelerates continuously");
 fmer_panel_encoder(&p,2,-1,&c,176);require(c.value[121]==17,"direction reversal immediately restores precision");
 fmer_panel_encoder(&p,2,-1,&c,201);fmer_panel_encoder(&p,2,-1,&c,226);
 p.fine_adjust=1;fmer_panel_encoder(&p,2,-1,&c,251);require(c.value[121]==11,"heldSEL prevents speed acceleration");
 p.fine_adjust=0;fmer_panel_encoder(&p,2,1,&c,1000);require(c.value[121]==12,"pause clears acceleration history");
 fmer_panel_navigate(&p);fmer_panel_encoder(&p,2,1,&c,1001);require(c.value[121]==13,"navigation resets acceleration");
 p.edit_ms=0xfffffff0u;p.edit_id=121;p.edit_direction=1;p.edit_run=3;
 fmer_panel_encoder(&p,2,1,&c,9u);require(c.value[121]==17,"acceleration timing survives unsigned clock wrap");
 fmer_panel_encoder(&p,3,1,&c,10u);require(c.value[123]==1,"switching controls cannot inherit an accelerated run");
 p.family=FMER_PANEL_HOME;c.value[FMER_CUTOFF]=20;fmer_panel_navigate(&p);
 for(unsigned n=0;n<34;n++)fmer_panel_encoder(&p,2,1,&c,2000+25*n);
 require(c.value[FMER_CUTOFF]==20000,"fast filter sweep reaches full range within34detents");
 for(unsigned n=0;n<34;n++)fmer_panel_encoder(&p,2,-1,&c,3000+25*n);
 require(c.value[FMER_CUTOFF]==20,"fast filter sweep returns to lower endpoint");
 // Each semantic ARP/FX setting appears once within its family. HOME macros
 // and dedicated ENV intentionally provide separate performance entry points.
 for(unsigned family:{(unsigned)FMER_PANEL_ARP,(unsigned)FMER_PANEL_FX}) {
  std::array<bool,FMER_PARAM_COUNT> seen{};p.family=family;
  for(unsigned page=0;page<fmer_panel_pages(family,0);++page){p.page[family]=page;
   for(unsigned k=0;k<4;++k){auto id=fmer_panel_knob_id(&p,k,&c);if(id==FMER_PANEL_INVALID)continue;
    require(!seen[id],"ARP andFX families never duplicate or move the same parameter");seen[id]=true;}}
 }
 p.family=FMER_PANEL_ARP;p.page[p.family]=1;
 require(fmer_panel_knob_id(&p,0,&c)==FMER_ARP_RATE && fmer_panel_knob_id(&p,1,&c)==FMER_TEMPO,"ARP timing page has a single rate and tempo location");
 for(unsigned id:{134u,(unsigned)FMER_VA_WAVE,(unsigned)FMER_ARP_ORDER,(unsigned)FMER_ARP_RATE,(unsigned)FMER_MIDI_CHANNEL})
  require(!fmer_panel_continuous(id),"selectors never accelerate");
 p.family=FMER_PANEL_HOME;c.value[FMER_ARP_ENABLE]=0;
 require(!fmer_panel_button(&p,10,&c,102) && p.family==FMER_PANEL_ARP && !c.value[FMER_ARP_ENABLE],"firstARP press opens without an unexpected musical action");
 fmer_panel_button(&p,3,&c,103);auto arp_page=p.page[FMER_PANEL_ARP];
 require(!fmer_panel_button(&p,10,&c,104) && c.value[FMER_ARP_ENABLE]==1 && p.page[FMER_PANEL_ARP]==arp_page,"repeatedARP enables on anysubpage and leavesnavigation stable");
 require(p.focused_id==FMER_ARP_ENABLE && p.focus_active,"ARP shortcut exposesexactenable popup");
 fmer_panel_button(&p,10,&c,105);require(!c.value[FMER_ARP_ENABLE],"repeatedARP togglesoff without an unhandledtransport command");
 std::array<bool,145> reached{};
 for(unsigned engine=0;engine<2;engine++)for(unsigned family=0;family<FMER_PANEL_FAMILIES;family++){
  c.value[FMER_ENGINE]=(uint16_t)engine;p.family=family;
  for(unsigned page=0;page<fmer_panel_pages(family,engine);page++)for(unsigned op=1;op<=6;op++){
   p.page[family]=page;p.operator_number=op;
   for(unsigned knob=0;knob<4;knob++){
    auto id=fmer_panel_knob_id(&p,knob,&c);if(id==FMER_PANEL_INVALID)continue;
    require(id<FMER_PARAM_COUNT && id!=159u,"mapped ID is canonical and never reserved");
    if(!engine && id<145)reached[id]=true;
    for(unsigned value:{fmer_control_min(id),fmer_control_max(id)})for(int delta:{INT_MIN,-1,1,INT_MAX})
      require(fmer_control_valid(id,fmer_panel_step(id,value,delta)),"every mapped boundary remains valid");
   }
  }
 }
 reached[134]=true; // Dedicated ALGORITHM encoder exercised above.
 for(bool accessible:reached)require(accessible,"all145 rawFMparameters have a reachable control");
 p.focus_active=1;p.edited_ms=0xffffff00u;
 require(fmer_panel_popup(&p,10) && !fmer_panel_popup(&p,2000),"popup timeout survives timerwrap");
 p.family=FMER_PANEL_SAVE;p.save_slot=63;p.save_bank=1;
 fmer_panel_button(&p,3,&c,0);require(p.save_request&&p.slot_index==127,"default63 is an explicit separate destination");
 for(unsigned action=0;action<4;action++) {
  p.family=FMER_PANEL_GLO;p.page[FMER_PANEL_GLO]=FMER_GLO_RESET;p.reset_choice=action;fmer_panel_navigate(&p);
  fmer_panel_button(&p,3,&c,0);require(p.reset_armed&&!p.reset_request,"first SEL only arms reset");
  fmer_panel_button(&p,8,&c,0);require(!p.reset_armed&&!p.reset_request,"HOME cancels reset");
  p.family=FMER_PANEL_GLO;fmer_panel_button(&p,3,&c,0);fmer_panel_button(&p,3,&c,0);
  require(p.reset_request==(action==3?10:action+3)&&!p.reset_armed,"second SEL emits exact independent reset");
 }
 p.family=FMER_PANEL_GLO;p.page[FMER_PANEL_GLO]=FMER_GLO_OUTPUT;fmer_midi_defaults(&p.midi);
 fmer_panel_encoder(&p,2,1,&c,0);require(p.midi.value[0]==1&&p.midi_revision,"MIDI output knob edits global route");
 fmer_panel_button(&p,3,&c,0);require(p.midi_save_request&&!p.save_request,"SEL requests global settings Save independently of patch Save");
 p.page[FMER_PANEL_GLO]=FMER_GLO_CLOCK;fmer_panel_encoder(&p,2,1,&c,0);require(p.midi.value[3]==1,"clock source on fixed K1");
 p.family=FMER_PANEL_FX;p.page[p.family]=0;
 const unsigned fx[3][4]={{FMER_CUTOFF,FMER_FX_RESONANCE,FMER_REVERB,FMER_DELAY},
  {FMER_CHORUS,FMER_PHASER,FMER_DRIVE,FMER_LFO_ENABLE},
  {FMER_DELAY_MS,FMER_FEEDBACK,FMER_REVERB_DECAY,FMER_REVERB_MODEL}};
 for(unsigned page=0;page<3;++page){p.page[p.family]=page;for(unsigned k=0;k<4;++k)require(fmer_panel_knob_id(&p,k,&c)==fx[page][k],"three FX pages have four useful stable positions");}
 p.page[p.family]=0;const auto algorithm=c.value[134];c.value[FMER_FILTER_TYPE]=0;
 fmer_panel_encoder(&p,1,-1,&c,0);require(c.value[FMER_FILTER_TYPE]==2 && c.value[134]==algorithm,"context filter type wraps without changing FM topology");
 p.page[p.family]=1;c.value[FMER_LFO_ENABLE]=1;c.value[FMER_LFO_DEPTH]=45;
 fmer_panel_encoder(&p,5,-1,&c,0);require(!c.value[FMER_LFO_ENABLE]&&c.value[FMER_LFO_DEPTH]==45,"FX LFO off preserves stored depth");
 fmer_panel_button(&p,5,&c,0);fmer_panel_button(&p,5,&c,0);
 require(c.value[FMER_LFO_ENABLE]&&c.value[FMER_LFO_DEPTH]==45,"LFO menu toggles the same canonical gate");
 // FM amplitude macros modify carriers only; native operator envelopes remain reachable.
 c.value[FMER_ENGINE]=0;c.value[134]=4;p.family=FMER_PANEL_ENV;p.focus_active=0;p.edit_run=0;
 for(unsigned op=0;op<6;op++){c.value[op*21]=50;c.value[op*21+16]=80;}
 require(fmer_panel_pages(FMER_PANEL_ENV,0)==1 && fmer_panel_pages(FMER_PANEL_EDIT,0)==8,"shared ENV and complete FM EDIT pages");
 fmer_panel_encoder(&p,2,1,&c,5000);
 for(unsigned op=0;op<6;op++)require(c.value[op*21]==(op%2?51:50),"FM attack gesture edits all carriers and leaves modulators alone");
 p.family=FMER_PANEL_EDIT;p.page[p.family]=4;p.operator_number=6;require(fmer_panel_knob_id(&p,0,&c)==0,"operator rates moved to EDIT without removing precision");
 p.family=FMER_PANEL_SEQ;p.page[p.family]=3;
 require(fmer_panel_pages(FMER_PANEL_SEQ,0)==9 && fmer_panel_knob_id(&p,0,&c)==FMER_SEQ_MODE && fmer_panel_knob_id(&p,1,&c)==FMER_GLIDE_MODE,"mode page exposes allocation and glide first");
 require(fmer_panel_knob_id(&p,2,&c)==FMER_GLIDE_MS && fmer_panel_knob_id(&p,3,&c)==FMER_GLIDE_CURVE,"mode page groups time and contour without a duplicate patch selector");
 c.value[FMER_SEQ_MODE]=1;
 p.page[p.family]=4;
 for(unsigned k=0;k<4;k++)require(fmer_panel_knob_id(&p,k,&c)==FMER_PANEL_INVALID,"performance mixer uses explicit independent track commands");
 c.value[FMER_SEQ_MODE]=0;c.value[FMER_SEQ_TRACK]=1;c.value[FMER_TRACK_LEVEL]=100;c.value[FMER_TRACK_MUTE]=0;
 p.page[p.family]=3;fmer_panel_navigate(&p);auto single_before=c;
 require(!fmer_panel_encoder(&p,0,1,&c,6000) && p.page[p.family]==8 && !std::memcmp(&c,&single_before,sizeof c),"SINGLE navigation skips inactive mixer and returns to Song without changing instrument");
 p.page[p.family]=4;
 for(unsigned encoder=2;encoder<5;++encoder){
  require(fmer_panel_knob_id(&p,encoder-2,&c)==FMER_PANEL_INVALID,"inactive mixer level track and mute knobs are explicitly locked");
  require(!fmer_panel_encoder(&p,encoder,1,&c,6001+encoder) && !std::memcmp(&c,&single_before,sizeof c) && !p.focus_active,"inactive mixer gestures do not alter dormant mix or working instrument");
 }
 require(fmer_panel_encoder(&p,5,1,&c,6010) && c.value[FMER_SEQ_MODE]==1,"visible K4 explicitly enables four-part mode");
 single_before.value[FMER_SEQ_MODE]=1;require(!std::memcmp(&c,&single_before,sizeof c),"mode gesture leaves selected mix and sound values intact for adapter reconciliation");
 for(unsigned track=0;track<4;track++){
  require(!fmer_panel_encoder(&p,track+2,-1,&c,6020+track) && p.performance_request==fmer_mix_command(track,FMER_MIX_LEVEL,-2),"four knobs map left to right to independent track levels");
 }
 // A full mixer sweep takes50 slow detents, fewer than20 fast detents;
 // SEL retains single-percent resolution and direction/track changes reset acceleration.
 p.mixer_layer=FMER_MIX_LEVEL;p.edit_run=0;
 int total=0;for(unsigned i=0;i<20;i++){fmer_panel_encoder(&p,2,1,&c,7000+i*20);total+=p.performance_request&1023u;}
 require(total>=100,"fast level sweep spans whole fader");
 fmer_panel_encoder(&p,2,-1,&c,7410);require(p.performance_request==fmer_mix_command(0,FMER_MIX_LEVEL,-2),"reversal immediately resets acceleration");
 fmer_panel_encoder(&p,3,1,&c,7420);require(p.performance_request==fmer_mix_command(1,FMER_MIX_LEVEL,2),"other track does not inherit speed");
 p.fine_adjust=1;for(unsigned i=0;i<10;i++){fmer_panel_encoder(&p,3,1,&c,7500+i*10);require(p.performance_request==fmer_mix_command(1,FMER_MIX_LEVEL,1),"fine level is always one percent");}p.fine_adjust=0;
 fmer_panel_encoder(&p,1,1,&c,6030);require(p.mixer_layer==FMER_MIX_MUTE,"algorithm knob chooses clearly labeled mixer layer");
 fmer_panel_encoder(&p,4,1,&c,6031);require(p.performance_request==fmer_mix_command(2,FMER_MIX_MUTE,1),"mute gesture targets its own strip");
 fmer_panel_button(&p,3,&c,6040);require(p.mixer_layer==FMER_MIX_SOLO && p.page[p.family]==4,"SEL advances mixer layer without leaving performance view");
 p.page[p.family]=3;require(fmer_panel_encoder(&p,2,-1,&c,6050) && !c.value[FMER_SEQ_MODE],"TRACKS retains explicit SINGLE mode choice");
 p.page[p.family]=5;require(fmer_panel_knob_id(&p,0,&c)==FMER_RECORD_MODE && fmer_panel_knob_id(&p,1,&c)==FMER_PANEL_INVALID,"record setup has no duplicated timing controls");
 p.family=FMER_PANEL_GLO;p.page[p.family]=FMER_GLO_GLIDE;p.midi_save_request=0;
 require(fmer_panel_knob_id(&p,0,&c)==FMER_GLIDE_MODE && fmer_panel_knob_id(&p,3,&c)==FMER_VOICE_BUDGET,"glide controls expose required mono voice budget");
 fmer_panel_button(&p,3,&c,0);require(!p.midi_save_request && p.page[p.family]==FMER_GLO_GLIDE,"SEL leaves GLO page unchanged and never accidentally writes a MIDI profile");
 p.family=FMER_PANEL_SAVE;p.save_slot=42;p.save_bank=1;p.save_action=0;
 fmer_panel_encoder(&p,4,1,&c,0);require(p.save_action==1 && !p.load_request,"full restore action selection does not immediately load");
 fmer_panel_button(&p,3,&c,0);require(p.load_request && !p.save_request && p.slot_index==106,"explicit full restore snapshots exact destination");
 require(!std::strcmp(fmer_panel_short_name(FMER_ARP_ORDER),"TYPE") && !std::strcmp(fmer_panel_name(FMER_ARP_ORDER),"ARP TYPE"),"visible ARP nomenclature is TYPE while wire ID stays compatible");
 // One turn path covers all128 destinations exactly once in either direction.
 for(int direction:{-1,1}){
  p.preset_bank=0;p.preset_candidate=0;std::array<bool,128> seen{};
  for(unsigned i=0;i<128;i++){
   fmer_panel_encoder(&p,6,direction,&c,8000+i);
   require(p.audition_slot<128 && !seen[p.audition_slot],"continuous bank browsing reaches every unique saved sound");
   seen[p.audition_slot]=true;
  }
  require(p.preset_bank==0 && p.preset_candidate==0,"full circular browse returns exactly to its starting sound");
 }
 p.family=FMER_PANEL_SEQ;p.page[p.family]=2;p.chain_cursor=7;c.value[FMER_SEQ_CHAIN_MASK]=1;
 fmer_panel_encoder(&p,2,8,&c,9000);require(p.chain_cursor==15,"chain cursor reaches the sixteenth shared pattern");
 require(fmer_panel_encoder(&p,3,1,&c,9001) && c.value[FMER_SEQ_CHAIN_MASK]==32769,"chain includes high pattern bit without truncation");
 fmer_panel_encoder(&p,2,1,&c,9002);require(p.chain_cursor==0,"chain cursor wraps sixteen patterns");
 p.family=FMER_PANEL_SAVE;p.save_scope=0;p.save_slot=63;p.save_bank=1;p.save_action=0;
 fmer_panel_encoder(&p,5,1,&c,9100);require(p.save_scope==1 && p.save_slot==15 && p.save_bank==1,"project scope clamps slot while preserving instrument bank");
 fmer_panel_encoder(&p,3,1,&c,9101);require(p.save_bank==1,"project has no misleading bank gesture");
 fmer_panel_button(&p,3,&c,9102);require(p.save_request && p.storage_scope_request==1 && p.slot_index==15,"project confirmation freezes exact separate scope and slot");
 fmer_panel_encoder(&p,2,1,&c,9103);require(p.save_slot==0 && p.slot_index==15,"project browse wraps sixteen without mutating frozen request");
 fmer_panel_encoder(&p,5,-1,&c,9104);fmer_panel_button(&p,3,&c,9105);
 require(p.storage_scope_request==0 && p.slot_index==64,"return to sound scope retains exact DEFAULT bank destination");
 require(FMER_GLO_INFO+1==FMER_GLO_RESET && FMER_GLO_RESET+1==fmer_panel_pages(FMER_PANEL_GLO,0),"info and reset occupy final two menu pages");

 require(fmer_delay_time(1,327,500000)==500 && fmer_delay_time(3,327,500000)==250,"quarter and eighth notes follow120BPM");
 require(fmer_delay_time(2,327,500000)==375 && fmer_delay_time(4,327,500000)==167,"dotted and triplet divisions round to actual milliseconds");
 require(fmer_delay_time(0,327,500000)==327,"free time survives disabling synchronization");
 require(fmer_delay_time(7,327,3000000)==1000,"slow dotted quarter explicitly reaches one-second buffer capacity");
 p.family=FMER_PANEL_ARP;
 require(fmer_panel_button(&p,13,&c,9200)==FMER_TRANSPORT_ARP_RECORD && p.family==FMER_PANEL_ARP,"REC from ARP captures generated notes without navigating away");
 p.family=FMER_PANEL_FX;p.page[p.family]=2;c.value[FMER_DELAY_SYNC]=0;
 require(fmer_panel_knob_id(&p,0,&c)==FMER_DELAY_MS,"free mode retains millisecond knob");
 fmer_panel_encoder(&p,1,1,&c,9201);
 require(c.value[FMER_DELAY_SYNC]==1 && fmer_panel_knob_id(&p,0,&c)==FMER_DELAY_SYNC,"algorithm selects sync and K1 follows musical divisions");
 p.family=FMER_PANEL_GLO;p.page[p.family]=FMER_GLO_VOICE;c.value[FMER_SEQ_MODE]=1;c.value[FMER_VOICE_BUDGET]=4;
 require(fmer_panel_knob_id(&p,0,&c)==FMER_SEQ_MODE,"Global exposes synth/four-track mode directly");
 require(fmer_panel_encoder(&p,4,1,&c,9500)==0 && c.value[FMER_SEQ_MODE]==1 && c.value[FMER_VOICE_BUDGET]==4,"Voices cannot leave four-track mode");
 fmer_panel_encoder(&p,2,1,&c,9501);
 require(c.value[FMER_SEQ_MODE]==1,"Global mode returns to four-track performance");
 p.fine_adjust=1;auto mode_before=c;
 fmer_panel_button(&p,8,&c,9600);require(!c.value[FMER_SEQ_MODE] && p.family==FMER_PANEL_HOME && !p.scope_only,"SEL HOME explicitly selects single synth");
 fmer_panel_button(&p,8,&c,9601);require(!std::memcmp(&mode_before,&c,sizeof c),"SEL HOME round trip preserves all other controls");p.fine_adjust=0;
 for(unsigned family:{FMER_PANEL_HOME,FMER_PANEL_FX}) {p.family=family;p.page[family]=0;for(unsigned k=0;k<4;k++)require(fmer_panel_knob_id(&p,k,&c)==fx[0][k],"HOME and FX use identical canonical controls");}
 for(unsigned family:{FMER_PANEL_SEQ,FMER_PANEL_GLO}) {p.family=family;p.page[family]=family==FMER_PANEL_SEQ?3:FMER_GLO_VOICE;auto before=c;require(!fmer_panel_encoder(&p,family==FMER_PANEL_SEQ?3:4,-1,&c,9700) && !std::memcmp(&before,&c,sizeof c),"voice editing cannot alter four-track mode or budget");}
 p.family=FMER_PANEL_FX;p.page[p.family]=3;p.fx_selected=0;p.audition_request=0;
 fmer_panel_encoder(&p,2,3,&c,9800);require(p.fx_selected==3,"chain knob selects distortion");
 fmer_panel_encoder(&p,3,-9,&c,9801);require(p.performance_request==fmer_fx_command(3,-6),"chain move is bounded for audio owner");
 fmer_panel_encoder(&p,6,1,&c,9802);require(p.family==FMER_PANEL_PRESETS && p.audition_request,"dedicated PRESETS still works from chain page");
 p.family=FMER_PANEL_FX;p.page[p.family]=3;fmer_panel_encoder(&p,0,1,&c,9803);
 require(p.page[FMER_PANEL_FX]==0,"SELECT can leave fourth FX page and wrap to first");
 p.fine_adjust=1;p.family=FMER_PANEL_FX;p.page[p.family]=3;
 fmer_panel_button(&p,2,&c,9900);require(p.reset_request==11 && p.page[p.family]==3,"SEL FX requests persistent default without paging");p.fine_adjust=0;
 p.family=FMER_PANEL_GLO;p.page[p.family]=FMER_GLO_RESET;p.reset_choice=4;p.reset_armed=0;
 fmer_panel_button(&p,3,&c,9901);require(p.reset_armed && !p.reset_request,"original FX reset needs confirmation");
 fmer_panel_button(&p,3,&c,9902);require(p.reset_request==12 && !p.reset_armed,"original FX reset separate from bank resets");

 p.family=FMER_PANEL_FX;p.page[p.family]=3;p.fx_order=fmer_fx_move(0,4,-6);p.fx_selected=4;
 fmer_panel_encoder(&p,2,1,&c,10000);require(p.fx_selected==0,"selection follows displayed reordered chain clockwise");
 fmer_panel_encoder(&p,2,-1,&c,10001);require(p.fx_selected==4,"selection reverses displayed order");
 const unsigned order[]={FMER_MIX_SOUND,FMER_MIX_PATTERN,FMER_MIX_RUN,FMER_MIX_LEVEL,FMER_MIX_MUTE,FMER_MIX_SOLO,FMER_MIX_FX};
 for(unsigned i=0;i<7;i++)require(fmer_mix_scroll(order[i],1,0)==order[(i+1)%7] && fmer_mix_scroll(order[i],-1,0)==order[(i+6)%7],"mixer follows visual workflow in both directions");
 for(unsigned action=0;action<4;action++){fmer_panel_shortcut(&p,&c,action);
    require(action<2?c.value[FMER_SEQ_MODE] && p.page[FMER_PANEL_SEQ]==(action?4:8):!c.value[FMER_SEQ_MODE] && c.value[FMER_VOICE_BUDGET]==(action==2?1:4),"mode shortcut publishes explicit allocation and destination");}
 c.value[FMER_SEQ_MODE]=1;p.family=FMER_PANEL_HOME;p.home_layer=FMER_MIX_LEVEL;
 for(unsigned i=0;i<4;i++){fmer_panel_encoder(&p,i+2,1,&c,10020+i);require(((p.performance_request>>18)&3u)==i,"HOME knob owns corresponding track");}
 for(unsigned i=0;i<4;i++)fmer_panel_button(&p,3,&c,10100+i);
 require(p.home_layer==FMER_MIX_LEVEL && p.family==FMER_PANEL_HOME,"HOME cycles only four mix layers");
 p.family=FMER_PANEL_SEQ;p.page[p.family]=8;p.audition_request=0;
 fmer_panel_encoder(&p,6,1,&c,10200);require(p.family==FMER_PANEL_PRESETS && p.audition_request,"PRESETS remains available from song page");
 p.family=FMER_PANEL_GLO;p.page[p.family]=FMER_GLO_USB_LINK;p.usb_apply=0;p.usb_role=0;p.usb_send=0;
 fmer_panel_encoder(&p,2,1,&c,10001);require(p.usb_role==1 && !p.usb_apply,"role browsing cannot seize USB");
 fmer_panel_encoder(&p,3,2,&c,10002);require(p.usb_send==2,"master selects clock and notes");
 fmer_panel_button(&p,3,&c,10003);require(p.usb_apply && !p.midi_save_request,"explicit link apply does not save global profile");
 c.value[FMER_SEQ_MODE]=0;p.family=FMER_PANEL_SEQ;p.page[p.family]=3;
 fmer_panel_button(&p,11,&c,11000);require(!c.value[FMER_SEQ_MODE] && p.page[p.family]==8,"entering Song preserves single-instrument mode");
 fmer_panel_encoder(&p,0,1,&c,11001);require(!c.value[FMER_SEQ_MODE],"page rotation preserves playing mode");
 p.family=FMER_PANEL_FX;p.page[p.family]=1;p.focused_id=FMER_PHASER;p.modulation=2u<<8;
 fmer_panel_encoder(&p,1,1,&c,11002);require(p.performance_request==0x60000103u,"algorithm selects the touched modulation recipe");
 // The entire mode-aware page ring is reversible, reaches each relevant page
 // exactly once, and cannot modify any canonical sound/performance control.
 for(unsigned multitrack=0;multitrack<2;multitrack++) {
  c.value[FMER_SEQ_MODE]=(uint16_t)multitrack;c.value[FMER_VOICE_BUDGET]=4;
  const auto snapshot=c;const unsigned order[]={4,8,1,0,6,7,5,2,3};
  unsigned start=multitrack?0:1,count=9-start;
  p.family=FMER_PANEL_FX;p.page[FMER_PANEL_SEQ]=7;fmer_panel_button(&p,11,&c,12000);
  require(p.page[p.family]==order[start],"SEQ from another section opens mode-aware performance landing");
  for(unsigned i=0;i<count;i++) {
   const auto page=order[start+i];require(p.page[p.family]==page,"SEQ follows performance-writing-setup page order");
   const auto next=fmer_panel_next_page(FMER_PANEL_SEQ,page,1,&c);
   require(fmer_panel_next_page(FMER_PANEL_SEQ,next,-1,&c)==page,"reverse navigation retraces every reachable page");
   fmer_panel_button(&p,11,&c,12001+i);
  }
  require(p.page[p.family]==order[start] && !std::memcmp(&snapshot,&c,sizeof c),"complete navigation cycle preserves mode, patch, notes and playback parameters");
  for(unsigned button:{2u,5u,6u,7u,11u}) {
   p.family=FMER_PANEL_SAVE;p.scope_only=1;p.reset_armed=1;p.operator_number=5;
   fmer_panel_section_home(&p,button,&c);
   require(p.page[p.family]==fmer_panel_landing(p.family,&c) && !p.scope_only && !p.reset_armed && !std::memcmp(&snapshot,&c,sizeof c),"hold landing is navigation only and cancels stale view/reset state");
   require(p.operator_number==5,"returning to EDIT Tune preserves the chosen FM operator");
  }
 }
 // One deliberate selector chooses a complete allocator state. The dedicated
 // preset encoder remains the sole patch browse wheel; mode never auditions.
 for(unsigned family:{FMER_PANEL_PRESETS,FMER_PANEL_SEQ,FMER_PANEL_GLO}) {
  p.family=family;p.page[family]=family==FMER_PANEL_SEQ?3u:0u;p.audition_request=0;
  c.value[FMER_SEQ_MODE]=1;c.value[FMER_GLIDE_MODE]=0;c.value[FMER_VOICE_BUDGET]=4;
  unsigned encoder=family==FMER_PANEL_PRESETS?0u:2u;const auto before=c;
  require(fmer_panel_encoder(&p,encoder,-1,&c,13000) && !c.value[FMER_SEQ_MODE] && c.value[FMER_VOICE_BUDGET]==4 && !c.value[FMER_GLIDE_MODE],"first mode detent selects four-voice polyphony");
  require(fmer_panel_encoder(&p,encoder,-1,&c,13001) && c.value[FMER_VOICE_BUDGET]==1 && c.value[FMER_GLIDE_MODE],"second mode detent selects valid mono glide");
  require(!fmer_panel_encoder(&p,encoder,-100,&c,13002),"mode selection saturates rather than wrapping");
  require(fmer_panel_encoder(&p,encoder,100,&c,13003) && !std::memcmp(&before,&c,sizeof c) && !p.audition_request,"fast explicit mode sweep returns four-track allocator without changing patch data");
 }
 std::puts("FMER734 panel PASS: mode-aware section landing, reversible pages, explicit 1V/4V/4T, instant banks and bounded controls");
}
