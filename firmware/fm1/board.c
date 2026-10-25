/* SPDX-License-Identifier: GPL-3.0-only
 * FMER board adapter, using the attributed, pinned Felucca board HAL.
 * No Felucca musical engine, preset store, fonts or startup erase is included.
 * Experimental bench identity 708 is not an upstream release version. */
#include <stdint.h>
#include <string.h>
#include "dsp_adapter.h"
#include "control_model.h"
#include "panel_model.h"
#include "panel_gesture.h"
#include "led_model.h"
#include "control_mailbox.h"
#include "bank_store.h"
#define HALF_FRAMES 128u
#define HALF_WORDS (2u * HALF_FRAMES)
#define FELUCCA_OTA 1
#define FELUCCA_CDC 0
#define FELUCCA_UAC 1
#define FELUCCA_ID "FM-1_735"
#define RING_PUBLISH() __asm__ volatile("csync" ::: "memory")
#include "fm1_time.h"
#include "fm1_sys.h"
#include "fm1_irq.h"
#include "fm1_guard.h"
#include "fm1_input.h"
#include "fm1_timer.h"
#include "fm1_audio.h"
#include "fm1_adc.h"
#include "fm1_lcd_hw.h"
/* Disjoint, separately guarded paths: musical journal and staged updater.
 * Neither callback accepts the other's partition. No startup formatting. */
#define FL_RANGE_OK(off, n) (FL_IN(off, n, 0x97000u, 0xE0000u) || FL_IN(off, n, 0xE0000u, 0xE5000u))
#include "fm1_flash.h"
#include "lcd.c"
#include FMER_USB_SOURCE
#include FMER_UART_SOURCE
#include "ota.c"
#include "ui.h"
#define FMER_TRACE_LOCK() irq_save()
#define FMER_TRACE_UNLOCK(f) irq_restore(f)
#include "trace.h"

#define BG 0x0021u       /* CADER #070709, quantized RGB565 */
#define PANEL 0x1082u    /* #101014 */
#define INK 0xF7DFu      /* #f5f7fa */
#define GREEN 0x77EAu    /* #76ff53 */
#define PINK 0xFBDau     /* #ff78d4 */
#define BOOT_MAGIC 0x464D4552u
/* External linkage is intentional: .noinit contains retained bytes. */
struct { uint32_t magic, pending, failed; } fmer_boot __attribute__((section(".noinit")));
static volatile struct {
    uint32_t in_audio, halves, max_us, overruns, midi_overflows, rejected;
    uint32_t voices, heap, flash_id, safe_mode, ready, init_failed;
    uint32_t max_event_us, max_dsp_us, last_event_us, last_dsp_us, last_us;
    uint32_t lcd_strips, max_lcd_us, sheds, voice_limit, stolen, controls_applied;
    uint32_t max_voices, max_engine, min_period_us, max_period_us;
    uint32_t last_control_us, max_control_us;
} diag;
static int32_t abuf[HALF_WORDS * 2] __attribute__((aligned(16)));
static int32_t q15[HALF_WORDS];
static volatile uint32_t gain = 256u, engine, cutoff = 20000u, delay_mix;
static volatile uint32_t algorithm, va_wave = 1u, attack_ms = 5u, release_ms = 200u;
static volatile uint32_t requested_budget = 6u;
static const uint32_t cutoff_steps[] = {20,30,45,67,100,150,220,330,470,680,1000,1500,2200,3300,4700,6800,10000,15000,20000};
static uint32_t cutoff_position = 18u;
static const uint32_t envelope_steps[] = {0,2,5,10,20,50,100,200,500,1000,2000,5000,10000};
static uint32_t attack_position = 2u, release_position = 7u;
static volatile uint32_t controls_generation = 1u, panic_request;
static volatile int32_t octave;
static uint8_t key_pitch[27];
static uint32_t keys_previous;
static uint8_t patch_pending[155];
static volatile uint32_t patch_ready, parameter_ready;
static uint32_t parameter_id, parameter_value;
static uint8_t screen_ready;
static fmer_controls_t controls, applied_controls;
static fmer_panel_t panel_state;
static fmer_midi_settings_t midi_requested;
static volatile uint32_t midi_pending,midi_generation,midi_applied;
static uint32_t midi_panel_seen,midi_usb_previous,midi_tx_recovery,midi_tx_overflows;
static uint32_t midi_tx_stop_pending;
static fmer_midi_metrics_t midi_metrics_snapshot;
static volatile uint8_t updating;
static void midi_settings_reply(void);
static volatile uint32_t control_dirty[(FMER_PARAM_COUNT+31)/32], controls_tick;
static fmer_performance_state_t performance_state;
/* Audio owns activity_pending; main owns the immutable LED readback. */
static fmer_activity_state_t activity_pending;
static fmer_led_state_t led_state;
static fmer_led_frame_t led_frame;
static uint32_t led_generation,led_updated_ms,led_active_voices,virtual_buttons;
static uint32_t led_button_seen,led_button_time[14],led_button_recent;
static uint32_t led_save_job,led_save_time,led_save_result;
/* Audio publishes only changed pattern content. Main/UI never reads the DSP. */
static fmer_pattern_state_t pattern_pending,pattern_shown;
static fmer_trace_t trace;
static uint32_t transport_queue[16];
static volatile uint32_t transport_read,transport_write;
static volatile uint32_t audition_pending,audition_slot;
#include "battery_history.h"
#include "battery_estimate.h"
static fmer_battery_estimator_t battery_estimator;
static uint32_t battery_percent=101;
static fmer_battery_history_t battery_history FMER_WORKSPACE;
static uint32_t battery_raw,battery_q8,battery_sample_ms,battery_success_ms,battery_valid,battery_last_raw;
static int16_t part_scope_pending[4][32],part_scope_shown[4][32];
static int16_t scope_ring[512],scope_pending[FMER_SCOPE_SAMPLES],scope_shown[FMER_SCOPE_SAMPLES];
static uint32_t scope_at,scope_generation,scope_read_generation,scope_last_ms;
static fmer_panel_gesture_t panel_gesture;
static uint32_t controls_seen,timer_last;
/* Native musical transfers change RAM only. SAVE persists a separately frozen
 * record in the bounded onboard journal, then offers an optional PC mirror.
 * Audio copies captures and admits a quiet handoff. Main owns full restoration,
 * encoding, CRC and flash service; full project adoption never runs in ISR. */
static fmer_native_state_t native_capture_pending,native_main_state,native_import_pending;
static fmer_native_transfer_t native_transfer;
static uint8_t native_export_wire[FMER_NATIVE_BYTES],native_save_wire[FMER_NATIVE_BYTES];
static volatile uint32_t native_capture_request,native_capture_kind,native_capture_done;
static volatile uint32_t native_import_ready,native_import_expected,native_import_id;
/* ready:0 idle,1 awaiting audio boundary,2 DMA stopped awaiting main owner. */
static volatile uint32_t native_main_owner;
static uint32_t native_quiet_started;
static volatile uint32_t native_last_import_id,native_last_import_result;
static volatile uint32_t native_live_generation,native_preset_id,native_sound_dirty;
static char native_patch_name[11];
static uint32_t native_serial,native_capture_handled,native_export_token,native_save_token;
static uint32_t native_save_acked,native_saved_generation,native_save_state;
static fmer_store_t onboard_store;
static fmer_bank_t onboard_bank;
static uint8_t storage_wire[FMER_NATIVE_BYTES];
static char storage_names[128][11];
static char storage_project_names[16][11];
static uint32_t storage_project_crc[16],storage_project_present;
static uint32_t storage_crc[128],storage_count;
static uint32_t storage_present[4],storage_ready,storage_result,storage_slot,storage_action,storage_busy;
static uint32_t storage_boot_crc,storage_boot_result,storage_started,storage_capture_token;
static uint32_t storage_expected,storage_import_token,storage_serial,storage_job,storage_finished_job,storage_saved_revision,storage_requested_generation;
static volatile uint32_t storage_pause_request,storage_audio_paused;
static void storage_request(uint32_t action,uint32_t slot);
static void storage_service(void);
static void storage_boot(void);
static void storage_reply(void);
static void storage_catalog_reply(uint32_t slot);
static void storage_export(uint32_t slot);
static void storage_project_catalog_reply(uint32_t slot);
static void storage_project_export(uint32_t slot);
static int storage_has_slot(uint32_t slot) {return slot<128u && ((storage_present[slot/32u]>>(slot%32u))&1u);}


static uint32_t native_request_capture(uint32_t kind) {
    uint32_t f=irq_save(),token=0;
    if(diag.ready && (!storage_busy || kind==3u) && native_capture_request==native_capture_done &&
       native_capture_handled==native_capture_done && !native_import_ready &&
       !(kind==2u && (native_save_state==1u || native_save_state==2u))) {
        if(!++native_serial)native_serial=1;
        token=native_serial;native_capture_kind=kind;RING_PUBLISH();native_capture_request=token;
        if(kind==2u)native_save_state=1;
    }
    irq_restore(f);return token;
}
static void native_service(void) {
    uint32_t f,token,kind;
    f=irq_save();token=native_capture_done;kind=native_capture_kind;
    if(!token || token==native_capture_handled) {irq_restore(f);return;}
    native_main_state=native_capture_pending;irq_restore(f);
    if(kind==3u) {
        if(storage_busy!=1u || token!=storage_capture_token) {native_capture_handled=token;return;}
        if(native_main_state.source_generation!=storage_requested_generation) {
            storage_result=11;storage_busy=0;storage_finished_job=storage_job;native_capture_handled=token;return;
        }
        if(fmer_native_encode(&native_main_state,storage_wire,sizeof storage_wire)==FMER_NATIVE_OK) {
            storage_expected=native_main_state.source_generation;
            if(storage_action==2u){RING_PUBLISH();storage_busy=4;}
            else {RING_PUBLISH();storage_pause_request=1;storage_busy=2;}
        } else {storage_result=12;storage_busy=0;storage_finished_job=storage_job;}
    } else if(kind==2u) {
        if(fmer_native_encode(&native_main_state,native_save_wire,sizeof native_save_wire)==FMER_NATIVE_OK) {
            native_save_token=token;native_saved_generation=native_main_state.source_generation;native_save_state=2;
        } else native_save_state=4;
    } else if(fmer_native_encode(&native_main_state,native_export_wire,sizeof native_export_wire)==FMER_NATIVE_OK)
        native_export_token=token;
    native_capture_handled=token;
}

