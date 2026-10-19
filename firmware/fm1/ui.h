/* SPDX-License-Identifier: GPL-3.0-only
 * Original FMER small-screen UI. Include after lcd.c in the board translation
 * unit. Render one complete changed strip in RAM, then submit one DMA transfer.
 * No allocation, visible clear, per-glyph SPI transaction or audio-ISR work.
 */
#ifndef FMER_UI_H
#define FMER_UI_H
#include <stdint.h>
#include <string.h>
#include "panel_model.h"
#include "delay_timing.h"
#include "dsp_adapter.h"
#include "memory_layout.h"
#include "algorithm_diagrams.h"
#include "splash.h"

#ifndef FMER_UI_CAN_DRAW
#define FMER_UI_CAN_DRAW() (!lcd_busy || (FM1_LCD_SPI_CON & 0x8000u))
#endif
#ifndef FMER_UI_SYNC
#define FMER_UI_SYNC() lcd_sync()
#endif
#ifndef FMER_UI_BLIT
#define FMER_UI_BLIT(x,y,w,h,p) lcd_blit(x,y,w,h,p)
#endif

typedef struct {
    uint32_t build, engine, algorithm, va_wave, attack_ms, release_ms;
    uint32_t cutoff_hz, cutoff_position, delay_percent, gain;
    int32_t octave;
    uint32_t voices, voice_limit, render_us, overruns, shed;
    uint32_t audio_paused, init_failed, usb_ready, page;
    /* ADC validity is separate from model validity. 0..100 is an explicitly
     * estimated percentage; 101 (or any larger value) means uncalibrated. */
    uint32_t battery_valid, battery_raw, battery_percent;
    uint32_t usb_audio_active;
    uint32_t usb_link_role,usb_link_state,usb_link_error,usb_link_rx,usb_link_tx;
    uint32_t beat_on; /* audio-owned pulse, also used by the panel PLAY light */
    const fmer_controls_t *controls;
    const fmer_panel_t *panel;
    const fmer_pattern_state_t *pattern;
    fmer_performance_state_t performance;
    const int16_t *scope,*part_scopes;
    uint32_t scope_generation;
    uint16_t fx_activity[6];
    uint16_t fx_order;
    uint32_t preset_id, sound_dirty, save_state, saved_generation, live_generation;
    const char *patch_name, *candidate_name;
    uint32_t storage_ready, storage_result, storage_slot, storage_valid_slots;
    uint32_t user_slot_present, store_busy, storage_action; /* 0none,1save,2load */
    const char *user_slot_name;
} fmer_ui_state_t;

enum { FMER_UI_HOME, FMER_UI_CUTOFF, FMER_UI_DELAY, FMER_UI_ATTACK,
       FMER_UI_RELEASE, FMER_UI_STATS };
enum { FMER_UI_WIDTH=240, FMER_UI_HEIGHT=240, FMER_UI_STRIP=24, FMER_UI_ROWS=10 };
enum { FMER_UI_BG=0x0000, FMER_UI_PANEL=0x1082, FMER_UI_INK=0xFFFF,
       FMER_UI_GREEN=0x87EE, FMER_UI_PINK=0xFC7E, FMER_UI_MUTED=0xB5D8,
       FMER_UI_PURPLE=0xCD1F };
enum { FMER_GRID_VELOCITY=16, FMER_GRID_GATE=32, FMER_GRID_SELECTED=48,
       FMER_GRID_PLAYHEAD, FMER_GRID_LENGTH, FMER_GRID_LOW, FMER_GRID_HIGH,
       FMER_GRID_BANK };
typedef struct {
    char first[40], second[40];
    uint32_t amount, maximum;
    uint16_t color;
    uint8_t scale, bar, label_chars, highlight;
    uint8_t scope_row, scope[FMER_SCOPE_SAMPLES];
} fmer_ui_row_t;
static struct {
    uint16_t pixels[FMER_UI_WIDTH*FMER_UI_STRIP];
    /* One bit per old waveform pixel, not another RGB framebuffer. This lets
     * the ready-only sender crop actual raster damage, including erased ink. */
    uint8_t scope_old[FMER_UI_WIDTH*FMER_UI_STRIP/8u];
    fmer_ui_row_t shown[FMER_UI_ROWS];
    uint32_t last_service, last_stats, rows_sent, bytes_sent;
    uint32_t voices, render_us, overruns, shed;
    uint32_t last_scope, scope_generation;
    uint32_t scope_peak, scope_gain, scope_quiet;
    uint8_t scope[FMER_SCOPE_SAMPLES];
    uint8_t part_scope[4][32];
    uint8_t fx_activity[6];
    uint16_t valid, scope_rows, scope_view;
    uint8_t next, started, splash;
} fmer_ui FMER_WORKSPACE;

/* Original 5x7 alphabet from FMER 701, extended with punctuation. */
static const uint8_t fmer_ui_glyphs[][5] = {
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
 {0x63,0x14,8,0x14,0x63},{3,4,0x78,4,3},{0x61,0x51,0x49,0x45,0x43},
 {8,8,8,8,8},{8,8,0x3e,8,8},{0x40,0x20,0x10,8,4},{0,0x36,0x36,0,0},
 {0x63,0x13,8,0x64,0x63},{0,0x41,0x22,0x14,8}
};

static char *fmer_ui_text(char *p, const char *s)
{ while (*s) *p++=*s++; *p=0; return p; }
static char *fmer_ui_number(char *p, uint32_t value)
{
    char digits[10]; uint32_t n=0;
    do { digits[n++]=(char)('0'+value%10u); value/=10u; } while(value);
    while(n) *p++=digits[--n]; *p=0; return p;
}
static char *fmer_ui_signed(char *p, int32_t value)
{
    *p++=value<0?'-':'+';
    return fmer_ui_number(p,value<0?0u-(uint32_t)value:(uint32_t)value);
}

/* Q10 log2 for positive control values, using bounded32-bit arithmetic.
 * Cutoff position is perceptual; the displayed/persisted Hz stay exact. */
static uint32_t fmer_ui_log_position(uint32_t value)
{
    uint32_t x=value<<15u,result=0,i;
    if(!value)return 0;
    while(x>=65536u){x>>=1u;result+=1024u;}
    for(i=0;i<10u;i++){
        x=(x*x)>>15u;
        if(x>=65536u){x>>=1u;result|=1u<<(9u-i);}
    }
    return result;
}

/* Named choices hide wire enums; continuous values retain their exact units. */
static void fmer_ui_parameter(char *out,uint32_t id,uint32_t value,int compact)
{
    static const char *const waves[]={"SINE","SAW","SQUARE","TRIANGLE","NOISE"};
    static const char *const orders[]={"UP","DOWN","EXCLUSIVE","PLAYED","INCLUSIVE","RANDOM","REPEAT","DOWN EXCL","DOWN INCL","OUTSIDE IN","STRUM"};
    char *p=out; const char *unit=fmer_panel_unit(id);
    if(id==FMER_PANEL_INVALID) {fmer_ui_text(p,"--");return;}
    if(id==FMER_SEQ_PITCH && value==FMER_TIE){fmer_ui_text(p,"TIE");return;}
    if(id==FMER_TRACK_SOUND){p=fmer_ui_text(p,value<64?"U":"D");p=fmer_ui_number(p,value%64u);return;}
    if(id==FMER_SEQ_TRACK){p=fmer_ui_text(p,"T");p=fmer_ui_number(p,value+1u);return;}
    if(id==FMER_ENGINE) p=fmer_ui_text(p,value?"VA ":"FM ");
    else if(id==FMER_GLIDE_MODE && value<3u){static const char *const names[]={"OFF ","LEGATO ","ALWAYS "};p=fmer_ui_text(p,names[value]);}
    else if(id==FMER_GLIDE_CURVE && value<3u){static const char *const names[]={"LINEAR ","EASE IN ","EASE OUT "};p=fmer_ui_text(p,names[value]);}
    else if(id==FMER_SEQ_MODE)p=fmer_ui_text(p,value?"4TRK ":"SINGLE ");
    else if(id==FMER_RECORD_MODE)p=fmer_ui_text(p,value==2u?"REPLACE ":value?"OVERDUB ":"STEP ");
    else if(id==FMER_VA_WAVE && value<5u) {p=fmer_ui_text(p,waves[value]);p=fmer_ui_text(p," ");}
    else if(id==FMER_ARP_ORDER && value<11u) {p=fmer_ui_text(p,orders[value]);p=fmer_ui_text(p," ");}
    else if(id==FMER_FILTER_TYPE && value<3u){static const char *const types[]={"LP ","HP ","BP "};p=fmer_ui_text(p,types[value]);}
    else if(id==FMER_REVERB_MODEL){static const char *const names[]={"ROOM ","PLATE ","HALL ","CLOUD "};p=fmer_ui_text(p,names[value<4?value:0]);}
    else if(id==FMER_DELAY_SYNC){p=fmer_ui_text(p,fmer_delay_division_name(value));p=fmer_ui_text(p," ");}
    else if(id==FMER_DELAY_MODEL)p=fmer_ui_text(p,value?"WARM ":"CLEAN ");
    else if(id==FMER_TRACK_MUTE || id==FMER_LFO_ENABLE || id==FMER_ARP_ENABLE || id==FMER_ARP_LATCH || id==FMER_ARP_TRIPLET || id==FMER_SEQ_CHAIN)
        p=fmer_ui_text(p,value?"ON ":"OFF ");
    else if(id==FMER_SEQ_PITCH && value==FMER_REST) {fmer_ui_text(p,"REST");return;}
    else if(id==FMER_MIDI_CHANNEL && !value) {fmer_ui_text(p,"OMNI");return;}
    if(p!=out) { if(p[-1]==' ')p[-1]=0;return; }
    if(id==FMER_ARP_RATE) p=fmer_ui_text(p,"1/");
    p=fmer_ui_number(p,value);
    if(*unit) {if(!compact)p=fmer_ui_text(p," ");fmer_ui_text(p,unit);}
}

/* The grid uses a bank-sized immutable snapshot, never guessed note data.
 * Keep at least two octaves visible; show the exact pitch window in the title. */
static void fmer_ui_grid_bounds(const fmer_ui_state_t *s,uint32_t bank,uint32_t *low,uint32_t *high)
{
    uint32_t i,minimum=128u,maximum=0u;
    if(s->pattern && s->pattern->revision && s->pattern->length<=64u)
        for(i=bank;i<bank+16u && i<s->pattern->length;i++)if(s->pattern->pitch[i]<128u) {
            uint32_t pitch=s->pattern->pitch[i];
            if(pitch<minimum)minimum=pitch;if(pitch>maximum)maximum=pitch;
        }
    if(minimum==128u){minimum=48;maximum=72;}
    *low=minimum/12u*12u;*high=(maximum+11u)/12u*12u;
    if(*high<*low+24u)*high=*low+24u;
    if(*high>127u){*high=127u;if(*low>*high-24u)*low=*high-24u;}
}

/* One canonical main-owned snapshot is used for all descriptions. Primary
 * values have21px glyphs; only actual contextual controls get numbered rows. */
