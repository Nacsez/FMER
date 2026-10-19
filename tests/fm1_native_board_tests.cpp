// Execute production quiet-handoff/main/timer statements against real adapter.
// Only board queue/hardware globals are fake; no HAL or device access occurs.
#include "../firmware/fm1/dsp_adapter.h"
#include "../firmware/fm1/trace.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
static fmer_native_state_t native_import_pending;
static uint32_t native_import_ready,native_import_expected,native_import_id;
static uint32_t native_main_owner,native_quiet_started;
static uint32_t native_last_import_id,native_last_import_result;
static uint32_t keys_previous,mi_r,mi_w,requested_budget;
static struct {uint32_t notes;} fm1_in;
static struct {uint32_t voice_limit,controls_applied,ready=1,safe_mode,in_audio,voices,stolen;} diag;
static uint32_t controls_generation,patch_ready,parameter_ready,audition_pending,transport_read,transport_write,native_live_generation;
static uint32_t midi_pending,panic_request,midi_in_overflow,updating,engine,algorithm,va_wave,cutoff,delay_mix,attack_ms,release_ms;
static uint32_t native_preset_id,native_sound_dirty;
static char native_patch_name[11];
static fmer_controls_t controls,applied_controls;
static fmer_midi_metrics_t midi_metrics_snapshot;
static fmer_performance_state_t performance_state;
static fmer_activity_state_t activity_pending;
static fmer_pattern_state_t pattern_pending;
static int32_t q15[256],abuf[512];
static uint32_t FM1_ALNK_CON0=0x800,previous_start,stop_count;
static uint32_t fake_ticks,fm1_ms,timer_last,input_scans,uac_calls,usb_calls,uart_calls,recover_calls;
static uint32_t trace_kind,trace_result,trace_apply,trace_quiet;
static bool inject_key;
#define FM1_TICKS_PER_US 24u
static uint32_t irq_save(){return 0;}
static void irq_restore(uint32_t){}
static uint32_t fm1_ticks(){return fake_ticks+=24u;}
static void fm1_audio_stop(){FM1_ALNK_CON0&=~0x800u;++stop_count;}
static void fm1_timer5_ack(){}
static void fm1_input_tick(){++input_scans;}
static void uac_service(){++uac_calls;}
static void midi_output_recover(){++recover_calls;}
static void usb_poll(){++usb_calls;}
static uint32_t link_host,link_calls;
static void usb_link_poll(){++link_calls;}
static void uart_midi_poll(){++uart_calls;}
static void trace_event(uint32_t kind,uint32_t id,int32_t value,uint32_t aux)
{trace_kind=kind;trace_result=id;trace_apply=(uint32_t)value;trace_quiet=aux;}
static fmer_native_transfer_t native_transfer;
#define RING_PUBLISH() ((void)0)
static void check(bool ok,const char* why)
{if(!ok){std::fprintf(stderr,"FAIL: %s\n",why);std::exit(1);}}
void fm1_timer5_irq(void);
static int checked_set_native(const fmer_native_state_t *state,uint32_t generation)
{
 check(!(FM1_ALNK_CON0&0x800u)&&native_main_owner&&native_import_ready==2u&&!diag.in_audio,"only quiet main owns full native adoption");
 const auto scans=input_scans,usb=usb_calls,uart=uart_calls,recover=recover_calls,uac=uac_calls;
 for(unsigned i=0;i<10;++i)fm1_timer5_irq();
 check(input_scans==scans+10&&uac_calls>uac&&usb_calls==usb&&uart_calls==uart&&recover_calls==recover,"timer scans input/UAC but defers concurrent MIDI producers during main adoption");
 if(inject_key)fm1_in.notes|=4u;
 return fmer_dsp_set_native(state,generation);
}
#define fmer_dsp_set_native checked_set_native
#include "fm1_native_board_block.inc"
#undef fmer_dsp_set_native
static void production_pause()
{
#include "fm1_native_pause.inc"
}
static void production_import_block(){production_pause();native_import_service();}
static uint32_t production_commit_guard()
{
 uint32_t result=FMER_NATIVE_OK;
#include "fm1_native_commit_guard.inc"
 return result;
}
static fmer_native_state_t snapshot()
{fmer_native_state_t s{};fmer_dsp_get_native(&s);return s;}
static bool same(const fmer_native_state_t& a,const fmer_native_state_t& b)
{
 return !std::memcmp(&a.controls,&b.controls,sizeof a.controls) && !std::memcmp(a.vced,b.vced,155) &&
  !std::memcmp(a.pitch,b.pitch,64) && !std::memcmp(a.velocity,b.velocity,64) && !std::memcmp(a.gate,b.gate,64) &&
  a.length==b.length && a.preset_id==b.preset_id && !std::memcmp(a.patterns,b.patterns,sizeof a.patterns);
}
static void prepare(uint32_t before,uint32_t desired)
{
 fmer_dsp_panic();check(fmer_dsp_voice_budget(before)!=0,"set preceding budget");
 requested_budget=before;native_import_pending=snapshot();
 native_import_pending.controls.value[FMER_VOICE_BUDGET]=(uint16_t)desired;
 native_import_pending.preset_id=FMER_NATIVE_CUSTOM_PRESET;
 native_import_expected=fmer_dsp_state_generation();native_import_id=73;
 native_import_ready=1;native_last_import_result=FMER_NATIVE_BUSY;
 mi_r=mi_w=17;keys_previous=0;fm1_in.notes=3;native_main_owner=0;FM1_ALNK_CON0=0x800;
 controls_generation=diag.controls_applied=0;panic_request=midi_pending=midi_in_overflow=0;inject_key=false;
 std::memset(q15,1,sizeof q15);std::memset(abuf,1,sizeof abuf);previous_start=73;
}
int main()
{
 check(fmer_dsp_init()!=0,"real adapter init");
 native_transfer.expected_generation=native_live_generation=9;
 check(production_commit_guard()==FMER_NATIVE_OK,"quiescent matching-generation commit guard accepts");
 mi_w=1;check(production_commit_guard()==FMER_NATIVE_STALE,"production commit guard rejects queued MIDI before publication");mi_w=0;
 patch_ready=1;check(production_commit_guard()==FMER_NATIVE_STALE,"production commit guard retains pending Yamaha-patch refusal");patch_ready=0;
 audition_pending=1;check(production_commit_guard()==FMER_NATIVE_STALE,"instant audition cannot be discarded by a concurrent native restore");audition_pending=0;
 for(auto before:{4u,1u}) {
  const auto desired=before==4?1u:4u;prepare(before,desired);
  fmer_dsp_midi(0x90,60,90,3);
  const auto before_state=snapshot();production_pause();
  check(native_import_ready==2&&!native_main_owner&&native_last_import_result==FMER_NATIVE_BUSY,"IRQ admits handoff without acknowledging unfinished adoption");
  check(!(FM1_ALNK_CON0&0x800u)&&!previous_start&&same(before_state,snapshot()),"IRQ stops DMA and resets period epoch without mutating music");
  check(fmer_dsp_active()!=0,"IRQ handoff does not prematurely panic voices");
  native_import_service();
  auto actual=snapshot();
  check(native_last_import_id==73 && native_last_import_result==FMER_NATIVE_OK && !native_import_ready,"import publishes successful result");
  check(actual.controls.value[FMER_VOICE_BUDGET]==desired && fmer_dsp_voice_limit()==desired && requested_budget==desired && diag.voice_limit==desired,
        "following board budget reconciliation preserves imported budget in both directions");
  check(same(native_import_pending,actual),"production main restore preserves every imported musical field");
  check(keys_previous==fm1_in.notes && !fmer_dsp_active(),"accepted restore clears note owners and suppresses held physical retrigger");
  check((FM1_ALNK_CON0&0x800u)&&!native_main_owner&&native_live_generation==actual.source_generation&&applied_controls.value[FMER_VOICE_BUDGET]==desired,"resume publishes canonical state, generation and budget before releasing ownership");
  check(trace_kind==FMER_TRACE_NATIVE_LOAD&&trace_result==FMER_NATIVE_OK&&trace_apply>0&&trace_quiet>=trace_apply,"intentional restore latency has separate measured trace");
 }
 for(unsigned command=0;command<2;command++) {
  prepare(4,1);fm1_in.notes=0;mi_w=mi_r+1;
  auto before=snapshot();production_import_block();auto after=snapshot();
  check(native_last_import_result==FMER_NATIVE_STALE && !native_import_ready,"queued MIDI makes import stale before mutation");
  check(mi_w-mi_r==1 && keys_previous==0,"refused restore preserves queued MIDI and physical-key bookkeeping");
  check(same(before,after) && before.source_generation==after.source_generation,"refused queued-MIDI restore leaves full native state untouched");
  // The unchanged production MIDI loop receives the preserved event next.
  if(command==0)fmer_dsp_midi(0xc0,5,0,1);else fmer_dsp_midi(0xb0,74,0,1);
  mi_r++;
  check(command==0?fmer_dsp_preset_id()==5:snapshot().controls.value[FMER_CUTOFF]==20,"preserved PC/CC retains its intended musical effect");
 }
 prepare(4,1);auto changed=snapshot().controls;changed.value[FMER_CUTOFF]=777;
 check(fmer_dsp_apply_controls(&changed)!=0,"intervening adopted control");
 auto before=snapshot();production_import_block();auto after=snapshot();
 check(native_last_import_result==FMER_NATIVE_STALE && same(before,after),"existing generation check still rejects an intervening adopted control");
 prepare(4,1);before=snapshot();production_pause();mi_w=mi_r+1;native_import_service();
 check(native_last_import_result==FMER_NATIVE_STALE&&(FM1_ALNK_CON0&0x800u)&&mi_w-mi_r==1&&same(before,snapshot())&&keys_previous==0,"MIDI arriving between handoff and main refuses restore, preserves queue/state and resumes DMA");
 check(trace_result==FMER_NATIVE_STALE&&!trace_apply&&trace_quiet>0,"post-pause stale refusal logs intentional silence");
 for(auto flag:{&panic_request,&midi_pending,&midi_in_overflow,&audition_pending,&parameter_ready}) {
  prepare(4,1);before=snapshot();production_pause();*flag=1;native_import_service();
  check(native_last_import_result==FMER_NATIVE_STALE&&*flag==1&&same(before,snapshot())&&(FM1_ALNK_CON0&0x800u),"main refusal preserves newly queued intent and always resumes");*flag=0;
 }
 prepare(4,1);inject_key=true;production_import_block();
 check(keys_previous==3&&fm1_in.notes==7,"physical key pressed after main claim remains a new edge");
 prepare(4,1);before=snapshot();native_import_pending.controls.value[FMER_CUTOFF]=0;
 production_import_block();
 check(native_last_import_result==FMER_NATIVE_STALE&&!native_main_owner&&!native_import_ready&&(FM1_ALNK_CON0&0x800u)&&same(before,snapshot()),"defensive core validation refusal preserves music and releases quiet ownership");
 check(trace_result==FMER_NATIVE_STALE&&trace_apply>0&&trace_quiet>=trace_apply,"timed core refusal retains measured work instead of hiding it");
 auto glide=snapshot().controls;glide.value[FMER_SEQ_MODE]=0;glide.value[FMER_GLIDE_MODE]=0;glide.value[FMER_VOICE_BUDGET]=2;
 check(fmer_dsp_apply_controls(&glide),"prepare two-voice mode");requested_budget=2;
 glide.value[FMER_GLIDE_MODE]=1;check(fmer_dsp_apply_controls(&glide),"enable automatic mono");sync_audio_budget();
 check(requested_budget==1 && fmer_dsp_voice_limit()==1,"production budget mirror adopts automatic mono");
 fmer_dsp_get_controls(&controls);mirror_controls();glide=controls;glide.value[FMER_GLIDE_MODE]=0;
 check(fmer_dsp_apply_controls(&glide),"disable glide");sync_audio_budget();
 check(requested_budget==2 && fmer_dsp_voice_limit()==2,"stale main one-voice mirror cannot undo restored polyphony");
 check(fmer_dsp_voice_budget(1),"simulate existing bounded overload shed");sync_audio_budget();
 check(requested_budget==1 && fmer_dsp_voice_limit()==1,"production mirror still retains overload protection");
 const auto usb=usb_calls;for(unsigned i=0;i<10;++i)fm1_timer5_irq();check(usb_calls>usb,"deferred timer MIDI service resumes after ownership release");
 std::printf("FMER native board integration PASS: exact production source %s;quiet adoption, budget/state publication, both stale guards, timer producer exclusion and post-claim key preservation\n",FMER_NATIVE_BOARD_SOURCE_SHA256);
}