static void trace_event(uint32_t kind,uint32_t id,int32_t value,uint32_t aux)
{ fmer_trace_push(&trace,fm1_ms,kind,id,value,aux); }
static void generated_note(uint32_t frame_low,uint8_t status,uint8_t note,uint8_t velocity,uint8_t source)
{ trace_event(FMER_TRACE_GENERATED,(uint32_t)note|((uint32_t)source<<8),
    (status&0xF0u)==0x90u?velocity:0,frame_low); }
static int midi_output(uint8_t status,uint8_t a,uint8_t b)
{
    uint32_t used=mo_w-mo_r,channel=status&15u,termination=status==0xFCu || (status&0xF0u)==0x80u || ((status&0xF0u)==0xB0u && (a==64u || a==120u || a==123u));
    if(!usb.config || updating)return 2; /* No receiver; neither sent nor congested. */
    if((midi_tx_recovery || midi_tx_stop_pending) && !termination)return 0;
    if(used>=MQ || (!termination && used>=MQ-16u)) {
        midi_tx_overflows++;
        if(status==0xFCu)midi_tx_stop_pending=1;
        else if(termination)midi_tx_recovery|=1u<<channel;
        return 0;
    }
    midi_out_event((status==0xF2u?3u:status>=0xF8u?15u:status>>4)|((uint32_t)status<<8)|((uint32_t)a<<16)|((uint32_t)b<<24));
    return 1;
}
static void midi_output_recover(void)
{
    uint32_t c;
    if(!usb.config){mo_r=mo_w;midi_tx_recovery=midi_tx_stop_pending=0;return;}
    if(midi_tx_stop_pending && mo_w-mo_r<MQ){midi_out_event(0xFC0Fu);midi_tx_stop_pending=0;}
    for(c=0;c<16u;c++)if((midi_tx_recovery&(1u<<c)) && mo_w-mo_r<=MQ-3u) {
        midi_out_event(11u|((0xB0u+c)<<8)|(64u<<16));
        midi_out_event(11u|((0xB0u+c)<<8)|(123u<<16));
        midi_out_event(11u|((0xB0u+c)<<8)|(120u<<16));
        midi_tx_recovery&=~(1u<<c);
    }
}
static void midi_settings_publish(void)
{
    uint32_t f;
    if(storage_busy || panel_state.midi_revision==midi_panel_seen)return;
    f=irq_save();midi_requested=panel_state.midi;midi_panel_seen=panel_state.midi_revision;
    midi_generation++;RING_PUBLISH();midi_pending=1;irq_restore(f);
}
#include "usb_link_board.h"
static void mirror_controls(void) {
    engine=controls.value[FMER_ENGINE]; algorithm=controls.value[134];
    va_wave=controls.value[FMER_VA_WAVE]; cutoff=controls.value[FMER_CUTOFF];
    delay_mix=controls.value[FMER_DELAY]; attack_ms=controls.value[FMER_ATTACK];
    release_ms=controls.value[FMER_RELEASE]; requested_budget=controls.value[FMER_VOICE_BUDGET];
}
/* Native restore is a destructive STOP operation. Its validation, sixteen
 * pattern expansion and effects reset are not bounded by one audio half.
 * Guard both sides of the handoff: an intervening message retains ownership
 * and makes this transaction stale, without panic or musical-state mutation. */
static int native_import_conflict(void) {
    return !diag.ready || diag.safe_mode || updating || panic_request || midi_in_overflow ||
        controls_generation!=diag.controls_applied || patch_ready || parameter_ready ||
        audition_pending || transport_read!=transport_write || midi_pending || mi_r!=mi_w ||
        fmer_dsp_state_generation()!=native_import_expected;
}
static void native_import_service(void) {
    uint32_t f,accepted,keys=0,started=0,apply_us=0,quiet_us;
    f=irq_save();
    if(native_import_ready!=2u){irq_restore(f);return;}
    accepted=!native_import_conflict();
    if(accepted) {
        /* Timer input scanning stays live; MIDI producers defer exactly as
         * during audio ISR ownership. Keys pressed after this commit point
         * remain new edges, rather than being swallowed by restore. */
        native_main_owner=1;keys=fm1_in.notes;started=fm1_ticks();
    }
    irq_restore(f);
    if(accepted) {
        accepted=fmer_dsp_set_native(&native_import_pending,native_import_expected);
        if(accepted) {
            keys_previous=keys;
            fmer_dsp_get_controls(&applied_controls);controls=applied_controls;mirror_controls();
            diag.voice_limit=fmer_dsp_voice_limit();diag.voices=fmer_dsp_active();diag.stolen=fmer_dsp_stolen();
            fmer_dsp_midi_metrics(&midi_metrics_snapshot);fmer_dsp_performance(&performance_state);
            fmer_dsp_get_activity(&activity_pending);fmer_dsp_get_pattern(&pattern_pending);
            native_live_generation=fmer_dsp_state_generation();native_preset_id=fmer_dsp_preset_id();
            native_sound_dirty=fmer_dsp_sound_dirty();fmer_dsp_patch_name(native_patch_name);
        }
        apply_us=(fm1_ticks()-started)/FM1_TICKS_PER_US;
    }
    /* Record intentional load silence separately from deadline diagnostics.
     * All state/result publication precedes the first resumed audio callback. */
    memset(q15,0,sizeof q15);memset(abuf,0,sizeof abuf);
    quiet_us=(fm1_ticks()-native_quiet_started)/FM1_TICKS_PER_US;
    trace_event(FMER_TRACE_NATIVE_LOAD,accepted?FMER_NATIVE_OK:FMER_NATIVE_STALE,(int32_t)apply_us,quiet_us);
    f=irq_save();
    native_last_import_id=native_import_id;
    native_last_import_result=accepted?FMER_NATIVE_OK:FMER_NATIVE_STALE;
    RING_PUBLISH();native_import_ready=0;native_main_owner=0;
    FM1_ALNK_CON0|=0x800u;
    irq_restore(f);
}
static void capture_controls(fmer_controls_t *out) {
    uint32_t f=irq_save();
    controls=*fmer_control_snapshot_source(&controls,&applied_controls,diag.ready,controls_generation,diag.controls_applied);
    mirror_controls();panel_state.fx_order=fmer_dsp_fx_order();panel_state.modulation=fmer_dsp_modulation();*out=controls;irq_restore(f);
}
static int publish_controls(const fmer_controls_t *base,const fmer_controls_t *next) {
    uint32_t i,changed[FMER_CONTROL_WORDS],count,f;
    if(!fmer_control_batch_valid(next))return 0;
    f=irq_save();
    count=fmer_control_publish(&controls,control_dirty,base,next,changed);
    for(i=0;i<FMER_PARAM_COUNT;i++)if(fmer_control_dirty(changed,i))
        fmer_trace_push_locked(&trace,fm1_ms,FMER_TRACE_CONTROL,i,controls.value[i],controls_generation+1u);
    if(count) {mirror_controls();controls_tick=fm1_ticks();RING_PUBLISH();controls_generation++;}
    irq_restore(f);return 1;
}
/* Audio owns the effective allocator, including glide normalization and load
 * shedding. Main's last request is a mirror, never a per-half override. */
static void sync_audio_budget(void) {requested_budget=fmer_dsp_voice_limit();}
static void queue_transport(uint32_t command) {
    uint32_t f;
    if(!command) return;
    trace_event(FMER_TRACE_TRANSPORT,command,1,controls_generation);
    if(command==FMER_TRANSPORT_PANIC) { panic_request=1; diag.safe_mode=0; return; }
    f=irq_save();
    if(transport_write-transport_read<16u) { transport_queue[transport_write%16u]=command; RING_PUBLISH();transport_write++; }
    else { diag.rejected++; panic_request=1; }
    irq_restore(f);
}
static void scope_capture(void) {
    uint32_t i,start;
    for(i=0;i<HALF_FRAMES;i++) { scope_ring[scope_at]=(int16_t)q15[i*2u];scope_at=(scope_at+1u)%512u; }
    if((uint32_t)(fm1_ms-scope_last_ms)<33u) return;
    scope_last_ms=fm1_ms;start=scope_at;
    /* Locate a rising zero crossing in oldest128 samples, then show384 samples.
     * Three-to-one decimation keeps the 128-point scope useful on low notes. */
    for(i=1;i<128u;i++) if(scope_ring[(scope_at+i-1u)%512u]<=0 && scope_ring[(scope_at+i)%512u]>0) {start=(scope_at+i)%512u;break;}
    for(i=0;i<FMER_SCOPE_SAMPLES;i++) scope_pending[i]=scope_ring[(start+i*3u)%512u];
    if(applied_controls.value[FMER_SEQ_MODE])fmer_dsp_part_scopes(part_scope_pending);
    RING_PUBLISH();scope_generation++;
}

