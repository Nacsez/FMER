/* SPDX-License-Identifier: GPL-3.0-only
 * Fixed, portable arrangement model. Zero initialization is an empty Live song.
 * Each lane shares the step clock; entries advance independently. Rest=16 steps.
 * Repeats are stored minus one, so an untouched entry plays once.
 */
#ifndef FMER_SONG_H
#define FMER_SONG_H
#include <stdint.h>
#include <string.h>
enum { FMER_SONG_TRACKS=4, FMER_SONG_ROWS=32, FMER_SONG_REST=16, FMER_SONG_BYTES=272 };
typedef struct { uint8_t pattern; int8_t transpose; uint8_t repeats; } fmer_song_row_t;
typedef struct {
    fmer_song_row_t rows[4][32];
    uint8_t length[4], enabled[4], loop[4], reserved[4];
} fmer_song_t;
static int fmer_song_valid(const fmer_song_t *s)
{
    unsigned t,r;
    for(t=0;t<4;t++) {
        if(s->length[t]>32 || s->enabled[t]>1 || s->loop[t]>1 || s->reserved[t] || (s->enabled[t]&&!s->length[t]))return 0;
        for(r=0;r<32;r++) {const fmer_song_row_t *v=&s->rows[t][r];
            if(v->pattern>16 || v->transpose< -24 || v->transpose>24 || v->repeats>31)return 0;}
    }
    return 1;
}
static void fmer_song_pack(const fmer_song_t *s,uint8_t *p)
{
    unsigned t,r;memset(p,0,FMER_SONG_BYTES);
    for(t=0;t<4;t++) {
        p[t]=s->length[t];p[4+t]=s->enabled[t];p[8+t]=s->loop[t];
        for(r=0;r<32;r++) {const fmer_song_row_t *v=&s->rows[t][r];
            unsigned n=v->pattern|(((unsigned)v->transpose&63u)<<5)|((unsigned)v->repeats<<11),o=16+2*(t*32+r);
            p[o]=(uint8_t)n;p[o+1]=(uint8_t)(n>>8);}
    }
}
static int fmer_song_wire_valid(const uint8_t *p)
{
    unsigned t,r;for(t=0;t<4;t++) {
        if(p[t]>32 || p[4+t]>1 || p[8+t]>1 || p[12+t] || (p[4+t]&&!p[t]))return 0;
        for(r=0;r<32;r++){unsigned o=16+2*(t*32+r),n=p[o]|((unsigned)p[o+1]<<8),tr=(n>>5)&63u;
            if((n&31u)>16 || (tr>24u&&tr<40u))return 0;}
    }return 1;
}
static int fmer_song_unpack(const uint8_t *p,fmer_song_t *s)
{
    unsigned t,r;memset(s,0,sizeof *s);
    for(t=0;t<4;t++) {
        s->length[t]=p[t];s->enabled[t]=p[4+t];s->loop[t]=p[8+t];s->reserved[t]=p[12+t];
        for(r=0;r<32;r++) {unsigned o=16+2*(t*32+r),n=p[o]|((unsigned)p[o+1]<<8),tr=(n>>5)&63u;
            s->rows[t][r].pattern=(uint8_t)(n&31u);s->rows[t][r].transpose=(int8_t)(tr>=32u?(int)tr-64:(int)tr);
            s->rows[t][r].repeats=(uint8_t)(n>>11);}
    }
    return fmer_song_valid(s);
}
#endif
