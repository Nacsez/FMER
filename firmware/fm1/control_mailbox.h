/* SPDX-License-Identifier: GPL-3.0-only
 * Pure control publication/adoption rules. Call publish under the board's
 * existing critical section; call adopt only from the single audio owner.
 */
#ifndef FMER_CONTROL_MAILBOX_H
#define FMER_CONTROL_MAILBOX_H
#include "control_model.h"
#include <string.h>
enum { FMER_CONTROL_WORDS=(FMER_PARAM_COUNT+31u)/32u };
static int fmer_control_dirty(const volatile uint32_t *dirty,uint32_t id)
{ return (dirty[id/32u]&(1u<<(id%32u)))!=0; }
/* A settled generation reads the audio owner's freshest recording/transport
 * state. A pending generation must retain the owner's not-yet-adopted edits. */
static const fmer_controls_t *fmer_control_snapshot_source(const fmer_controls_t *canonical,
    const fmer_controls_t *applied,uint32_t ready,uint32_t generation,uint32_t adopted)
{ return ready && generation==adopted?applied:canonical; }
static int fmer_control_batch_valid(const fmer_controls_t *next)
{
    uint32_t i;
    for(i=0;i<FMER_PARAM_COUNT;i++) {
        if(!fmer_control_valid(i,next->value[i]))return 0;
    }
    return next->value[FMER_SEQ_STEP]<next->value[FMER_SEQ_LENGTH];
}
/* A stale base is permitted: only deliberate base->next edits are published.
 * In particular, an audio-side voice-budget shed cannot become an accidental
 * upward edit just because main copied its controls before that interrupt. */
static uint32_t fmer_control_publish(fmer_controls_t *canonical,volatile uint32_t *dirty,
    const fmer_controls_t *base,const fmer_controls_t *next,uint32_t *changed)
{
    uint32_t i,n=0;memset(changed,0,FMER_CONTROL_WORDS*sizeof *changed);
    for(i=0;i<FMER_PARAM_COUNT;i++)if(next->value[i]!=base->value[i] && next->value[i]!=canonical->value[i]) {
        canonical->value[i]=next->value[i];dirty[i/32u]|=1u<<(i%32u);
        changed[i/32u]|=1u<<(i%32u);n++;
    }
    return n;
}
/* Select a new bank first, then its step, then merge deliberate field edits.
 * Each selection obtains fresh stored data before the next operation. An old
 * bank's length/cursor/fields are not edits unless their dirty bits say so.
 * This also covers shrinking after recording advances beyond main's snapshot.
 * The apply callback must validate the complete batch (the board supplies
 * fmer_dsp_apply_controls), including values returned by get. */
static int fmer_control_adopt(const fmer_controls_t *desired,const volatile uint32_t *dirty,
    void (*get)(fmer_controls_t *),int (*apply)(const fmer_controls_t *))
{
    fmer_controls_t actual,next;uint32_t i,word,bits,length,step;
    /* Refuse malformed explicit values before an intermediate selection can
     * mutate the instrument. Cross-field step/length is clamped below. */
    for(word=0;word<FMER_CONTROL_WORDS;word++)
        for(bits=dirty[word],i=word*32u;bits && i<FMER_PARAM_COUNT;bits>>=1u,i++)
            if((bits&1u) && !fmer_control_valid(i,desired->value[i]))return 0;
    get(&actual);
    if(fmer_control_dirty(dirty,FMER_SEQ_TRACK) && desired->value[FMER_SEQ_TRACK]!=actual.value[FMER_SEQ_TRACK]) {
        next=actual;next.value[FMER_SEQ_TRACK]=desired->value[FMER_SEQ_TRACK];
        if(!apply(&next))return 0;get(&actual);
    }
    if(fmer_control_dirty(dirty,FMER_TRACK_SOUND) && desired->value[FMER_TRACK_SOUND]!=actual.value[FMER_TRACK_SOUND]) {
        next=actual;next.value[FMER_TRACK_SOUND]=desired->value[FMER_TRACK_SOUND];
        if(!apply(&next))return 0;get(&actual);
    }
    if(fmer_control_dirty(dirty,FMER_SEQ_PATTERN) &&
       desired->value[FMER_SEQ_PATTERN]!=actual.value[FMER_SEQ_PATTERN]) {
        next=actual;next.value[FMER_SEQ_PATTERN]=desired->value[FMER_SEQ_PATTERN];
        if(!apply(&next))return 0;
        get(&actual);
    }
    length=fmer_control_dirty(dirty,FMER_SEQ_LENGTH)?desired->value[FMER_SEQ_LENGTH]:actual.value[FMER_SEQ_LENGTH];
    step=fmer_control_dirty(dirty,FMER_SEQ_STEP)?desired->value[FMER_SEQ_STEP]:actual.value[FMER_SEQ_STEP];
    if(!length || length>64u)return 0;
    if(step>=length)step=length-1u;
    if(step!=actual.value[FMER_SEQ_STEP]) {
        next=actual;
        if(length>next.value[FMER_SEQ_LENGTH])next.value[FMER_SEQ_LENGTH]=(uint16_t)length;
        next.value[FMER_SEQ_STEP]=(uint16_t)step;
        if(!apply(&next))return 0;
        get(&actual);
    }
    next=actual;
    for(word=0;word<FMER_CONTROL_WORDS;word++)
        for(bits=dirty[word],i=word*32u;bits && i<FMER_PARAM_COUNT;bits>>=1u,i++)
            if(bits&1u)next.value[i]=desired->value[i];
    next.value[FMER_SEQ_STEP]=(uint16_t)step;
    /* The canonical DSP setter validates the merged batch before committing.
     * Repeating all198 checks here adds work to every unrelated knob edit. */
    return apply(&next);
}
#endif