/* Original, minimal 5x7 block alphabet. No acquired typeface data. */
static const uint8_t glyphs[][5] = {
 {0x3e,0x51,0x49,0x45,0x3e},{0,0x42,0x7f,0x40,0},{0x62,0x51,0x49,0x49,0x46},
 {0x22,0x41,0x49,0x49,0x36},{0x18,0x14,0x12,0x7f,0x10},{0x27,0x45,0x45,0x45,0x39},
 {0x3c,0x4a,0x49,0x49,0x30},{1,0x71,9,5,3},{0x36,0x49,0x49,0x49,0x36},
 {6,0x49,0x49,0x29,0x1e},{0x7e,9,9,9,0x7e},{0x7f,0x49,0x49,0x49,0x36},
 {0x3e,0x41,0x41,0x41,0x22},{0x7f,0x41,0x41,0x22,0x1c},{0x7f,0x49,0x49,0x49,0x41},
 {0x7f,9,9,9,1},{0x3e,0x41,0x49,0x49,0x7a},{0x7f,8,8,8,0x7f},
 {0,0x41,0x7f,0x41,0},{0x20,0x40,0x41,0x3f,1},{0x7f,8,0x14,0x22,0x41},
 {0x7f,0x40,0x40,0x40,0x40},{0x7f,2,0x0c,2,0x7f},{0x7f,4,8,0x10,0x7f},
 {0x3e,0x41,0x41,0x41,0x3e},{0x7f,9,9,9,6},{0x3e,0x41,0x51,0x21,0x5e},
 {0x7f,9,0x19,0x29,0x46},{0x46,0x49,0x49,0x49,0x31},{1,1,0x7f,1,1},
 {0x3f,0x40,0x40,0x40,0x3f},{0x1f,0x20,0x40,0x20,0x1f},{0x3f,0x40,0x38,0x40,0x3f},
 {0x63,0x14,8,0x14,0x63},{3,4,0x78,4,3},{0x61,0x51,0x49,0x45,0x43}
};
static void label(uint32_t x, uint32_t y, const char *s, uint16_t color, uint32_t scale)
{
    for (; *s && x + 5u * scale <= 240u; s++, x += 6u * scale) {
        int i = *s >= '0' && *s <= '9' ? *s - '0' : *s >= 'A' && *s <= 'Z' ? *s - 'A' + 10 : -1;
        uint32_t a, b;
        if (i < 0) continue;
        for (a = 0; a < 5; a++) for (b = 0; b < 7; b++)
            if (glyphs[i][a] & (1u << b)) lcd_fill(x+a*scale,y+b*scale,scale,scale,color);
    }
}
static char *decimal(char *p, uint32_t n)
{
    char b[10]; uint32_t k = 0;
    do { b[k++] = (char)('0' + n % 10); n /= 10; } while (n);
    while (k) *p++ = b[--k];
    *p = 0; return p;
}
static void lights(void)
{
    fmer_led_state_t next;
    fmer_led_frame_t frame;
    uint32_t now=fm1_ms,f,i,voices;
    if(led_generation && (uint32_t)(now-led_updated_ms)<5u)return;
    memset(&next,0,sizeof next);
    next.family=panel_state.family;next.fine_adjust=panel_state.fine_adjust;
    next.octave=octave;
    f=irq_save();
    next.physical_buttons=fm1_in.buttons|virtual_buttons;
    next.physical_keys=fm1_in.notes;
    next.seq_running=performance_state.running;next.recording=performance_state.recording;
    next.arp_enabled=applied_controls.value[FMER_ARP_ENABLE];next.arp_held=performance_state.arp_held;
    next.audio_paused=diag.safe_mode|updating;next.init_failed=diag.init_failed;
    next.count_in=pattern_pending.count_in_active;
    next.lfo_enabled=applied_controls.value[FMER_LFO_ENABLE];
    next.fx_enabled=applied_controls.value[FMER_DELAY] || applied_controls.value[FMER_REVERB] ||
        applied_controls.value[FMER_CHORUS] || applied_controls.value[FMER_PHASER] || applied_controls.value[FMER_DRIVE];
    next.sound_dirty=native_sound_dirty;next.save_busy=storage_busy;
    if(storage_finished_job && storage_finished_job!=led_save_job){led_save_job=storage_finished_job;led_save_time=now;led_save_result=storage_result?2u:1u;}
    if(led_save_job && now-led_save_time<(led_save_result==1u?800u:2000u))next.save_feedback=led_save_result;
    voices=activity_pending.active_voices;
    next.beat_on=activity_pending.beat_on;
    for(i=0;i<4u;i++) {
        next.active_pitch[i]=activity_pending.active_notes[i];
        next.gated_pitch[i]=activity_pending.gated_notes[i];
    }
    irq_restore(f);
    for(i=0;i<14u;i++){
        uint32_t bit=1u<<i;
        if((next.physical_buttons&bit) && !(led_button_seen&bit)){led_button_time[i]=now;led_button_recent|=bit;}
        if(now-led_button_time[i]>=60u)led_button_recent&=~bit;
    }
    led_button_seen=next.physical_buttons;next.recent_buttons=led_button_recent;
    fmer_led_render(&next,now,&frame);
    /* The timer scans these arrays. Publish both together; no nested HAL lock. */
    f=irq_save();
    memcpy(fm1_led,frame.lit,sizeof frame.lit);
    memcpy(fm1_led_dim,frame.dim,sizeof frame.dim);
    memcpy(fm1_led_half,frame.half,sizeof frame.half);
    memcpy(fm1_led_three_quarter,frame.three_quarter,sizeof frame.three_quarter);
    irq_restore(f);
    led_state=next;led_frame=frame;led_active_voices=voices;led_updated_ms=now;
    if(!++led_generation)led_generation=1u;
}
static void value(uint32_t x, uint32_t y, uint32_t n, uint16_t c)
{ char b[11]; decimal(b,n); label(x,y,b,c,2); }
static void screen(void)
{
    fmer_ui_state_t state;
    char patch_name[11];
    uint32_t start=fm1_ticks(),elapsed,f;
    memset(&state,0,sizeof state);
    state.build=735; state.engine=engine; state.algorithm=algorithm; state.va_wave=va_wave;
    state.battery_raw=battery_raw;state.battery_valid=battery_valid && fm1_ms-battery_success_ms<5000u;state.battery_percent=battery_percent;
    state.gain=gain; state.octave=octave; state.voices=diag.voices; state.voice_limit=diag.voice_limit;
    state.render_us=diag.max_us; state.overruns=diag.overruns; state.shed=diag.sheds;
    state.audio_paused=diag.safe_mode; state.init_failed=diag.init_failed; state.usb_ready=usb.config && !usb.suspended;state.usb_audio_active=uac.alt && uac.go && uac.flowing;
    state.usb_link_role=link_role;state.usb_link_state=ul.state;state.usb_link_error=ul.error;
    state.usb_link_rx=ul.rx_events;state.usb_link_tx=ul.tx_events;
    f=irq_save();
    state.performance=performance_state;
    state.beat_on=activity_pending.beat_on;
    fmer_dsp_fx_activity(state.fx_activity);state.fx_order=(uint16_t)fmer_dsp_fx_order();panel_state.fx_order=state.fx_order;panel_state.modulation=fmer_dsp_modulation();
    state.preset_id=native_preset_id;state.sound_dirty=native_sound_dirty;
    state.live_generation=native_live_generation;
    memcpy(patch_name,native_patch_name,sizeof patch_name);
    if(pattern_pending.revision!=pattern_shown.revision)pattern_shown=pattern_pending;
    if(scope_generation!=scope_read_generation) {
        memcpy(part_scope_shown,part_scope_pending,sizeof part_scope_shown);
        memcpy(scope_shown,scope_pending,sizeof scope_shown);scope_read_generation=scope_generation;
    }
    irq_restore(f);
    state.patch_name=patch_name;state.candidate_name=fmer_dsp_factory_name(panel_state.preset_candidate);
    state.save_state=native_save_state;state.saved_generation=native_saved_generation;
    state.storage_ready=storage_ready;state.storage_result=storage_result;state.storage_slot=storage_slot;
    state.storage_action=storage_action;state.storage_valid_slots=storage_count;state.store_busy=storage_busy!=0;
    {uint32_t project=panel_state.family==FMER_PANEL_SAVE && panel_state.save_scope;
     uint32_t slot=panel_state.family==FMER_PANEL_SAVE?panel_state.save_slot+64u*panel_state.save_bank:panel_state.preset_candidate;
     if(project){slot=panel_state.save_slot;state.user_slot_present=slot<16u && ((storage_project_present>>slot)&1u);state.user_slot_name=slot<16u?storage_project_names[slot]:0;}
     else {state.user_slot_present=storage_has_slot(slot);state.user_slot_name=slot<128u?storage_names[slot]:0;}
     if(panel_state.family==FMER_PANEL_PRESETS && panel_state.preset_bank==2u)state.candidate_name=state.user_slot_name;}
    state.controls=&controls; state.panel=&panel_state;
    state.pattern=&pattern_shown;
    state.part_scopes=&part_scope_shown[0][0];state.scope=scope_shown; state.scope_generation=scope_read_generation;
    if(fmer_ui_service(&state,fm1_ms)) diag.lcd_strips++;
    elapsed=(fm1_ticks()-start)/FM1_TICKS_PER_US;
    if(elapsed>diag.max_lcd_us) diag.max_lcd_us=elapsed;
}
static void fm1_fault(const fm1_crash_t *c)
{
    fm1_audio_stop();
    if (screen_ready) {
        lcd_fill(0,0,240,240,BG); label(12,20,"FMER FAULT",PINK,2);
        value(12,55,c->vec,INK); value(12,85,c->pc,INK); lcd_sync();
    }
    /* The watchdog records the failed boot. Repeated faults enter USB boot. */
    for (;;) {}
}