static void fmer_ui_describe(uint32_t row,const fmer_ui_state_t *s,fmer_ui_row_t *r)
{
    const fmer_controls_t *c=s->controls;const fmer_panel_t *panel=s->panel;
    uint32_t id,engine,family,page,popup,bank,low,high,i; char *p;
    memset(r,0,sizeof *r);r->color=FMER_UI_GREEN;r->scale=2;
    if(!c || !panel) {if(row==0)fmer_ui_text(r->first,"FMER NO CONTROL");return;}
    engine=c->value[FMER_ENGINE];family=panel->family;page=fmer_panel_page(panel,c);
    popup=fmer_panel_popup(panel,fmer_ui.last_service);
    if(family==FMER_PANEL_HOME && panel->scope_only && !s->audio_paused && !s->init_failed) {
        r->bar=2;
        if(c->value[FMER_SEQ_MODE] && row<8u) {
            r->scope_row=(uint8_t)(row%2u);r->maximum=48;
            /* Four full-width part traces followed by the main mix. Reuse the
             * frozen frame and line renderer, without labels or live controls. */
            for(i=0;i<FMER_SCOPE_SAMPLES;i++){
                uint32_t at=i*31u/(FMER_SCOPE_SAMPLES-1u),fraction=i*31u%(FMER_SCOPE_SAMPLES-1u);
                uint32_t a=fmer_ui.part_scope[row/2u][at],b=fmer_ui.part_scope[row/2u][at<31u?at+1u:at];
                r->scope[i]=(uint8_t)((a*(127u-fraction)+b*fraction)*255u/(127u*48u));
            }
        } else {
            r->scope_row=(uint8_t)(c->value[FMER_SEQ_MODE]?row-8u:row);
            r->maximum=c->value[FMER_SEQ_MODE]?48:240;
            memcpy(r->scope,fmer_ui.scope,sizeof r->scope);
        }return;
    }
    if(row==0) {
        p=fmer_ui_text(r->first,"FMER ");p=fmer_ui_number(p,s->build);
        p=fmer_ui_text(p,engine?" VA1 ":" FM0 ");
        fmer_ui_text(p,s->performance.recording?"REC":s->performance.running?"PLAY":"STOP");
        r->bar=6;r->amount=s->build;r->scope[0]=(uint8_t)engine;
        r->scope[1]=(uint8_t)(s->performance.recording?2:s->performance.running?1:0);
        r->scope[2]=(uint8_t)(s->battery_valid && s->battery_percent<=100u?s->battery_percent+1u:0u);
        r->scope[3]=(uint8_t)s->usb_ready;r->scope[4]=(uint8_t)s->usb_audio_active;
        r->scope[5]=panel->midi.value[3];r->scope[6]=(uint8_t)s->beat_on;
        r->scope[7]=(uint8_t)c->value[FMER_SEQ_MODE];r->scope[8]=(uint8_t)s->voice_limit;
        r->color=FMER_UI_MUTED;return;
    }
    if(family==FMER_PANEL_SEQ && page==3u && !s->init_failed && !s->audio_paused && !(s->pattern && s->pattern->count_in_active && row>=2u && row<=5u)) {
        if(row==1)fmer_ui_text(r->first,"PLAY MODE");
        if(row==2){fmer_ui_text(r->first,fmer_panel_mode_name(c));r->scale=3;r->color=FMER_UI_GREEN;}
        if(row==3){if(c->value[FMER_SEQ_MODE]){p=fmer_ui_text(r->first,"4 MONO PARTS / T");fmer_ui_number(p,c->value[FMER_SEQ_TRACK]+1u);}else fmer_ui_text(r->first,c->value[FMER_VOICE_BUDGET]==1u?"ONE SOUND / MONO":"ONE SOUND / CHORDS");}
        if(row==4)fmer_ui_text(r->first,"K1: 1V > 4V > 4T");
        if(row==5){fmer_ui_text(r->first,"4T CHANGE STOPS");r->color=FMER_UI_MUTED;}
        if(row>=6u){
            id=fmer_panel_knob_id(panel,row-6u,c);
            p=fmer_ui_number(r->first,row-5u);p=fmer_ui_text(p," ");p=fmer_ui_text(p,row==6u?"MODE":row==7u?"GLIDE":row==8u?"TIME":"CURVE");p=fmer_ui_text(p," ");
            if(c->value[FMER_SEQ_MODE] && row>=7u){fmer_ui_text(p,"LOCK");r->color=FMER_UI_MUTED;return;}
            if(row==6u)fmer_ui_text(p,fmer_panel_mode_name(c));else fmer_ui_parameter(p,id,c->value[id],1);
            r->highlight=row==6u+panel->focused_knob;
        }return;
    }
    if(!engine && popup && panel->focused_id==134u) {
        if(row==1) {
            p=fmer_ui_text(r->first,"ALG ");p=fmer_ui_number(p,c->value[134]+1u);
            p=fmer_ui_text(p,"/32 RAW ");fmer_ui_number(p,c->value[134]);
            r->color=FMER_UI_PINK;
        } else if(row>=2u && row<=8u) {
            r->bar=7;r->scope_row=(uint8_t)(row-2u);r->amount=c->value[134];
        } else if(row==9) {
            fmer_ui_text(r->first,fmer_algorithm_diagrams[c->value[134]].unsupported_feedback?
                "THIS SOUND / FB N/A":"THIS SOUND / SAVE");r->scale=1;
        }
        return;
    }
    if(family==FMER_PANEL_HOME && c->value[FMER_SEQ_MODE] && s->pattern) {
        if(row<=4u){
            uint32_t pair=(row-1u)/2u,t,k;r->bar=16;r->scope_row=(uint8_t)((row-1u)%2u);
            for(k=0;k<2u;k++){
                t=pair*2u+k;memcpy(r->scope+k*32u,fmer_ui.part_scope[t],32);
                r->scope[64+k]=(uint8_t)(t+1u);r->scope[66+k]=s->pattern->track_mute[t];r->scope[68+k]=s->pattern->track_solo[t];r->scope[70+k]=s->pattern->track_fx[t];
            }return;
        }
        if(row<=6u){r->bar=2;r->scope_row=(uint8_t)(row-5u);r->maximum=48;memcpy(r->scope,fmer_ui.scope,sizeof r->scope);return;}
        if(row==7u){static const char *const names[]={"VOLUME","PATTERN","PATCH","MUTE","SOLO","FX","PLAY"};p=fmer_ui_text(r->first,"MIX ");fmer_ui_text(p,names[panel->home_layer]);r->color=FMER_UI_PINK;return;}
        r->bar=17;r->scope_row=(uint8_t)(row-8u);r->amount=panel->home_layer;
        for(i=0;i<4;i++){r->scope[i*4]=s->pattern->track_level[i];r->scope[i*4+1]=s->pattern->track_mute[i];r->scope[i*4+2]=s->pattern->track_solo[i];r->scope[i*4+3]=s->pattern->track_fx[i];}return;
    }
    /* Count-in uses the same audio-owned beat as the click and PLAY LED.
     * It temporarily replaces only the visual area, leaving the four knobs
     * in their stable positions on every sequencer page. */
    if((family==FMER_PANEL_SEQ || family==FMER_PANEL_ARP) && s->pattern && s->pattern->count_in_active && row>=2u && row<=5u) {
        if(row==2){fmer_ui_text(r->first,s->pattern->count_in?"COUNT IN":"WAIT FOR CLOCK");r->scale=s->pattern->count_in?3:2;}
        if(row==3){if(s->pattern->count_in){p=fmer_ui_text(r->first,"BEAT ");p=fmer_ui_number(p,5u-s->pattern->count_in);fmer_ui_text(p," / 4");}
            else fmer_ui_text(r->first,"REC ARMED");r->scale=3;}
        if(row==4){r->bar=12;r->amount=s->pattern->count_in?5u-s->pattern->count_in:0u;r->maximum=s->beat_on;}
        if(row==5)fmer_ui_text(r->first,c->value[FMER_RECORD_MODE]==2u?"REPLACE ONE PASS":"OVERDUB UNTIL REC");
        r->color=FMER_UI_PINK;return;
    }
    if(family==FMER_PANEL_SEQ && page==4u && c->value[FMER_SEQ_MODE]) {
        static const char *const layers[]={"VOLUME","PATTERN","PATCH","MUTE","SOLO","FX SEND","RUN"};
        if(row==1){p=fmer_ui_text(r->first,"MIX ");fmer_ui_text(p,layers[panel->mixer_layer]);r->color=FMER_UI_PINK;return;}
        if(row==9){fmer_ui_text(r->first,panel->mixer_layer==FMER_MIX_RUN?"LEFT STOP RIGHT BAR":"SEL PLAY: NEXT BAR");r->scale=2;return;}
        if(!s->pattern || !s->pattern->revision)return;
        r->bar=13;r->scope_row=(uint8_t)(row-2u);r->amount=panel->mixer_layer;
        r->maximum=c->value[FMER_SEQ_TRACK];r->scope[36]=(uint8_t)s->performance.running;r->scope[48]=(uint8_t)((fmer_ui.last_service/250u)&1u);
        for(i=0;i<4u;i++){
            uint8_t *v=r->scope+i*8u;
            v[0]=s->pattern->track_level[i];v[1]=s->pattern->track_pattern[i];v[2]=s->pattern->track_queued[i];
            v[3]=s->pattern->track_sound[i];v[4]=s->pattern->track_mute[i];v[5]=s->pattern->track_solo[i];
            v[6]=s->pattern->track_fx[i];v[7]=s->pattern->track_step[i];r->scope[32u+i]=s->pattern->track_length[i];r->scope[40u+i]=s->pattern->track_stopped[i];r->scope[44u+i]=s->pattern->track_launch[i];
        }
        return;
    }
    if(family==FMER_PANEL_SEQ && page==8u && s->pattern) {
        const fmer_song_t *song=&s->pattern->song;uint32_t t=c->value[FMER_SEQ_MODE]?panel->song_track:0u,entry=panel->song_row;
        const fmer_song_row_t *v=&song->rows[t][entry];
        if(row==1){p=fmer_ui_text(r->first,"T");p=fmer_ui_number(p,t+1u);p=fmer_ui_text(p,s->pattern->song_live[t]?" LIVE":" SONG");fmer_ui_text(p,panel->song_layer?" / SETUP":" / EDIT");r->color=FMER_UI_PINK;return;}
        if(row>=2u && row<=5u){
            uint32_t lane=row-2u,origin=0,start=0,j,n=0,play=0;
            if(!c->value[FMER_SEQ_MODE] && lane){if(row==4u)fmer_ui_text(r->first,"ONE SOUND / LANE 1");return;}
            for(j=0;j<entry && j<song->length[t];j++){const fmer_song_row_t *a=&song->rows[t][j];origin+=(a->pattern<16u?s->pattern->pattern_length[a->pattern]:16u)*(a->repeats+1u);}
            origin=origin/128u*128u;r->bar=15;r->amount=lane==t;r->maximum=origin;
            r->scope[96]=(uint8_t)(lane+1u);r->scope[97]=(uint8_t)(song->enabled[lane] && !s->pattern->song_live[lane]);
            for(j=0;j<song->length[lane];j++){
                const fmer_song_row_t *a=&song->rows[lane][j];uint32_t len=a->pattern<16u?s->pattern->pattern_length[a->pattern]:16u,rep;
                if(!len)len=16u;
                if(j==s->pattern->song_row[lane])play=start+len*s->pattern->song_repeat[lane]+s->pattern->track_step[lane];
                for(rep=0;rep<=a->repeats;rep++){
                    uint32_t end=start+len;
                    if(end>origin && start<origin+128u && n<32u){uint32_t lo=start<origin?0u:start-origin,hi=end>origin+128u?128u:end-origin;
                        r->scope[n*3u]=(uint8_t)(lo*208u/128u);r->scope[n*3u+1u]=(uint8_t)((hi*208u/128u)-(lo*208u/128u));
                        r->scope[n*3u+2u]=(uint8_t)(a->pattern|((lane==t && j==entry)?128u:0u));n++;}
                    start=end;
                }
            }
            r->scope[98]=(uint8_t)n;r->scope[99]=(uint8_t)(s->performance.running && !s->pattern->track_stopped[lane] && !s->pattern->song_live[lane] && play>=origin && play<origin+128u);
            r->scope[100]=(uint8_t)((play>=origin?play-origin:0u)*208u/128u);return;
        }
        if(row==6){p=fmer_ui_text(r->first,"1 ENTRY ");p=fmer_ui_number(p,entry+1u);if(entry>=song->length[t])fmer_ui_text(p," NEW");else {p=fmer_ui_text(p," / ");fmer_ui_number(p,song->length[t]);}}
        if(!panel->song_layer){
            if(row==7){p=fmer_ui_text(r->first,"2 PATTERN ");if(v->pattern==16u)fmer_ui_text(p,"REST");else {p=fmer_ui_text(p,"P");fmer_ui_number(p,v->pattern);}}
            if(row==8){p=fmer_ui_text(r->first,"3 TRANSPOSE ");if(v->transpose<0){p=fmer_ui_text(p,"-");fmer_ui_number(p,(uint32_t)-v->transpose);}else {p=fmer_ui_text(p,"+");fmer_ui_number(p,v->transpose);}}
            if(row==9){p=fmer_ui_text(r->first,"4 REPEATS ");fmer_ui_number(p,v->repeats+1u);}
        }else {
            if(row==7)fmer_ui_text(r->first,song->enabled[t]?"2 LANE SONG":"2 LANE LIVE");
            if(row==8)fmer_ui_text(r->first,song->loop[t]?"3 END LOOP":"3 END STOP");
            if(row==9)fmer_ui_text(r->first,"4 -DELETE +INSERT");
        }
        return;
    }
    if(family==FMER_PANEL_GLO && page==FMER_GLO_USB_LINK && row>=2u) {
        static const char *const roles[]={"PC / NORMAL","LINK MASTER","LINK RECEIVER"};
        static const char *const sends[]={"CLOCK","NOTES","CLOCK + NOTES"};
        r->color=FMER_UI_INK;
        if(row==2){fmer_ui_text(r->first,s->usb_link_role==1u?(s->usb_link_state==6u?"LINK CONNECTED":s->usb_link_state==7u?"LINK FAILED":"LINK WAITING"):s->usb_link_role==2u?"RECEIVER READY":"NORMAL PC USB");r->color=FMER_UI_GREEN;}
        if(row==3){p=fmer_ui_text(r->first,"RX ");p=fmer_ui_number(p,s->usb_link_rx);p=fmer_ui_text(p," TX ");fmer_ui_number(p,s->usb_link_tx);}
        if(row==4){if(s->usb_link_error){p=fmer_ui_text(r->first,"LINK ERROR ");fmer_ui_number(p,s->usb_link_error);}else fmer_ui_text(r->first,"BOTH UNITS ON");}
        if(row==5)fmer_ui_text(r->first,"GLO PAGE HOME BACK");
        if(row==6){p=fmer_ui_text(r->first,"1 ");fmer_ui_text(p,roles[panel->usb_role]);}
        if(row==7){if(panel->usb_role==1u){p=fmer_ui_text(r->first,"2 ");fmer_ui_text(p,sends[panel->usb_send]);}else fmer_ui_text(r->first,panel->usb_role==2u?"FOLLOW USB CLOCK":"PC AUDIO + MIDI");}
        if(row==8)fmer_ui_text(r->first,"UNPLUG PC FIRST");
        if(row==9){fmer_ui_text(r->first,"SEL APPLY / RETRY");r->color=FMER_UI_PINK;}
        return;
    }
    if(family==FMER_PANEL_GLO && page==FMER_GLO_HOTKEYS && row>=2u) {
        static const char *const lines[]={"SEL+SEQ  SONG","HOME+SEQ MIXER","SEL+HOME 4T/4V","ENV+HOME GLIDE","LFO+HOME POLY","SEL+PLAY TRACK BAR","SEL+2PLAY ALL BAR","SEL+FX SET DEFAULT"};
        fmer_ui_text(r->first,lines[row-2u]);r->color=FMER_UI_INK;return;
    }
    if(family==FMER_PANEL_SEQ && page==7u && row>=2u) {
        static const char *const actions[]={"COPY","PASTE","CUT","CLEAR","UNDO"};
        uint32_t start=panel->block_start,length=panel->block_count;
        if(row==2){fmer_ui_text(r->first,actions[panel->block_action]);r->scale=3;r->color=FMER_UI_PINK;}
        if(row==3){p=fmer_ui_text(r->first,"STEPS ");p=fmer_ui_number(p,start);p=fmer_ui_text(p," - ");fmer_ui_number(p,start+length-1u);}
        if(row==4){p=fmer_ui_text(r->first,"CLIP ");p=fmer_ui_number(p,s->pattern?s->pattern->clipboard_length:0u);fmer_ui_text(p," STEPS");}
        if(row==5){fmer_ui_text(r->first,s->pattern && s->pattern->edit_result?"CHECK EDIT RANGE":"SEL TO APPLY");r->color=FMER_UI_PINK;}
        if(row==6){p=fmer_ui_text(r->first,"1 FROM ");fmer_ui_number(p,start);}
        if(row==7){p=fmer_ui_text(r->first,"2 COUNT ");fmer_ui_number(p,length);}
        if(row==8){p=fmer_ui_text(r->first,"3 TO ");fmer_ui_number(p,panel->block_destination);}
        if(row==9){p=fmer_ui_text(r->first,"4 ");fmer_ui_text(p,actions[panel->block_action]);}
        return;
    }
    if(family==FMER_PANEL_SEQ && page==6u && row==8u) {
        uint32_t at=c->value[FMER_SEQ_STEP],end=at;
        if(s->pattern){while(at && s->pattern->pitch[at]==FMER_TIE)--at;
            if(s->pattern->pitch[at]<FMER_REST){end=at+1u;while(end<s->pattern->length && s->pattern->pitch[end]==FMER_TIE)++end;}else end=at;}
        p=fmer_ui_text(r->first,"3 HOLD ");p=fmer_ui_number(p,end-at);fmer_ui_text(p," STEPS");return;
    }
    if(family==FMER_PANEL_GLO && page>=FMER_GLO_OUTPUT && page<=FMER_GLO_CLOCK && row>=2u) {
        static const char *const routes[]={"OFF","KEYS","ARP/SEQ","AUTO"};
        static const char *const clocks[]={"OWN BPM","USB IN","TRS IN"};
        uint32_t id=7u,v;r->scale=2;
        if(row==2)fmer_ui_text(r->first,"SEL SAVE SETUP");
        if(row==3)fmer_ui_text(r->first,page==FMER_GLO_OUTPUT?
            (panel->midi.value[7]?"ALL TRACKS: ONE CH":"TRACKS: CH 1 2 3 4"):
            (panel->midi.value[3]?"TEMPO FROM MIDI IN":"TEMPO FROM FMER"));
        if(row==4)fmer_ui_text(r->first,page==FMER_GLO_OUTPUT?
            (panel->midi.value[0]==3?"AUTO KEYS/ARP/SEQ":panel->midi.value[0]==2?"ARP + SEQ NOTES":panel->midi.value[0]==1?"SEND PLAYED KEYS":"MIDI NOTES OFF"):
            (panel->midi.value[5]?"FOLLOW START/STOP":"IGNORE START/STOP"));
        if(row==5) {
            if(s->storage_action==6u)fmer_ui_text(r->first,s->store_busy?"SAVING WAIT":s->storage_result?"SAVE FAILED":"MIDI SETTINGS SAVED");
            else fmer_ui_text(r->first,"GLO PAGE HOME BACK");
        }
    if(row>=6) {
            static const uint8_t ids[2][4]={{0,1,2,7},{3,4,5,6}};
            static const char *const names[]={"SEND","KEY CH","HEAR FMER","TEMPO","SEND CLOCK","MIDI START","SEND KNOBS","CH MODE"};
            id=ids[page-FMER_GLO_OUTPUT][row-6u];
            v=panel->midi.value[id];p=fmer_ui_number(r->first,row-5u);p=fmer_ui_text(p," ");p=fmer_ui_text(p,names[id]);p=fmer_ui_text(p," ");
            if(id==7u)p=fmer_ui_text(p,v?"MERGED":"SPLIT");else if(id==0u)p=fmer_ui_text(p,routes[v]);else if(id==3u)p=fmer_ui_text(p,clocks[v]);
            else if(id!=1u)p=fmer_ui_text(p,v?"ON":"OFF");
            if(id==1u)fmer_ui_number(p,v+1u);
        }
        return;
    }
    if(family==FMER_PANEL_FX && page==3u && row>=1u) {
        if(row==1u){fmer_ui_text(r->first,"SIGNAL CHAIN 4/4");r->color=FMER_UI_INK;return;}
        static const char*const names[]={"FILTER","REVERB","DELAY","DISTORTION","CHORUS","PHASER"};
        uint8_t order[6];fmer_fx_unrank(s->fx_order,order);r->scale=2;
        if(row<8u){uint32_t effect=order[row-2u];p=fmer_ui_number(r->first,row-1u);p=fmer_ui_text(p," > ");fmer_ui_text(p,names[effect]);r->color=effect==panel->fx_selected?FMER_UI_PINK:FMER_UI_INK;r->highlight=effect==panel->fx_selected;}
        else fmer_ui_text(r->first,row==8u?"1 SELECT  2 MOVE":s->storage_action==11u?(s->store_busy?"SAVING DEFAULT":s->storage_result?"SAVE FAILED":"DEFAULT SAVED"):"3 RESET SEL+FX SET");
        return;
    }
        if(family==FMER_PANEL_GLO && page==FMER_GLO_LEGEND && row>=2u) {
        static const char *const lines[]={"EST CHARGE","USB MIDI","USB AUDIO","OWN CLOCK","USB CLOCK","TRS CLOCK","PLAY / STOP","FOUR TRACKS"};
        fmer_ui_text(r->first,lines[row-2u]);r->scale=2;r->color=FMER_UI_INK;
        r->bar=14;r->scope[0]=(uint8_t)(row-2u);return;
    }

    if(row>=6) {
        if(family==FMER_PANEL_PRESETS) {
            if(row==6){p=fmer_ui_text(r->first,"1 BANK ");fmer_ui_text(p,panel->preset_bank==2u?"USER":panel->preset_bank?"VA":"FM");}
            if(row==7){p=fmer_ui_text(r->first,"SELECT MODE ");fmer_ui_text(p,fmer_panel_mode_name(c));r->color=FMER_UI_GREEN;return;}
            if(row==8)fmer_ui_text(r->first,"SAVE TO KEEP EDITS");
            if(row==9)fmer_ui_text(r->first,"HOME: PLAY / EDIT");
            r->color=FMER_UI_MUTED;return;
        }
        if(family==FMER_PANEL_SAVE) {
            if(row==6){p=fmer_ui_text(r->first,"1 SLOT ");p=fmer_ui_number(p,panel->save_slot);if(!panel->save_scope)fmer_ui_text(p,panel->save_bank?" 2 DEFAULT":" 2 USER");}
            if(row==7)fmer_ui_text(r->first,panel->save_action?"SEL LOAD + STOP":s->user_slot_present?"SEL REPLACE + STOP":"SEL SAVE + STOP");
            if(row==8)fmer_ui_text(r->first,panel->save_action?"3 ACTION LOAD":"3 ACTION SAVE");
            if(row==9)fmer_ui_text(r->first,panel->save_scope?"4 SCOPE PROJECT":"4 SCOPE SOUND");
            r->color=FMER_UI_MUTED;return;
        }
        if(family==FMER_PANEL_SEQ && page==2u) {
            if(row==6){p=fmer_ui_text(r->first,"1 PATTERN ");fmer_ui_number(p,panel->chain_cursor);}
            if(row==7)fmer_ui_text(r->first,c->value[FMER_SEQ_CHAIN_MASK]&(1u<<panel->chain_cursor)?"2 INCLUDE ON":"2 INCLUDE OFF");
            if(row==8)fmer_ui_text(r->first,"KEEP ONE PATTERN");
            if(row==9){p=fmer_ui_text(r->first,"MASK ");p=fmer_ui_number(p,c->value[FMER_SEQ_CHAIN_MASK]);fmer_ui_text(p,c->value[FMER_SEQ_CHAIN]?" ON":" OFF");}
            r->color=FMER_UI_INK;return;
        }
        if(family==FMER_PANEL_SEQ && page==4u && !c->value[FMER_SEQ_MODE] && row<9u) {
            static const uint16_t inactive[]={FMER_TRACK_LEVEL,FMER_SEQ_TRACK,FMER_TRACK_MUTE};
            id=inactive[row-6u];p=fmer_ui_number(r->first,row-5u);p=fmer_ui_text(p," ");
            p=fmer_ui_text(p,fmer_panel_short_name(id));p=fmer_ui_text(p," ");
            fmer_ui_parameter(p,id,c->value[id],1);fmer_ui_text(r->first+strlen(r->first)," LOCK");
            r->color=FMER_UI_MUTED;return;
        }
        id=fmer_panel_knob_id(panel,row-6u,c);
        if(id==FMER_PANEL_INVALID)return;
        p=fmer_ui_number(r->first,row-5u);p=fmer_ui_text(p," ");
        if(family==FMER_PANEL_ENV){static const char *const names[]={"ATTACK","DECAY","SUSTAIN","RELEASE"};p=fmer_ui_text(p,names[row-6u]);}
        else p=fmer_ui_text(p,fmer_panel_short_name(id));
        p=fmer_ui_text(p," ");if(id==FMER_SEQ_MODE)fmer_ui_text(p,fmer_panel_mode_name(c));else fmer_ui_parameter(p,id,c->value[id],1);
        r->highlight=row==6u+panel->focused_knob;
        r->color=popup && (row==6u+panel->focused_knob || (id==FMER_CUTOFF && panel->focused_id==FMER_FILTER_TYPE))?FMER_UI_PINK:FMER_UI_INK;
        if(id==FMER_VOICE_BUDGET && (c->value[FMER_SEQ_MODE] || c->value[FMER_GLIDE_MODE])) {fmer_ui_text(r->first+strlen(r->first)," LOCK");r->color=FMER_UI_MUTED;}
        if(family==FMER_PANEL_HOME || family==FMER_PANEL_FX || family==FMER_PANEL_ENV || (family==FMER_PANEL_SEQ && page>=3u) || (family==FMER_PANEL_GLO && page==FMER_GLO_GLIDE)){
            r->bar=10;if(id==FMER_CUTOFF)r->scope[60]=(uint8_t)(1u+c->value[FMER_FILTER_TYPE]);r->maximum=fmer_control_max(id)-fmer_control_min(id);r->amount=c->value[id]-fmer_control_min(id);
            if(id==FMER_CUTOFF || id==FMER_VA_CUTOFF || id==FMER_ATTACK || id==FMER_DECAY || id==FMER_RELEASE || id==FMER_GLIDE_MS){
                uint32_t lo=fmer_ui_log_position(fmer_control_min(id)+1u);
                r->amount=fmer_ui_log_position(c->value[id]+1u)-lo;r->maximum=fmer_ui_log_position(fmer_control_max(id)+1u)-lo;}
        }
        return;
    }
    if(row==1 && (family==FMER_PANEL_ARP || family==FMER_PANEL_FX) && c->value[FMER_SEQ_MODE] && s->pattern){
        uint32_t t=c->value[FMER_SEQ_TRACK],solo=0;for(i=0;i<4;i++)solo|=s->pattern->track_solo[i];
        p=fmer_ui_text(r->first,family==FMER_PANEL_ARP?"ARP ":"FX ");
        if(family==FMER_PANEL_FX){fmer_ui_parameter(p,FMER_FILTER_TYPE,c->value[FMER_FILTER_TYPE],1);p=r->first+strlen(r->first);}
        else p=fmer_ui_number(p,c->value[FMER_ARP_ENABLE]);
        p=fmer_ui_text(p," T");p=fmer_ui_number(p,t+1);
        p=fmer_ui_text(p,s->pattern->track_mute[t] || (solo&&!s->pattern->track_solo[t])?" M":s->pattern->track_solo[t]?" S":"");
        fmer_ui_text(p,s->pattern->track_fx[t]?" FX1":" FX0");r->color=FMER_UI_PINK;return;
    }
    if(row==1) {
        if(family==FMER_PANEL_SEQ) {
            if(page){static const char *const titles[]={"","PATTERNS","CHAIN","MODE","PERFORM","RECORD","ALG MOVE SEL DEL","COPY / EDIT"};
                p=fmer_ui_text(r->first,titles[page]);
                if(page==3u || page==4u)fmer_ui_text(p,c->value[FMER_SEQ_MODE]?" 4TRK":" SINGLE");
                r->color=FMER_UI_INK;return;}
            bank=c->value[FMER_SEQ_STEP]/16u*16u;fmer_ui_grid_bounds(s,bank,&low,&high);
            p=fmer_ui_text(r->first,"P");p=fmer_ui_number(p,c->value[FMER_SEQ_PATTERN]);p=fmer_ui_text(p," ");p=fmer_ui_number(p,bank);p=fmer_ui_text(p,"-");p=fmer_ui_number(p,bank+15u);
            if(panel->fine_adjust)fmer_ui_text(p," FINE");
            else {p=fmer_ui_text(p," P");p=fmer_ui_number(p,low);p=fmer_ui_text(p,"-");fmer_ui_number(p,high);}
            r->color=FMER_UI_INK;return;
        }
        p=fmer_ui_text(r->first,family==FMER_PANEL_GLO?fmer_panel_page_name(panel,c):fmer_panel_family_name(family));
        if(family==FMER_PANEL_HOME) {
            p=fmer_ui_text(r->first,s->patch_name?s->patch_name:"FMER SOUND");
            if(s->sound_dirty)fmer_ui_text(p," +");r->scale=3;
        }
        if(!engine && family==FMER_PANEL_EDIT && page<6u) {
            p=fmer_ui_text(p," OP");p=fmer_ui_number(p,panel->operator_number);
        }
        if(family==FMER_PANEL_FX){
            p=fmer_ui_text(r->first,"FX ");fmer_ui_parameter(p,FMER_FILTER_TYPE,c->value[FMER_FILTER_TYPE],1);
            p=r->first+strlen(r->first);p=fmer_ui_text(p," ");p=fmer_ui_number(p,page+1u);fmer_ui_text(p,"/4");return;
        }
        if(family==FMER_PANEL_LFO) {
            p=fmer_ui_text(r->first,c->value[FMER_LFO_ENABLE]?"LFO ON ":"LFO OFF ");
            p=fmer_ui_number(p,page+1u);p=fmer_ui_text(p,"/");fmer_ui_number(p,fmer_panel_pages(family,engine));
            r->color=c->value[FMER_LFO_ENABLE]?FMER_UI_GREEN:FMER_UI_PINK;return;
        }
        if(family==FMER_PANEL_ARP) {
            p=fmer_ui_text(r->first,c->value[FMER_ARP_ENABLE]?"ARP ON":"ARP OFF");
            p=fmer_ui_text(p," ");p=fmer_ui_number(p,page+1u);fmer_ui_text(p,"/2");
            r->color=c->value[FMER_ARP_ENABLE]?FMER_UI_GREEN:FMER_UI_PINK;return;
        }
        if(fmer_panel_pages(family,engine)>1u) {p=fmer_ui_text(p," ");p=fmer_ui_number(p,page+1u);p=fmer_ui_text(p,"/");fmer_ui_number(p,fmer_panel_pages(family,engine));}
        r->color=FMER_UI_INK;return;
    }
    if(s->init_failed || s->audio_paused) {
        if(row==2) {fmer_ui_text(r->first,s->init_failed?"DSP FAILED":"AUDIO PAUSED");r->color=FMER_UI_PINK;r->scale=3;}
        if(row==3)fmer_ui_text(r->first,"HOLD PLAY TO RESET");
        if(row==5)fmer_ui_text(r->first,"GLO: DIAGNOSTICS");return;
    }
    if(family==FMER_PANEL_PRESETS) {
        if(row==2){fmer_ui_text(r->first,panel->preset_bank==2u && !s->user_slot_present?"EMPTY":s->candidate_name?s->candidate_name:"PRESET");r->scale=3;}
        if(row==3){p=fmer_ui_text(r->first,panel->preset_bank==2u?"USER SLOT ":panel->preset_bank?"VA SLOT ":"FM SLOT ");fmer_ui_number(p,panel->preset_candidate);}
        if(row==4)fmer_ui_text(r->first,"PRESETS: BROWSE");
        if(row==5){fmer_ui_text(r->first,panel->preset_bank==2u && !s->user_slot_present?"EMPTY - SKIPPED":"PLAY KEYS TO HEAR");r->color=FMER_UI_MUTED;}
        return;
    }
    if(family==FMER_PANEL_SEQ) {
        if(page==3u || page==4u) {
            uint32_t track=row-2u;
            if(!c->value[FMER_SEQ_MODE]) {
                if(row==2){fmer_ui_text(r->first,page==4u?"SINGLE: MIXER OFF":"SINGLE: ONE SOUND");r->color=FMER_UI_PINK;}
                if(row==3)fmer_ui_text(r->first,page==4u?"K4 MODE -> 4TRK":"K1 MODE -> 4TRK");
                if(row==4){fmer_ui_text(r->first,"MODE CHANGE STOPS");r->color=FMER_UI_MUTED;}
                if(row==5)fmer_ui_text(r->first,"THEN PRESS PLAY");
                return;
            }
            if(!s->pattern || !s->pattern->revision){if(row==3)fmer_ui_text(r->first,"TRACKS PENDING");return;}
            r->bar=11;r->scope[0]=(uint8_t)track;r->scope[1]=(uint8_t)(track==c->value[FMER_SEQ_TRACK]);
            r->scope[2]=s->pattern->track_pattern[track];r->scope[3]=s->pattern->track_queued[track];
            r->scope[4]=s->pattern->track_step[track];r->scope[5]=s->pattern->track_level[track];
            r->scope[6]=s->pattern->track_mute[track];r->scope[7]=s->pattern->track_sound[track];
            r->scope[8]=(uint8_t)s->performance.running;
            r->amount=page==4u;r->color=r->scope[6]?FMER_UI_MUTED:r->scope[1]?FMER_UI_PINK:FMER_UI_GREEN;
            p=fmer_ui_text(r->first,"T");p=fmer_ui_number(p,track+1u);p=fmer_ui_text(p," ");
            if(page==4u){p=fmer_ui_number(p,r->scope[5]);p=fmer_ui_text(p,"% M");fmer_ui_number(p,r->scope[6]);}
            else {p=fmer_ui_text(p,"P");p=fmer_ui_number(p,r->scope[2]);
                if(r->scope[3]<FMER_PATTERN_BANKS){p=fmer_ui_text(p," Q");p=fmer_ui_number(p,r->scope[3]);}
                p=fmer_ui_text(p,r->scope[7]<64u?" U":" D");p=fmer_ui_number(p,r->scope[7]%64u);
                p=fmer_ui_text(p," S");fmer_ui_number(p,r->scope[4]);}
            return;
        }
        if(page==5u) {
            if(row==2){p=fmer_ui_text(r->first,"TRACK T");fmer_ui_number(p,c->value[FMER_SEQ_TRACK]+1u);}
            if(row==3)fmer_ui_text(r->first,s->performance.recording?"RECORDING":c->value[FMER_RECORD_MODE]?"REC:4 BEAT LEAD-IN":"REC:STEP ENTRY");
            if(row==4)fmer_ui_text(r->first,c->value[FMER_RECORD_MODE]==2u?"REPLACE ONE PASS":c->value[FMER_RECORD_MODE]?"OVERDUB LOOPS":"SEL K2 REST / TIE");
            if(row==5)fmer_ui_text(r->first,c->value[FMER_RECORD_MODE]==2u?"SILENCE IS REST":c->value[FMER_RECORD_MODE]?"REC TO END RECORD":"PLAY RUN SEL PAGE");
            return;
        }
        id=popup?panel->focused_id:fmer_panel_knob_id(panel,panel->focused_knob<4u?panel->focused_knob:0u,c);
        if(id==FMER_PANEL_INVALID)id=fmer_panel_knob_id(panel,0,c);
        if(row==2) {
            if(page==2u && !popup){p=fmer_ui_text(r->first,"P");p=fmer_ui_number(p,panel->chain_cursor);fmer_ui_text(p,c->value[FMER_SEQ_CHAIN_MASK]&(1u<<panel->chain_cursor)?" ON":" OFF");r->scale=3;return;}
            p=r->first;
            if(id!=FMER_VA_WAVE && !(id==FMER_SEQ_PITCH && c->value[id]>=FMER_REST)) {
                if(family==FMER_PANEL_ENV){static const char *const names[]={"ATTACK","DECAY","SUSTAIN","RELEASE"};p=fmer_ui_text(p,names[row-6u]);}
        else p=fmer_ui_text(p,fmer_panel_short_name(id));p=fmer_ui_text(p," ");
            }
            fmer_ui_parameter(p,id,id<FMER_PARAM_COUNT?c->value[id]:0,1);
            r->scale=3;r->color=panel->fine_adjust?FMER_UI_PINK:FMER_UI_GREEN;return;
        }
        if(page && page!=6u) {
            if(row==3u || row==4u){r->bar=4;r->scope_row=(uint8_t)((row-3u)*8u);
                r->scope[0]=(uint8_t)(page==2u?panel->chain_cursor:c->value[FMER_SEQ_PATTERN]);
                r->scope[1]=(uint8_t)(s->performance.running?s->performance.playing_pattern:FMER_PATTERN_BANKS);
                r->scope[2]=(uint8_t)(s->performance.running?s->performance.queued_pattern:FMER_PATTERN_BANKS);
                r->amount=c->value[FMER_SEQ_CHAIN_MASK];r->scope[4]=(uint8_t)c->value[FMER_SEQ_CHAIN];}
            if(row==5){p=fmer_ui_text(r->first,"E");p=fmer_ui_number(p,c->value[FMER_SEQ_PATTERN]);
                if(s->performance.running){p=fmer_ui_text(p," PLAY");p=fmer_ui_number(p,s->performance.playing_pattern);
                    if(s->performance.queued_pattern<FMER_PATTERN_BANKS){p=fmer_ui_text(p," NEXT");fmer_ui_number(p,s->performance.queued_pattern);}}
                else fmer_ui_text(p," STOP");r->color=FMER_UI_MUTED;}
            return;
        }
        if(row>=3 && row<=5) {
            if(!s->pattern || !s->pattern->revision || !s->pattern->length || s->pattern->length>64u) {
                if(row==4)fmer_ui_text(r->first,"PATTERN PENDING");return;
            }
            bank=c->value[FMER_SEQ_STEP]/16u*16u;fmer_ui_grid_bounds(s,bank,&low,&high);
            r->bar=3;r->scope_row=(uint8_t)(row-3u);
            for(i=0;i<16u;i++) {
                r->scope[i]=s->pattern->pitch[bank+i];
                r->scope[FMER_GRID_VELOCITY+i]=s->pattern->velocity[bank+i];
                r->scope[FMER_GRID_GATE+i]=s->pattern->gate[bank+i];
            }
            r->scope[FMER_GRID_SELECTED]=(uint8_t)(c->value[FMER_SEQ_STEP]-bank);
            r->scope[FMER_GRID_PLAYHEAD]=(uint8_t)(s->performance.running && s->performance.playing_pattern==c->value[FMER_SEQ_PATTERN] && s->performance.seq_position>=bank && s->performance.seq_position<bank+16u?s->performance.seq_position-bank:255u);
            r->scope[FMER_GRID_LENGTH]=(uint8_t)s->pattern->length;
            r->scope[FMER_GRID_LOW]=(uint8_t)low;r->scope[FMER_GRID_HIGH]=(uint8_t)high;r->scope[FMER_GRID_BANK]=(uint8_t)bank;return;
        }
    }
    if(!popup && family==FMER_PANEL_SAVE) {
        if(row==2){p=fmer_ui_text(r->first,panel->save_scope?"PROJECT ":panel->save_bank?"DEFAULT ":"USER ");fmer_ui_number(p,panel->save_slot);r->scale=!panel->save_scope && panel->save_bank?2:3;}
        if(row==3)fmer_ui_text(r->first,s->user_slot_present && s->user_slot_name?s->user_slot_name:"EMPTY SLOT");
        if(row==4)fmer_ui_text(r->first,panel->save_scope?"SOUND / SEQ / SONG":"INSTRUMENT ONLY");
        if(row==5){
            if(s->store_busy)fmer_ui_text(r->first,"SAVING WAIT");
            else if(!s->storage_ready)fmer_ui_text(r->first,"STORE NOT READY");
            else if(panel->save_action)fmer_ui_text(r->first,s->user_slot_present?(panel->save_scope?"SEL LOAD PROJECT":"SEL LOAD SOUND"):"EMPTY NO LOAD");
            else if(s->storage_action==(panel->save_scope?8u:1u) && s->storage_slot==(panel->save_scope?panel->save_slot:panel->save_slot+64u*panel->save_bank)) {
                if(!s->storage_result){fmer_ui_text(r->first,s->live_generation!=s->saved_generation?"SAVED THEN EDITED":"SAVED ON DEVICE");r->color=FMER_UI_GREEN;}
                else {p=fmer_ui_text(r->first,s->storage_result==5u?"STORE FULL ":s->storage_result==4u?"VERIFY FAILED ":s->storage_result==10u?"STORE BUSY ":s->storage_result==11u?"EDIT RETRY ":s->storage_result==12u?"BAD FORMAT ":"SAVE ERROR ");fmer_ui_number(p,s->storage_result);r->color=FMER_UI_PINK;}
            } else {fmer_ui_text(r->first,"SEL CONFIRM SAVE");r->color=FMER_UI_MUTED;}
        }return;
    }
    if(!popup && family==FMER_PANEL_GLO && page==FMER_GLO_RESET) {
        uint32_t action=panel->reset_choice==4u?12u:panel->reset_choice==3u?10u:panel->reset_choice+3u;
        if(row==2)fmer_ui_text(r->first,panel->reset_choice==0?"RESET TO FMER":panel->reset_choice==1?"RESET USER BANK":panel->reset_choice==2?"CLEAR USER BANK":panel->reset_choice==3?"CLEAR PROJECTS":"ORIGINAL FX ROUTE");
        if(row==3)fmer_ui_text(r->first,panel->reset_choice==0?"DEFAULT":panel->reset_choice==1?"64 ORIGINAL COPIES":panel->reset_choice==2?"64 EMPTY SLOTS":panel->reset_choice==3?"16 EMPTY PROJECTS":"RESET FX DEFAULT");
        if(row==4)fmer_ui_text(r->first,panel->reset_choice>=3?"SOUNDS UNCHANGED":panel->reset_choice==0?"USER UNCHANGED":"DEFAULT UNCHANGED");
        if(row==5)fmer_ui_text(r->first,s->store_busy?(s->storage_action==action?"RESETTING WAIT":"STORE BUSY WAIT"):panel->reset_armed?"SEL CONFIRM RESET":s->storage_action==action?(s->storage_result?"RESET FAILED":"RESET COMPLETE"):"1 ACTION  SEL ARM");
        return;
    }
    if(!popup && family==FMER_PANEL_GLO && page==FMER_GLO_INFO) {
        if(row==2){p=fmer_ui_text(r->first,"MAX US ");fmer_ui_number(p,fmer_ui.render_us);}
        if(row==3){p=fmer_ui_text(r->first,"OVERRUN ");fmer_ui_number(p,fmer_ui.overruns);}
        if(row==4){p=fmer_ui_text(r->first,"EST BATTERY ");if(s->battery_valid && s->battery_percent<=100u){p=fmer_ui_number(p,s->battery_percent);fmer_ui_text(p,"%");}else fmer_ui_text(p,"--%");}
        if(row==5){
            p=fmer_ui_text(r->first,"ADC ");
            p=s->battery_valid?fmer_ui_number(p,s->battery_raw):fmer_ui_text(p,"--");
            p=fmer_ui_text(p," FW ");fmer_ui_number(p,s->build);
        }return;
    }
    if(family==FMER_PANEL_GLO && page==FMER_GLO_GLIDE) {
        if(row==2)fmer_ui_text(r->first,"MONO GLIDE");
        if(row==3)fmer_ui_text(r->first,c->value[FMER_SEQ_MODE]?"4 MONO PARTS":c->value[FMER_GLIDE_MODE]?"GLIDE: AUTO MONO":"GLIDE OFF: POLY OK");
        if(row==4)fmer_ui_text(r->first,"LEGATO:OVERLAP");
        if(row==5)fmer_ui_text(r->first,"ALWAYS:ALL NOTES");return;
    }
    if(family==FMER_PANEL_HOME && !popup) {
        if(row>=2 && row<=5) {r->bar=2;r->scope_row=(uint8_t)(row-2u);r->maximum=96;memcpy(r->scope,fmer_ui.scope,sizeof r->scope);}
        return;
    }
    if(family==FMER_PANEL_FX) {
        if(row>=2u && row<=4u){r->bar=2;r->scope_row=(uint8_t)(row-2u);r->maximum=72;memcpy(r->scope,fmer_ui.scope,sizeof r->scope);}
        if(row==5u){
            if(page==1u){uint32_t ph=panel->focused_id==FMER_PHASER,profile=(panel->modulation>>(ph*8u))&3u;
                p=fmer_ui_text(r->first,ph?"PH ":"CH ");p=fmer_ui_text(p,fmer_modulation_name(ph,profile));p=fmer_ui_text(p," ");fmer_ui_number(p,profile+1u);}
            else if(page==2u){uint32_t ms=c->value[FMER_DELAY_SYNC] && s->pattern?s->pattern->delay_ms:c->value[FMER_DELAY_MS];p=fmer_ui_text(r->first,"ALG SYNC ");p=fmer_ui_number(p,ms);p=fmer_ui_text(p,"MS");if(ms>=1000u)fmer_ui_text(p," MAX");}
            else{r->bar=8;memcpy(r->scope,fmer_ui.fx_activity,6);}
        }return;
    }
    if(family==FMER_PANEL_ENV) {
        if(row>=2u && row<=4u){
            uint32_t k,total=0,widths[4],levels[5];
            r->bar=9;r->scope_row=(uint8_t)(row-2u);
            if(engine){
                widths[0]=fmer_ui_log_position(c->value[FMER_ATTACK]+1u)/128u+8u;
                widths[1]=fmer_ui_log_position(c->value[FMER_DECAY]+1u)/128u+8u;
                widths[2]=36u;widths[3]=fmer_ui_log_position(c->value[FMER_RELEASE]+1u)/128u+8u;
                levels[0]=0;levels[1]=100;levels[2]=levels[3]=c->value[FMER_SUSTAIN];levels[4]=0;
            }else{
                uint32_t base=fmer_panel_knob_id(panel,0,c)/21u*21u;
                for(k=0;k<4;k++){uint32_t rate=100u-c->value[base+k];widths[k]=8u+rate*rate/96u;}
                levels[0]=c->value[base+7u];for(k=0;k<4;k++)levels[k+1u]=c->value[base+4u+k]*100u/99u;
            }
            for(k=0;k<4;k++)total+=widths[k];
            r->scope[0]=8;for(k=0;k<4;k++)r->scope[k+1u]=(uint8_t)(r->scope[k]+widths[k]*220u/total);
            for(k=0;k<5;k++)r->scope[5u+k]=(uint8_t)(64u-levels[k]*56u/100u);
        }
        if(row==5u){fmer_ui_text(r->first,engine?"TIME MS / LEVEL %":"ALL OUT / 99=FAST");}return;
    }
    id=popup?panel->focused_id:fmer_panel_knob_id(panel,panel->focused_knob<4u?panel->focused_knob:0u,c);
    if(id==FMER_PANEL_INVALID)id=fmer_panel_knob_id(panel,0,c);
    if(row==2){fmer_ui_text(r->first,fmer_panel_name(id));r->scale=3;r->color=FMER_UI_INK;}
    if(row==3){if(id==FMER_SEQ_MODE)fmer_ui_text(r->first,fmer_panel_mode_name(c));else fmer_ui_parameter(r->first,id,id<FMER_PARAM_COUNT?c->value[id]:0u,0);r->scale=3;}
    if(row==4 && id!=FMER_PANEL_INVALID){
        r->bar=1;if(id==FMER_CUTOFF)r->scope[60]=(uint8_t)(1u+c->value[FMER_FILTER_TYPE]);
        if(id==FMER_CUTOFF || id==FMER_VA_CUTOFF) {
            uint32_t minimum=fmer_ui_log_position(fmer_control_min(id));
            r->amount=fmer_ui_log_position(c->value[id])-minimum;
            r->maximum=fmer_ui_log_position(fmer_control_max(id))-minimum;
        } else {r->amount=c->value[id]-fmer_control_min(id);r->maximum=fmer_control_max(id)-fmer_control_min(id);}
    }
    if(row==5) {
        if(family==FMER_PANEL_GLO && page==FMER_GLO_VOICE)fmer_ui_text(r->first,c->value[FMER_SEQ_MODE]?"1 VOICE PER TRACK":"SINGLE SYNTH MODE");
        else if(fmer_panel_stored_only(id))fmer_ui_text(r->first,"STORED ONLY NO DSP");
        else if(id==141u)fmer_ui_text(r->first,"PER NOTE LFO");
        else if(panel->fine_adjust)fmer_ui_text(r->first,
            id==FMER_CUTOFF || id==FMER_VA_CUTOFF?"FINE 1/8 SEMITONE":
            id==FMER_ATTACK || id==FMER_DECAY || id==FMER_RELEASE || id==FMER_DELAY_MS || id==FMER_LFO_RATE?"FINE PROPORTIONAL":"SEL FINE 1 UNIT");
        else if(id<145u || id==FMER_VA_WAVE || id==FMER_VA_CUTOFF || id==FMER_RESONANCE ||
                (id>=FMER_ATTACK && id<=FMER_RELEASE) || id==FMER_LFO_RATE || id==FMER_LFO_DEPTH)
            fmer_ui_text(r->first,"NEXT NOTE SEL:FINE");
        else if(family==FMER_PANEL_SEQ && page==3u){p=fmer_ui_text(r->first,"ALG TRACK ");fmer_ui_number(p,c->value[FMER_SEQ_TRACK]+1u);}
        else if(family==FMER_PANEL_ARP){
            if(c->value[FMER_ARP_ENABLE] && c->value[FMER_ARP_ORDER]==6u &&
               s->performance.arp_held*c->value[FMER_ARP_OCTAVES]>s->voice_limit) {
                p=fmer_ui_text(r->first,"MAX ");p=fmer_ui_number(p,s->voice_limit);fmer_ui_text(p," VOICES");
            } else fmer_ui_text(r->first,c->value[FMER_ARP_ENABLE]?s->performance.arp_held?"ARP TO STOP":"ON - HOLD KEYS":"PRESS ARP FOR ON");
        }
        else if(family==FMER_PANEL_FX) {r->bar=8;memcpy(r->scope,fmer_ui.fx_activity,6);}
        else if(family==FMER_PANEL_LFO)fmer_ui_text(r->first,c->value[FMER_LFO_ENABLE]?"LFO ON PRESS OFF":"LFO OFF PRESS ON");
        else if(family==FMER_PANEL_SEQ)fmer_ui_text(r->first,"PLAY RUN HOLD STOP");
        else if(popup)fmer_ui_text(r->first,"HOLD SEL: FINE");
        else if(family==FMER_PANEL_HOME)fmer_ui_text(r->first,"PLAY RUN HOLD STOP");
        else if(!engine && (family==FMER_PANEL_EDIT || (family==FMER_PANEL_ENV && page<2u)))fmer_ui_text(r->first,"SELECT OP SEL PAGE");
        else fmer_ui_text(r->first,family==FMER_PANEL_GLO?"GLO PAGE HOME BACK":"SEL PAGE HOME BACK");
        r->color=fmer_panel_stored_only(id)?FMER_UI_PINK:FMER_UI_MUTED;
    }
}

