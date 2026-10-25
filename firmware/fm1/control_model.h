/* SPDX-License-Identifier: GPL-3.0-only
 * Canonical numeric controls shared by panel, audio owner and bench protocol.
 * 0..144 retain DX7 VCED offsets. Reserved IDs must never be accepted as edits.
 */
#ifndef FMER_CONTROL_MODEL_H
#define FMER_CONTROL_MODEL_H
#include <stdint.h>
enum {
 FMER_FILTER_TYPE=145, FMER_FX_RESONANCE, FMER_LFO_ENABLE, FMER_REVERB_MODEL, FMER_DELAY_MODEL,
 FMER_GLIDE_MODE=150, FMER_GLIDE_MS, FMER_GLIDE_CURVE, FMER_SEQ_MODE,
 FMER_SEQ_TRACK, FMER_TRACK_SOUND, FMER_TRACK_LEVEL, FMER_TRACK_MUTE, FMER_RECORD_MODE, FMER_DELAY_SYNC,
 FMER_ENGINE=160, FMER_VA_WAVE, FMER_CUTOFF, FMER_RESONANCE,
 FMER_ATTACK, FMER_DECAY, FMER_SUSTAIN, FMER_RELEASE,
 FMER_DRIVE, FMER_CHORUS, FMER_DELAY, FMER_DELAY_MS, FMER_FEEDBACK,
 FMER_REVERB, FMER_PHASER, FMER_LFO_RATE, FMER_LFO_DEPTH, FMER_VA_CUTOFF,
 FMER_TEMPO, FMER_ARP_ENABLE, FMER_ARP_ORDER, FMER_ARP_RATE, FMER_ARP_OCTAVES,
 FMER_ARP_GATE, FMER_ARP_LATCH, FMER_ARP_SWING, FMER_SEQ_LENGTH, FMER_SEQ_STEP,
 FMER_SEQ_PITCH, FMER_SEQ_VELOCITY, FMER_SEQ_GATE, FMER_VOICE_BUDGET,
 FMER_ARP_TRIPLET, FMER_MIDI_CHANNEL, FMER_REVERB_DECAY,
 FMER_SEQ_PATTERN, FMER_SEQ_CHAIN, FMER_SEQ_CHAIN_MASK, FMER_PARAM_COUNT
};
enum { FMER_TRANSPORT_PLAY=1, FMER_TRANSPORT_RECORD=2, FMER_TRANSPORT_STOP=3,
       FMER_TRANSPORT_CLEAR_STEP=4, FMER_TRANSPORT_PANIC=5, FMER_TRANSPORT_ARP_RECORD=6,
       FMER_TRANSPORT_LAUNCH_TRACK=7, FMER_TRANSPORT_LAUNCH_ALL=8,
       FMER_TRANSPORT_PRESET_BASE=16 };
enum { FMER_REST=128, FMER_TIE=129, FMER_SCOPE_SAMPLES=128 };
typedef struct { uint16_t value[FMER_PARAM_COUNT]; } fmer_controls_t;
typedef struct {
 uint32_t running, recording, seq_position, edit_step, arp_held, generated_drops;
 uint32_t emitted_notes, performance_errors, revision;
 uint32_t step_pitch, step_velocity, step_gate;
 uint32_t selected_pattern, playing_pattern, queued_pattern, chain_mask, chain_enabled;
} fmer_performance_state_t;
/* LFO rate is centihertz; depth is cents. VA/filter/envelope changes that
 * require note snapshots are explicitly indicated in the instrument UI. */
static uint32_t fmer_control_min(uint32_t id) {
 switch(id) {
 case FMER_CUTOFF: case FMER_VA_CUTOFF:return 20;
 case FMER_DELAY_MS:return 20;
 case FMER_LFO_RATE:return 10;
 case FMER_TEMPO:return 20;
 case FMER_ARP_RATE: case FMER_ARP_OCTAVES: case FMER_SEQ_LENGTH:
 case FMER_SEQ_VELOCITY: case FMER_SEQ_GATE: case FMER_VOICE_BUDGET: case FMER_SEQ_CHAIN_MASK:return 1;
 case FMER_ARP_SWING:return 50;
 default:return 0;
 }
}
static uint32_t fmer_control_max(uint32_t id) {
 static const uint8_t op[]={99,99,99,99,99,99,99,99,99,99,99,3,3,7,3,7,99,1,31,99,14};
 static const uint8_t global[]={99,99,99,99,99,99,99,99,31,7,1,99,99,99,99,1,5,7,48};
 if(id<126) return op[id%21];
 if(id<145) return global[id-126];
 switch(id) {
 case FMER_GLIDE_MODE: case FMER_GLIDE_CURVE:return 2;
 case FMER_GLIDE_MS:return 2000;
 case FMER_SEQ_MODE: case FMER_TRACK_MUTE:return 1;
 case FMER_RECORD_MODE:return 2;
 case FMER_SEQ_TRACK:return 3;
 case FMER_TRACK_SOUND:return 127;
 case FMER_TRACK_LEVEL:return 100;
 case FMER_ENGINE: case FMER_ARP_ENABLE: case FMER_ARP_LATCH: case FMER_ARP_TRIPLET: case FMER_SEQ_CHAIN:return 1;
 case FMER_FILTER_TYPE:return 2;
 case FMER_FX_RESONANCE:return 100;
 case FMER_LFO_ENABLE: case FMER_DELAY_MODEL:return 1;
 case FMER_REVERB_MODEL:return 3;
 case FMER_DELAY_SYNC:return 7;
 case FMER_VA_WAVE:return 4;
 case FMER_CUTOFF:return 20000;
 case FMER_VA_CUTOFF:return 18000;
 case FMER_RESONANCE:return 95;
 case FMER_ATTACK: case FMER_DECAY: case FMER_RELEASE:return 10000;
 case FMER_DELAY_MS: case FMER_LFO_RATE:return 1000;
 case FMER_FEEDBACK:return 85;
 case FMER_TEMPO:return 300;
 case FMER_ARP_ORDER:return 10;
 case FMER_SEQ_PATTERN:return 15;
 case FMER_SEQ_CHAIN_MASK:return 65535;
 case FMER_MIDI_CHANNEL:return 16;
 case FMER_ARP_RATE:return 32;
 case FMER_ARP_OCTAVES:return 4;case FMER_VOICE_BUDGET:return 6;
 case FMER_ARP_SWING:return 75;
 case FMER_SEQ_LENGTH:return 64;
 case FMER_SEQ_STEP:return 63;
 case FMER_SEQ_PITCH:return FMER_TIE;
 case FMER_SEQ_VELOCITY:return 127;
 default:return (id>=160 && id<FMER_PARAM_COUNT)?100:0;
 }
}
static int fmer_control_valid(uint32_t id,uint32_t value) {
 if(id>=FMER_PARAM_COUNT) return 0;
 if(value<fmer_control_min(id) || value>fmer_control_max(id)) return 0;
 if(id==FMER_ARP_RATE && (value==0 || (value&(value-1)))) return 0;
 return 1;
}
#endif