void fm1_timer5_irq(void)
{
    static uint32_t sub, owed, acc;
    uint32_t t = fm1_ticks(), due = sub % 5u == 0u;
    fm1_timer5_ack(); fm1_input_tick();
    acc += t-timer_last; timer_last=t;
    while (acc >= 24000u) { acc -= 24000u; fm1_ms++; }
    if (due) owed |= 1;
    if (sub % 5u == 2u) owed |= 2;
    if (++sub == 10u) sub=0;
    if (diag.in_audio || native_main_owner) { if (due && !link_host) uac_service(); return; }
    if (owed & 1) {midi_output_recover();if(link_host)usb_link_poll();else usb_poll();}
    if (owed & 2) uart_midi_poll();
    owed=0;
}
extern void isr_timer5(void), isr_alnk0(void);

static void keyboard(uint32_t *note_ons)
{
    uint32_t keys=fm1_in.notes, changed=keys^keys_previous, i;
    /* Release all changed keys first. Admit at most two new notes per audio
     * half across local and USB/TRS sources; retain other edges for next half. */
    for (i=0;i<27;i++) if ((changed & (1u<<i)) && !(keys & (1u<<i))) {
        trace_event(FMER_TRACE_NOTE,key_pitch[i],0,3u);
        fmer_dsp_midi(0x80,key_pitch[i],0,3); keys_previous &= ~(1u<<i);
    }
    for (i=0;i<27 && *note_ons<2u;i++) if ((changed & keys) & (1u<<i)) {
            key_pitch[i]=(uint8_t)(53+(int32_t)i+12*octave);
            trace_event(FMER_TRACE_NOTE,key_pitch[i],100,3u);
            fmer_dsp_midi(0x90,key_pitch[i],100,3);
            keys_previous |= 1u<<i; (*note_ons)++;
    }
}
void fm1_alnk0_irq(void)
{
    uint32_t t, half, i, consumed=0, note_ons=0, observed, render_start, dsp_done, period, f, late;
    static uint32_t previous_start, severe_streak;
    uint8_t pending;
    diag.in_audio=1; t=fm1_ticks(); pending=fm1_audio_pending(); fm1_audio_ack_aux(pending);
    if (pending & FM1_AUDIO_HALF) {
        if(previous_start) {
            period=(t-previous_start)/FM1_TICKS_PER_US;
            if(!diag.min_period_us || period<diag.min_period_us) diag.min_period_us=period;
            if(period>diag.max_period_us) diag.max_period_us=period;
        }
        previous_start=t;
        half=fm1_audio_free_half();
        /* Consume this event now so a later DMA half event remains pending if
         * rendering misses its deadline. Do not acknowledge a newer event. */
        fm1_audio_ack_half();
        if(storage_pause_request) {
            storage_pause_request=0;
            if(native_import_ready || patch_ready || parameter_ready || audition_pending || transport_read!=transport_write ||
               controls_generation!=diag.controls_applied || midi_pending || mi_r!=mi_w ||
               fmer_dsp_state_generation()!=storage_expected) storage_audio_paused=2;
            else {
                fmer_dsp_panic();keys_previous=fm1_in.notes;storage_saved_revision=fmer_dsp_state_generation();
                memset(q15,0,sizeof q15);memset(abuf,0,sizeof abuf);
                fm1_audio_stop();previous_start=0;RING_PUBLISH();storage_audio_paused=1;
                diag.in_audio=0;return;
            }
        }
        if(native_import_ready==1u) {
            if(native_import_conflict()) {
                native_last_import_id=native_import_id;native_last_import_result=FMER_NATIVE_STALE;
                RING_PUBLISH();native_import_ready=0;
            } else {
                /* Stop DMA before touching its buffers. No panic or full DSP
                 * adoption here: main rechecks all queues before claiming it. */
                fm1_audio_stop();native_quiet_started=fm1_ticks();
                memset(q15,0,sizeof q15);memset(abuf,0,sizeof abuf);
                previous_start=0;RING_PUBLISH();native_import_ready=2;
                diag.in_audio=0;return;
            }
        }
        diag.last_event_us=diag.last_dsp_us=0;
        uac_render_start();
        if(diag.ready && panic_request) {
            fmer_dsp_panic(); panic_request=0; keys_previous=fm1_in.notes;
            mi_r=mi_w; transport_read=transport_write;
        }
        if (diag.ready && !diag.safe_mode && !updating) {
            if(midi_usb_previous && !usb.config)fmer_dsp_midi_disconnected();
            if(!midi_usb_previous && usb.config && midi_requested.value[FMER_MIDI_ROUTE])midi_tx_recovery|=1u<<midi_requested.value[FMER_MIDI_TX_CHANNEL];
            midi_usb_previous=usb.config;
            if(midi_pending) {if(!fmer_dsp_set_midi_settings(&midi_requested))diag.rejected++;else midi_applied=midi_generation;midi_pending=0;}
            if (midi_in_overflow) {
                if (midi_in_overflow) { mi_r=mi_w; midi_in_overflow=0; diag.midi_overflows++; }
                fmer_dsp_panic(); keys_previous=fm1_in.notes;
            }
            observed=controls_generation;
            if(observed!=controls_seen) {
                if(!fmer_control_adopt(&controls,control_dirty,fmer_dsp_get_controls,fmer_dsp_apply_controls))
                    diag.rejected++;
                else {
                    diag.controls_applied=observed;
                    memset((void*)control_dirty,0,sizeof control_dirty);
                }
                controls_seen=observed;
                diag.last_control_us=(fm1_ticks()-controls_tick)/FM1_TICKS_PER_US;
                if(diag.last_control_us>diag.max_control_us) diag.max_control_us=diag.last_control_us;
                trace_event(diag.controls_applied==observed?FMER_TRACE_APPLIED:FMER_TRACE_FAULT,
                            diag.controls_applied==observed?0u:2u,(int32_t)observed,diag.last_control_us);
            }
            if(patch_ready) { if(!fmer_dsp_patch(patch_pending,155)) diag.rejected++; patch_ready=0; }
            if(parameter_ready) { if(!fmer_dsp_parameter(parameter_id,parameter_value)) diag.rejected++; parameter_ready=0; }
            if(audition_pending && !native_import_ready){uint32_t slot=audition_slot;audition_pending=0;if(!fmer_dsp_audition(slot))diag.rejected++;else trace_event(FMER_TRACE_TRANSPORT,FMER_TRANSPORT_PRESET_BASE+slot,0,0);}
            if(transport_read!=transport_write) {
                uint32_t cmd=transport_queue[transport_read%16u];transport_read++;
                if(!fmer_dsp_transport(cmd)) diag.rejected++;
            }
            sync_audio_budget();
            diag.voice_limit=fmer_dsp_voice_limit();
            while (mi_r!=mi_w && consumed++<8u) {
                uint32_t at=mi_r%MQ, p=midi_in_q[at]; uint8_t source=midi_in_source[at];
                uint32_t is_on=((p>>8)&0xF0u)==0x90u && ((p>>24)&127u);
                if(is_on && note_ons>=2u) break;
                note_ons+=is_on?1u:0u;
                RING_PUBLISH(); mi_r++;
                if(((p>>8)&0xF0u)==0x80u || ((p>>8)&0xF0u)==0x90u)
                    trace_event(FMER_TRACE_NOTE,(p>>16)&127u,((p>>8)&0xF0u)==0x90u?(int32_t)((p>>24)&127u):0,source|(((p>>8)&15u)<<8));
                fmer_dsp_midi((uint8_t)(p>>8),(uint8_t)((p>>16)&127u),(uint8_t)((p>>24)&127u),source);
            }
            keyboard(&note_ons);
            render_start=fm1_ticks();
            diag.last_event_us=(render_start-t)/FM1_TICKS_PER_US;
            if(diag.last_event_us>diag.max_event_us) diag.max_event_us=diag.last_event_us;
            fmer_dsp_render(q15,HALF_FRAMES,gain);
            dsp_done=fm1_ticks(); diag.last_dsp_us=(dsp_done-render_start)/FM1_TICKS_PER_US;
            if(diag.last_dsp_us>diag.max_dsp_us) diag.max_dsp_us=diag.last_dsp_us;
        } else { memset(q15,0,sizeof q15); mi_r=mi_w; }
        if(diag.ready) { diag.voices=fmer_dsp_active(); diag.stolen=fmer_dsp_stolen(); }
        if(diag.ready) {
            fmer_dsp_get_controls(&applied_controls);
            fmer_dsp_midi_metrics(&midi_metrics_snapshot);
            fmer_dsp_performance(&performance_state);
            fmer_dsp_get_activity(&activity_pending);
            if(fmer_dsp_pattern_revision()!=pattern_pending.revision)
                fmer_dsp_get_pattern(&pattern_pending);
            native_live_generation=fmer_dsp_state_generation();native_preset_id=fmer_dsp_preset_id();
            native_sound_dirty=fmer_dsp_sound_dirty();fmer_dsp_patch_name(native_patch_name);
            if(native_capture_request!=native_capture_done) {
                fmer_dsp_get_native(&native_capture_pending);RING_PUBLISH();native_capture_done=native_capture_request;
            }
        }
        scope_capture();
        uac_tap(q15,HALF_FRAMES);
        /* Never publish a late block into the half DMA is already consuming.
         * Reserve ~300us of the 128/44100-s period for bounded publication;
         * the critical copy prevents timer preemption after the half check.
         * A missed block repeats old audio once; its pending IRQ is retained. */
        f=irq_save();
        late=(fm1_audio_free_half()!=half || fm1_ticks()-t>2600u*FM1_TICKS_PER_US);
        if(!late) for (i=0;i<HALF_WORDS;i++) abuf[half*HALF_WORDS+i]=q15[i]*256;
        irq_restore(f); diag.halves++;
        observed=(fm1_ticks()-t)/FM1_TICKS_PER_US;
        diag.last_us=observed;
        if (observed>diag.max_us) { diag.max_us=observed; diag.max_voices=diag.voices; diag.max_engine=engine; }
        /* An overloaded chord reduces the voice budget deterministically on
         * the next half. Keep playing; only persistent single-voice overload
         * enters protective pause, preserving USB/update service. */
        if (late || observed>2800u || fm1_audio_free_half()!=half) {
            diag.overruns++; trace_event(FMER_TRACE_FAULT,1,(int32_t)diag.overruns,requested_budget);
            if(requested_budget>1u && !applied_controls.value[FMER_SEQ_MODE] &&
               fmer_dsp_voice_budget(requested_budget-1u)) {
                requested_budget--;controls.value[FMER_VOICE_BUDGET]=(uint16_t)requested_budget;
                /* Apply the bounded reduction before main can reconcile its
                 * canonical state from the audio snapshot captured above. */
                applied_controls.value[FMER_VOICE_BUDGET]=(uint16_t)requested_budget;
                diag.voice_limit=fmer_dsp_voice_limit();diag.voices=fmer_dsp_active();diag.stolen=fmer_dsp_stolen();
                diag.sheds++;severe_streak=0;
            }
            else if(++severe_streak>=3u) { diag.safe_mode=1; panic_request=1; }
        } else severe_streak=0;
    }
    diag.in_audio=0;
}

