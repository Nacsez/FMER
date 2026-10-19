/* SPDX-License-Identifier: GPL-3.0-only
 * Main-loop adapter for the original FMER journal. Included after board HAL
 * and ota_fread. No erase/program or CRC occurs in an audio callback.
 */
#ifndef FMER_ONBOARD_STORE_H
#define FMER_ONBOARD_STORE_H
static char *reply_begin(uint8_t *,uint32_t);
static void reply_end(uint8_t *,char *);
static void native_result_reply(uint32_t,uint32_t,uint32_t);
static uint32_t storage_boot_scanning;
static fmer_midi_settings_t storage_midi_frozen;
static int storage_read(void *ctx,uint32_t off,void *dst,uint32_t n)
{
 (void)ctx;
 if(diag.flash_id!=0x856014u || !fmer_store_range(off,n))return -1;
 fm1_wdt_feed();
 if(storage_boot_scanning)return ota_fread(off,dst,n);
 /* fl_plain_window_init maps this data partition unencrypted. Runtime reads
  * leave SPI ownership and the audio clock alone; the HAL invalidates caches
  * before every erase/program, and readback verifies actual written bytes. */
 memcpy(dst,(const void *)FL_XIP(off),n);return 0;
}
static int storage_erase(void *ctx,uint32_t off)
{
 uint32_t took;(void)ctx;fm1_wdt_feed();
 if(diag.flash_id!=0x856014u || storage_audio_paused!=1u || (FM1_ALNK_CON0&0x800u) || !storage_busy ||
    !fmer_store_range(off,4096u) || (off&4095u))return -1;
 return fl_erase4k(off,&took);
}
static int storage_program(void *ctx,uint32_t off,const void *src,uint32_t n)
{
 (void)ctx;fm1_wdt_feed();
 if(diag.flash_id!=0x856014u || storage_audio_paused!=1u || (FM1_ALNK_CON0&0x800u) || !storage_busy ||
    !n || n>256u || (off&255u)+n>256u || !fmer_store_range(off,n))return -1;
 return fl_write(off,src,n);
}
static const fmer_store_io_t storage_io={0,storage_read,storage_erase,storage_program};
static void storage_catalog(void)
{
 uint32_t slot,i;memset(storage_present,0,sizeof storage_present);storage_count=0;
 memset(storage_names,0,sizeof storage_names);
 for(slot=0;slot<128u;slot++) {
  fmer_dsp_cache_sound(slot,0);
  if(fmer_bank_load(&onboard_bank,&onboard_store,slot,storage_wire,fmer_dsp_original_default)!=FMER_STORE_OK)continue;
  storage_crc[slot]=fmer_store_crc(storage_wire,FMER_NATIVE_BYTES);++storage_count;
  fmer_dsp_cache_sound(slot,storage_wire);
  storage_present[slot/32u]|=1u<<(slot%32u);
  for(i=0;i<10u;i++) {
   uint8_t ch=storage_wire[FMER_NATIVE_VCED+145u+i];
   storage_names[slot][i]=(char)(ch>=32u&&ch<127u?ch:' ');
  }
 }
 storage_project_present=0;memset(storage_project_names,0,sizeof storage_project_names);
 for(slot=0;slot<16;slot++){
  if(fmer_bank_project_load(&onboard_bank,&onboard_store,slot,storage_wire)!=FMER_STORE_OK)continue;
  storage_project_present|=1u<<slot;storage_project_crc[slot]=fmer_store_crc(storage_wire,FMER_NATIVE_BYTES);
  for(i=0;i<10;i++){uint8_t ch=storage_wire[FMER_NATIVE_VCED+145+i];storage_project_names[slot][i]=(char)(ch>=32&&ch<127?ch:' ');}
 }

}
static void storage_boot(void)
{
 uint32_t slot;storage_result=FMER_STORE_NOT_READY;storage_ready=0;
 if(diag.flash_id!=0x856014u)return;
 storage_boot_scanning=1;
 storage_boot_result=fmer_store_mount(&onboard_store,&storage_io);
 if(storage_boot_result==FMER_STORE_OK || storage_boot_result==FMER_STORE_FOREIGN) {
  if(fmer_store_region_crc(&onboard_store,&storage_boot_crc)!=FMER_STORE_OK)storage_boot_result=FMER_STORE_IO;
  else if(fmer_bank_mount(&onboard_bank,&onboard_store)==FMER_STORE_OK)storage_ready=1;
  else storage_boot_result=FMER_STORE_VERIFY;
 }
 storage_result=storage_boot_result;
 if(storage_ready)storage_catalog();
 storage_boot_scanning=0;
 if(!storage_ready || !diag.ready)return;
 fmer_dsp_set_fx_default(onboard_bank.fx_default,1);
 fmer_dsp_set_midi_settings(&onboard_bank.midi);panel_state.midi=onboard_bank.midi;
 midi_requested=onboard_bank.midi;midi_generation=midi_applied=1;
 slot=onboard_bank.latest_project;
 if(slot<16u&&(storage_project_present&(1u<<slot))){
  storage_action=9;storage_slot=slot;storage_result=fmer_bank_project_load(&onboard_bank,&onboard_store,slot,storage_wire);
 }else{
  slot=onboard_bank.latest_slot;if(slot>=128u||!storage_has_slot(slot))return;
  storage_action=2;storage_slot=slot;storage_result=fmer_bank_load(&onboard_bank,&onboard_store,slot,storage_wire,fmer_dsp_original_default);
 }
 if(storage_result==FMER_STORE_OK){
  if(storage_action==2u&&onboard_bank.layout==3u){
   /* A Sound has no saved project. Keep the fresh standalone project defaults
    * (including OVERDUB) rather than importing its interchange-only STEP mirror.
    * Legacy full-arrangement boot and explicit Project boot remain exact. */
   native_export_token=0;fmer_dsp_get_native(&native_main_state);
   if(fmer_native_encode(&native_main_state,native_export_wire,sizeof native_export_wire)!=FMER_NATIVE_OK||
      !fmer_native_merge_sound_slot(storage_wire,native_export_wire,slot)){storage_result=12;return;}
  }
  if(fmer_native_decode(storage_wire,FMER_NATIVE_BYTES,&native_import_pending)!=FMER_NATIVE_OK||!fmer_dsp_set_native(&native_import_pending,fmer_dsp_state_generation()))storage_result=12;
  else{panel_state.save_scope=storage_action==9;panel_state.save_slot=slot%64u;panel_state.save_bank=panel_state.save_scope?0:slot/64u;}
 }

}
static void storage_finish(uint32_t result)
{
 storage_result=result;storage_busy=0;storage_finished_job=storage_job;
 trace_event(FMER_TRACE_STORAGE,storage_slot,(int32_t)result,storage_action);
}
/* Decode into the existing mailbox; never allocate a second full native state. */
static void storage_publish_import(const uint8_t *wire)
{
 uint32_t f;
 if(fmer_native_decode(wire,FMER_NATIVE_BYTES,&native_import_pending)!=FMER_NATIVE_OK){storage_finish(12);return;}
 f=irq_save();
 if(controls_generation!=diag.controls_applied||patch_ready||parameter_ready||audition_pending||
    transport_read!=transport_write||mi_r!=mi_w||native_live_generation!=storage_expected){irq_restore(f);storage_finish(11);return;}
 if(!++native_serial)native_serial=1;storage_import_token=native_serial;
 native_import_expected=storage_expected;native_import_id=storage_import_token;
 native_last_import_id=storage_import_token;native_last_import_result=FMER_NATIVE_BUSY;
 storage_busy=3;RING_PUBLISH();native_import_ready=1;irq_restore(f);
}
static void storage_request(uint32_t action,uint32_t slot)
{
 uint32_t token;
 if(storage_busy)return;
 if(!++storage_serial)storage_serial=1;storage_job=storage_serial;
 storage_slot=slot;storage_action=action;storage_started=fm1_ms;storage_requested_generation=native_live_generation;
 if(slot>=((action==8||action==9)?16u:128u)||action<1u||action>12u){storage_finish(FMER_STORE_ARGUMENT);return;}
 if(!storage_ready||!diag.ready||(onboard_bank.layout!=3u&&action!=2u&&action!=7u)){storage_finish(FMER_STORE_NOT_READY);return;}
 if(midi_pending||native_import_ready||native_transfer.active||native_capture_request!=native_capture_done||native_capture_handled!=native_capture_done){storage_finish(10);return;}
 storage_midi_frozen=midi_requested;storage_busy=1;storage_result=10;
 if(action==9u){
  storage_expected=native_live_generation;
  storage_result=fmer_bank_project_load(&onboard_bank,&onboard_store,slot,storage_wire);
  if(storage_result!=FMER_STORE_OK){storage_finish(storage_result);return;}
  storage_publish_import(storage_wire);
 }else{
  if(action==2u&&!storage_has_slot(slot)){storage_finish(FMER_STORE_EMPTY);return;}
  token=native_request_capture(3u);if(!token){storage_finish(10);return;}storage_capture_token=token;
 }
}
static void storage_service(void)
{
 uint32_t result,f;
 if(!storage_busy)return;
 if(storage_busy==4u){
  native_export_token=0;
  result=fmer_bank_load(&onboard_bank,&onboard_store,storage_slot,native_export_wire,fmer_dsp_original_default);
  if(result!=FMER_STORE_OK){storage_finish(result);return;}
  if(!fmer_native_merge_sound_slot(native_export_wire,storage_wire,storage_slot)){storage_finish(12);return;}
  storage_publish_import(native_export_wire);return;
 }
 if(storage_busy==3u) {
  if(native_import_ready)return;
  if(native_last_import_id!=storage_import_token || native_last_import_result!=FMER_NATIVE_OK){storage_finish(11);return;}
  panel_state.save_scope=storage_action==9u;panel_state.save_slot=storage_slot%64u;panel_state.save_bank=panel_state.save_scope?0:storage_slot/64u;panel_state.family=FMER_PANEL_HOME;fmer_panel_navigate(&panel_state);
  storage_finish(FMER_STORE_OK);return;
 }
 if(storage_busy!=2u || !storage_audio_paused) {
  if((uint32_t)(fm1_ms-storage_started)>2000u) {
   f=irq_save();storage_pause_request=0;irq_restore(f);storage_finish(10);
  }
  return;
 }
 if(storage_audio_paused!=1u){storage_audio_paused=0;storage_finish(11);return;}
 /* The ISR acknowledged quiet ownership and stopped DMA; only main writes.
  * Preserve its frozen bytes through all verification, then publish catalog. */
 result=storage_action==1u?fmer_bank_save(&onboard_bank,&onboard_store,storage_slot,storage_wire):
     storage_action==6u?fmer_bank_save_midi(&onboard_bank,&onboard_store,&storage_midi_frozen):
     storage_action==7u?fmer_bank_initialize(&onboard_bank,&onboard_store):
     storage_action==8u?fmer_bank_project_save(&onboard_bank,&onboard_store,storage_slot,storage_wire):
     storage_action==10u?fmer_bank_reset_projects(&onboard_bank,&onboard_store):
     storage_action==11u?fmer_bank_save_fx_default(&onboard_bank,&onboard_store,fmer_native_rd16(storage_wire+FMER_NATIVE_PADDING+32)):
     storage_action==12u?fmer_bank_save_fx_default(&onboard_bank,&onboard_store,0u):
     fmer_bank_reset(&onboard_bank,&onboard_store,storage_action);
 if(result==FMER_STORE_OK&&(storage_action==1u||storage_action==8u)){
  result=storage_action==8u?fmer_bank_project_load(&onboard_bank,&onboard_store,storage_slot,native_save_wire):
      fmer_bank_load(&onboard_bank,&onboard_store,storage_slot,native_save_wire,fmer_dsp_original_default);
  if(result==FMER_STORE_OK&&(storage_action==8u?memcmp(native_save_wire,storage_wire,FMER_NATIVE_BYTES):!fmer_bank_sound_equal(native_save_wire,storage_wire)))result=FMER_STORE_VERIFY;
 }
 if(result==FMER_STORE_OK&&(storage_action==1u||storage_action==8u)){
  native_save_token=storage_capture_token;native_saved_generation=storage_saved_revision;native_save_state=2;
  panel_state.save_scope=storage_action==8u;panel_state.save_slot=storage_slot%64u;panel_state.save_bank=panel_state.save_scope?0:storage_slot/64u;
 }
 /* Failed writes can have committed despite a lost acknowledgement. Remount
  * before any future mutation; never retry with stale indexes. */
 if(!onboard_store.mounted) {
  uint32_t mounted=fmer_store_mount(&onboard_store,&storage_io);
  storage_ready=(mounted==FMER_STORE_OK || mounted==FMER_STORE_FOREIGN);
  if(storage_ready && fmer_bank_mount(&onboard_bank,&onboard_store)!=FMER_STORE_OK)storage_ready=0;
 }
 if(storage_ready)storage_catalog();
 if(storage_ready && (storage_action==11u || storage_action==12u))fmer_dsp_set_fx_default(onboard_bank.fx_default,result==FMER_STORE_OK && storage_action==12u);
 memset(abuf,0,sizeof abuf);storage_audio_paused=0;RING_PUBLISH();FM1_ALNK_CON0|=0x800u;
 storage_finish(result);
}
static void storage_reply(void)
{
 uint8_t response[384];char *p=reply_begin(response,21);uint32_t i;
 uint32_t v[]={4,storage_ready,storage_busy,storage_action,storage_slot,storage_result,
  storage_job,storage_finished_job,storage_count,onboard_bank.latest_slot,
  (uint32_t)onboard_store.generation,(uint32_t)(onboard_store.generation>>32),
  onboard_store.blank_cells,onboard_store.foreign_cells,onboard_store.incomplete_cells,
  storage_boot_crc,storage_boot_result,FMER_NATIVE_BYTES,onboard_bank.layout,onboard_bank.latest_project,storage_project_present,16u,onboard_bank.fx_default};
 for(i=0;i<sizeof v/sizeof v[0];i++){if(i)*p++=' ';p=decimal(p,v[i]);}reply_end(response,p);
}
static void storage_catalog_reply(uint32_t slot)
{
 uint8_t response[192];char *p=reply_begin(response,23);uint32_t i;
 p=decimal(p,slot);*p++=' ';p=decimal(p,storage_has_slot(slot));
 *p++=' ';p=decimal(p,(uint32_t)onboard_store.generation);
 *p++=' ';p=decimal(p,(uint32_t)(onboard_store.generation>>32));
 *p++=' ';p=decimal(p,storage_has_slot(slot)?storage_crc[slot]:0u);
 for(i=0;i<10u;i++){*p++=' ';p=decimal(p,(uint8_t)storage_names[slot][i]);}reply_end(response,p);
}
static void storage_export(uint32_t slot)
{
 uint32_t n,result;
 if(storage_busy || native_capture_request!=native_capture_done || native_capture_handled!=native_capture_done) {
  native_result_reply(24,slot,FMER_NATIVE_BUSY);return;
 }
 if(!storage_has_slot(slot)){native_result_reply(24,slot,FMER_NATIVE_ARGUMENT);return;}
 result=fmer_bank_load(&onboard_bank,&onboard_store,slot,native_export_wire,fmer_dsp_original_default);n=FMER_NATIVE_BYTES;
 if(result!=FMER_STORE_OK || n!=FMER_NATIVE_BYTES || fmer_native_validate(native_export_wire,n)!=FMER_NATIVE_OK) {
  native_export_token=0;native_result_reply(24,slot,FMER_NATIVE_FORMAT);return;
 }
 if(!++native_serial)native_serial=1;native_export_token=native_serial;
 native_result_reply(24,slot,FMER_NATIVE_OK);
}
static void storage_project_catalog_reply(uint32_t slot)
{
 uint8_t response[192];char *p=reply_begin(response,29);uint32_t i,present=slot<16u&&((storage_project_present>>slot)&1u);
 p=decimal(p,slot);*p++=' ';p=decimal(p,present);*p++=' ';p=decimal(p,(uint32_t)onboard_store.generation);
 *p++=' ';p=decimal(p,(uint32_t)(onboard_store.generation>>32));*p++=' ';p=decimal(p,present?storage_project_crc[slot]:0u);
 for(i=0;i<10u;i++){*p++=' ';p=decimal(p,present?(uint8_t)storage_project_names[slot][i]:0u);}reply_end(response,p);
}
static void storage_project_export(uint32_t slot)
{
 uint32_t result;
 if(storage_busy||native_capture_request!=native_capture_done||native_capture_handled!=native_capture_done){native_result_reply(30,slot,FMER_NATIVE_BUSY);return;}
 result=fmer_bank_project_load(&onboard_bank,&onboard_store,slot,native_export_wire);
 if(result!=FMER_STORE_OK){native_export_token=0;native_result_reply(30,slot,FMER_NATIVE_FORMAT);return;}
 if(!++native_serial)native_serial=1;native_export_token=native_serial;native_result_reply(30,slot,FMER_NATIVE_OK);
}
#endif
