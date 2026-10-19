/* SPDX-License-Identifier: GPL-3.0-only
 * Original FMER navigation model. Pure C, no HAL, allocation or DSP calls.
 * The caller publishes one canonical control snapshot to the audio owner.
 */
#ifndef FMER_PANEL_MODEL_H
#define FMER_PANEL_MODEL_H
#include <stdint.h>
#include <string.h>
#include "control_model.h"
#include "modulation_profiles.h"
#include "midi_settings.h"
#include "performance_commands.h"
#include "algorithm_diagrams.h"
#include "fx_order.h"

enum { FMER_PANEL_HOME, FMER_PANEL_EDIT, FMER_PANEL_ENV, FMER_PANEL_FX,
       FMER_PANEL_LFO, FMER_PANEL_ARP, FMER_PANEL_SEQ, FMER_PANEL_GLO,
       FMER_PANEL_SAVE, FMER_PANEL_PRESETS, FMER_PANEL_FAMILIES };
enum { FMER_PANEL_INVALID=0xffffu, FMER_PANEL_POPUP_MS=1500u };
/* Musical controls first, information and destructive maintenance last. */
enum { FMER_GLO_VOICE, FMER_GLO_GLIDE, FMER_GLO_INPUT, FMER_GLO_OUTPUT,
       FMER_GLO_CLOCK, FMER_GLO_USB_LINK, FMER_GLO_LEGEND, FMER_GLO_HOTKEYS, FMER_GLO_INFO, FMER_GLO_RESET };
typedef struct {
    uint32_t family, page[FMER_PANEL_FAMILIES], operator_number;
    uint32_t focused_knob, focused_id, edited_ms, focus_active, navigation_revision;
    uint32_t fx_selected,fx_order;
    uint32_t fine_adjust; /* main supplies held-SEL state; no button polling here */
    uint32_t preset_candidate;
    uint32_t preset_bank, save_slot, save_bank, chain_cursor;
    uint32_t reset_choice, reset_armed, reset_request;
    fmer_midi_settings_t midi;
    uint32_t midi_revision,midi_save_request;
    uint32_t usb_role,usb_send,usb_apply; /* volatile session roles; never saved */
    /* Board consumes these after button handling; pure panel never touches
     * storage. Requests freeze the chosen destination, not an implicit slot. */
    uint32_t save_request, load_request, slot_index;
    uint32_t audition_request, audition_slot, save_action; /* sound-only browse / explicit full restore */
    uint32_t save_scope, storage_scope_request; /* 0 instrument, 1 project; frozen at confirmation */
    uint32_t edit_id, edit_ms, edit_run, edit_fine;
    int32_t edit_direction;
    uint32_t performance_request, mixer_layer,home_layer;
    uint32_t song_track,song_row,song_layer;
    uint32_t modulation; /* audio-owned recipe snapshot, chorus low byte */
    uint32_t block_start,block_count,block_destination,block_action;
    uint32_t scope_only; /* transient view, never part of a saved instrument */
} fmer_panel_t;

static void fmer_panel_init(fmer_panel_t *s)
{ memset(s,0,sizeof *s);fmer_midi_defaults(&s->midi);s->operator_number=1;s->block_count=1;s->focused_id=FMER_PANEL_INVALID; }

static uint32_t fmer_panel_pages(uint32_t family,uint32_t engine)
{
    switch(family) {
    case FMER_PANEL_EDIT:return engine?1:8;
    case FMER_PANEL_ENV:return 1;
    case FMER_PANEL_FX:return 4;
    case FMER_PANEL_LFO:return engine?1:2;
    case FMER_PANEL_ARP:return 2;
    case FMER_PANEL_SEQ:return 9;
    case FMER_PANEL_GLO:return 10;
    default:return 1;
    }
}
static uint32_t fmer_panel_page(const fmer_panel_t *s,const fmer_controls_t *c)
{ return s->page[s->family]%fmer_panel_pages(s->family,c->value[FMER_ENGINE]); }
static int fmer_panel_popup(const fmer_panel_t *s,uint32_t now)
{ return s->focus_active && (uint32_t)(now-s->edited_ms)<FMER_PANEL_POPUP_MS; }
static void fmer_panel_navigate(fmer_panel_t *s)
{ s->focus_active=0; s->edit_run=0; s->reset_armed=0; s->navigation_revision++; }
static uint32_t fmer_panel_wrap(uint32_t value,int32_t delta,uint32_t count)
{
    int32_t n=(int32_t)value+(delta%(int32_t)count);
    if(n<0) n+=(int32_t)count;
    if(n>=(int32_t)count) n-=(int32_t)count;
    return (uint32_t)n;
}

/* Page IDs stay stable for telemetry and screen fixtures. Only the navigation
 * order changes: performance first, then writing/editing, then setup. */