static uint32_t ota_now_ms(void) { return fm1_ms; }
static void ota_idle(void) { fm1_wdt_feed(); }
static int ota_erase(uint32_t off)
{
    uint32_t took;
    if (diag.flash_id!=0x856014u || !FL_IN(off,0x1000u,0xE0000u,0xE5000u) || (off&0xFFFu)) return -8;
    return fl_erase4k(off,&took);
}
static int ota_prog(uint32_t off,const void *p,uint32_t n)
{
    if (diag.flash_id!=0x856014u || !FL_IN(off,n,0xE0000u,0xE5000u)) return -8;
    return fl_write(off,p,n);
}
static int ota_fread(uint32_t off,void *p,uint32_t n)
{
    uint8_t *d=p;
    if (off>0x100000u || n>0x100000u-off) return -8;
    while(n) {
        uint32_t k=n>256u?256u:n, f=irq_save();
        int rc=FL_FAR(fl_read_ram)(off,d,k); irq_restore(f);
        if(rc) return rc; off+=k; d+=k; n-=k;
    }
    return 0;
}
#include "onboard_store.h"

static void ota_show(uint32_t step,int32_t code)
{
    lcd_fill(0,0,240,240,BG); label(12,30,"FMER UPDATE",GREEN,2);
    label(12,65,"STEP",INK,2); value(90,65,step,GREEN);
    if(code) { label(12,100,"CODE",PINK,2); value(90,100,(uint32_t)(code<0?-code:code),PINK); }
    lcd_sync();
}
static void ota_commit(const uint8_t *parm)
{
    fmer_boot.pending=0; usb_detach(); fm1_delay_ms(30); fm1_enter_update(parm);
}

/* Yamaha single-voice and parameter messages are accepted into bounded mailboxes;
 * only the audio owner mutates the core. No bulk-bank or persistent write path. */