static uint16_t fmer_ui_wire(uint16_t c) { return (uint16_t)((c>>8)|(c<<8)); }
static void fmer_ui_rect(uint32_t x,uint32_t y,uint32_t w,uint32_t h,uint16_t color)
{
    uint32_t a,b; const uint16_t c=fmer_ui_wire(color);
    if(x>=FMER_UI_WIDTH || y>=FMER_UI_STRIP) return;
    if(w>FMER_UI_WIDTH-x) w=FMER_UI_WIDTH-x;
    if(h>FMER_UI_STRIP-y) h=FMER_UI_STRIP-y;
    for(b=y;b<y+h;b++) for(a=x;a<x+w;a++) fmer_ui.pixels[b*FMER_UI_WIDTH+a]=c;
}
static void fmer_ui_letters(uint32_t y,const char *text,uint16_t color,uint32_t scale,uint32_t label_chars)
{
    uint32_t x=8,a,b,index=0; int glyph;
    for(;*text && x+5u*scale<=232u;text++,x+=6u*scale,index++) {
        glyph=*text>='0' && *text<='9'?*text-'0':*text>='A' && *text<='Z'?*text-'A'+10:*text>='a' && *text<='z'?*text-'a'+10:
            *text=='-'?36:*text=='+'?37:*text=='/'?38:*text==':'?39:*text=='%'?40:*text=='>'?41:-1;
        if(glyph<0) continue;
        for(a=0;a<5;a++) for(b=0;b<7;b++) if(fmer_ui_glyphs[glyph][a]&(1u<<b))
            fmer_ui_rect(x+a*scale,y+b*scale,scale,scale,index<label_chars?FMER_UI_INK:color);
    }
}
static void fmer_ui_grid_rect(uint32_t row,uint32_t x,uint32_t y,uint32_t w,uint32_t h,uint16_t color)
{
    uint32_t begin=row*24u,end=begin+24u,bottom=y+h;
    if(y>=end || bottom<=begin)return;
    if(y<begin)y=begin;if(bottom>end)bottom=end;
    fmer_ui_rect(x,y-begin,w,bottom-y,color);
}
static void fmer_ui_grid_text(uint32_t row,uint32_t x,uint32_t y,const char *text,uint16_t color,uint32_t scale) {
    uint32_t a,b;int glyph;
    for(;*text && x+5u*scale<240u;++text,x+=6u*scale){
        glyph=*text>='0' && *text<='9'?*text-'0':*text>='A' && *text<='Z'?*text-'A'+10:
            *text=='-'?36:*text=='+'?37:*text=='/'?38:*text==':'?39:*text=='%'?40:*text=='>'?41:-1;
        if(glyph<0)continue;
        for(a=0;a<5u;++a)for(b=0;b<7u;++b)if(fmer_ui_glyphs[glyph][a]&(1u<<b))
            fmer_ui_grid_rect(row,x+a*scale,y+b*scale,scale,scale,color);
    }
}
/* Original beveled segment lettering: only the brand/accent uses it;
 * parameter text keeps the tested larger readable alphabet. */