static uint32_t fmer_panel_landing(uint32_t family,const fmer_controls_t *c)
{ return family==FMER_PANEL_SEQ?(c->value[FMER_SEQ_MODE]?4u:8u):0u; }
static uint32_t fmer_panel_next_page(uint32_t family,uint32_t page,int32_t delta,const fmer_controls_t *c)
{
    static const uint8_t seq[]={4,8,1,0,6,7,5,2,3};
    uint32_t i,start=c->value[FMER_SEQ_MODE]?0u:1u;
    if(family!=FMER_PANEL_SEQ)return fmer_panel_wrap(page,delta,fmer_panel_pages(family,c->value[FMER_ENGINE]));
    for(i=start;i<9u && seq[i]!=page;i++);
    if(i==9u)return seq[start];
    return seq[start+fmer_panel_wrap(i-start,delta,9u-start)];
}
static void fmer_panel_section_home(fmer_panel_t *s,uint32_t button,const fmer_controls_t *c)
{
    uint32_t family=button==2u?FMER_PANEL_FX:button==5u?FMER_PANEL_LFO:button==6u?FMER_PANEL_EDIT:
        button==7u?FMER_PANEL_GLO:button==11u?FMER_PANEL_SEQ:FMER_PANEL_FAMILIES;
    if(family==FMER_PANEL_FAMILIES)return;
    s->family=family;s->page[family]=fmer_panel_landing(family,c);s->scope_only=0;
    s->save_request=s->load_request=s->reset_request=s->midi_save_request=0;
    fmer_panel_navigate(s);
}
static const char *fmer_panel_mode_name(const fmer_controls_t *c)
{ return c->value[FMER_SEQ_MODE]?"4T":c->value[FMER_VOICE_BUDGET]==1u?"1V":c->value[FMER_VOICE_BUDGET]==2u?"2V":c->value[FMER_VOICE_BUDGET]==3u?"3V":"4V"; }
static int fmer_panel_mode_edit(fmer_panel_t *s,fmer_controls_t *c,int32_t delta)
{
    uint32_t mode=c->value[FMER_SEQ_MODE]?2u:c->value[FMER_VOICE_BUDGET]==1u?0u:1u,next;
    /* A discrete, bounded choice: fast turns cannot wrap back into another
     * allocation. Selecting a mode never recalls an instrument or project. */
    if(delta>2)delta=2;if(delta< -2)delta=-2;
    next=delta<0?(uint32_t)(-delta)>mode?0u:mode-(uint32_t)(-delta):(uint32_t)delta>2u-mode?2u:mode+(uint32_t)delta;
    if(next==mode)return 0;
    c->value[FMER_SEQ_MODE]=(uint16_t)(next==2u);
    c->value[FMER_VOICE_BUDGET]=(uint16_t)(next==0u?1u:4u);
    c->value[FMER_GLIDE_MODE]=(uint16_t)(next==0u?c->value[FMER_GLIDE_MODE]?c->value[FMER_GLIDE_MODE]:1u:0u);
    fmer_panel_navigate(s);return 1;
}

static uint32_t fmer_panel_knob_id(const fmer_panel_t *s,uint32_t knob,const fmer_controls_t *c)
{
    static const uint16_t fm_edit[4][4]={
      {16,18,19,20},{14,15,17,13},{8,9,10,11},{12,FMER_PANEL_INVALID,FMER_PANEL_INVALID,FMER_PANEL_INVALID}};
    static const uint16_t fm_lfo[2][4]={{142,137,139,140},{138,143,141,136}};
    static const uint16_t fx[3][4]={{FMER_CUTOFF,FMER_FX_RESONANCE,FMER_REVERB,FMER_DELAY},
      {FMER_CHORUS,FMER_PHASER,FMER_DRIVE,FMER_LFO_ENABLE},
      {FMER_DELAY_MS,FMER_FEEDBACK,FMER_REVERB_DECAY,FMER_REVERB_MODEL}};
    static const uint16_t arp[2][4]={{FMER_ARP_ORDER,FMER_ARP_OCTAVES,FMER_ARP_LATCH,FMER_ARP_TRIPLET},
      {FMER_ARP_RATE,FMER_TEMPO,FMER_ARP_GATE,FMER_ARP_SWING}};
    static const uint16_t seq[8][4]={{FMER_SEQ_STEP,FMER_SEQ_PITCH,FMER_SEQ_VELOCITY,FMER_SEQ_GATE},
      {FMER_SEQ_PATTERN,FMER_TEMPO,FMER_SEQ_LENGTH,FMER_SEQ_CHAIN},
      {FMER_PANEL_INVALID,FMER_PANEL_INVALID,FMER_PANEL_INVALID,FMER_PANEL_INVALID},
      {FMER_SEQ_MODE,FMER_GLIDE_MODE,FMER_GLIDE_MS,FMER_GLIDE_CURVE},
      {FMER_TRACK_LEVEL,FMER_SEQ_TRACK,FMER_TRACK_MUTE,FMER_SEQ_MODE},
      {FMER_RECORD_MODE,FMER_PANEL_INVALID,FMER_PANEL_INVALID,FMER_PANEL_INVALID},
      {FMER_SEQ_STEP,FMER_SEQ_PITCH,FMER_PANEL_INVALID,FMER_SEQ_GATE},
      {FMER_PANEL_INVALID,FMER_PANEL_INVALID,FMER_PANEL_INVALID,FMER_PANEL_INVALID}};
    static const uint16_t va_env[4]={FMER_ATTACK,FMER_DECAY,FMER_SUSTAIN,FMER_RELEASE};
    uint32_t page,engine,base;
    if(knob>3 || s->family>=FMER_PANEL_FAMILIES) return FMER_PANEL_INVALID;
    engine=c->value[FMER_ENGINE]; page=fmer_panel_page(s,c);
    base=(6u-s->operator_number)*21u;
    switch(s->family) {
    case FMER_PANEL_HOME:
        return fx[0][knob];
    case FMER_PANEL_EDIT:
        if(!engine && page==3u && knob==1u)return 135u;
        if(!engine) {if(page>=4u)return page<6u?base+(page-4u)*4u+knob:126u+(page-6u)*4u+knob;return fm_edit[page][knob]==FMER_PANEL_INVALID?FMER_PANEL_INVALID:base+fm_edit[page][knob];}
        return knob==0?FMER_VA_WAVE:knob==1?FMER_VA_CUTOFF:knob==2?FMER_RESONANCE:FMER_PANEL_INVALID;
    case FMER_PANEL_ENV:
        if(engine)return va_env[knob];
        /* The loudest carrier is the reference; edits apply the chosen field
         * to every carrier. Operator timbre envelopes remain independently editable. */
        {uint32_t op,best=5,level=0,mask=fmer_algorithm_diagrams[c->value[134]].carriers;
         static const uint8_t fields[]={0,1,6,3};
         for(op=0;op<6;op++)if((mask&(1u<<op)) && c->value[op*21u+16u]>=level){best=op;level=c->value[op*21u+16u];}
         return best*21u+fields[knob];}
    case FMER_PANEL_FX:if(page==3u)return FMER_PANEL_INVALID;return page==2u && knob==0u && c->value[FMER_DELAY_SYNC]?FMER_DELAY_SYNC:fx[page][knob];
    case FMER_PANEL_LFO:
        if(!engine) return fm_lfo[page][knob];
        return knob==0?FMER_LFO_RATE:knob==1?FMER_LFO_DEPTH:knob==3?FMER_LFO_ENABLE:FMER_PANEL_INVALID;
    case FMER_PANEL_ARP:return arp[page][knob];
    case FMER_PANEL_SEQ:
        /* SINGLE has one polyphonic instrument, outside the four-part mixer.
         * Keep navigation passive and require the visible K4 mode action;
         * inactive mix gestures must not silently alter a dormant part. */
        if(page==4u && c->value[FMER_SEQ_MODE])return FMER_PANEL_INVALID;
        if(page==4u && !c->value[FMER_SEQ_MODE] && knob<3u)return FMER_PANEL_INVALID;
        return page<8u?seq[page][knob]:FMER_PANEL_INVALID;
    case FMER_PANEL_GLO:
        if(page==FMER_GLO_GLIDE) {static const uint16_t glide[]={FMER_GLIDE_MODE,FMER_GLIDE_MS,FMER_GLIDE_CURVE,FMER_VOICE_BUDGET};return glide[knob];}
        if(page==2) return knob==0?FMER_MIDI_CHANNEL:FMER_PANEL_INVALID;
        if(page) return FMER_PANEL_INVALID;
        return knob==0?FMER_SEQ_MODE:knob==1?FMER_TEMPO:knob==2?FMER_VOICE_BUDGET:144u;
    default:return FMER_PANEL_INVALID;
    }
}