static void diagnostics_reply(uint32_t version)
{
    uint8_t response[512]; char *s=(char*)response+7; uint32_t i,n;
    uint32_t f=irq_save();
    uint32_t values[]={diag.halves,diag.max_us,diag.overruns,diag.midi_overflows,
        diag.rejected,diag.voices,diag.heap,diag.flash_id,diag.safe_mode,diag.init_failed,
        fm1_crash.magic==FM1_CRASH_MAGIC ? fm1_crash.count : 0,
        engine,algorithm,va_wave,cutoff,delay_mix,attack_ms,release_ms,gain,(uint32_t)(octave+3),
        diag.voice_limit,diag.stolen,diag.sheds,diag.max_event_us,diag.max_dsp_us,diag.last_us,
        diag.lcd_strips,diag.max_lcd_us,fm1_lcd_timeouts,controls_generation,diag.controls_applied,
        diag.max_voices,diag.max_engine,diag.last_event_us,diag.last_dsp_us,
        diag.min_period_us,diag.max_period_us};
    irq_restore(f);
    n=version==1u?11u:(uint32_t)(sizeof(values)/sizeof(values[0]));
    response[0]=0xF0; response[1]=0x7D; memcpy(response+2,"FMER",4); response[6]=(uint8_t)version;
    for(i=0;i<n;i++) { if(i) *s++=' '; s=decimal(s,values[i]); }
    *s++=(char)0xF7;
    ota_frame_done(); ota_wire_send(response,(uint32_t)(s-(char*)response));
}
static void panel_virtual(uint32_t kind,uint32_t id,int32_t value);
static char *signed_decimal(char *p,int32_t value)
{ if(value<0) { *p++='-'; return decimal(p,0u-(uint32_t)value); } return decimal(p,(uint32_t)value); }
static char *reply_begin(uint8_t *response,uint32_t op)
{ response[0]=0xF0;response[1]=0x7D;memcpy(response+2,"FMER",4);response[6]=(uint8_t)op;return (char*)response+7; }
static void reply_end(uint8_t *response,char *end)
{ *end++=(char)0xF7;ota_frame_done();ota_wire_send(response,(uint32_t)(end-(char*)response)); }
static void request_echo(const uint8_t *p,uint32_t n)
{ uint8_t response[32];response[0]=0xF0;memcpy(response+1,p,n);response[n+1]=0xF7;ota_frame_done();ota_wire_send(response,n+2); }
static uint32_t native_u32(const uint8_t *p)
{ uint32_t i,v=0;for(i=0;i<5u;i++)v|=(uint32_t)p[i]<<(7u*i);return v; }
static void midi_settings_reply(void)
{
    uint8_t response[512];char *p=reply_begin(response,25);uint32_t i,f,values[26];f=irq_save();
    values[0]=1;values[1]=midi_generation;values[2]=midi_applied;
    values[3]=storage_ready && !memcmp(panel_state.midi.value,onboard_bank.midi.value,8);
    for(i=0;i<8u;i++)values[4+i]=panel_state.midi.value[i];
    memcpy(values+12,&midi_metrics_snapshot,sizeof midi_metrics_snapshot);
    values[22]=mo_w-mo_r;values[23]=midi_tx_overflows;values[24]=usb.config;values[25]=midi_tx_recovery;
    irq_restore(f);for(i=0;i<26u;i++){if(i)*p++=' ';p=decimal(p,values[i]);}reply_end(response,p);
}
static void output_metrics_reply(void) {
    uint8_t response[128];char *p=reply_begin(response,27);uint32_t values[7],i,f=irq_save();
    fmer_dsp_output_metrics(values);irq_restore(f);
    for(i=0;i<7;i++){if(i)*p++=' ';p=decimal(p,values[i]);}reply_end(response,p);
}
static void usb_link_status_reply(void) {
    uint8_t response[320];uint32_t i,f=irq_save();
    uint32_t v[]={1,link_role,ul.state,ul.error,ul.devctl,ul.csr,ul.connects,ul.disconnects,
        ul.failures,ul.io_failures,ul.rx_events,ul.tx_events,ul.rx_packets,ul.tx_packets,ul.ignored,ul.phase,ul.stage};
    irq_restore(f);char *p=reply_begin(response,33);
    for(i=0;i<17;i++){if(i)*p++=' ';p=decimal(p,v[i]);}reply_end(response,p);
}
static void usb_audio_status_reply(void) {
    /* Snapshot only: no USB register access or work in the audio callback. */
    uint8_t response[320];uint32_t i,f=irq_save();
    uint32_t values[]={1,fm1_ms,usb.config,uac.alt,uac.go,uac.flowing,uac.feed,ua_w-ua_r,
        uac.starts,uac.pkts,uac.frames,uac.underruns,uac.overruns,uac.missed,uac.stalls,
        uac.adj_up,uac.adj_down,uac.fill_lo,uac.fill_hi,usb.resets};
    irq_restore(f);char *p=reply_begin(response,31);
    for(i=0;i<20u;i++){if(i)*p++=' ';p=decimal(p,values[i]);}reply_end(response,p);
}
static void battery_history_reply(uint32_t offset){
    uint8_t response[192];uint32_t i,count=fmer_battery_history_count(&battery_history),n=offset<count?count-offset:0;
    char *p=reply_begin(response,32);if(n>4)n=4;
    p=decimal(p,2);*p++=' ';p=decimal(p,battery_history.total);*p++=' ';p=decimal(p,count);*p++=' ';p=decimal(p,offset);*p++=' ';p=decimal(p,n);
    for(i=0;i<n;i++){const fmer_battery_sample_t *a=fmer_battery_history_get(&battery_history,offset+i);
        *p++=' ';p=decimal(p,a->seconds_usb&0x7fffffffu);*p++=' ';p=decimal(p,a->raw);
        *p++=' ';p=decimal(p,a->filtered);*p++=' ';p=decimal(p,a->seconds_usb>>31);
    }
    reply_end(response,p);
}
static void battery_status_reply(void) {
    /* Observations only: cached ADC samples, never a forced conversion or a
     * voltage/charge estimate. USB enumeration does not establish charging. */
    uint8_t response[128];uint32_t i,now=fm1_ms;
    uint32_t age=battery_valid?now-battery_success_ms:0xffffffffu;
    uint32_t values[]={1,battery_last_raw,battery_raw,age,battery_valid && age<5000u,usb.config?1u:0u};
    char *p=reply_begin(response,28);
    for(i=0;i<6u;i++){if(i)*p++=' ';p=decimal(p,values[i]);}reply_end(response,p);
}
static void native_result_reply(uint32_t op,uint32_t token,uint32_t result) {
    uint8_t response[64];char *p=reply_begin(response,op);
    p=decimal(p,token);*p++=' ';p=decimal(p,result);reply_end(response,p);
}
static void native_status_reply(void) {
    uint8_t response[192];uint32_t i,f=irq_save();char *p;
    uint32_t values[]={2,native_live_generation,native_preset_id,native_sound_dirty,
      native_save_token,native_save_acked,native_export_token,native_last_import_id,native_last_import_result};
    irq_restore(f);p=reply_begin(response,13);
    for(i=0;i<9u;i++){if(i)*p++=' ';p=decimal(p,values[i]);}reply_end(response,p);
}
static void native_read_reply(uint32_t token,uint32_t offset) {
    uint8_t response[384];uint32_t i,count=FMER_NATIVE_BYTES-offset;char *p;
    const uint8_t *data=token && token==native_save_token?native_save_wire:
        token && token==native_export_token?native_export_wire:0;
    if(!data || offset>=FMER_NATIVE_BYTES){native_result_reply(15,token,FMER_NATIVE_STALE);return;}
    if(count>64u)count=64u;p=reply_begin(response,15);
    p=decimal(p,token);*p++=' ';p=decimal(p,offset);*p++=' ';p=decimal(p,count);
    for(i=0;i<count;i++){*p++=' ';p=decimal(p,data[offset+i]);}reply_end(response,p);
}
static void trace_reply(uint32_t cursor) {
    fmer_trace_event_t events[FMER_TRACE_BATCH]; uint8_t response[512];
    uint32_t newest,oldest,i,n=fmer_trace_snapshot(&trace,cursor,events,&newest,&oldest);
    char *p=reply_begin(response,5);
    p=decimal(p,1);*p++=' ';p=decimal(p,fm1_ms);*p++=' ';p=decimal(p,newest);*p++=' ';p=decimal(p,oldest);*p++=' ';p=decimal(p,n);
    for(i=0;i<n;i++) {
        *p++=' ';p=decimal(p,events[i].sequence);*p++=' ';p=decimal(p,events[i].ms);
        *p++=' ';p=decimal(p,events[i].kind);*p++=' ';p=decimal(p,events[i].id);
        *p++=' ';p=signed_decimal(p,events[i].value);*p++=' ';p=decimal(p,events[i].aux);
    }
    reply_end(response,p);
}
static void controls_reply(uint32_t start) {
    uint8_t response[256];uint16_t values[24];uint32_t i,n=FMER_PARAM_COUNT-start,f;
    const fmer_controls_t *source;
    char *p=reply_begin(response,6);
    if(n>24u)n=24u;
    f=irq_save();source=fmer_control_snapshot_source(&controls,&applied_controls,diag.ready,controls_generation,diag.controls_applied);
    for(i=0;i<n;i++)values[i]=source->value[start+i];irq_restore(f);
    p=decimal(p,start);*p++=' ';p=decimal(p,n);
    for(i=0;i<n;i++){*p++=' ';p=decimal(p,values[i]);}reply_end(response,p);
}
static void performance_reply(void) {
    uint8_t response[512];char *p=reply_begin(response,8);uint32_t i,f=irq_save();
    uint32_t values[]={2,fm1_ms,fm1_in_stat.gap_max/FM1_TICKS_PER_US,
        fm1_in_stat.cost_max/FM1_TICKS_PER_US,controls_generation,diag.controls_applied,
        diag.last_control_us,diag.max_control_us,trace.newest,trace.count?trace.newest-trace.count+1u:1u,
        scope_generation,performance_state.running,performance_state.recording,
        performance_state.seq_position,performance_state.edit_step,performance_state.arp_held,
        performance_state.generated_drops,performance_state.emitted_notes,performance_state.performance_errors,
        performance_state.revision,performance_state.step_pitch,performance_state.step_velocity,performance_state.step_gate,
        panel_state.family,fmer_panel_page(&panel_state,&controls),panel_state.operator_number,fm1_in.frames,
        performance_state.selected_pattern,performance_state.playing_pattern,performance_state.queued_pattern,
        performance_state.chain_mask,performance_state.chain_enabled};
    irq_restore(f);
    for(i=0;i<sizeof values/sizeof values[0];i++){if(i)*p++=' ';p=decimal(p,values[i]);}reply_end(response,p);
}
static void pattern_reply(uint32_t start) {
    uint8_t response[256],pitch[16],velocity[16],gate[16];
    uint32_t i,n=64u-start,revision,length,f=irq_save();
    char *p;
    if(n>16u)n=16u;
    revision=pattern_pending.revision;length=pattern_pending.length;
    for(i=0;i<n;i++) {
        pitch[i]=pattern_pending.pitch[start+i];velocity[i]=pattern_pending.velocity[start+i];gate[i]=pattern_pending.gate[start+i];
    }
    irq_restore(f);p=reply_begin(response,11);
    p=decimal(p,revision);*p++=' ';p=decimal(p,length);*p++=' ';p=decimal(p,start);*p++=' ';p=decimal(p,n);
    for(i=0;i<n;i++) {
        *p++=' ';p=decimal(p,pitch[i]);*p++=' ';p=decimal(p,velocity[i]);*p++=' ';p=decimal(p,gate[i]);
    }
    reply_end(response,p);
}
static void lights_reply(void) {
    uint8_t response[512];uint32_t v[40],i,k=0;
    char *p=reply_begin(response,12);
    /* Main-owned immutable output: this reports commanded LEDs, not optical
     * feedback. Maximum ASCII payload is bounded below the 512-byte buffer. */
    v[k++]=1;v[k++]=fm1_ms;v[k++]=led_generation;v[k++]=led_updated_ms;
    v[k++]=led_state.family;v[k++]=(uint32_t)(led_state.octave+3);
    v[k++]=led_state.physical_buttons;v[k++]=led_state.physical_keys;
    v[k++]=(led_state.fine_adjust?1u:0u)|(led_state.seq_running?2u:0u)|
        (led_state.recording?4u:0u)|(led_state.arp_enabled?8u:0u)|
        (led_state.arp_held?16u:0u)|(led_state.beat_on?32u:0u)|
        (led_state.audio_paused?64u:0u)|(led_state.init_failed?128u:0u);
    v[k++]=led_active_voices;
    for(i=0;i<4u;i++)v[k++]=led_state.active_pitch[i];
    for(i=0;i<4u;i++)v[k++]=led_state.gated_pitch[i];
    for(i=0;i<11u;i++)v[k++]=led_frame.lit[i];
    for(i=0;i<11u;i++)v[k++]=led_frame.dim[i];
    for(i=0;i<k;i++){if(i)*p++=' ';p=decimal(p,v[i]);}reply_end(response,p);
}
static void companion_service(const uint8_t *p,uint32_t n)
{
    uint32_t i,sum=0;
    if(n==161u && p[0]==0x43u && p[1]<16u && p[2]==0 && p[3]==1 && p[4]==27u) {
        for(i=5;i<161;i++) sum+=p[i];
        if(!(sum&127u) && !patch_ready) { memcpy(patch_pending,p+5,155); RING_PUBLISH(); patch_ready=1; }
        else diag.rejected++;
        ota_frame_done();
    } else if(n==5u && p[0]==0x43u && (p[1]&0xF0u)==0x10u) {
        uint32_t id=(uint32_t)p[2]*128u+p[3];
        if(id<145u && !parameter_ready) { parameter_id=id; parameter_value=p[4]; RING_PUBLISH(); parameter_ready=1; }
        else diag.rejected++;
        ota_frame_done();
    } else if(n==6u && p[0]==0x7Du && memcmp(p+1,"FMER",4)==0 && (p[5]==1u || p[5]==2u)) {
        /* Version one remains readable; version two adds bounded timing/UI/control evidence. */
        diagnostics_reply(p[5]);
    } else if(n==13u && p[0]==0x7Du && memcmp(p+1,"FMER",4)==0 && p[5]==3u) {
        /* Bench/live controls in RAM only: engine,wave,cutoff-step,delay%,
         * attack-step,release-step,voice-budget. Echo means queued, and the
         * diagnostic generation/applied counters prove audio-owner adoption. */
        fmer_controls_t base,next;capture_controls(&base);next=base;
        if(p[6]>1u || p[7]>3u || p[8]>18u || p[9]>100u ||
           p[10]>12u || p[11]>12u || p[12]<1u || p[12]>6u) {
            diag.rejected++; ota_frame_done(); return;
        }
        next.value[FMER_ENGINE]=p[6];next.value[FMER_VA_WAVE]=p[7];
        next.value[FMER_CUTOFF]=(uint16_t)cutoff_steps[p[8]];next.value[FMER_DELAY]=p[9];
        next.value[FMER_ATTACK]=(uint16_t)envelope_steps[p[10]];next.value[FMER_RELEASE]=(uint16_t)envelope_steps[p[11]];
        next.value[FMER_VOICE_BUDGET]=p[12];if(publish_controls(&base,&next))request_echo(p,n);else {diag.rejected++;ota_frame_done();}
    } else if(n==6u && p[0]==0x7Du && memcmp(p+1,"FMER",4)==0 && p[5]==4u) {
        /* Reset profiling peaks only; lifetime failures are never erased. */
        uint8_t response[]={0xF0,0x7D,'F','M','E','R',4,0xF7}; uint32_t f=irq_save();
        diag.max_us=diag.max_event_us=diag.max_dsp_us=diag.max_lcd_us=0;
        diag.min_period_us=diag.max_period_us=0;
        diag.max_control_us=0;fm1_in_stat.gap_max=fm1_in_stat.cost_max=0;
        irq_restore(f); ota_frame_done(); ota_wire_send(response,sizeof response);
    } else if(n==11u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==5u && p[10]<16u) {
        uint32_t cursor=0;for(i=0;i<5u;i++)cursor|=(uint32_t)p[6+i]<<(7u*i);trace_reply(cursor);
    } else if(n==8u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==6u && ((uint32_t)p[6]+128u*p[7])<FMER_PARAM_COUNT) {
        controls_reply((uint32_t)p[6]+128u*p[7]);
    } else if(n==11u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==7u) {
        uint32_t id=(uint32_t)p[6]+128u*p[7],v=(uint32_t)p[8]+128u*p[9]+16384u*p[10];
        if(fmer_control_valid(id,v)) {
            fmer_controls_t base,next;capture_controls(&base);next=base;next.value[id]=(uint16_t)v;
            if(id==FMER_SEQ_LENGTH && next.value[FMER_SEQ_STEP]>=v)next.value[FMER_SEQ_STEP]=(uint16_t)(v-1u);
            if(publish_controls(&base,&next))request_echo(p,n);else {diag.rejected++;ota_frame_done();}
        }
        else {diag.rejected++;ota_frame_done();}
    } else if(n==6u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==8u) {
        performance_reply();
    } else if(n==7u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==9u && p[6]>=1u && p[6]<=8u) {
        queue_transport(p[6]);request_echo(p,n);
    } else if(n==9u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==10u &&
              ((p[6]==1u && p[7]<7u) || (p[6]==2u && p[7]<14u && (p[8]==64u || p[8]==65u)))) {
        panel_virtual(p[6],p[7],(int32_t)p[8]-64);request_echo(p,n);
    } else if(n==8u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==11u &&
              ((uint32_t)p[6]+128u*p[7])<64u && diag.ready) {
        pattern_reply((uint32_t)p[6]+128u*p[7]);
    } else if(n==6u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==12u) {
        lights_reply();
    } else if(n==6u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==13u) {
        native_status_reply();
    } else if(n==6u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==14u) {
        if(native_request_capture(1u))request_echo(p,n);else native_result_reply(14,0,FMER_NATIVE_BUSY);
    } else if(n==13u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==15u && p[10]<16u) {
        native_read_reply(native_u32(p+6),(uint32_t)p[11]+128u*p[12]);
    } else if(n==16u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==16u && p[10]<16u && p[15]<16u) {
        uint32_t token=native_u32(p+6),result=FMER_NATIVE_BUSY;
        if(diag.ready && !native_import_ready && !storage_busy)
            result=fmer_native_transfer_begin(&native_transfer,token,native_u32(p+11),FMER_NATIVE_BYTES);
        native_result_reply(16,token,result);
    } else if(n>=16u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==17u && p[10]<16u &&
              p[13]>=1u && p[13]<=64u && n==14u+2u*p[13]) {
        uint8_t bytes[64];uint32_t token=native_u32(p+6),result=FMER_NATIVE_ARGUMENT;
        for(i=0;i<p[13];i++) {
            if(p[14u+2u*i]>15u || p[15u+2u*i]>15u)break;
            bytes[i]=(uint8_t)((p[14u+2u*i]<<4)|p[15u+2u*i]);
        }
        if(i==p[13] && !native_import_ready)
            result=fmer_native_transfer_chunk(&native_transfer,token,(uint32_t)p[11]+128u*p[12],bytes,p[13]);
        native_result_reply(17,token,result);
    } else if(n==11u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==18u && p[10]<16u) {
        uint32_t token=native_u32(p+6),f,result=FMER_NATIVE_BUSY;
        if(!native_import_ready && !storage_busy && diag.ready && native_capture_request==native_capture_done) {
            result=fmer_native_transfer_ready(&native_transfer,token,native_live_generation);
            if(result==FMER_NATIVE_OK)
                result=fmer_native_decode(native_transfer.bytes,FMER_NATIVE_BYTES,&native_import_pending);
            if(result==FMER_NATIVE_OK) {
                f=irq_save();
                if(controls_generation!=diag.controls_applied || patch_ready || parameter_ready || audition_pending ||
                   transport_read!=transport_write || mi_r!=mi_w ||
                   native_transfer.expected_generation!=native_live_generation)
                    result=FMER_NATIVE_STALE;
                else {
                    native_import_expected=native_transfer.expected_generation;native_import_id=token;
                    native_last_import_id=token;native_last_import_result=FMER_NATIVE_BUSY;
                    fmer_native_transfer_reset(&native_transfer);
                    RING_PUBLISH();native_import_ready=1;result=FMER_NATIVE_BUSY;
                }
                irq_restore(f);
            }
        }
        native_result_reply(18,token,result);
    } else if(n==16u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==19u && p[10]<16u && p[15]<16u) {
        uint32_t token=native_u32(p+6),result=FMER_NATIVE_STALE;
        if(token && token==native_save_token && native_u32(p+11)==fmer_native_rd32(native_save_wire+28)) {
            native_save_acked=token;native_save_state=3;result=FMER_NATIVE_OK;
        }
        native_result_reply(19,token,result);
    } else if(n==11u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==20u && p[10]<16u) {
        uint32_t token=native_u32(p+6),result=FMER_NATIVE_OK;
        if(native_import_ready)result=FMER_NATIVE_BUSY;
        else if(token && native_transfer.active && token!=native_transfer.id)result=FMER_NATIVE_TRANSACTION;
        else fmer_native_transfer_reset(&native_transfer);
        native_result_reply(20,token,result);
    } else if(n==6u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==21u) {
        storage_reply();
    } else if(n==23u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==22u &&
              p[6]>=1u && p[6]<=12u && p[7]<128u && p[12]<16u && p[17]<16u && p[22]<16u) {
        if(native_u32(p+8)!=native_live_generation || native_u32(p+13)!=(uint32_t)onboard_store.generation ||
           native_u32(p+18)!=(uint32_t)(onboard_store.generation>>32))native_result_reply(22,p[7],FMER_NATIVE_STALE);
        else if(storage_busy)native_result_reply(22,p[7],FMER_NATIVE_BUSY);
        else {storage_request(p[6],p[7]);storage_reply();}
    } else if(n==7u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==23u && p[6]<128u) {
        storage_catalog_reply(p[6]);
    } else if(n==7u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==24u && p[6]<128u) {
        storage_export(p[6]);
    } else if(n==7u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==29u && p[6]<16u) {
        storage_project_catalog_reply(p[6]);
    } else if(n==7u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==30u && p[6]<16u) {
        storage_project_export(p[6]);
    } else if(n==6u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==25u) {
        midi_settings_reply();
    } else if(n==6u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==27u) {
        output_metrics_reply();
    } else if(n==6u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==31u) {
        usb_audio_status_reply();
    } else if(n==6u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==33u) {
        usb_link_status_reply();
    } else if(n==6u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==28u) {
        battery_status_reply();
    } else if(n==7u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==32u && p[6]<128u) {
        battery_history_reply(p[6]);
    } else if(n==19u && p[0]==0x7D && !memcmp(p+1,"FMER",4) && p[5]==26u && p[10]<16u) {
        fmer_midi_settings_t candidate;memcpy(candidate.value,p+11,8);
        if(native_u32(p+6)!=midi_generation)native_result_reply(26,0,FMER_NATIVE_STALE);
        else if(storage_busy || midi_pending)native_result_reply(26,0,FMER_NATIVE_BUSY);
        else if(!fmer_midi_settings_valid(&candidate))native_result_reply(26,0,FMER_NATIVE_ARGUMENT);
        else {panel_state.midi=candidate;panel_state.midi_revision++;midi_settings_publish();midi_settings_reply();}
    } else { diag.rejected++; ota_frame_done(); }
}
#include "frame_dispatch.h"
static uint32_t bounded(int32_t v,uint32_t lo,uint32_t hi)
{ return v<(int32_t)lo?lo:v>(int32_t)hi?hi:(uint32_t)v; }
static void panel_button_event(uint32_t id,uint32_t down,uint32_t simulated,fmer_controls_t *next) {
    uint32_t action;
    if(down && id!=8u)panel_state.scope_only=0;
    trace_event(FMER_TRACE_BUTTON,id,(int32_t)down,panel_state.family|simulated);
    action=fmer_panel_gesture_edge(&panel_gesture,id,down,fm1_ms);
    panel_state.fine_adjust=panel_gesture.select_down;
    if(action==FMER_GESTURE_PANIC)queue_transport(FMER_TRANSPORT_PANIC);
    else if(action==FMER_GESTURE_LAUNCH_ALL)queue_transport(FMER_TRANSPORT_LAUNCH_ALL);
    else if(action==FMER_GESTURE_LAUNCH_TRACK)queue_transport(FMER_TRANSPORT_LAUNCH_TRACK);
    else if(action>=FMER_GESTURE_SONG && action<=FMER_GESTURE_POLY)fmer_panel_shortcut(&panel_state,next,action-FMER_GESTURE_SONG);
    else if(action>=FMER_GESTURE_SECTION_HOME)fmer_panel_section_home(&panel_state,action-FMER_GESTURE_SECTION_HOME,next);
    else if(action) {
        id=action-1u;
        if(id==0u) {if(octave> -3)octave--;}
        else if(id==1u) {if(octave<3)octave++;}
        else {
            queue_transport(fmer_panel_button(&panel_state,id,next,fm1_ms));
            if(panel_state.performance_request){queue_transport(panel_state.performance_request);panel_state.performance_request=0;}
            if(panel_state.save_request)storage_request(panel_state.storage_scope_request?8u:1u,panel_state.slot_index);
            if(panel_state.load_request)storage_request(panel_state.storage_scope_request?9u:2u,panel_state.slot_index);
            if(panel_state.reset_request)storage_request(panel_state.reset_request,0u);
            if(panel_state.midi_save_request && !midi_pending)storage_request(6u,0u);
        }
    }
}
static void panel_virtual(uint32_t kind,uint32_t id,int32_t value) {
    fmer_controls_t base,next;capture_controls(&base);next=base;uint32_t nav=panel_state.navigation_revision;
    if(kind==1u) {
        trace_event(FMER_TRACE_ENCODER,id,value,panel_state.family|0x80000000u);
        if(value)fmer_panel_gesture_encoder(&panel_gesture);
        fmer_panel_encoder(&panel_state,id,value,&next,fm1_ms);
        if(panel_state.performance_request){queue_transport(panel_state.performance_request);panel_state.performance_request=0;}
        if(panel_state.audition_request){audition_slot=panel_state.audition_slot;RING_PUBLISH();audition_pending=1;panel_state.audition_request=0;}
    } else {
        if(value>0)virtual_buttons|=1u<<id;else virtual_buttons&=~(1u<<id);
        panel_button_event(id,value>0,0x80000000u,&next);
    }
    publish_controls(&base,&next);
    if(nav!=panel_state.navigation_revision) trace_event(FMER_TRACE_PAGE,panel_state.family,(int32_t)fmer_panel_page(&panel_state,&controls),panel_state.operator_number|0x80000000u);
}
static void panel(void)
{
    int32_t deltas[7]; uint32_t i,released,pressed=fm1_input_edges(&released),f,nav;
    fmer_controls_t base,next;
    /* HAL calls unconditionally enable interrupts; never nest them in our lock. */
    for(i=0;i<7u;i++) deltas[i]=fm1_enc_take(i);
    f=irq_save();
    controls=*fmer_control_snapshot_source(&controls,&applied_controls,diag.ready,controls_generation,diag.controls_applied);
    mirror_controls();
    base=controls;next=base;irq_restore(f);nav=panel_state.navigation_revision;
    for(i=0;i<14u;i++) {
        if(pressed&(1u<<i))panel_button_event(i,1,0,&next);
    }
    {uint32_t action=fmer_panel_gesture_tick(&panel_gesture,fm1_ms);
     if(action==FMER_GESTURE_PANIC)queue_transport(FMER_TRANSPORT_PANIC);
     else if(action==FMER_GESTURE_LAUNCH_TRACK)queue_transport(FMER_TRANSPORT_LAUNCH_TRACK);
     else if(action==FMER_GESTURE_LAUNCH_ALL)queue_transport(FMER_TRANSPORT_LAUNCH_ALL);
     else if(action>=FMER_GESTURE_SECTION_HOME)fmer_panel_section_home(&panel_state,action-FMER_GESTURE_SECTION_HOME,&next);}
    for(i=0;i<7u;i++) if(deltas[i]) {
        trace_event(FMER_TRACE_ENCODER,i,deltas[i],panel_state.family);
        fmer_panel_gesture_encoder(&panel_gesture);
        fmer_panel_encoder(&panel_state,i,deltas[i],&next,fm1_ms);
        if(panel_state.performance_request){queue_transport(panel_state.performance_request);panel_state.performance_request=0;}
        if(panel_state.audition_request){audition_slot=panel_state.audition_slot;RING_PUBLISH();audition_pending=1;panel_state.audition_request=0;}
    }
    /* Preserve the modifier for turns drained in the same pass as release. */
    for(i=0;i<14u;i++)if(released&(1u<<i))panel_button_event(i,0,0,&next);
    publish_controls(&base,&next);
    if(nav!=panel_state.navigation_revision)trace_event(FMER_TRACE_PAGE,panel_state.family,(int32_t)fmer_panel_page(&panel_state,&controls),panel_state.operator_number);
}

