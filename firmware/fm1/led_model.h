/* SPDX-License-Identifier: GPL-3.0-only
 * Original FMER LED state model. Pure C; no HAL, allocation or device writes.
 *
 * Wiring facts were audited against Felucca commit
 * 20c275e39f75fa820978032efaceddfc5283c8cb: firmware/hal/fm1_input.h
 * FM1_KEYMAP and firmware/src/ui_input.c LED_PLAY_GREEN. PLAY has a separate
 * green emitter at column 8 / row bit 1. Other physical colors are not selected
 * in software and still require an owner observation on our unit. No RGB API
 * is implied. Dim brightness is provided by the existing HAL scan pulse.
 *
 * Build a complete frame off line, then publish both arrays together under the
 * board's short, non-nested IRQ critical section. Never visibly clear and rebuild the HAL
 * arrays. Keys retain note meanings on every page; no sequencer step overlay.
 */
#ifndef FMER_LED_MODEL_H
#define FMER_LED_MODEL_H
#include <stdint.h>
#include <string.h>
#include "panel_model.h"

enum {
    FMER_LED_COLUMNS=11, FMER_LED_KEYS=41,
    FMER_LED_PLAY_GREEN=(8u<<3)|1u, FMER_LED_NO_POSITION=0xffu,
    FMER_LED_OFF=0, FMER_LED_DIM=1, FMER_LED_LIT=2, FMER_LED_HALF=3,
    FMER_LED_THREE_QUARTER=4
};
typedef struct {
    uint32_t family, physical_buttons, physical_keys, fine_adjust;
    uint32_t seq_running, recording, arp_enabled, arp_held, beat_on;
    uint32_t audio_paused, init_failed;
    uint32_t count_in,fx_enabled,lfo_enabled,sound_dirty,save_busy,save_feedback;
    uint32_t recent_buttons; /* 60 ms acknowledgement, not a held modifier */
    int32_t octave;
    /* Actual voice ownership pitches, before patch transpose or pitch bend.
     * Active includes release tails and potentially silent envelope phases;
     * gated is the active subset held by a key or sustain. Not audio metering.
     * Fresh snapshots remove stolen/finished voices without event latches. */
    uint32_t active_pitch[4], gated_pitch[4];
} fmer_led_state_t;
typedef struct {
    uint8_t lit[FMER_LED_COLUMNS], dim[FMER_LED_COLUMNS], half[FMER_LED_COLUMNS], three_quarter[FMER_LED_COLUMNS];
} fmer_led_frame_t;

/* Packed column / row-bit address. IDs 0..13 are physical buttons and
 * 14..40 are piano keys F3..G5 at octave zero (MIDI 53..79). */
static uint32_t fmer_led_key_position(uint32_t id)
{
    static const uint8_t col[FMER_LED_KEYS]={
        0,1,6,4,2,0,9,8,7,5,3,1,10,7,
        3,2,5,4,7,6,8,9,10,0,1,2,3,4,5,6,7,8,9,10,0,1,2,3,4,6,5};
    static const uint8_t row[FMER_LED_KEYS]={
        4,4,1,1,1,1,2,2,1,1,1,1,2,2,
        4,4,4,4,4,4,4,4,4,3,3,3,3,3,3,3,3,3,3,3,2,2,2,2,2,2,2};
    return id<FMER_LED_KEYS?((uint32_t)col[id]<<3)|row[id]:FMER_LED_NO_POSITION;
}
static void fmer_led_put_position(fmer_led_frame_t *out,uint32_t pos,uint32_t level)
{
    uint32_t col=pos>>3,row=pos&7u;
    if(col>=FMER_LED_COLUMNS || row<1u || row>4u) return;
    if(level==FMER_LED_LIT){out->lit[col]|=(uint8_t)(1u<<row);out->half[col]&=(uint8_t)~(1u<<row);out->three_quarter[col]&=(uint8_t)~(1u<<row);}
    else if(level==FMER_LED_THREE_QUARTER && (!(out->lit[col]&(1u<<row)) || (out->half[col]&(1u<<row)))){out->lit[col]|=(uint8_t)(1u<<row);out->half[col]&=(uint8_t)~(1u<<row);out->three_quarter[col]|=(uint8_t)(1u<<row);}
    else if(level==FMER_LED_HALF && !(out->lit[col]&(1u<<row))){out->lit[col]|=(uint8_t)(1u<<row);out->half[col]|=(uint8_t)(1u<<row);}
    else if(level==FMER_LED_DIM) out->dim[col]|=(uint8_t)(1u<<row);
}
static void fmer_led_put_key(fmer_led_frame_t *out,uint32_t id,uint32_t level)
{ fmer_led_put_position(out,fmer_led_key_position(id),level); }
static uint32_t fmer_led_key_level(const fmer_led_frame_t *frame,uint32_t id)
{
    uint32_t pos=fmer_led_key_position(id),col=pos>>3,mask=1u<<(pos&7u);
    if(col>=FMER_LED_COLUMNS) return FMER_LED_OFF;
    return (frame->half[col]&mask)?FMER_LED_HALF:(frame->three_quarter[col]&mask)?FMER_LED_THREE_QUARTER:(frame->lit[col]&mask)?FMER_LED_LIT:(frame->dim[col]&mask)?FMER_LED_DIM:FMER_LED_OFF;
}