/* Slow turns resolve scalar units and proportional musical intervals. Main-loop
 * edit timing accelerates only continuous values; SEL disables acceleration.
 * Integer ratios avoid logarithms, floats and imported-value ladder snapping. */
static int fmer_panel_continuous(uint32_t id)
{
    return id!=134u && id!=144u && id!=FMER_SEQ_STEP && id!=FMER_SEQ_PITCH &&
        id!=FMER_SEQ_LENGTH && id!=FMER_ARP_RATE && id!=FMER_TRACK_SOUND && !(id<126u && id%21u==18u) &&
        fmer_control_max(id)-fmer_control_min(id)>=32u;
}
static uint32_t fmer_panel_step_mode(uint32_t id,uint32_t value,int32_t delta,uint32_t fine)
{
    static const uint16_t rate[]={1,2,4,8,16,32};
    uint32_t i,next,stride=1,ratio=0,offset=0,min=fmer_control_min(id),max=fmer_control_max(id);
    if(delta>256) delta=256; if(delta< -256) delta=-256;
    if(value<min)value=min;if(value>max)value=max;
    if(id==FMER_ARP_RATE) {
        while(delta) {
            next=value;
            if(delta>0) { for(i=0;i<6u;i++) if(rate[i]>value) {next=rate[i];break;} delta--; }
            else { for(i=6u;i>0;i--) if(rate[i-1]<value) {next=rate[i-1];break;} delta++; }
            value=next;
        }
        return value;
    }
    if(id==FMER_CUTOFF || id==FMER_VA_CUTOFF || id==FMER_DELAY_MS)
        ratio=fine?16503u:17358u; /* 2^(1/96), 2^(1/12), Q14 */
    else if(id==FMER_ATTACK || id==FMER_DECAY || id==FMER_RELEASE || id==FMER_GLIDE_MS) {
        ratio=fine?16622u:18390u;offset=20u; /* proportional above a20ms floor */
    } else if(id==FMER_LFO_RATE) {ratio=fine?16503u:17358u;offset=10u;}
    if(ratio) {
        while(delta) {
            uint32_t shifted=value+offset;
            if(delta>0) {
                next=(shifted*ratio+8192u)/16384u-offset;
                if(next<=value)next=value+1u;
                value=next>max?max:next;delta--;
            } else {
                next=(shifted*16384u+ratio/2u)/ratio;
                next=next>offset?next-offset:0u;
                if(next>=value)next=value?value-1u:0u;
                value=next<min?min:next;delta++;
            }
        }
        return value;
    }
    delta*=(int32_t)stride;
    if(delta<0) { uint32_t amount=(uint32_t)(-delta); return amount>value-min?min:value-amount; }
    return (uint32_t)delta>max-value?max:value+(uint32_t)delta;
}
static uint32_t fmer_panel_step(uint32_t id,uint32_t value,int32_t delta)
{ return fmer_panel_step_mode(id,value,delta,0); }
static int fmer_panel_edit(fmer_panel_t *s,fmer_controls_t *c,uint32_t id,uint32_t knob,int32_t delta,uint32_t now)
{
    uint32_t value,speed=1,elapsed;int32_t direction=delta<0?-1:1;
    /* Allocation changes require the explicit MODE gesture. */
    if(id==FMER_VOICE_BUDGET && (c->value[FMER_SEQ_MODE] || c->value[FMER_GLIDE_MODE])) return 0;
    if(!fmer_control_valid(id,id<FMER_PARAM_COUNT?c->value[id]:0)) return 0;
    elapsed=(uint32_t)(now-s->edit_ms);
    if(s->edit_run && s->edit_id==id && s->edit_direction==direction && s->edit_fine==s->fine_adjust && elapsed<=100u)
        {if(s->edit_run<3u)s->edit_run++;}
    else s->edit_run=1;
    if(!s->fine_adjust && s->edit_run>=3u && fmer_panel_continuous(id))
        speed=elapsed<=35u?4u:elapsed<=75u?2u:1u;
    s->edit_id=id;s->edit_ms=now;s->edit_direction=direction;s->edit_fine=s->fine_adjust;
    s->focused_id=id; s->focused_knob=knob; s->edited_ms=now; s->focus_active=1;
    if(delta>256)delta=256;if(delta< -256)delta=-256;
    value=fmer_panel_step_mode(id,c->value[id],delta*(int32_t)speed,s->fine_adjust);
    if(id==FMER_SEQ_STEP && value>=c->value[FMER_SEQ_LENGTH])
        value=c->value[FMER_SEQ_LENGTH]-1u;
    if(!fmer_control_valid(id,value) || value==c->value[id]) return 0;
    c->value[id]=(uint16_t)value;
    if(s->family==FMER_PANEL_ENV && !c->value[FMER_ENGINE]) {
        uint32_t op,mask=fmer_algorithm_diagrams[c->value[134]].carriers;
        for(op=0;op<6;op++)if(mask&(1u<<op))c->value[op*21u+id%21u]=(uint16_t)value;
    }
    if(id==FMER_SEQ_LENGTH && c->value[FMER_SEQ_STEP]>=value)
        c->value[FMER_SEQ_STEP]=(uint16_t)(value-1u);
    return 1;
}
static uint32_t fmer_panel_button(fmer_panel_t *s,uint32_t button,fmer_controls_t *c,uint32_t now)
{
    uint32_t family=FMER_PANEL_FAMILIES;
    if(button==8u && s->fine_adjust) {
        c->value[FMER_SEQ_MODE]=(uint16_t)!c->value[FMER_SEQ_MODE];
        if(!c->value[FMER_SEQ_MODE]){c->value[FMER_GLIDE_MODE]=0;c->value[FMER_VOICE_BUDGET]=4;}
        s->family=FMER_PANEL_HOME;s->scope_only=0;fmer_panel_navigate(s);return 0;
    }
    if(button==8u && s->family==FMER_PANEL_HOME) {
        s->scope_only=!s->scope_only;fmer_panel_navigate(s);return 0;
    }
    s->scope_only=0;
    s->save_request=s->load_request=s->reset_request=s->midi_save_request=0;
    if(button==2u && s->fine_adjust){s->family=FMER_PANEL_FX;s->page[s->family]=3;s->reset_request=11u;fmer_panel_navigate(s);return 0;}
    if(button==3u && s->family==FMER_PANEL_GLO && fmer_panel_page(s,c)==FMER_GLO_USB_LINK) {s->usb_apply=1;return 0;}
    if(button==3u && s->family==FMER_PANEL_GLO && fmer_panel_page(s,c)>=FMER_GLO_OUTPUT && fmer_panel_page(s,c)<=FMER_GLO_CLOCK) {s->midi_save_request=1;return 0;}
    if(button==3u && s->family==FMER_PANEL_GLO && fmer_panel_page(s,c)==FMER_GLO_RESET) {
        if(s->reset_armed){s->reset_request=s->reset_choice==4u?12u:s->reset_choice==3u?10u:s->reset_choice+3u;s->reset_armed=0;}
        else s->reset_armed=1;
        return 0;
    }
    if(button==3u && s->family==FMER_PANEL_GLO)return 0;
    if(button==3u && s->family==FMER_PANEL_HOME && c->value[FMER_SEQ_MODE]) {
        s->home_layer=fmer_mix_scroll(s->home_layer,1,1);fmer_panel_navigate(s);return 0;
    }
    if(button==3u && s->family==FMER_PANEL_SEQ && fmer_panel_page(s,c)==8u) {
        s->song_layer=(s->song_layer+1u)%2u;fmer_panel_navigate(s);return 0;
    }
    if(button==3u && s->family==FMER_PANEL_SEQ && fmer_panel_page(s,c)==6u) {
        s->performance_request=fmer_note_command(c->value[FMER_SEQ_PATTERN],c->value[FMER_SEQ_STEP],FMER_NOTE_DELETE,0);
        fmer_panel_navigate(s);return 0;
    }
    if(button==3u && s->family==FMER_PANEL_SEQ && fmer_panel_page(s,c)==7u) {
        s->performance_request=fmer_block_command(c->value[FMER_SEQ_PATTERN],s->block_start,s->block_count,s->block_destination,s->block_action);
        fmer_panel_navigate(s);return 0;
    }
    if(button==3u && s->family==FMER_PANEL_SEQ && fmer_panel_page(s,c)==4u && c->value[FMER_SEQ_MODE]) {
        s->mixer_layer=fmer_mix_scroll(s->mixer_layer,1,0);fmer_panel_navigate(s);return 0;
    }
    if(button==12) return FMER_TRANSPORT_PLAY;
    if(button==13 && s->family==FMER_PANEL_ARP)return FMER_TRANSPORT_ARP_RECORD;
    if(button==13) { s->family=FMER_PANEL_SEQ; fmer_panel_navigate(s); return FMER_TRANSPORT_RECORD; }
    if(button==3u && s->family==FMER_PANEL_PRESETS) {
        s->family=FMER_PANEL_HOME;fmer_panel_navigate(s);return 0;
    }
    if(button==3u && s->family==FMER_PANEL_SAVE) {
        if(s->save_action)s->load_request=1;else s->save_request=1;
        s->storage_scope_request=s->save_scope;
        s->slot_index=s->save_scope?s->save_slot:s->save_slot+64u*s->save_bank;return 0;
    }
    if(button==10u && s->family==FMER_PANEL_ARP) {
        c->value[FMER_ARP_ENABLE]=(uint16_t)!c->value[FMER_ARP_ENABLE];
        s->focused_id=FMER_ARP_ENABLE;s->focused_knob=4;
        s->edited_ms=now;s->focus_active=1;return 0;
    }
    if(button==5u && s->family==FMER_PANEL_LFO) {
        c->value[FMER_LFO_ENABLE]=(uint16_t)!c->value[FMER_LFO_ENABLE];
        s->focused_id=FMER_LFO_ENABLE;s->focused_knob=4;
        s->edited_ms=now;s->focus_active=1;return 0;
    }
    switch(button) {
    case 8:family=FMER_PANEL_HOME;break; case 6:family=FMER_PANEL_EDIT;break;
    case 4:family=FMER_PANEL_ENV;break; case 2:family=FMER_PANEL_FX;break;
    case 5:family=FMER_PANEL_LFO;break; case 10:family=FMER_PANEL_ARP;break;
    case 11:family=FMER_PANEL_SEQ;break; case 7:family=FMER_PANEL_GLO;break;
    case 9:family=FMER_PANEL_SAVE;break;
    case 3:family=s->family;break;
    default:return 0;
    }
    if(family==s->family && family!=FMER_PANEL_HOME) {
        s->page[family]=fmer_panel_next_page(family,s->page[family],1,c);
    }
    else if(family==FMER_PANEL_SEQ)s->page[family]=fmer_panel_landing(family,c);
    s->family=family;
    fmer_panel_navigate(s); return 0;
}
/* Global mode shortcuts are atomic canonical snapshots, not fake page taps. */
static void fmer_panel_shortcut(fmer_panel_t *s,fmer_controls_t *c,uint32_t action)
{
    s->scope_only=0;s->family=action<2u?FMER_PANEL_SEQ:FMER_PANEL_HOME;
    if(action<2u){c->value[FMER_SEQ_MODE]=1;s->page[FMER_PANEL_SEQ]=action?4u:8u;}
    else {c->value[FMER_SEQ_MODE]=0;c->value[FMER_GLIDE_MODE]=action==2u?1u:0u;c->value[FMER_VOICE_BUDGET]=action==2u?1u:4u;}
    fmer_panel_navigate(s);
}
/* Stable MIDI IDs from707 stay unchanged while banks present32FM/32VA. */
static uint32_t fmer_panel_factory_id(uint32_t bank,uint32_t index)
{ return bank?index<8u?index+8u:index+32u:index<8u?index:index+8u; }
static uint32_t fmer_panel_factory_index(uint32_t bank,uint32_t id)
{ return bank?id<16u?id-8u:id-32u:id<8u?id:id-8u; }
static void fmer_panel_audition(fmer_panel_t *s)
{ s->audition_slot=s->preset_candidate+(s->preset_bank==2u?0u:64u);s->audition_request=1; }
static void fmer_panel_browse(fmer_panel_t *s,int32_t delta)
{
    uint32_t index=s->preset_bank==2u?s->preset_candidate:fmer_panel_factory_index(s->preset_bank,s->preset_candidate);
    /* A single128-slot ring makes every bank discoverable from PRESETS. The
     * legacy factory program IDs remain stable on disk and over MIDI. */
    index=fmer_panel_wrap(index+s->preset_bank*32u,delta,128u);
    s->preset_bank=index<32u?0u:index<64u?1u:2u;
    index-=s->preset_bank*32u;
    s->preset_candidate=s->preset_bank==2u?index:fmer_panel_factory_id(s->preset_bank,index);
    s->family=FMER_PANEL_PRESETS;fmer_panel_navigate(s);fmer_panel_audition(s);
}
static int fmer_panel_encoder(fmer_panel_t *s,uint32_t encoder,int32_t delta,fmer_controls_t *c,uint32_t now)
{
    uint32_t page,engine=c->value[FMER_ENGINE];
    if(!delta || encoder>6) return 0;
    s->scope_only=0;
    if((s->family==FMER_PANEL_PRESETS && encoder==0u) ||
       (s->family==FMER_PANEL_SEQ && fmer_panel_page(s,c)==3u && encoder==2u) ||
       (s->family==FMER_PANEL_GLO && fmer_panel_page(s,c)==FMER_GLO_VOICE && encoder==2u))
        return fmer_panel_mode_edit(s,c,delta);
    if(s->family==FMER_PANEL_SEQ && fmer_panel_page(s,c)==3u && encoder>=3u && encoder<=5u && c->value[FMER_SEQ_MODE])return 0;
    if(s->family==FMER_PANEL_FX && fmer_panel_page(s,c)==3u && encoder>=1u && encoder<=5u) {
        if(encoder==2u || encoder==1u){uint8_t order[6];uint32_t at;fmer_fx_unrank(s->fx_order,order);
            for(at=0;at<6u && order[at]!=s->fx_selected;at++);s->fx_selected=order[fmer_panel_wrap(at%6u,delta,6u)];}
        if(encoder==3u)s->performance_request=fmer_fx_command(s->fx_selected,delta);
        if(encoder==4u)s->performance_request=fmer_fx_command(6u,1);
        if(encoder!=0u)fmer_panel_navigate(s);return 0;
    }
    if(s->family==FMER_PANEL_PRESETS && encoder>=2u && encoder<=5u) {
        if(encoder==2u){s->preset_bank=fmer_panel_wrap(s->preset_bank,delta,3u);
            s->preset_candidate=s->preset_bank==2u?s->save_slot:fmer_panel_factory_id(s->preset_bank,0u);fmer_panel_navigate(s);fmer_panel_audition(s);}
        return 0;
    }
    if(s->family==FMER_PANEL_SAVE && encoder>=2u && encoder<=5u) {
        if(encoder==2u)s->save_slot=fmer_panel_wrap(s->save_slot,delta,s->save_scope?16u:64u);
        if(encoder==3u && !s->save_scope)s->save_bank=fmer_panel_wrap(s->save_bank,delta,2u);
        if(encoder==4u)s->save_action=fmer_panel_wrap(s->save_action,delta,2u);
        if(encoder==5u){s->save_scope=fmer_panel_wrap(s->save_scope,delta,2u);if(s->save_scope && s->save_slot>=16u)s->save_slot=15u;}
        fmer_panel_navigate(s);return 0;
    }
    if(s->family==FMER_PANEL_GLO && fmer_panel_page(s,c)==FMER_GLO_USB_LINK && encoder>=2u && encoder<=5u) {
        if(encoder==2u)s->usb_role=fmer_panel_wrap(s->usb_role,delta,3);
        if(encoder==3u && s->usb_role==1u)s->usb_send=fmer_panel_wrap(s->usb_send,delta,3);
        fmer_panel_navigate(s);return 0;
    }
    if(s->family==FMER_PANEL_GLO && fmer_panel_page(s,c)>=FMER_GLO_OUTPUT && fmer_panel_page(s,c)<=FMER_GLO_CLOCK && encoder>=2u && encoder<=5u) {
        static const uint8_t ids[2][4]={{0,1,2,7},{3,4,5,6}};
        uint32_t id=ids[fmer_panel_page(s,c)-FMER_GLO_OUTPUT][encoder-2u],old=s->midi.value[id];

        s->midi.value[id]=(uint8_t)fmer_panel_wrap(old,delta,fmer_midi_setting_max(id)+1u);
        if(old!=s->midi.value[id])s->midi_revision++;
        fmer_panel_navigate(s);return 0;
    }
    if(s->family==FMER_PANEL_GLO && fmer_panel_page(s,c)==FMER_GLO_RESET && encoder>=2u && encoder<=5u) {
        if(encoder==2u)s->reset_choice=fmer_panel_wrap(s->reset_choice,delta,5u);
        fmer_panel_navigate(s);return 0;
    }
    if(s->family==FMER_PANEL_SEQ && fmer_panel_page(s,c)==2u && encoder>=2u && encoder<=5u) {
        if(encoder==2u){s->chain_cursor=fmer_panel_wrap(s->chain_cursor,delta,fmer_control_max(FMER_SEQ_PATTERN)+1u);fmer_panel_navigate(s);return 0;}
        if(encoder==3u){uint32_t old=c->value[FMER_SEQ_CHAIN_MASK],bit=1u<<s->chain_cursor;
            uint32_t mask=delta>0?old|bit:old&~bit;fmer_panel_navigate(s);
            if(!mask || mask==old)return 0;c->value[FMER_SEQ_CHAIN_MASK]=(uint16_t)mask;return 1;}
        return 0;
    }
        if(((s->family==FMER_PANEL_HOME) || (s->family==FMER_PANEL_SEQ && fmer_panel_page(s,c)==4u)) && c->value[FMER_SEQ_MODE] && encoder<=5u){
            uint32_t *layer=s->family==FMER_PANEL_HOME?&s->home_layer:&s->mixer_layer;
            if(encoder<=1u)*layer=fmer_mix_scroll(*layer,delta,s->family==FMER_PANEL_HOME);
            else {
                int32_t movement=delta;
                if(*layer==FMER_MIX_LEVEL){
                    uint32_t id=FMER_PARAM_COUNT+encoder,elapsed=now-s->edit_ms,speed=2u;
                    int32_t direction=delta<0?-1:1;
                    if(s->edit_run && s->edit_id==id && s->edit_direction==direction && s->edit_fine==s->fine_adjust && elapsed<=100u){if(s->edit_run<3u)s->edit_run++;}
                    else s->edit_run=1;
                    if(s->edit_run>=3u && elapsed<=75u)speed=elapsed<=35u?6u:4u;
                    if(s->fine_adjust)speed=1u;
                    s->edit_id=id;s->edit_ms=now;s->edit_direction=direction;s->edit_fine=s->fine_adjust;
                    if(movement>100)movement=100;if(movement< -100)movement=-100;
                    movement*=(int32_t)speed;
                }
                s->performance_request=fmer_mix_command(encoder-2u,*layer,movement);
            }
            if(encoder>=2u && *layer==FMER_MIX_LEVEL){s->focus_active=0;s->reset_armed=0;s->navigation_revision++;}
            else fmer_panel_navigate(s);
            return 0;
        }
    if(s->family==FMER_PANEL_SEQ && fmer_panel_page(s,c)==8u && encoder<=5u) {
        if(!c->value[FMER_SEQ_MODE])s->song_track=0;
        if(encoder==1u && c->value[FMER_SEQ_MODE])s->song_track=fmer_panel_wrap(s->song_track,delta,4u);
        else if(encoder==0u || encoder==2u)s->song_row=fmer_panel_wrap(s->song_row,delta,32u);
        else if(encoder>=3u && encoder<=5u) {
            uint32_t action=s->song_layer?encoder==3u?3u:encoder==4u?4u:delta>0?6u:5u:encoder-3u;
            s->performance_request=fmer_song_command(s->song_track,s->song_row,action,delta);
        }
        fmer_panel_navigate(s);return 0;
    }
    if(s->family==FMER_PANEL_SEQ) {
        page=fmer_panel_page(s,c);
        if(page==3u && encoder==1u) {return fmer_panel_edit(s,c,FMER_SEQ_TRACK,0,delta,now);}
        if(page==6u && encoder==3u && s->fine_adjust){
            c->value[FMER_SEQ_PITCH]=(uint16_t)(delta<0?FMER_REST:FMER_TIE);fmer_panel_navigate(s);return 1;
        }
        if(page==6u && encoder==1u){
            s->performance_request=fmer_note_command(c->value[FMER_SEQ_PATTERN],c->value[FMER_SEQ_STEP],FMER_NOTE_MOVE,delta);
            fmer_panel_navigate(s);return 0;
        }
        if(page==6u && encoder==4u){
            s->performance_request=fmer_note_command(c->value[FMER_SEQ_PATTERN],c->value[FMER_SEQ_STEP],FMER_NOTE_LENGTH,delta);
            fmer_panel_navigate(s);return 0;
        }
        if(page==7u && encoder>=2u && encoder<=5u){
            uint32_t length=c->value[FMER_SEQ_LENGTH];
            if(encoder==2u)s->block_start=fmer_panel_wrap(s->block_start,delta,length);
            if(s->block_start>=length)s->block_start=length-1u;
            if(encoder==3u)s->block_count=fmer_panel_wrap(s->block_count-1u,delta,length-s->block_start)+1u;
            if(s->block_count>length-s->block_start)s->block_count=length-s->block_start;
            if(encoder==4u)s->block_destination=fmer_panel_wrap(s->block_destination,delta,length);
            if(s->block_destination>=length)s->block_destination=length-1u;
            if(encoder==5u)s->block_action=fmer_panel_wrap(s->block_action,delta,FMER_BLOCK_ACTIONS);
            fmer_panel_navigate(s);return 0;
        }
    }
    if(encoder>=2 && encoder<=5) return fmer_panel_edit(s,c,fmer_panel_knob_id(s,encoder-2u,c),encoder-2u,delta,now);
    if(encoder==1 && s->family==FMER_PANEL_FX && fmer_panel_page(s,c)==1u){
        uint32_t effect=s->focused_id==FMER_PHASER?1u:0u;
        uint32_t preset=fmer_panel_wrap((s->modulation>>(effect*8u))&3u,delta,4u);
        s->performance_request=0x60000000u|(effect<<8)|preset;
        s->focused_id=effect?FMER_PHASER:FMER_CHORUS;s->focused_knob=effect;
        s->edited_ms=now;s->focus_active=1;return 0;
    }
    if(encoder==1) {
        uint32_t id=engine?FMER_VA_WAVE:134u,previous;
        if(s->family==FMER_PANEL_FX)id=fmer_panel_page(s,c)==0u?FMER_FILTER_TYPE:fmer_panel_page(s,c)==2u?FMER_DELAY_SYNC:FMER_DELAY_MODEL;
        previous=c->value[id];
        if(s->family==FMER_PANEL_PRESETS || s->family==FMER_PANEL_SAVE) {s->family=FMER_PANEL_HOME;fmer_panel_navigate(s);}
        s->focused_id=id;s->focused_knob=4;s->edited_ms=now;s->focus_active=1;
        c->value[id]=(uint16_t)fmer_panel_wrap(previous,delta,fmer_control_max(id)+1u);
        return c->value[id]!=previous;
    }
    if(encoder==6) {fmer_panel_browse(s,delta);return 0;}
    if(s->family==FMER_PANEL_HOME) {
        uint32_t next=delta>0?1u:0u;
        fmer_panel_navigate(s); c->value[FMER_ENGINE]=(uint16_t)next; return next!=engine;
    }
    page=fmer_panel_page(s,c);
    if(!engine && (s->family==FMER_PANEL_EDIT && page<6u))
        s->operator_number=fmer_panel_wrap(s->operator_number-1u,delta,6u)+1u;
    else s->page[s->family]=fmer_panel_next_page(s->family,page,delta,c);
    
    fmer_panel_navigate(s);return 0;
}