static void main_loop(uint32_t rescue)
{
    uint32_t f,t=0,hold=0; int32_t knob=256*16;
    lcd_init(); screen_ready=1; fmer_ui_reset(); fmer_ui_show_splash();
    fm1_input_init(); fm1_adc_init();
    /* Repeated early DSP faults leave a small MIDI/OTA rescue application alive
     * without constructing the DSP. This is working-app rescue, not ROM recovery. */
    if(!rescue) diag.ready=fmer_dsp_init();
    diag.init_failed=!diag.ready; diag.safe_mode=rescue; diag.heap=fmer_heap_used();
    fmer_panel_init(&panel_state);
    midi_requested=panel_state.midi;
    f=irq_save();diag.flash_id=FL_FAR(fl_jedec_ram)();irq_restore(f);
    fl_plain_window_init();storage_boot();
    if(diag.ready) {
        diag.voice_limit=fmer_dsp_voice_limit();fmer_dsp_get_controls(&controls);
        fmer_dsp_set_event_tap(generated_note);
        fmer_dsp_set_midi_output(midi_output);
        applied_controls=controls;mirror_controls();
        fmer_dsp_get_pattern(&pattern_pending);pattern_shown=pattern_pending;
        controls_seen=controls_generation;diag.controls_applied=controls_generation;
        native_live_generation=fmer_dsp_state_generation();native_preset_id=fmer_dsp_preset_id();
        native_sound_dirty=fmer_dsp_sound_dirty();fmer_dsp_patch_name(native_patch_name);
    }
    controls_tick=fm1_ticks();fmer_trace_push_locked(&trace,fm1_ms,FMER_TRACE_BOOT,730,0,0);
    usb_start(); uart_midi_init(); fm1_timer5_start(isr_timer5,4);
    fm1_audio_init(abuf,HALF_WORDS,isr_alnk0,3); fm1_guard_lock_top();
    /* Runtime scan gaps exclude DSP/USB/audio construction before IRQ enable. */
    timer_last=fm1_ticks();fm1_in_stat.last=timer_last;fm1_irq_enable_all();
    /* JEDEC was validated before storage mount. Avoid redundant SPI takeover
     * with interrupts disabled after the audio/input clocks are running. */
    for(;;) {
        fm1_wdt_feed(); native_import_service(); if(!link_host)usb_retry(fm1_ms);
        if(fm1_ms>30000u) { fmer_boot.pending=0; fmer_boot.failed=0; }
        fmer_frame_dispatch();
        if(usb.ota_req && !storage_busy && !native_import_ready) {
            usb.ota_req=0; updating=1; fm1_audio_stop(); memset(abuf,0,sizeof abuf);
            led_generation=0;lights(); /* Stop stale note/RUN indicators during update. */
            if(diag.flash_id==0x856014u) ota_session(); else ota_show(9,-8);
            updating=0; panic_request=1;
            /* Vectors are now guarded; restarting DMA must not reattach the ISR. */
            FM1_ALNK_CON0 |= 0x800u; t=0; fmer_ui_reset();
        }
        /* Keep the known ROM path available in addition to MIDI OTA. */
        if((fm1_in.buttons&3u)!=3u) hold=fm1_ms;
        if(usb.uboot_req || fm1_ms-hold>5000u) {
            fm1_audio_stop(); fmer_boot.pending=0; usb_detach(); fm1_delay_ms(30); fm1_enter_uboot();
        }
        native_import_service();panel();usb_link_apply();midi_settings_publish();native_service();storage_service();
        native_import_service();lights();
        if(fm1_ms-battery_sample_ms>=1000u){int32_t sample=fm1_adc_read(FM1_ADC_BATT);battery_sample_ms=fm1_ms;
            if(sample>=0){battery_last_raw=(uint32_t)sample;battery_q8=battery_valid?(battery_q8*7u+(uint32_t)sample*256u)/8u:(uint32_t)sample*256u;
                battery_raw=(battery_q8+128u)/256u;battery_success_ms=fm1_ms;battery_valid=1;
                battery_percent=fmer_battery_update(&battery_estimator,battery_raw,fm1_ms);
                fmer_battery_history_add(&battery_history,fm1_ms,battery_last_raw,battery_raw,usb.config && !usb.suspended?1u:0u);}}
        if(fm1_ms-t>=20u) {
            int32_t a=fm1_adc_read(FM1_ADC_MASTER); t=fm1_ms;
            if(a>=0) { knob+=(a*16-knob)/4; gain=(uint32_t)(knob/16); }
        }
        screen();
    }
}
extern uint32_t _data_start[],_data_end[],_data_load[],_bss_start[],_bss_end[];
extern uint32_t _pool_start[],_pool_end[],_rt_start[],_rt_end[],_rt_load[];
extern uint32_t _workspace_start[],_workspace_end[];
void fm1_cstart(void)
{
    uint32_t *s,*d,p3,src,wdt,rescue;
    fm1_time_init(); fm1_reset_reason();
    p3=fm1_boot.p3_rst; src=fm1_boot.rst_src; wdt=fm1_boot.wdt_con;
    fm1_wdt_arm(0x0D);
    if(fmer_boot.magic!=BOOT_MAGIC) { fmer_boot.magic=BOOT_MAGIC; fmer_boot.failed=0; fmer_boot.pending=0; }
    if(fmer_boot.pending) fmer_boot.failed++;
    fmer_boot.pending=1;
    rescue=fmer_boot.failed>=2u;
    fm1_irq_init();
    for(d=_bss_start;d<_bss_end;d++) *d=0;
    for(d=_pool_start;d<_pool_end;d++) *d=0;
    /* Separate NOLOAD workspaces are not covered by .bss initialization. */
    for(d=_workspace_start;d<_workspace_end;d++) *d=0;
    for(s=_data_load,d=_data_start;d<_data_end;s++,d++) *d=*s;
    for(s=_rt_load,d=_rt_start;d<_rt_end;s++,d++) *d=*s;
    fm1_mailbox_clear();
    fm1_guard_enable(FM1_GUARD_STACK|FM1_GUARD_WRITE|FM1_GUARD_BUS|FM1_GUARD_PC);
    fm1_boot.p3_rst=(uint8_t)p3; fm1_boot.rst_src=src; fm1_boot.wdt_con=(uint8_t)wdt;
    main_loop(rescue); for(;;) {}
}