static void fmer_led_render(const fmer_led_state_t *s,uint32_t now_ms,fmer_led_frame_t *out)
{
    static const uint8_t family_button[FMER_PANEL_FAMILIES]={8,6,4,2,5,10,11,7,9,3};
    uint32_t i,arp_gate=0,failed=s->audio_paused||s->init_failed;
    memset(out,0,sizeof *out);

    if(!failed)for(i=0;i<14u;i++)fmer_led_put_key(out,i,FMER_LED_DIM);

    /* Bright identifies the current page; dim effect/modulation indicators
     * mean enabled, never signal metering. ARP retains its gate pulse even
     * on its own page. SAVE is navigation, not proof of a completed write. */
    if(s->family<FMER_PANEL_FAMILIES)
        fmer_led_put_key(out,family_button[s->family],
            s->family==FMER_PANEL_ARP?FMER_LED_DIM:FMER_LED_LIT);
    if(s->octave>=-3 && s->octave<=3 && s->octave) {uint32_t oct=(uint32_t)(s->octave<0?-s->octave:s->octave);
        /* First shift must stand out from the unshifted ready glow. */
        fmer_led_put_key(out,s->octave<0?0:1,oct==1?FMER_LED_HALF:oct==2?FMER_LED_THREE_QUARTER:FMER_LED_LIT);}
    if(s->fine_adjust) fmer_led_put_key(out,3,FMER_LED_LIT);

    if(!failed) {
        /* Lowest HAL brightness: find keys in darkness; actual gates stay bright. */
        for(i=0;i<27u;i++)fmer_led_put_key(out,14u+i,FMER_LED_DIM);
        if(s->seq_running) {
            uint32_t level=s->beat_on?FMER_LED_LIT:FMER_LED_DIM;
            fmer_led_put_key(out,11,level);
            fmer_led_put_position(out,FMER_LED_PLAY_GREEN,level);
        }
        if(s->recording) fmer_led_put_key(out,13,s->count_in?(s->beat_on?FMER_LED_LIT:FMER_LED_DIM):FMER_LED_LIT);
        if(s->fx_enabled)fmer_led_put_key(out,2,FMER_LED_DIM);
        if(s->lfo_enabled)fmer_led_put_key(out,5,FMER_LED_DIM);
        if(s->sound_dirty)fmer_led_put_key(out,9,FMER_LED_DIM);
        for(i=0;i<4u;i++) arp_gate|=s->active_pitch[i]&s->gated_pitch[i];
        if(s->arp_enabled)
            fmer_led_put_key(out,10,(!s->arp_held||arp_gate)?FMER_LED_LIT:FMER_LED_DIM);

        /* The visible keyboard follows the selected octave without folding
         * unrelated pitches onto it. Invalid octave snapshots do not index
         * the MIDI masks. Physical-key feedback below remains available. */
        if(s->octave>=-3 && s->octave<=3) for(i=0;i<27u;i++) {
            uint32_t pitch=(uint32_t)(53+(int32_t)i+12*s->octave);
            uint32_t mask=1u<<(pitch&31u);
            if(s->active_pitch[pitch>>5]&mask)
                fmer_led_put_key(out,14u+i,(s->gated_pitch[pitch>>5]&mask)?FMER_LED_LIT:FMER_LED_DIM);
        }
    } else if(((now_ms/250u)&1u)==0u) {
        /* Fault/pause uses the ordinary PLAY emitter, never false green RUN.
         * Physical held PLAY below stays bright for panic feedback. */
        fmer_led_put_key(out,12,FMER_LED_LIT);
    }

    /* Completed storage jobs are main-owned: 1 is verified success for 800ms,
     * 2 is failure for 2s. Busy/error blink differs from steady SAVE page. */
    if(s->save_busy || s->save_feedback){
        uint32_t pos=fmer_led_key_position(9),col=pos>>3,mask=1u<<(pos&7u);
        out->lit[col]&=(uint8_t)~mask;out->dim[col]&=(uint8_t)~mask;
        fmer_led_put_key(out,9,s->save_feedback==1u?FMER_LED_LIT:
            ((now_ms/(s->save_busy?125u:250u))&1u)?FMER_LED_DIM:FMER_LED_LIT);
    }
    for(i=0;i<14u;i++)if(s->recent_buttons&(1u<<i))fmer_led_put_key(out,i,FMER_LED_LIT);

    /* These are contact indicators, not a claim that every held key has a
     * voice. During arpeggiation the held chord stays dim so generated gated
     * notes can stand out. Full brightness wins overlapping sources. */
    for(i=0;i<27u;i++) if(s->physical_keys&(1u<<i))
        fmer_led_put_key(out,14u+i,(s->arp_enabled&&s->arp_held)?FMER_LED_DIM:FMER_LED_LIT);
    for(i=0;i<14u;i++) if(s->physical_buttons&(1u<<i))
        fmer_led_put_key(out,i,i==9u?FMER_LED_DIM:FMER_LED_LIT);
    for(i=0;i<FMER_LED_COLUMNS;i++) out->dim[i]&=(uint8_t)~out->lit[i];
}
#endif
