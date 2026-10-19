// Execute exact board capture/pause/import statements and actual store adapter.
// Real shared DSP, synthetic NOR/registers/USB, no device I/O.
#include "../firmware/fm1/dsp_adapter.h"
#include "../firmware/fm1/bank_store.h"
#include "../firmware/fm1/panel_model.h"
#include "../firmware/fm1/trace.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <array>

static unsigned checks,programs,erases,spi_reads,feeds;
static bool silent_write;
static std::array<uint8_t,0x100000> nor;
static uint32_t fm1_ms,FM1_ALNK_CON0=0x800,previous_start;
static struct {uint32_t flash_id=0x856014,ready=1,controls_applied=1,in_audio,voice_limit,safe_mode,voices,stolen;} diag;
static struct {uint32_t notes;} fm1_in;
static uint32_t controls_generation=1,patch_ready,parameter_ready,audition_pending,transport_read,transport_write,mi_r,mi_w,keys_previous,requested_budget;
static int32_t q15[256],abuf[512];
static fmer_panel_t panel_state;
static fmer_midi_settings_t midi_requested;
static uint32_t midi_generation,midi_applied,midi_pending;
static uint32_t panic_request,midi_in_overflow,updating,engine,algorithm,va_wave,cutoff,delay_mix,attack_ms,release_ms;
static fmer_controls_t controls,applied_controls;
static fmer_midi_metrics_t midi_metrics_snapshot;
static fmer_performance_state_t performance_state;
static fmer_activity_state_t activity_pending;
static fmer_pattern_state_t pattern_pending;
#define FM1_TICKS_PER_US 24u
static uint32_t fake_ticks;
static uint32_t fm1_ticks(){return fake_ticks+=24u;}
#define RING_PUBLISH() ((void)0)
#define FL_XIP(off) (nor.data()+(off))
static uint32_t irq_save(){return 0;}
static void irq_restore(uint32_t){}
static void fm1_wdt_feed(){++feeds;}
static void fm1_audio_stop(){FM1_ALNK_CON0&=~0x800u;}
static void trace_event(uint32_t,uint32_t,int32_t,uint32_t){}
static void check(bool yes,const char *why)
{++checks;if(!yes){std::fprintf(stderr,"FAIL %u: %s\n",checks,why);std::exit(1);}}
static int ota_fread(uint32_t off,void *p,uint32_t n)
{if(!fmer_store_range(off,n))return -1;++spi_reads;std::memcpy(p,nor.data()+off,n);return 0;}
static int fl_erase4k(uint32_t off,uint32_t *took)
{check(!(FM1_ALNK_CON0&0x800u),"actual DMA stopped before erase");check(fmer_store_range(off,4096)&&!(off&4095),"erase bounds");++erases;*took=1;std::memset(nor.data()+off,255,4096);return 0;}
static int fl_write(uint32_t off,const void *src,uint32_t n)
{
 check(!(FM1_ALNK_CON0&0x800u),"actual DMA stopped before program");
 check(fmer_store_range(off,n)&&n&&n<=256&&((off&255)+n)<=256,"program bounds/page");++programs;
 if(silent_write)return 0;const auto *p=(const uint8_t *)src;
 for(uint32_t i=0;i<n;i++)nor[off+i]&=p[i];return 0;
}
static char *decimal(char *p,uint32_t n){return p+std::sprintf(p,"%u",n);}
static char *reply_begin(uint8_t *p,uint32_t){return (char *)p;}
static void reply_end(uint8_t *,char *){}
static void native_result_reply(uint32_t,uint32_t,uint32_t){}
#ifndef FMER_TEST_GLOBALS_HEADER
#define FMER_TEST_GLOBALS_HEADER "storage_board_globals.inc"
#endif
#ifndef FMER_TEST_ONBOARD_HEADER
#define FMER_TEST_ONBOARD_HEADER "../firmware/fm1/onboard_store.h"
#endif
#include FMER_TEST_GLOBALS_HEADER
#include FMER_TEST_ONBOARD_HEADER
static void production_pause()
{
#include "storage_board_pause.inc"
}
static void production_capture()
{
 native_live_generation=fmer_dsp_state_generation();
#include "storage_board_capture.inc"
}
static void production_import_pause()
{
#include "storage_board_import.inc"
}
static void production_import()
{
 production_import_pause();
 if(native_import_ready==2u) {
  check(!(FM1_ALNK_CON0&0x800u),"native adoption main service starts with DMA stopped");
  native_import_service();
  check(FM1_ALNK_CON0&0x800u,"native adoption always resumes DMA");
 }
}
static void save_until_pause(uint32_t slot,uint32_t action=1)
{
 native_live_generation=fmer_dsp_state_generation();storage_request(action,slot);
 check(storage_busy==1,"save requests coherent audio-owned capture");
 production_capture();native_service();check(storage_busy==2&&storage_pause_request,"capture publication requests pause");
}
static std::array<uint8_t,FMER_NATIVE_BYTES> snapshot()
{
 fmer_native_state_t state{};std::array<uint8_t,FMER_NATIVE_BYTES> bytes{};
 fmer_dsp_get_native(&state);check(fmer_native_encode(&state,bytes.data(),bytes.size())==FMER_NATIVE_OK,"snapshot real DSP");return bytes;
}
static bool same_musical(const std::array<uint8_t,FMER_NATIVE_BYTES> &a,const std::array<uint8_t,FMER_NATIVE_BYTES> &b)
{
 auto x=a,y=b;for(unsigned i=16;i<20;i++)x[i]=y[i]=0;for(unsigned i=28;i<32;i++)x[i]=y[i]=0;return x==y;
}
static int set_cutoff(uint16_t value)
{fmer_controls_t c;fmer_dsp_get_controls(&c);c.value[FMER_CUTOFF]=value;return fmer_dsp_apply_controls(&c);}
static void fresh_scan_and_save()
{
 nor.fill(0xa5);std::memset(nor.data()+FMER_STORE_LO,255,FMER_STORE_HI-FMER_STORE_LO);
 fmer_panel_init(&panel_state);storage_boot();
 check(storage_ready&&storage_boot_result==0&&onboard_store.blank_cells==73,"fresh boot mounts all73 erased cells");
 check(storage_boot_crc==0x7944953eu&&spi_reads>0,"fresh physical SPI scan matches historical erased-region CRC");
 check(!programs&&!erases,"boot never erases/programs");
 const auto before=snapshot();save_until_pause(5);const auto job=storage_job;
 storage_request(1,9);check(storage_slot==5&&storage_job==job,"concurrent SAVE cannot retarget active job");
 const auto writes=programs;storage_service();check(programs==writes&&storage_busy==2,"main cannot write before audio acknowledgement");
 fmer_dsp_midi(0x90,60,100,3);fm1_in.notes=1;
 production_pause();check(storage_audio_paused==1&&!(FM1_ALNK_CON0&0x800)&&!fmer_dsp_active(),"audio owner clears voices and stops DMA");
 storage_service();check(!storage_busy&&storage_result==0&&storage_has_slot(5),"complete persistent save acknowledged");
 check(FM1_ALNK_CON0&0x800,"DMA restarted after bounded main-loop save");
 check(native_saved_generation==fmer_dsp_state_generation(),"panic-only revision does not falsely mark saved patch edited");
 check(native_save_token==storage_capture_token&&native_save_state==2,"exact onboard bytes offered for optional PC mirror");
 std::array<uint8_t,FMER_NATIVE_BYTES> actual{};uint32_t length=0;
 check(fmer_bank_load(&onboard_bank,&onboard_store,5,actual.data(),fmer_dsp_original_default)==0&&fmer_bank_sound_equal(actual.data(),before.data()),"saved instrument equals coherent pre-pause snapshot");
 check(fmer_native_validate(actual.data(),actual.size())==FMER_NATIVE_OK&&actual[FMER_NATIVE_STEPS+1]==FMER_REST&&fmer_native_rd16(actual.data()+32+2*FMER_RECORD_MODE)==0,"sound export is a valid canonical empty project");
 check(std::memcmp(actual.data(),native_save_wire,actual.size())==0,"PC mirror exactly matches durable slot");
 for(uint32_t i=0;i<FMER_STORE_LO;i++)if(nor[i]!=0xa5)check(false,"lower protected bytes preserved");
 for(uint32_t i=FMER_STORE_HI;i<nor.size();i++)if(nor[i]!=0xa5)check(false,"upper protected bytes preserved");
}
static void conflict_and_timeout()
{
 save_until_pause(6);const auto writes=programs;mi_w=mi_r+1;production_pause();
 check(storage_audio_paused==2&&(FM1_ALNK_CON0&0x800),"queued MIDI refuses pause without stopping audio");
 storage_service();check(storage_result==11&&!storage_busy&&programs==writes,"stale pause performs no flash mutation");mi_r=mi_w;
 native_live_generation=fmer_dsp_state_generation();storage_request(1,7);const auto cancelled=storage_job;
 fm1_ms+=2001;storage_service();check(!storage_busy&&storage_result==10&&storage_finished_job==cancelled,"capture timeout is a completed refusal");
 production_capture();native_service();check(!storage_busy&&!storage_pause_request&&programs==writes,"late capture cannot revive timed-out SAVE");
 // Edit after request and before capture must not silently change the saved snapshot.
 native_live_generation=fmer_dsp_state_generation();storage_request(1,7);
 check(set_cutoff(777)!=0,"intervening live edit");
 production_capture();native_service();check(!storage_busy&&storage_result==11&&!storage_pause_request,"intervening pre-capture edit refused");
}
static void restore_and_boot()
{
 // A sound load must preserve even the high patterns, independent mixer and
 // recorder state, while assigning the recalled instrument to the selected track.
 fmer_native_state_t state{};fmer_dsp_get_native(&state);
 state.patterns[14].length=64;state.patterns[14].pitch[0]=72;state.patterns[14].pitch[1]=FMER_TIE;
 state.tracks[2].level=45;state.tracks[2].mute=1;state.tracks[2].chain_mask=0x8001;
 state.controls.value[FMER_RECORD_MODE]=1;
 check(fmer_dsp_set_native(&state,fmer_dsp_state_generation())!=0,"prepare live pattern16 and mixer edits");
 native_live_generation=fmer_dsp_state_generation();const auto before=snapshot();mi_w=mi_r+1;
 storage_request(2,5);production_capture();native_service();storage_service();
 check(storage_result==11&&!storage_busy&&same_musical(snapshot(),before),"queued MIDI blocks load without losing live edits");mi_r=mi_w;
 storage_request(2,5);check(storage_busy==1,"sound load first requests coherent project capture");
 production_capture();native_service();check(storage_busy==4&&!storage_pause_request&&(FM1_ALNK_CON0&0x800),"sound load captures without stopping DMA");
 storage_service();check(storage_busy==3&&native_import_ready,"load queues validated audio-owner adoption");
 production_import();storage_service();check(!storage_busy&&storage_result==0&&panel_state.save_slot==5,"load completes after audio-owner result");
 std::array<uint8_t,FMER_NATIVE_BYTES> saved{};uint32_t n=0;
 fmer_bank_load(&onboard_bank,&onboard_store,5,saved.data(),fmer_dsp_original_default);
 auto expected=saved;check(fmer_native_merge_sound_slot(expected.data(),before.data(),5)!=0,"merge expected instrument with coherent project");
 check(same_musical(snapshot(),expected),"sound load restores instrument and preserves all16 patterns plus project settings");
 fmer_dsp_get_native(&state);
 check(state.patterns[14].length==64&&state.patterns[14].pitch[0]==72&&state.patterns[14].pitch[1]==FMER_TIE&&state.tracks[2].chain_mask==0x8001&&state.tracks[2].mute==1&&state.tracks[2].level==45&&state.tracks[0].sound==5,"load retains pattern16, tie, wide chain and mixer; selects sound5");
 // Model a freshly initialized DSP at boot, rather than reusing the last project.
 std::array<uint8_t,FMER_NATIVE_BYTES> fresh{};
 check(fmer_dsp_original_default(0,fresh.data())&&fmer_native_decode(fresh.data(),fresh.size(),&state)==FMER_NATIVE_OK&&fmer_dsp_set_native(&state,fmer_dsp_state_generation()),"fresh standalone project before boot");
 const auto fresh_project=snapshot();expected=saved;
 check(fmer_native_merge_sound_slot(expected.data(),fresh_project.data(),5)!=0,"expected standalone sound boot preserves fresh project defaults");
 const auto writes=programs;storage_boot();
 check(programs==writes&&same_musical(snapshot(),expected)&&panel_state.save_slot==5,"boot restores latest sound with fresh project using reads only");
 fmer_dsp_get_native(&state);check(state.controls.value[FMER_RECORD_MODE]==1&&state.tracks[0].sound==5&&state.patterns[14].pitch[0]==FMER_REST,"sound-only standalone boot keeps OVERDUB and empty pattern16");
}
static void project_save_load_and_boot()
{
 fmer_native_state_t state{};fmer_dsp_get_native(&state);
 state.patterns[14].length=64;state.patterns[14].pitch[3]=36;state.patterns[14].pitch[4]=FMER_TIE;
 state.tracks[3].chain_mask=0x8001;state.tracks[3].level=37;state.tracks[3].mute=1;
 check(fmer_dsp_set_native(&state,fmer_dsp_state_generation())!=0,"prepare complete sixteen-pattern project");
 const auto expected=snapshot();save_until_pause(15,8);production_pause();storage_service();
 check(!storage_busy&&storage_result==0&&panel_state.save_scope==1&&panel_state.save_slot==15&&(storage_project_present&0x8000),"project16 saves through actual paused adapter and updates catalog");
 std::array<uint8_t,FMER_NATIVE_BYTES> saved{};
 check(fmer_bank_project_load(&onboard_bank,&onboard_store,15,saved.data())==0&&saved==expected,"project preserves exact coherent full snapshot");
 check(std::memcmp(saved.data(),native_save_wire,saved.size())==0,"project PC mirror equals committed snapshot");
 check(set_cutoff(2468)!=0,"change sound after project save");
 native_live_generation=fmer_dsp_state_generation();storage_request(9,15);
 check(storage_busy==3&&native_import_ready&&!storage_pause_request,"project load queues audio adoption without flash pause");
 production_import();storage_service();
 check(!storage_busy&&storage_result==0&&same_musical(snapshot(),expected)&&panel_state.save_scope==1,"project load restores complete sixteen-pattern snapshot");
 check(set_cutoff(4321)!=0,"different sound for later instrument save");
 save_until_pause(6);production_pause();storage_service();
 const auto writes=programs;storage_boot();
 check(programs==writes&&same_musical(snapshot(),expected)&&panel_state.save_scope==1&&panel_state.save_slot==15,"boot prefers latest saved project over later instrument save");
}
static void callback_guards_and_failure()
{
 uint8_t page[32]{};const auto writes=programs,old_erases=erases;
 storage_busy=2;storage_audio_paused=1;FM1_ALNK_CON0|=0x800;
 check(storage_program(0,FMER_STORE_LO,page,sizeof page)!=0&&storage_erase(0,FMER_STORE_LO)!=0,"DMA guard rejects stale pause acknowledgement");
 FM1_ALNK_CON0&=~0x800u;
 check(storage_program(0,0xe0000,page,sizeof page)!=0&&storage_erase(0,0xe0000)!=0,"storage rejects OTA partition");
 check(storage_program(0,0x96000,page,sizeof page)!=0&&storage_erase(0,0x96000)!=0,"storage rejects preceding preserved VM");
 diag.flash_id=0;check(storage_program(0,FMER_STORE_LO,page,sizeof page)!=0,"unexpected JEDEC blocks program");diag.flash_id=0x856014;
 check(programs==writes&&erases==old_erases,"refused callbacks never reach HAL");
 storage_busy=storage_audio_paused=0;FM1_ALNK_CON0|=0x800;
 const auto old_generation=onboard_store.generation;save_until_pause(8);production_pause();silent_write=true;
 storage_service();silent_write=false;
 check(!storage_busy&&storage_result==FMER_STORE_VERIFY&&storage_ready&&onboard_store.mounted,"failed save remounts and reports verification error");
 check(onboard_store.generation==old_generation&&storage_has_slot(5)&&storage_has_slot(8),"failed save retains existing record and original fallback");
 check(FM1_ALNK_CON0&0x800,"failed save still restarts audio");
}
static void default_bank_and_reset()
{
 check(set_cutoff(1234)!=0,"edit before saving default");save_until_pause(64);production_pause();storage_service();
 check(!storage_busy&&storage_result==0&&panel_state.save_bank==1,"default destination persists");
 check(set_cutoff(9876)!=0&&fmer_dsp_factory_preset(0),"recall edited default through audio API");
 fmer_controls_t c;fmer_dsp_get_controls(&c);check(c.value[FMER_CUTOFF]==9876,"sound-only recall preserves shared FX even for a saved default");
 for(unsigned action: {3u,5u,4u}) {
  native_live_generation=fmer_dsp_state_generation();storage_request(action,0);
  production_capture();native_service();production_pause();storage_service();
  check(!storage_busy&&storage_result==0,"reset finishes through exact pause/write adapter");
  check(storage_project_present==0x8000,"instrument resets preserve independent project16");
  if(action==3){check(fmer_dsp_factory_preset(0)!=0,"reset default recall");fmer_dsp_get_controls(&c);check(c.value[FMER_CUTOFF]==9876&&storage_has_slot(5),"default reset sound recall preserves shared FX and USER");}
  if(action==5)check(storage_count==64&&!storage_has_slot(5)&&storage_has_slot(64),"clear empties only USER");
  if(action==4)check(storage_count==128&&storage_has_slot(5),"reset USER restores all64 independent copies");
 }
 const auto writes=programs;storage_boot();check(storage_count==128&&programs==writes,"reset epochs survive read-only reboot");
}
int main()
{
 check(fmer_dsp_init()!=0,"real shared DSP initializes");
 fresh_scan_and_save();conflict_and_timeout();restore_and_boot();callback_guards_and_failure();project_save_load_and_boot();default_bank_and_reset();
 midi_requested={{3,4,1,1,0,1,0,0}};panel_state.midi=midi_requested;
 fmer_dsp_set_midi_settings(&midi_requested);native_live_generation=fmer_dsp_state_generation();
 storage_request(6,0);production_capture();native_service();production_pause();storage_service();
 check(!storage_busy&&storage_result==0&&!std::memcmp(&onboard_bank.midi,&midi_requested,sizeof midi_requested),"exact board pipeline saves global MIDI settings");
 const auto expected_midi=midi_requested;fmer_midi_defaults(&midi_requested);panel_state.midi=midi_requested;storage_boot();
 check(!std::memcmp(&panel_state.midi,&expected_midi,sizeof expected_midi),"boot restores MIDI setup independently of patch");
 const auto live_before_clear=snapshot();save_until_pause(0,10);production_pause();storage_service();
 check(!storage_busy&&storage_result==0&&!storage_project_present&&storage_count==128&&same_musical(snapshot(),live_before_clear),"Clear Projects removes only stored projects and retains live project and sound banks");
 check(!std::memcmp(&onboard_bank.midi,&expected_midi,sizeof expected_midi),"Clear Projects preserves MIDI setup");
 save_until_pause(0,7);production_pause();storage_service();
 check(!storage_busy&&storage_result==0&&onboard_bank.layout==3&&storage_count==128&&!storage_project_present,"explicit Initialize publishes empty projects and 128 independent defaults");
 check(!std::memcmp(&onboard_bank.midi,&expected_midi,sizeof expected_midi),"Initialize preserves MIDI setup");
 const auto writes=programs;storage_boot();
 check(programs==writes&&storage_count==128&&!storage_project_present&&onboard_bank.layout==3,"initialized layout and project clear survive read-only reboot");
 check(fmer_dsp_set_fx_default(719,1)!=0,"prepare custom routing");
 save_until_pause(0,11);production_pause();storage_service();
 check(!storage_busy && !storage_result && onboard_bank.fx_default==719,"board pipeline captures and commits personal routing default");
 check(fmer_dsp_set_fx_default(0,1)!=0,"simulate lost volatile default");storage_boot();
 check(onboard_bank.fx_default==719 && fmer_dsp_fx_order()==719,"read-only boot applies personal default with no saved project");
 const auto before_default_reset=snapshot();const auto midi_before_default_reset=onboard_bank.midi;
 save_until_pause(0,12);production_pause();storage_service();
 check(!storage_busy && !storage_result && onboard_bank.fx_default==0 && fmer_dsp_fx_order()==0,"original FX reset applies and persists rank zero");
 auto reset_expected=before_default_reset;fmer_native_wr16(reset_expected.data()+FMER_NATIVE_PADDING+32,0);fmer_native_wr32(reset_expected.data()+28,fmer_native_crc(reset_expected.data()));
 check(same_musical(snapshot(),reset_expected) && !std::memcmp(&onboard_bank.midi,&midi_before_default_reset,sizeof midi_before_default_reset),"routing reset preserves every other working value and MIDI setup");
 std::printf("PASS %u storage board integration checks; exact production capture/pause/import and adapter; real DSP, synthetic NOR only\n",checks);return 0;
}