static void fmer_ui_segment(uint32_t x,uint32_t y,uint32_t w,uint32_t h,uint16_t color) {
    fmer_ui_rect(x+1,y,w>2?w-2:w,h,color);
    if(h>2)fmer_ui_rect(x,y+1,w,h-2,color);
}
static void fmer_ui_brand(void) {
    uint32_t n,x,y;const uint16_t color=FMER_UI_GREEN;
    for(n=0;n<4;++n) {
        x=8+n*18;fmer_ui_segment(x,3,3,18,color);
        if(n!=1) {fmer_ui_segment(x,3,15,3,color);fmer_ui_segment(x,10,13,3,color);}
        if(n==2)fmer_ui_segment(x,18,15,3,color);
        if(n==1) {
            fmer_ui_segment(x+13,3,3,18,color);
            for(y=0;y<7;++y){fmer_ui_rect(x+3+y/2,4+y,2,2,color);fmer_ui_rect(x+11-y/2,4+y,2,2,color);}
        }
        if(n==3){fmer_ui_segment(x+12,4,3,8,color);for(y=0;y<9;++y)fmer_ui_rect(x+6+y,12+y,3,1,color);}
    }
}
static void fmer_ui_line(uint32_t row,int x,int y,int end_x,int end_y,uint16_t color) {
    int dx=end_x>x?end_x-x:x-end_x,sx=x<end_x?1:-1;
    int dy=end_y>y?y-end_y:end_y-y,sy=y<end_y?1:-1,error=dx+dy,e2;
    for(;;) {fmer_ui_grid_rect(row,(uint32_t)x,(uint32_t)y,1,1,color);if(x==end_x&&y==end_y)break;
        e2=2*error;if(e2>=dy){error+=dy;x+=sx;}if(e2<=dx){error+=dx;y+=sy;}}
}
static void fmer_ui_algorithm(uint32_t row,uint32_t algorithm) {
    const fmer_algorithm_diagram_t *d=&fmer_algorithm_diagrams[algorithm<32?algorithm:0];
    uint32_t i,j,a,b;int x,y;
    for(i=0;i<6;++i)for(j=0;j<6;++j)if(d->incoming[i]&(1u<<j)) {
        fmer_ui_line(row,d->x[j],d->y[j]+9,d->x[i],d->y[i]-9,FMER_UI_MUTED);
        fmer_ui_line(row,d->x[i]-2,d->y[i]-12,d->x[i],d->y[i]-9,FMER_UI_MUTED);
        fmer_ui_line(row,d->x[i]+2,d->y[i]-12,d->x[i],d->y[i]-9,FMER_UI_MUTED);
    }
    fmer_ui_grid_rect(row,10,160,220,1,FMER_UI_GREEN);
    for(i=0;i<6;++i) {
        uint16_t color=(d->carriers&(1u<<i))?FMER_UI_GREEN:FMER_UI_PURPLE;
        x=d->x[i];y=d->y[i];
        if(d->carriers&(1u<<i))fmer_ui_line(row,x,y+9,x,160,FMER_UI_GREEN);
        if(d->feedback&(1u<<i)) {
            fmer_ui_line(row,x+8,y+4,x+13,y+4,FMER_UI_PINK);
            fmer_ui_line(row,x+13,y+4,x+13,y-12,FMER_UI_PINK);
            fmer_ui_line(row,x+13,y-12,x,y-12,FMER_UI_PINK);
            fmer_ui_line(row,x,y-12,x,y-9,FMER_UI_PINK);
        }
        fmer_ui_grid_rect(row,x-8,y-9,17,18,color);
        fmer_ui_grid_rect(row,x-7,y-8,15,16,FMER_UI_BG);
        for(a=0;a<5;++a)for(b=0;b<7;++b)if(fmer_ui_glyphs[6-i][a]&(1u<<b))
            fmer_ui_grid_rect(row,x-5+a*2,y-7+b*2,2,2,color);
    }
}
/* Boot only, before audio/USB construction. Reuse the existing DMA strip.
 * Input/audio become live during the brief splash hold in service(), not a delay. */
