// Real shared adapter plus the exact board control-mailbox rules, no HAL/I/O.
#include "../firmware/fm1/control_mailbox.h"
#include "../firmware/fm1/dsp_adapter.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
static void check(bool ok,const char *why){if(!ok){std::fprintf(stderr,"FAIL: %s\n",why);std::exit(1);}}
static void select(unsigned step){fmer_controls_t c;fmer_dsp_get_controls(&c);c.value[FMER_SEQ_STEP]=(uint16_t)step;check(fmer_dsp_apply_controls(&c),"select real stored step");}
static void malformed_snapshot(fmer_controls_t* c){fmer_dsp_get_controls(c);c->value[FMER_ATTACK]=65535;}
int main(){
 check(fmer_dsp_init(),"real adapter initializes");
 fmer_controls_t step_mode;fmer_dsp_get_controls(&step_mode);step_mode.value[FMER_RECORD_MODE]=0;
 check(fmer_dsp_apply_controls(&step_mode),"explicit STEP mode for untimed mailbox recording tests");
 fmer_controls_t base,next,canonical;fmer_dsp_get_controls(&base);next=canonical=base;
 uint32_t dirty[FMER_CONTROL_WORDS]{},changed[FMER_CONTROL_WORDS]{};
 const auto before_bad_snapshot=fmer_dsp_state_generation();
 check(!fmer_control_adopt(&canonical,dirty,malformed_snapshot,fmer_dsp_apply_controls),"non-dirty malformed snapshot is rejected by canonical DSP validator");
 fmer_controls_t after_bad_snapshot;fmer_dsp_get_controls(&after_bad_snapshot);
 check(!memcmp(&base,&after_bad_snapshot,sizeof base) && before_bad_snapshot==fmer_dsp_state_generation(),"invalid merged state never commits");
 // main copies budget4; an audio interrupt sheds to3 before an unrelated edit
 // publishes. The stale copied4 is not an instruction to undo the shed.
 canonical.value[FMER_VOICE_BUDGET]=3;next.value[FMER_CUTOFF]=2200;
 check(fmer_control_publish(&canonical,dirty,&base,&next,changed)==1,"only deliberate cutoff is published");
 check(canonical.value[FMER_VOICE_BUDGET]==3 && !fmer_control_dirty(dirty,FMER_VOICE_BUDGET),"audio shed survives stale main snapshot");
 check(fmer_control_dirty(dirty,FMER_CUTOFF),"actual edit remains pending");
 check(fmer_dsp_voice_budget(3),"overload reduction applies in the audio owner before returning to main");
 fmer_controls_t shed;fmer_dsp_get_controls(&shed);
 check(fmer_control_snapshot_source(&canonical,&shed,1,1,1)->value[FMER_VOICE_BUDGET]==3,"settled-generation reconciliation cannot undo the adopted shed");
 check(fmer_dsp_voice_budget(4),"explicit reset for remaining cases");
 base=canonical;next=base;next.value[FMER_VOICE_BUDGET]=4;
 check(fmer_control_publish(&canonical,dirty,&base,&next,changed)==1 && fmer_control_dirty(dirty,FMER_VOICE_BUDGET),"explicit owner restoration remains possible");

 select(5);fmer_dsp_get_controls(&base);next=canonical=base;
 next.value[FMER_SEQ_LENGTH]=8;next.value[FMER_SEQ_PITCH]=65;
 next.value[FMER_SEQ_VELOCITY]=87;next.value[FMER_SEQ_GATE]=42;
 memset(dirty,0,sizeof dirty);
 check(fmer_control_batch_valid(&next),"pending length and field edit is valid at captured step5");
 fmer_control_publish(&canonical,dirty,&base,&next,changed);
 check(!fmer_control_dirty(dirty,FMER_SEQ_STEP),"step was not explicitly moved by main");
 // Advance the REAL recording path from5 to15 after the main snapshot.
 check(fmer_dsp_transport(FMER_TRANSPORT_RECORD),"step-entry begins");
 for(unsigned note=50;note<60;note++){fmer_dsp_midi(0x90,(uint8_t)note,70,1);fmer_dsp_midi(0x80,(uint8_t)note,0,1);}
 fmer_controls_t recorded;fmer_dsp_get_controls(&recorded);
 check(recorded.value[FMER_SEQ_STEP]==15,"audio owner recorded ten notes independently of main");
 check(fmer_control_adopt(&canonical,dirty,fmer_dsp_get_controls,fmer_dsp_apply_controls),"recording-aware shrink adoption succeeds");
 fmer_controls_t actual;fmer_dsp_get_controls(&actual);
 check(actual.value[FMER_SEQ_LENGTH]==8 && actual.value[FMER_SEQ_STEP]==7,"implicit selection clamps to shortened pattern");
 check(actual.value[FMER_SEQ_PITCH]==65 && actual.value[FMER_SEQ_VELOCITY]==87 && actual.value[FMER_SEQ_GATE]==42,"explicit step fields survive selection refresh");
 check(fmer_dsp_transport(FMER_TRANSPORT_RECORD),"step-entry ends");
 select(6);select(7);fmer_dsp_get_controls(&actual);
 check(actual.value[FMER_SEQ_PITCH]==65 && actual.value[FMER_SEQ_GATE]==42,"edited target step retained in real pattern");

 // An unrelated edit during recording must not move the cursor backwards or
 // copy a previous step's pitch onto the newly selected one.
 select(0);fmer_dsp_get_controls(&base);next=canonical=base;next.value[FMER_DELAY]=23;
 memset(dirty,0,sizeof dirty);fmer_control_publish(&canonical,dirty,&base,&next,changed);
 check(fmer_dsp_transport(FMER_TRANSPORT_RECORD),"second step-entry begins");
 fmer_dsp_midi(0x90,72,91,1);fmer_dsp_midi(0x80,72,0,1);fmer_dsp_get_controls(&recorded);
 check(recorded.value[FMER_SEQ_STEP]==1,"recording advanced before unrelated adoption");
 check(fmer_control_snapshot_source(&base,&recorded,1,3,3)->value[FMER_SEQ_STEP]==1,"readback sees recorded cursor before main panel reconciliation");
 check(fmer_control_snapshot_source(&canonical,&recorded,1,4,3)->value[FMER_DELAY]==23,"readback preserves pending edits until adoption");
 check(fmer_control_adopt(&canonical,dirty,fmer_dsp_get_controls,fmer_dsp_apply_controls),"unrelated edit merges onto fresh snapshot");
 fmer_dsp_get_controls(&actual);
 check(actual.value[FMER_SEQ_STEP]==1 && actual.value[FMER_SEQ_PITCH]==recorded.value[FMER_SEQ_PITCH] && actual.value[FMER_DELAY]==23,"recorded cursor and neighbor data preserved");
 fmer_dsp_panic();
 // Bank0 has an old long cursor; bank1 has a distinct short stored pattern.
 fmer_dsp_get_controls(&actual);actual.value[FMER_SEQ_PATTERN]=1;
 check(fmer_dsp_apply_controls(&actual),"choose destination bank1");
 fmer_dsp_get_controls(&actual);actual.value[FMER_SEQ_LENGTH]=1;actual.value[FMER_SEQ_PITCH]=89;
 actual.value[FMER_SEQ_VELOCITY]=76;actual.value[FMER_SEQ_GATE]=37;
 check(fmer_dsp_apply_controls(&actual),"prepare short destination pattern");
 actual.value[FMER_SEQ_PATTERN]=0;check(fmer_dsp_apply_controls(&actual),"return old bank");
 fmer_dsp_get_controls(&actual);actual.value[FMER_SEQ_LENGTH]=64;
 check(fmer_dsp_apply_controls(&actual),"expand old bank");select(63);
 fmer_dsp_get_controls(&base);next=canonical=base;next.value[FMER_SEQ_PATTERN]=1;
 memset(dirty,0,sizeof dirty);fmer_control_publish(&canonical,dirty,&base,&next,changed);
 check(fmer_control_adopt(&canonical,dirty,fmer_dsp_get_controls,fmer_dsp_apply_controls),"bank adoption loads destination before old step63 can be reapplied");
 fmer_dsp_get_controls(&actual);
 check(actual.value[FMER_SEQ_PATTERN]==1&&actual.value[FMER_SEQ_LENGTH]==1&&actual.value[FMER_SEQ_STEP]==0&&
       actual.value[FMER_SEQ_PITCH]==89&&actual.value[FMER_SEQ_VELOCITY]==76&&actual.value[FMER_SEQ_GATE]==37,
       "bank-only selection preserves every destination value and chooses valid cursor0");

 // One pending gesture can deliberately select bank2, grow to four steps,
 // select step3, and edit that step; old bank1 data must remain untouched.
 fmer_dsp_get_controls(&base);next=canonical=base;next.value[FMER_SEQ_PATTERN]=2;
 next.value[FMER_SEQ_LENGTH]=4;next.value[FMER_SEQ_STEP]=3;next.value[FMER_SEQ_PITCH]=81;
 next.value[FMER_SEQ_VELOCITY]=92;next.value[FMER_SEQ_GATE]=61;
 memset(dirty,0,sizeof dirty);fmer_control_publish(&canonical,dirty,&base,&next,changed);
 check(fmer_control_adopt(&canonical,dirty,fmer_dsp_get_controls,fmer_dsp_apply_controls),"bank, length, step and explicit fields adopt in dependency order");
 fmer_dsp_get_controls(&actual);
 check(actual.value[FMER_SEQ_PATTERN]==2&&actual.value[FMER_SEQ_LENGTH]==4&&actual.value[FMER_SEQ_STEP]==3&&
       actual.value[FMER_SEQ_PITCH]==81&&actual.value[FMER_SEQ_VELOCITY]==92&&actual.value[FMER_SEQ_GATE]==61,
       "explicit destination edits survive bank and step refresh");
 fmer_native_state_t bank_state{};fmer_dsp_get_native(&bank_state);
 check(bank_state.patterns[0].pitch[0]==89&&bank_state.patterns[0].velocity[0]==76&&
       bank_state.patterns[1].pitch[3]==81&&bank_state.patterns[1].pitch[0]==FMER_REST,
       "mailbox edits only requested bank and step");

 fmer_dsp_get_controls(&base);next=canonical=base;next.value[FMER_SEQ_PATTERN]=3;next.value[FMER_TEMPO]=301;
 memset(dirty,0,sizeof dirty);fmer_control_publish(&canonical,dirty,&base,&next,changed);
 const auto generation=fmer_dsp_state_generation();
 check(!fmer_control_adopt(&canonical,dirty,fmer_dsp_get_controls,fmer_dsp_apply_controls),"malformed combined edit is rejected");
 fmer_dsp_get_controls(&actual);
 check(!memcmp(&base,&actual,sizeof base)&&generation==fmer_dsp_state_generation(),"invalid field cannot partially select destination bank");
 // Exercise every valid control through the actual main-to-audio mailbox.
 for(unsigned id=0;id<FMER_PARAM_COUNT;++id){
  fmer_dsp_get_controls(&base);next=canonical=base;
  next.value[id]=static_cast<uint16_t>(fmer_control_max(id));
  if(id==FMER_SEQ_STEP)next.value[id]=next.value[FMER_SEQ_LENGTH]-1;
  if(id==FMER_SEQ_LENGTH && next.value[FMER_SEQ_STEP]>=next.value[id])next.value[FMER_SEQ_STEP]=0;
  check(fmer_control_batch_valid(&next),"every canonical maximum publishes through mailbox");
 }
 for(unsigned division=0;division<8;++division){
  fmer_dsp_get_controls(&base);next=canonical=base;next.value[FMER_DELAY_SYNC]=division;
  memset(dirty,0,sizeof dirty);fmer_control_publish(&canonical,dirty,&base,&next,changed);
  check(fmer_control_batch_valid(&next) && fmer_control_adopt(&canonical,dirty,fmer_dsp_get_controls,fmer_dsp_apply_controls),"sync division crosses real mailbox boundary");
  fmer_dsp_get_controls(&actual);check(actual.value[FMER_DELAY_SYNC]==division,"audio owner adopted exact sync choice");
 }
 std::puts("FMER control mailbox PASS: stale-budget race, recording advance, bank-first adoption, explicit edits and nonmutating refusal");
}
