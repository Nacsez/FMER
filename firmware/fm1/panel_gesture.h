/* SPDX-License-Identifier: GPL-3.0-only
 * Main-owner button gestures shared by physical and virtual input. No I/O.
 * A held SEL modifies edits; only an unused release advances the page.
 */
#ifndef FMER_PANEL_GESTURE_H
#define FMER_PANEL_GESTURE_H
#include <stdint.h>
enum { FMER_GESTURE_NONE=0, FMER_GESTURE_PANIC=256,
       FMER_GESTURE_LAUNCH_TRACK=257, FMER_GESTURE_LAUNCH_ALL=258, FMER_GESTURE_SONG=259,
       FMER_GESTURE_MIXER=260, FMER_GESTURE_MONO=261, FMER_GESTURE_POLY=262 };
enum { FMER_GESTURE_SECTION_HOME=512u, FMER_GESTURE_SECTION_HOLD_MS=800u };
typedef struct {
    uint32_t select_down, select_used, play_down, play_started_ms;
    uint32_t held,used; /* HOME / ENV / LFO defer their ordinary tap until release. */
    uint32_t launch_pending,launch_started_ms,play_modified;
    uint32_t section_started_ms[5];
} fmer_panel_gesture_t;
static uint32_t fmer_panel_gesture_section(uint32_t id)
{ return id==2u?0u:id==5u?1u:id==6u?2u:id==7u?3u:id==11u?4u:5u; }
/* Ordinary actions are button ID+1. PLAY dispatches on a short release. */
static uint32_t fmer_panel_gesture_edge(fmer_panel_gesture_t *g,uint32_t id,uint32_t down,uint32_t now)
{
    if(id==3u) {
        if(down) {
            if(!g->select_down) {g->select_down=1;g->select_used=0;}
            /* FX then SEL is not the persistent SEL+FX shortcut. Consume the
             * reversed chord so deferred FX release cannot acquire a modifier
             * that was absent when it was pressed. */
            if(g->held&(1u<<2)){g->used|=1u<<2;g->select_used=1;}
        }
        else if(g->select_down) {
            uint32_t action=g->select_used?0u:4u;
            g->select_down=g->select_used=0; return action;
        }
        return 0;
    }
    if(id==11u && down && (g->select_down || (g->held&(1u<<8)))) {
        if(g->select_down){g->select_used=1;return FMER_GESTURE_SONG;}
        g->used|=1u<<8;return FMER_GESTURE_MIXER;
    }
    if(id==2u && down && g->select_down){
        if(g->held&(1u<<2))return 0;
        g->held|=1u<<2;g->used|=1u<<2;g->select_used=1;return 3u;
    }
    if(id==8u || id==4u || fmer_panel_gesture_section(id)<5u) {
        uint32_t bit=1u<<id,section=fmer_panel_gesture_section(id);
        if(down) {
            if(g->held&bit)return 0;g->held|=bit;g->used&=~bit;
            if(section<5u){g->section_started_ms[section]=now;if(g->select_down)g->select_used=1;}
            if(id==8u) {
                if(g->select_down){g->select_used=1;g->used|=bit;return 9u;}
                if(g->held&(1u<<4)){g->used|=bit|(1u<<4);return FMER_GESTURE_MONO;}
                if(g->held&(1u<<5)){g->used|=bit|(1u<<5);return FMER_GESTURE_POLY;}
            }
            return 0;
        }
        if(!(g->held&bit))return 0;g->held&=~bit;
        if(g->used&bit){g->used&=~bit;return 0;}
        if(section<5u && (uint32_t)(now-g->section_started_ms[section])>=FMER_GESTURE_SECTION_HOLD_MS)
            return FMER_GESTURE_SECTION_HOME+id;
        return id+1u;
    }
    if(id==12u) {
        if(down) {if(!g->play_down) {g->play_down=1;g->play_started_ms=now;
            g->play_modified=g->select_down;if(g->select_down)g->select_used=1;}}
        else {
            uint32_t action=g->play_down==1u?13u:0u;
            if(g->play_down==1u && (uint32_t)(now-g->play_started_ms)>=800u)
                action=FMER_GESTURE_PANIC;
            g->play_down=0;
            if(action==FMER_GESTURE_PANIC){g->launch_pending=0;return action;}
            if(action && g->play_modified){
                if(g->launch_pending && (uint32_t)(now-g->launch_started_ms)<300u){
                    g->launch_pending=0;return FMER_GESTURE_LAUNCH_ALL;
                }
                g->launch_pending=1;g->launch_started_ms=now;return 0;
            }
            return action;
        }
        return 0;
    }
    if(down && (id==8u || id==2u) && g->select_down)g->select_used=1;
    return down && id<14u?id+1u:0u;
}
static void fmer_panel_gesture_encoder(fmer_panel_gesture_t *g)
{ if(g->select_down)g->select_used=1; }
static uint32_t fmer_panel_gesture_tick(fmer_panel_gesture_t *g,uint32_t now)
{
    static const uint8_t sections[]={2,5,6,7,11};uint32_t i;
    if(g->play_down==1u && (uint32_t)(now-g->play_started_ms)>=800u) {
        g->play_down=2;g->launch_pending=0;return FMER_GESTURE_PANIC;
    }
    if(g->launch_pending && (uint32_t)(now-g->launch_started_ms)>=300u){
        g->launch_pending=0;return FMER_GESTURE_LAUNCH_TRACK;
    }
    for(i=0;i<5u;i++){
        uint32_t bit=1u<<sections[i];
        if((g->held&bit) && !(g->used&bit) && (uint32_t)(now-g->section_started_ms[i])>=FMER_GESTURE_SECTION_HOLD_MS){
            g->used|=bit;return FMER_GESTURE_SECTION_HOME+sections[i];
        }
    }
    return 0;
}
#endif