static void fmer_ui_show_splash(void) {
    uint32_t row,i,at;uint16_t color;
    for(row=0;row<FMER_UI_ROWS;++row) {
        FMER_UI_SYNC();
        for(i=0;i<FMER_UI_WIDTH*FMER_UI_STRIP;++i) {
            at=row*FMER_UI_WIDTH*FMER_UI_STRIP+i;
            color=fmer_splash_palette[(fmer_splash_pixels[at/4]>>(6u-2u*(at%4u)))&3u];
            fmer_ui.pixels[i]=fmer_ui_wire(color);
        }
        FMER_UI_BLIT(0,row*FMER_UI_STRIP,FMER_UI_WIDTH,FMER_UI_STRIP,fmer_ui.pixels);
    }
    FMER_UI_SYNC();fmer_ui.splash=1;
}

static void fmer_ui_usb_icon(uint32_t x,uint32_t audio) {
    fmer_ui_rect(x+4,6,2,11,FMER_UI_INK);fmer_ui_rect(x,7,10,2,FMER_UI_INK);
    fmer_ui_rect(x,6,2,5,FMER_UI_INK);fmer_ui_rect(x+8,6,2,5,FMER_UI_INK);
    if(audio)fmer_ui_rect(x,18,10,2,FMER_UI_GREEN);
}
static void fmer_ui_clock_icon(uint32_t x,uint32_t source,uint32_t beat) {
    fmer_ui_rect(x,6,10,12,beat?(source?FMER_UI_PINK:FMER_UI_GREEN):FMER_UI_PANEL);
    fmer_ui_grid_text(0,x+2,8,source==2u?"T":source?"U":"I",FMER_UI_INK,1);
}
static void fmer_ui_play_icon(uint32_t x,uint32_t running) {
    uint32_t i;if(running==1u)for(i=0;i<9u;i++)fmer_ui_rect(x+i,6+i/2,1,12-i,FMER_UI_GREEN);
    else fmer_ui_rect(x,7,9,9,running==2u?FMER_UI_PINK:FMER_UI_INK);
}
static void fmer_ui_battery_icon(uint32_t x,const char *text,uint16_t color) {
    uint32_t width=(uint32_t)strlen(text)*12u-2u+8u;
    fmer_ui_rect(x,2,width,20,color);fmer_ui_rect(x+1,3,width-2,18,FMER_UI_BG);
    fmer_ui_rect(x+width,9,3,6,color);fmer_ui_grid_text(0,x+4,5,text,color,2);
}
static void fmer_ui_slider(const fmer_ui_row_t *r,uint32_t y,uint32_t height,uint32_t thumb_y,uint32_t thumb_h)
{
 uint32_t fill=r->maximum?(r->amount>r->maximum?224u:224u*r->amount/r->maximum):0,lo=0,hi=fill;
 uint16_t color=r->color==FMER_UI_PINK?FMER_UI_PINK:FMER_UI_GREEN;
 fmer_ui_rect(8,y,224,height,FMER_UI_PANEL);
 if(r->scope[60]==2u){lo=fill;hi=224;}
 else if(r->scope[60]==3u){lo=fill>18u?fill-18u:0u;hi=fill+18u<224u?fill+18u:224u;}
 if(hi>lo)fmer_ui_rect(8+lo,y,hi-lo,height,color);
 fmer_ui_rect(8+(fill>220u?220u:fill),thumb_y,4,thumb_h,FMER_UI_INK);
}
static void fmer_ui_transport_icon(uint32_t row,uint32_t x,uint32_t y,uint32_t kind,uint16_t color)
{
 uint32_t i;
 if(kind==0u){fmer_ui_grid_rect(row,x,y,12,12,color);return;}
 if(kind==1u){for(i=0;i<12;i++)fmer_ui_grid_rect(row,x+i,y+i/2,1,12-i,color);return;}
 fmer_ui_grid_rect(row,x+3,y,10,2,color);fmer_ui_grid_rect(row,x+12,y+2,2,9,color);
 fmer_ui_grid_rect(row,x+2,y+11,11,2,color);fmer_ui_grid_rect(row,x,y+4,2,7,color);
 for(i=0;i<5;i++)fmer_ui_grid_rect(row,x+i,y+4-i,1,1+2*i,color);
}
static void fmer_ui_render(const fmer_ui_row_t *r)
{
    uint32_t i,fill; const uint16_t background=fmer_ui_wire(FMER_UI_BG);
    for(i=0;i<FMER_UI_WIDTH*FMER_UI_STRIP;i++) fmer_ui.pixels[i]=background;
    if(r->highlight){fmer_ui_rect(6,0,228,24,FMER_UI_PANEL);}
    if(r->bar==6) {
        char label[12],battery[8];uint32_t x,left,battery_x;
        if(r->scope[2]){char*p=fmer_ui_number(battery,r->scope[2]-1u);fmer_ui_text(p,"%");}
        else fmer_ui_text(battery,"--%");
        battery_x=234u-((uint32_t)strlen(battery)*12u-2u+8u);
        left=battery_x-93u; /* Right aligned group,4px gaps; at least8px after brand. */
        fmer_ui_brand();
        fmer_ui_grid_text(0,left,5,r->scope[0]?"VA":"FM",FMER_UI_INK,2);
        if(r->scope[7])fmer_ui_text(label,"4T");
        else {char*p=fmer_ui_number(label,r->scope[8]);fmer_ui_text(p,"V");}
        fmer_ui_grid_text(0,left+26,5,label,FMER_UI_GREEN,2);
        fmer_ui_play_icon(left+52,r->scope[1]);
        if(r->scope[3])fmer_ui_usb_icon(left+65,r->scope[4]);
        fmer_ui_clock_icon(left+79,r->scope[5],r->scope[6]);
        /* USB enumeration is observable; charging current is not. Pink wins
         * below10% even while attached, and no estimate is invented. */
        fmer_ui_battery_icon(battery_x,battery,r->scope[2] && r->scope[2]<=10u?FMER_UI_PINK:r->scope[3]?FMER_UI_GREEN:FMER_UI_INK);
        fmer_ui_rect(8,23,224,1,FMER_UI_PANEL);
    } else if(r->bar==14) {
        uint32_t kind=r->scope[0];
        if(kind==0)fmer_ui_battery_icon(8,"65%",FMER_UI_INK);
        else if(kind<3u)fmer_ui_usb_icon(26,kind==2u);
        else if(kind<6u)fmer_ui_clock_icon(26,kind-3u,1);
        else if(kind==6u){fmer_ui_play_icon(16,1);fmer_ui_play_icon(38,0);}
        else fmer_ui_grid_text(0,20,5,"4T",FMER_UI_GREEN,2);
        fmer_ui_grid_text(0,76,5,r->first,FMER_UI_INK,2);
    } else if(r->bar==7) {
        fmer_ui_algorithm(r->scope_row,r->amount);
    } else if(r->bar==2) {
        /* Three strips form one72px oscilloscope. Coordinates are derived
         * only from actual post-mix PCM with the explicitly labeled visual
         * AUTO gain. This display gain never changes samples or DSP state. */
        int x,y,x1,y1,dx,dy,step,error,e2;uint32_t sample;
        uint32_t height=r->maximum?r->maximum:72u;
        for(i=8;i<232;i+=8) if(r->scope_row==height/48u)fmer_ui_rect(i,(height/2u)%24u,2,1,FMER_UI_PANEL);
        for(sample=1;sample<FMER_SCOPE_SAMPLES;sample++) {
            x=8+(int)((sample-1u)*223u/(FMER_SCOPE_SAMPLES-1u));
            x1=8+(int)(sample*223u/(FMER_SCOPE_SAMPLES-1u));
            y=(int)(r->scope[sample-1u]*(height-1u)/255u);y1=(int)(r->scope[sample]*(height-1u)/255u);
            dx=x1-x;dy=y1>y?y1-y:y-y1;step=y<y1?1:-1;error=dx-dy;
            for(;;) {
                if(y>=(int)r->scope_row*24 && y<(int)(r->scope_row+1u)*24)
                    fmer_ui_rect((uint32_t)x,(uint32_t)(y-(int)r->scope_row*24),1,1,FMER_UI_GREEN);
                if(x==x1 && y==y1)break;
                e2=2*error;if(e2> -dy){error-=dy;x++;}if(e2<dx){error+=dx;y+=step;}
            }
        }
        if(r->first[0]){fmer_ui_rect(8,16,224,8,FMER_UI_BG);fmer_ui_letters(16,r->first,FMER_UI_MUTED,1,0);}
    } else if(r->bar==16) {
        uint32_t k,i,row=r->scope_row;char text[8],*p;
        for(k=0;k<2;k++){
            uint32_t x=6+k*120;uint16_t color=r->scope[66+k]?FMER_UI_MUTED:FMER_UI_GREEN;
            p=fmer_ui_text(text,"T");fmer_ui_number(p,r->scope[64+k]);fmer_ui_grid_text(row,x,0,text,FMER_UI_INK,1);
            if(r->scope[66+k])fmer_ui_grid_text(row,x+24,0,"M",FMER_UI_PINK,1);
            if(r->scope[68+k])fmer_ui_grid_text(row,x+36,0,"S",FMER_UI_PINK,1);
            if(r->scope[70+k])fmer_ui_grid_text(row,x+48,0,"FX",FMER_UI_GREEN,1);
            fmer_ui_grid_rect(row,x,46,108,1,FMER_UI_PANEL);
            for(i=1;i<32;i++)fmer_ui_line(row,(int)(x+(i-1)*106/31),r->scope[k*32+i-1],(int)(x+i*106/31),r->scope[k*32+i],color);
        }
    } else if(r->bar==17) {
        uint32_t t;char text[8];
        for(t=0;t<4;t++){
            const uint8_t *v=r->scope+t*4;uint32_t x=8+t*57,selected=r->amount==FMER_MIX_LEVEL?v[0]:r->amount==FMER_MIX_MUTE?v[1]:r->amount==FMER_MIX_SOLO?v[2]:v[3];
            if(r->amount==FMER_MIX_LEVEL)fmer_ui_number(text,selected);else fmer_ui_text(text,selected?"ON":"OFF");
            fmer_ui_grid_text(r->scope_row,x+2,4,text,selected?FMER_UI_INK:FMER_UI_MUTED,2);
            fmer_ui_grid_rect(r->scope_row,x,28,47,8,FMER_UI_PANEL);
            if(r->amount==FMER_MIX_LEVEL){if(selected)fmer_ui_grid_rect(r->scope_row,x,28,47*selected/100u,8,FMER_UI_GREEN);}
            else if(selected)fmer_ui_grid_rect(r->scope_row,x,28,47,8,FMER_UI_PINK);
        }
    } else if(r->bar==15) {
        uint32_t i;char label[8],*p=fmer_ui_text(label,"T");fmer_ui_number(p,r->scope[96]);
        fmer_ui_grid_text(0,2,1,label,r->amount?FMER_UI_PINK:FMER_UI_INK,1);
        fmer_ui_rect(2,14,12,3,r->scope[97]?FMER_UI_GREEN:FMER_UI_MUTED);
        for(i=0;i<r->scope[98];i++){
            uint32_t x=24u+r->scope[3u*i],width=r->scope[3u*i+1u],pat=r->scope[3u*i+2u]&31u;
            uint16_t color=(r->scope[3u*i+2u]&128u)?FMER_UI_PINK:FMER_UI_GREEN;
            if(width>1u)width--;if(!width)width=1;
            fmer_ui_rect(x,2,width,19,FMER_UI_PANEL);fmer_ui_rect(x,2,width,2,color);fmer_ui_rect(x,19,width,2,color);
            fmer_ui_rect(x,2,1,19,color);fmer_ui_rect(x+width-1,2,1,19,color);
            if(width>=19u){if(pat==16u)fmer_ui_text(label,"--");else {p=fmer_ui_text(label,"P");fmer_ui_number(p,pat);}fmer_ui_grid_text(0,x+2,7,label,FMER_UI_INK,1);}
        }
        if(r->scope[99])fmer_ui_rect(24+r->scope[100],0,2,24,FMER_UI_INK);
    } else if(r->bar==13) {
        uint32_t t,solo=0;for(t=0;t<4u;t++)solo|=r->scope[t*8u+5u];
        for(t=0;t<4u;t++){
            const uint8_t *v=r->scope+t*8u;uint32_t x=8u+t*57u,row=r->scope_row;
            uint16_t color=v[4] || (solo && !v[5])?FMER_UI_MUTED:FMER_UI_GREEN;
            char label[16],*p;
            {uint32_t sy=21,sh=20,sx=x,sw=49;
             if(r->amount==FMER_MIX_PATTERN)sy=41;
             else if(r->amount==FMER_MIX_RUN){sy=59;sh=19;}
             else if(r->amount==FMER_MIX_LEVEL){sy=80;sh=39;}
             else if(r->amount>=FMER_MIX_MUTE && r->amount<=FMER_MIX_FX){sy=121;sh=22;sw=16;sx+=r->amount==FMER_MIX_MUTE?0:r->amount==FMER_MIX_SOLO?17:34;}
             fmer_ui_grid_rect(row,sx,sy,sw,sh,FMER_UI_PANEL);
             fmer_ui_grid_rect(row,sx,sy,sw,2,FMER_UI_PINK);fmer_ui_grid_rect(row,sx,sy+sh-2,sw,2,FMER_UI_PINK);
             fmer_ui_grid_rect(row,sx,sy,1,sh,FMER_UI_PINK);fmer_ui_grid_rect(row,sx+sw-1,sy,1,sh,FMER_UI_PINK);
             if(t==r->maximum){fmer_ui_grid_rect(row,x,0,49,18,FMER_UI_PANEL);fmer_ui_grid_rect(row,x,17,49,2,FMER_UI_PINK);}}
            fmer_ui_grid_rect(row,x+52,0,1,166,FMER_UI_PANEL);
            p=fmer_ui_text(label,"T");fmer_ui_number(p,t+1u);
            fmer_ui_grid_text(row,x,1,label,t==r->maximum?FMER_UI_PINK:FMER_UI_INK,2);
            p=fmer_ui_text(label,v[3]<64u?"U":"D");fmer_ui_number(p,v[3]%64u);
            fmer_ui_grid_text(row,x,23,label,r->amount==FMER_MIX_SOUND?FMER_UI_PINK:color,2);
            p=fmer_ui_text(label,"P");fmer_ui_number(p,v[1]);
            fmer_ui_grid_text(row,x,43,label,r->amount==FMER_MIX_PATTERN?FMER_UI_PINK:color,2);
            {uint32_t pending=r->scope[44u+t] || v[2]<16u;
             uint32_t icon=r->scope[44u+t]?2u:r->scope[36]&&!r->scope[40u+t]?1u:0u;
             if(!pending || r->scope[48])fmer_ui_transport_icon(row,x+2,61,icon,pending?FMER_UI_PINK:FMER_UI_INK);
             if(v[2]<16u){fmer_ui_number(label,v[2]);fmer_ui_grid_text(row,x+26,62,label,FMER_UI_PINK,1);}}
            fill=(v[0]>100u?100u:v[0])*31u/100u;
            fmer_ui_grid_rect(row,x+5,82,6,34,FMER_UI_PANEL);
            if(fill)fmer_ui_grid_rect(row,x+5,115-fill,6,fill,color);
            fmer_ui_grid_rect(row,x,113-fill,14,4,r->amount==FMER_MIX_LEVEL?FMER_UI_PINK:FMER_UI_INK);
            fmer_ui_number(label,v[0]);fmer_ui_grid_text(row,x+14,83,label,color,2);
            fmer_ui_grid_text(row,x+17,102,"%",FMER_UI_MUTED,1);
            fmer_ui_grid_text(row,x,124,"M",v[4]?FMER_UI_PINK:FMER_UI_MUTED,2);
            fmer_ui_grid_text(row,x+17,124,"S",v[5]?FMER_UI_PINK:FMER_UI_MUTED,2);
            fmer_ui_grid_text(row,x+34,124,"F",v[6]?color:FMER_UI_MUTED,2);
            if(r->amount>=FMER_MIX_MUTE && r->amount<=FMER_MIX_FX){uint32_t bx=r->amount==FMER_MIX_MUTE?0:r->amount==FMER_MIX_SOLO?17:34;
                fmer_ui_grid_rect(row,x+bx,141,13,2,FMER_UI_PINK);}
            fmer_ui_grid_rect(row,x,153,47,2,FMER_UI_PANEL);
            if(r->scope[36] && !r->scope[40u+t])fmer_ui_grid_rect(row,x+v[7]*44u/(r->scope[32u+t]>1u?r->scope[32u+t]-1u:1u),151,3,6,color);
        }
    } else if(r->bar==11) {
        /* Position is a64-step timeline, not an invented note graph. */
        fmer_ui_letters(1,r->first,r->color,2,0);
        fmer_ui_rect(8,20,224,2,FMER_UI_PANEL);
        if(r->amount) {
            fill=(r->scope[5]>100u?100u:r->scope[5])*224u/100u;
            if(fill)fmer_ui_rect(8,19,fill,3,r->color);
        } else if(r->scope[8]) {
            uint32_t position=r->scope[4]<64u?r->scope[4]:63u;
            fmer_ui_rect(8+position*220u/63u,18,4,5,r->scope[6]?FMER_UI_MUTED:FMER_UI_GREEN);
        }
        if(r->scope[1])fmer_ui_rect(2,2,3,20,FMER_UI_PINK);
    } else if(r->bar==10) {
        fmer_ui_letters(1,r->first,r->color,2,r->label_chars);
        fmer_ui_slider(r,18,5,16,8);
    } else if(r->bar==9) {
        uint32_t k;for(k=0;k<4;k++){
            int x0=r->scope[k],x1=r->scope[k+1u],y0=r->scope[k+5u],y1=r->scope[k+6u],x;
            for(x=x0;x<=x1;x++){int y=y0+(y1-y0)*(x-x0)/(x1>x0?x1-x0:1);
                fmer_ui_grid_rect(r->scope_row,(uint32_t)x,(uint32_t)y,1,2,FMER_UI_GREEN);}
            fmer_ui_grid_rect(r->scope_row,(uint32_t)x0-2u,(uint32_t)y0-2u,4,4,FMER_UI_PINK);
        }
        fmer_ui_grid_rect(r->scope_row,8,67,224,1,FMER_UI_MUTED);
    } else if(r->bar==8) {
        /* Six stage-difference activity circles; muted center means no change.
         * Labels stay fixed FL/RV/DL/DR/CH/PH; brighter/larger means more activity. */
        static const char labels[]="FL    RV    DL    DR    CH    PH";
        fmer_ui_letters(0,labels,FMER_UI_MUTED,1,0);
        for(i=0;i<6;++i){int x,y,rad=r->scope[i]?1+(int)r->scope[i]/5:0;
            if(rad>6)rad=6;
            for(y=-rad;y<=rad;++y)for(x=-rad;x<=rad;++x)if(x*x+y*y<=rad*rad)
                fmer_ui_rect(14u+i*36u+x,16u+y,1,1,rad?FMER_UI_PINK:FMER_UI_MUTED);
        }
    } else if(r->bar==4) {
        uint32_t slot,x,a,b,digit,n;uint16_t color;
        for(slot=r->scope_row;slot<r->scope_row+8u;slot++){
            x=8u+(slot-r->scope_row)*28u;color=(r->amount&(1u<<slot))?FMER_UI_INK:FMER_UI_MUTED;
            fmer_ui_rect(x,1,26,22,FMER_UI_PANEL);
            if(slot==r->scope[0]){
                fmer_ui_rect(x,1,26,1,FMER_UI_PINK);fmer_ui_rect(x,22,26,1,FMER_UI_PINK);
                fmer_ui_rect(x,1,1,22,FMER_UI_PINK);fmer_ui_rect(x+25,1,1,22,FMER_UI_PINK);
            }
            if(slot==r->scope[1])fmer_ui_rect(x+2,2,22,3,FMER_UI_GREEN);
            if(slot==r->scope[2])fmer_ui_rect(x+2,19,22,3,FMER_UI_PURPLE);
            if(r->scope[4] && (r->amount&(1u<<slot)))color=FMER_UI_GREEN;
            for(n=0;n<(slot<10u?1u:2u);n++){
                digit=slot<10u?slot:n?slot%10u:1u;
                for(a=0;a<5u;a++)for(b=0;b<7u;b++)if(fmer_ui_glyphs[digit][a]&(1u<<b))
                    fmer_ui_rect(x+(slot<10u?8u:2u+n*12u)+a*2u,5u+b*2u,2,2,color);
            }
        }
    } else if(r->bar==12) {
        /* Each box is a quarter beat; the bright fill is exactly the
         * audio-owner click pulse, not a separately advanced UI oscillator. */
        for(i=0;i<4u;i++){
            uint32_t x=12u+i*56u;uint16_t color=i+1u<r->amount?FMER_UI_GREEN:FMER_UI_MUTED;
            if(i+1u==r->amount)color=r->maximum?FMER_UI_PINK:FMER_UI_INK;
            fmer_ui_rect(x,2,44,20,FMER_UI_PANEL);
            fmer_ui_rect(x,2,44,2,color);fmer_ui_rect(x,20,44,2,color);
            fmer_ui_rect(x,2,2,20,color);fmer_ui_rect(x+42,2,2,20,color);
            if(i+1u==r->amount && r->maximum)fmer_ui_rect(x+4,6,36,12,color);
        }
    } else if(r->bar==3) {
        uint32_t step,x,pitch,y,width,low=r->scope[FMER_GRID_LOW],high=r->scope[FMER_GRID_HIGH];
        if(high<=low)high=low+1u;
        for(pitch=low;pitch<=high;pitch++)if(pitch%12u==0u) {
            y=66u-(pitch-low)*60u/(high-low);
            fmer_ui_grid_rect(r->scope_row,8,y,224,1,FMER_UI_PANEL);
        }
        for(step=0;step<16u;step++) {
            uint16_t color=step+r->scope[FMER_GRID_BANK]<r->scope[FMER_GRID_LENGTH]?FMER_UI_GREEN:FMER_UI_MUTED;
            x=8u+step*14u;
            fmer_ui_grid_rect(r->scope_row,x,0,1,72,FMER_UI_PANEL);
            pitch=r->scope[step];
            if(step+r->scope[FMER_GRID_BANK]>=r->scope[FMER_GRID_LENGTH]) {
                fmer_ui_grid_rect(r->scope_row,x+4,35,6,1,FMER_UI_PANEL);
            } else if(pitch==FMER_TIE) {
                uint32_t prior=step,y_tie=35u;
                while(prior && r->scope[prior-1u]>=128u)prior--;
                if(prior){uint32_t pitch_tie=r->scope[prior-1u];
                    if(pitch_tie<low)pitch_tie=low;if(pitch_tie>high)pitch_tie=high;
                    y_tie=66u-(pitch_tie-low)*60u/(high-low);}
                fmer_ui_grid_rect(r->scope_row,x,y_tie,13,1,FMER_UI_PURPLE);
                fmer_ui_grid_rect(r->scope_row,x+12,y_tie-2u,1,5,FMER_UI_PURPLE);
            } else if(pitch>=128u) {
                fmer_ui_grid_rect(r->scope_row,x+4,35,6,2,FMER_UI_MUTED);
            } else {
                if(pitch<low)pitch=low;if(pitch>high)pitch=high;
                y=66u-(pitch-low)*60u/(high-low);
                width=1u+(r->scope[FMER_GRID_GATE+step]>100u?100u:r->scope[FMER_GRID_GATE+step])*9u/100u;
                fmer_ui_grid_rect(r->scope_row,x+3,y-1u,width,3,color);
                width=(r->scope[FMER_GRID_VELOCITY+step]>127u?127u:r->scope[FMER_GRID_VELOCITY+step])*10u/127u;
                if(width)fmer_ui_grid_rect(r->scope_row,x+3,69,width,1,FMER_UI_MUTED);
            }
            if(step==r->scope[FMER_GRID_SELECTED]) {
                fmer_ui_grid_rect(r->scope_row,x+1,0,12,1,FMER_UI_PINK);
                fmer_ui_grid_rect(r->scope_row,x+1,71,12,1,FMER_UI_PINK);
                fmer_ui_grid_rect(r->scope_row,x+1,0,1,72,FMER_UI_PINK);
                fmer_ui_grid_rect(r->scope_row,x+12,0,1,72,FMER_UI_PINK);
            }
            if(step==r->scope[FMER_GRID_PLAYHEAD]) {
                fmer_ui_grid_rect(r->scope_row,x+3,2,8,3,FMER_UI_GREEN);
                fmer_ui_grid_rect(r->scope_row,x+13,0,1,72,FMER_UI_GREEN);
            }
        }
    } else if(r->bar==5) {
        uint32_t x;int previous=0;
        for(x=0;x<224u;++x) {
            int delta=(int)x-(int)r->scope[0]*2, y, peak;
            int distance=delta<0?-delta:delta;
            if(r->scope[1]==0u)y=delta<0?17:17+delta/2;
            else if(r->scope[1]==1u)y=delta>0?17:17-delta/2;
            else y=17+distance*(1+(int)r->scope[2]/25)/3;
            peak=r->scope[1]!=2u && distance<14?(14-distance)*(int)r->scope[2]/100:0;
            y-=peak;if(y<2)y=2;if(y>45)y=45;
            fmer_ui_grid_rect(r->scope_row,8+x,46,1,1,FMER_UI_MUTED);
            if(x && y!=previous){int top=y<previous?y:previous;int height=y>previous?y-previous:previous-y;fmer_ui_grid_rect(r->scope_row,8+x,top,1,height+1,FMER_UI_GREEN);}
            else fmer_ui_grid_rect(r->scope_row,8+x,y,1,2,FMER_UI_GREEN);
            previous=y;
        }
        fmer_ui_grid_rect(r->scope_row,8+r->scope[0]*2,0,1,48,FMER_UI_PINK);
    } else if(r->bar==1) {
        fmer_ui_slider(r,7,10,4,16);
    } else {
        fmer_ui_letters((FMER_UI_STRIP-7u*r->scale)/2u,r->first,r->color,r->scale,r->label_chars);
        if(r->second[0]) fmer_ui_letters(8,r->second,r->color,1,0);
    }
    if(r->highlight){fmer_ui_rect(6,0,228,1,FMER_UI_PINK);fmer_ui_rect(6,23,228,1,FMER_UI_PINK);fmer_ui_rect(6,0,2,24,FMER_UI_PINK);fmer_ui_rect(232,0,2,24,FMER_UI_PINK);}
}