static const char *fmer_panel_family_name(uint32_t family)
{ static const char *const names[]={"HOME","EDIT","ENVELOPE","EFFECTS","LFO","ARPEGGIO","SEQUENCER","SYSTEM","SAVE","PRESETS"};return family<FMER_PANEL_FAMILIES?names[family]:"HOME"; }
static const char *fmer_panel_page_name(const fmer_panel_t *s,const fmer_controls_t *c)
{
    static const char *const fm[]={"TUNE","SENSITIVITY","KEY SCALE","CURVE","OP RATES","OP LEVELS","PITCH RATES","PITCH LEVELS"};
    static const char *const env[]={"OP RATES","OP LEVELS","PITCH RATES","PITCH LEVELS"};
    static const char *const fx[]={"FILTER / SPACE","MODULATION","SPACE SETTINGS","SIGNAL CHAIN"};
    uint32_t p=fmer_panel_page(s,c);
    switch(s->family) {
    case FMER_PANEL_EDIT:return c->value[FMER_ENGINE]?"VA OSC/FILTER":fm[p];
    case FMER_PANEL_ENV:return c->value[FMER_ENGINE]?"VA ADSR":"FM AMP ENVELOPE";
    case FMER_PANEL_FX:return fx[p];
    case FMER_PANEL_LFO:return c->value[FMER_ENGINE]?"VA VIBRATO":p?"FM SYNC":"FM MODULATION";
    case FMER_PANEL_ARP:return p?"TIMING":"TYPE/LATCH";
    case FMER_PANEL_SEQ:{static const char *const pages[]={"STEP EDIT","PATTERNS","CHAIN MEMBERS","PLAY MODE","PERFORM","RECORD","NOTE EDIT","COPY / EDIT","SONG"};return pages[p];}
    case FMER_PANEL_GLO:{static const char *const pages[]={"VOICE/TEMPO","MONO GLIDE","MIDI INPUT","MIDI OUTPUT","MIDI CLOCK","USB LINK","ICON LEGEND","SHORTCUTS","INFO","RESET/CLEAR"};return pages[p];}
    case FMER_PANEL_SAVE:return s->save_scope?"PROJECT":"INSTRUMENT";
    case FMER_PANEL_PRESETS:return s->preset_bank==2u?"USER SOUNDS":s->preset_bank?"VA DEFAULTS":"FM DEFAULTS";
    default:return c->value[FMER_ENGINE]?"VA SOUND":"FM SOUND";
    }
}
static const char *fmer_panel_name(uint32_t id)
{
    static const char *const op[]={"RATE 1","RATE 2","RATE 3","RATE 4","LEVEL 1","LEVEL 2","LEVEL 3","LEVEL 4","BREAKPOINT","LEFT DEPTH","RIGHT DEPTH","LEFT CURVE","RIGHT CURVE","RATE SCALE","AM SENS","VELOCITY","OUTPUT","OSC MODE","COARSE","FINE","DETUNE"};
    static const char *const globals[]={"PITCH R1","PITCH R2","PITCH R3","PITCH R4","PITCH L1","PITCH L2","PITCH L3","PITCH L4","ALGORITHM","FM FEEDBACK","OSC SYNC","LFO SPEED","LFO DELAY","PITCH DEPTH","AMP DEPTH","LFO SYNC","LFO WAVE","PITCH SENS","TRANSPOSE"};
    static const char *const extra[]={"ENGINE","WAVEFORM","MASTER CUT","RESONANCE","ATTACK","DECAY","SUSTAIN","RELEASE","DRIVE","CHORUS","DELAY MIX","DELAY TIME","DELAY FB","REVERB","PHASER","LFO RATE","LFO DEPTH","VOICE CUT","TEMPO","ARP ENABLE","ARP TYPE","ARP RATE","ARP OCT","ARP GATE","ARP LATCH","ARP SWING","SEQ LENGTH","SEQ STEP","SEQ PITCH","VELOCITY","SEQ GATE","VOICE LIMIT","TRIPLET","MIDI CH","VERB DECAY","PATTERN","CHAIN","CHAIN MASK"};
    if(id<126) return op[id%21]; if(id<145) return globals[id-126];
    if(id>=145 && id<150){static const char *const fx[]={"FILTER TYPE","FX RESONANCE","LFO ENABLE","REVERB MODEL","DELAY MODEL"};return fx[id-145];}
    if(id>=150 && id<=158){static const char *const names[]={"GLIDE MODE","GLIDE TIME","GLIDE CURVE","SEQ MODE","TRACK","TRACK SOUND","TRACK LEVEL","TRACK MUTE","RECORD MODE"};return names[id-150];}
    if(id==FMER_DELAY_SYNC)return "DELAY SYNC";
    if(id>=160 && id<FMER_PARAM_COUNT) return extra[id-160];return "UNASSIGNED";
}
static const char *fmer_panel_short_name(uint32_t id)
{
    switch(id) {
    case FMER_FILTER_TYPE:return "TYPE";case FMER_FX_RESONANCE:return "RESON";
    case FMER_LFO_ENABLE:return "LFO";case FMER_REVERB_MODEL:return "VERB";case FMER_DELAY_MODEL:return "ECHO";
    case FMER_CUTOFF:return "FREQ";case FMER_VA_CUTOFF:return "VCUT";case FMER_RESONANCE:return "RESO";
    case FMER_DELAY_SYNC:return "SYNC";case FMER_DELAY:return "DELAY";case FMER_DELAY_MS:return "TIME";case FMER_FEEDBACK:return "FEEDBK";
    case FMER_VA_WAVE:return "WAVE";case FMER_ENGINE:return "ENGINE";
    case FMER_LFO_RATE:return "RATE";case FMER_LFO_DEPTH:return "DEPTH";
    case FMER_ARP_ENABLE:return "ARP";case FMER_ARP_ORDER:return "TYPE";case FMER_ARP_RATE:return "RATE";
    case FMER_GLIDE_MODE:return "GLIDE";case FMER_GLIDE_MS:return "TIME";case FMER_GLIDE_CURVE:return "CURVE";
    case FMER_SEQ_MODE:return "MODE";case FMER_SEQ_TRACK:return "TRACK";case FMER_TRACK_SOUND:return "SOUND";
    case FMER_TRACK_LEVEL:return "LEVEL";case FMER_TRACK_MUTE:return "MUTE";case FMER_RECORD_MODE:return "RECORD";
    case FMER_ARP_OCTAVES:return "OCT";case FMER_ARP_GATE:case FMER_SEQ_GATE:return "GATE";
    case FMER_ARP_LATCH:return "LATCH";case FMER_ARP_SWING:return "SWING";
    case FMER_SEQ_LENGTH:return "LENGTH";case FMER_SEQ_STEP:return "STEP";case FMER_SEQ_PITCH:return "PITCH";
    case FMER_SEQ_VELOCITY:return "VEL";case FMER_VOICE_BUDGET:return "VOICES";
    case FMER_SEQ_PATTERN:return "PATTERN";case FMER_SEQ_CHAIN:return "CHAIN";case FMER_SEQ_CHAIN_MASK:return "MASK";
    case FMER_REVERB_DECAY:return "DECAY";case FMER_MIDI_CHANNEL:return "MIDI CH";
    case 134:return "ALGO";case 135:return "FEEDBK";case 144:return "TRANS";
    default:if(id<126) {static const char *const names[]={"RATE1","RATE2","RATE3","RATE4","LEVEL1","LEVEL2","LEVEL3","LEVEL4","BREAK","LDEPTH","RDEPTH","LCURVE","RCURVE","RSCALE","AMS","VEL","LEVEL","MODE","COARSE","FINE","DETUNE"};return names[id%21];}return fmer_panel_name(id);
    }
}
static const char *fmer_panel_unit(uint32_t id)
{
    if(id==FMER_CUTOFF || id==FMER_VA_CUTOFF) return "HZ";
    if(id==FMER_ATTACK || id==FMER_DECAY || id==FMER_RELEASE || id==FMER_DELAY_MS || id==FMER_GLIDE_MS) return "MS";
    if(id==FMER_LFO_RATE) return "CHZ";
    if(id==FMER_LFO_DEPTH) return "CENT";
    if(id==FMER_TEMPO) return "BPM";
    if(id==FMER_TRACK_LEVEL || id==FMER_FX_RESONANCE || id==FMER_RESONANCE || id==FMER_REVERB_DECAY || id==FMER_SUSTAIN || (id>=FMER_DRIVE && id<=FMER_PHASER && id!=FMER_DELAY_MS) || id==FMER_ARP_GATE || id==FMER_ARP_SWING || id==FMER_SEQ_GATE) return "%";
    return "";
}
static int fmer_panel_stored_only(uint32_t id)
{ return id==136u; }
#endif
