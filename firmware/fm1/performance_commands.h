/* SPDX-License-Identifier: GPL-3.0-only
 * Bounded panel -> audio-owner commands. Relative mixer gestures preserve
 * independent edits when several knobs arrive before the next audio half.
 * Wire transport commands remain the existing one-byte public protocol.
 */
#ifndef FMER_PERFORMANCE_COMMANDS_H
#define FMER_PERFORMANCE_COMMANDS_H
#include <stdint.h>
enum {FMER_MIX_LEVEL,FMER_MIX_PATTERN,FMER_MIX_SOUND,FMER_MIX_MUTE,
      FMER_MIX_SOLO,FMER_MIX_FX,FMER_MIX_RUN,FMER_MIX_LAYERS};
enum {FMER_NOTE_MOVE,FMER_NOTE_LENGTH,FMER_NOTE_REST,FMER_NOTE_DELETE};
enum {FMER_BLOCK_COPY,FMER_BLOCK_PASTE,FMER_BLOCK_CUT,FMER_BLOCK_CLEAR,FMER_BLOCK_UNDO,FMER_BLOCK_ACTIONS};
static uint32_t fmer_mix_command(uint32_t track,uint32_t layer,int32_t delta)
{if(delta>256)delta=256;if(delta< -256)delta=-256;return 0x10000000u|(layer<<20)|(track<<18)|((uint32_t)delta&1023u);}
static uint32_t fmer_note_command(uint32_t pattern,uint32_t step,uint32_t action,int32_t value)
{if(value>256)value=256;if(value< -256)value=-256;return 0x20000000u|(action<<24)|(pattern<<20)|(step<<14)|((uint32_t)value&16383u);}
static uint32_t fmer_block_command(uint32_t pattern,uint32_t start,uint32_t count,uint32_t destination,uint32_t action)
{return 0x30000000u|(action<<24)|(pattern<<20)|(start<<14)|((count-1u)<<8)|destination;}
static uint32_t fmer_fx_command(uint32_t effect,int32_t delta)
{if(delta>6)delta=6;if(delta< -6)delta=-6;return 0x40000000u|(effect<<8)|((uint32_t)delta&255u);}
/* Stable protocol IDs above; presentation order is independent. */
static uint32_t fmer_mix_scroll(uint32_t layer,int32_t delta,int home)
{
 static const uint8_t full[]={FMER_MIX_SOUND,FMER_MIX_PATTERN,FMER_MIX_RUN,FMER_MIX_LEVEL,FMER_MIX_MUTE,FMER_MIX_SOLO,FMER_MIX_FX};
 static const uint8_t mini[]={FMER_MIX_LEVEL,FMER_MIX_MUTE,FMER_MIX_SOLO,FMER_MIX_FX};
 const uint8_t *order=home?mini:full;int n=home?4:7,i;
 for(i=0;i<n;i++)if(order[i]==layer)break;if(i==n)i=0;
 i=(i+delta%n+n)%n;return order[i];
}
static uint32_t fmer_song_command(uint32_t track,uint32_t row,uint32_t action,int32_t delta)
{if(delta>64)delta=64;if(delta< -64)delta=-64;return 0x50000000u|(action<<20)|(track<<18)|(row<<8)|((uint32_t)delta&255u);}
#endif