/* Reset only cache metadata. Never touch pixels while a previous DMA may read
 * them. Next service will wait non-blockingly for transport readiness. */
/* Compare only the changing waveform ink. Axis dots and optional HOME status
 * are identical on this path; any changed overlay or geometry uses a full row.
 * The resulting rectangle contains every changed pixel (old AND new traces),
 * so sparse transfers never leave green ghosts. Existing DMA buffer is packed
 * in place after comparison, with source >= destination for each copied row. */
static int fmer_ui_scope_damage(const fmer_ui_row_t *old,const fmer_ui_row_t *next,
                                uint32_t *left,uint32_t *top,uint32_t *width,uint32_t *height)
{
    uint32_t i,x,y,right=0,bottom=0;const uint16_t ink=fmer_ui_wire(FMER_UI_GREEN);
    *left=FMER_UI_WIDTH;*top=FMER_UI_STRIP;
    fmer_ui_render(old);memset(fmer_ui.scope_old,0,sizeof fmer_ui.scope_old);
    for(i=0;i<FMER_UI_WIDTH*FMER_UI_STRIP;i++)if(fmer_ui.pixels[i]==ink)
        fmer_ui.scope_old[i/8u]|=(uint8_t)(1u<<(i%8u));
    fmer_ui_render(next);
    for(i=0;i<FMER_UI_WIDTH*FMER_UI_STRIP;i++)
        if(((fmer_ui.scope_old[i/8u]>>(i%8u))&1u)!=(uint32_t)(fmer_ui.pixels[i]==ink)) {
            x=i%FMER_UI_WIDTH;y=i/FMER_UI_WIDTH;
            if(x<*left)*left=x;if(x>right)right=x;
            if(y<*top)*top=y;if(y>bottom)bottom=y;
        }
    if(*left==FMER_UI_WIDTH)return 0;
    *width=right-*left+1u;*height=bottom-*top+1u;
    for(y=0;y<*height;y++)memmove(fmer_ui.pixels+y*(*width),
        fmer_ui.pixels+(y+*top)*FMER_UI_WIDTH+*left,*width*sizeof(uint16_t));
    return 1;
}

static void fmer_ui_reset(void)
{ fmer_ui.valid=0; fmer_ui.next=0; fmer_ui.started=0; fmer_ui.scope_rows=0;fmer_ui.scope_view=0; }

/* Outside interrupts only. Max one 240x24 transfer (11520 bytes). Normal
 * control pages retain2ms pacing. A coherent full-screen scope frame drains
 * as soon as DMA is ready, without adding a20ms software scanout floor.
 * Slow statistics update at250ms; controls stay prompt.
 * Hardware readiness is polled before sync, so this does not spin for pixel DMA.
 * SPI timeouts/physical panel behavior remain separate board diagnostics.
 */
static int fmer_ui_service(const fmer_ui_state_t *s,uint32_t now_ms)
{
    static const uint8_t priority[]={3,2,1,0,4,5,6,7,8,9};
    static const uint8_t seq_priority[]={2,1,0,6,7,8,9,3,4,5};
    uint32_t i,row,pass,view=0,x,y,w,h; fmer_ui_row_t desired;
    if(fmer_ui.splash) {
        if(now_ms<1200u && !s->init_failed && !s->voices && s->panel &&
           !s->panel->navigation_revision && !s->panel->focus_active)return 0;
        fmer_ui.splash=0;
    }
    if(fmer_ui.started && (uint32_t)(now_ms-fmer_ui.last_service)<2u &&
       !(s->panel && s->panel->family==FMER_PANEL_HOME && s->panel->scope_only && fmer_ui.scope_rows)) return 0;
    if(!FMER_UI_CAN_DRAW()) return 0;
    fmer_ui.last_service=now_ms;
    if(!fmer_ui.started || (uint32_t)(now_ms-fmer_ui.last_stats)>=250u) {
        fmer_ui.voices=s->voices; fmer_ui.render_us=s->render_us;
        fmer_ui.overruns=s->overruns; fmer_ui.shed=s->shed; fmer_ui.last_stats=now_ms;
    }
    if(s->panel && !s->audio_paused && !s->init_failed){
        if(s->panel->family==FMER_PANEL_HOME && !fmer_panel_popup(s->panel,now_ms))view=s->panel->scope_only?1023u:s->controls && s->controls->value[FMER_SEQ_MODE]?126u:60u;
        if(s->panel->family==FMER_PANEL_FX)view=28u;
    }
    if(view!=fmer_ui.scope_view){fmer_ui.scope_rows=0;fmer_ui.scope_view=(uint16_t)view;fmer_ui.next=0;}
    if((!fmer_ui.started || (uint32_t)(now_ms-fmer_ui.last_scope)>=33u) && !fmer_ui.scope_rows) {
        for(uint32_t m=0;m<6;++m){uint32_t a=s->fx_activity[m],v=0;
            while(a>32u && v<30u){a=a*3u/4u;++v;}fmer_ui.fx_activity[m]=(uint8_t)v;}
        if(s->scope && (!fmer_ui.started || s->scope_generation!=fmer_ui.scope_generation)) {
            uint32_t peak=0,gain=1;
            for(i=0;i<FMER_SCOPE_SAMPLES;i++) {
                int32_t sample=s->scope[i];uint32_t magnitude=(uint32_t)(sample<0?-sample:sample);
                if(magnitude>peak)peak=magnitude;
            }
            /* Do not turn tiny digital residue into a full-height wave.
             * Down-scale immediately; a decaying held peak slows increases
             * to avoid pumping between neighboring snapshots. */
            fmer_ui.scope_quiet=peak<=32u;
            if(fmer_ui.scope_quiet)fmer_ui.scope_peak=0;
            else {
                uint32_t held=fmer_ui.started?fmer_ui.scope_peak-fmer_ui.scope_peak/8u:0u;
                fmer_ui.scope_peak=peak>held?peak:held;
                while(gain<256u && fmer_ui.scope_peak*gain*2u<=32768u)gain*=2u;
            }
            fmer_ui.scope_gain=gain;
            for(i=0;i<FMER_SCOPE_SAMPLES;i++) {
                int32_t scaled=(int32_t)s->scope[i]*(int32_t)gain*127;
                int32_t y=fmer_ui.scope_quiet?128:128-(scaled+(scaled<0?-16384:16384))/32768;
                fmer_ui.scope[i]=(uint8_t)(y<0?0:y>255?255:y);
            }
            for(uint32_t t=0;t<4;t++){
                int32_t peak=128;
                if(s->part_scopes)for(i=0;i<32;i++){int32_t v=s->part_scopes[t*32+i];if(v<0)v=-v;if(v>peak)peak=v;}
                for(i=0;i<32;i++){int32_t v=s->part_scopes?s->part_scopes[t*32+i]:0;fmer_ui.part_scope[t][i]=(uint8_t)(25-v*18/peak);}
            }
            fmer_ui.scope_generation=s->scope_generation;fmer_ui.scope_rows=(uint16_t)view;
            if(view==1023u)fmer_ui.next=0; /* every coherent frame scans top-to-bottom */
        } else if(!fmer_ui.started) {
            memset(fmer_ui.scope,128,sizeof fmer_ui.scope);
            fmer_ui.scope_peak=0;fmer_ui.scope_gain=1;fmer_ui.scope_quiet=1;
        }
        fmer_ui.last_scope=now_ms;
    }
    fmer_ui.started=1;
    /* Exact focused value first, then labels/context, then the decorative
     * waveform. Frequent PCM generations cannot starve a changed knob value. */
    for(pass=0;pass<2;pass++)for(i=0;i<FMER_UI_ROWS;i++) {
        row=s->panel && s->panel->scope_only?(i+fmer_ui.next)%10u:s->panel && s->panel->family==FMER_PANEL_SEQ?seq_priority[i]:priority[i];fmer_ui_describe(row,s,&desired);
        if((desired.bar==2 || desired.bar==16)!=(pass==1))continue;
        if((fmer_ui.valid&(1u<<row)) && !memcmp(&desired,&fmer_ui.shown[row],sizeof desired)) {if(desired.bar==2 || desired.bar==16)fmer_ui.scope_rows&=(uint16_t)~(1u<<row);continue;}
        FMER_UI_SYNC();
        x=y=0;w=FMER_UI_WIDTH;h=FMER_UI_STRIP;
        if(desired.bar==2 && (fmer_ui.valid&(1u<<row)) && fmer_ui.shown[row].bar==2 &&
           desired.maximum==fmer_ui.shown[row].maximum && desired.scope_row==fmer_ui.shown[row].scope_row &&
           !memcmp(desired.first,fmer_ui.shown[row].first,sizeof desired.first)) {
            if(!fmer_ui_scope_damage(&fmer_ui.shown[row],&desired,&x,&y,&w,&h)) {
                fmer_ui.shown[row]=desired;fmer_ui.scope_rows&=(uint16_t)~(1u<<row);
                fmer_ui.next=(uint8_t)((row+1u)%FMER_UI_ROWS);
                return 0; /* bound raster work even when later strips also match */
            }
        } else fmer_ui_render(&desired);
        FMER_UI_BLIT(x,row*FMER_UI_STRIP+y,w,h,fmer_ui.pixels);
        fmer_ui.shown[row]=desired; fmer_ui.valid|=(uint16_t)(1u<<row); fmer_ui.next=(uint8_t)((fmer_ui.next+i+1u)%FMER_UI_ROWS);
        if(desired.bar==2 || desired.bar==16)fmer_ui.scope_rows&=(uint16_t)~(1u<<row);
        fmer_ui.rows_sent++; fmer_ui.bytes_sent+=w*h*2u;
        return 1;
    }
    return 0;
}
#endif
